"""
Tests for CORS headers and error visibility at the application boundary.
Verifies that:
- Allowed development origins (http://localhost:5173 and http://127.0.0.1:5173) receive matching single-origin headers.
- Disallowed origins receive no Access-Control-Allow-Origin grant.
- Preflight OPTIONS and actual POST to /api/v1/artifacts/generate work properly.
- Valid job creation with distinct document.id, upload_id, and knowledge_version_id succeeds.
- Invalid upload/version ownership is rejected with 400 and preserves CORS headers.
- Handled validation errors (422) preserve CORS headers.
- Unhandled 500 errors produced at the ASGI/ServerErrorMiddleware boundary preserve CORS headers.
- Backend errors remain real errors (never disguised as 200).
"""
import uuid
from datetime import datetime, timezone
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_app, create_fastapi_app, CORSAppProxy, ALLOWED_DEVELOPMENT_ORIGINS
from app.db.session import get_db
from app.models.document import Base, Document
from app.models.knowledge import KnowledgeVersion
from app.schemas.knowledge import KnowledgeVersionStatus


@pytest.fixture
def test_db_session():
    """Isolated in-memory SQLite database with repaired schema."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def app_with_db(test_db_session):
    """Application configured with test database dependency override."""
    application = create_app()

    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.pop(get_db, None)


class TestCORSBoundaryAndVisibility:
    """Verify CORS compliance across preflight, actual POST, validation error, and 500 server error."""

    def test_options_preflight_from_both_allowed_origins(self, app_with_db):
        """OPTIONS preflight from localhost:5173 and 127.0.0.1:5173 returns 200 and single matching origin."""
        client = TestClient(app_with_db)

        for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            response = client.options(
                "/api/v1/artifacts/generate",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert "POST" in response.headers.get("access-control-allow-methods", "").upper()
            assert response.headers.get("access-control-allow-credentials") == "true"

    def test_disallowed_origin_receives_no_cors_grant(self, app_with_db):
        """A request from an origin not in the allowlist must NOT receive Access-Control-Allow-Origin."""
        client = TestClient(app_with_db)

        response = client.options(
            "/api/v1/artifacts/generate",
            headers={
                "Origin": "http://malicious-site.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert "access-control-allow-origin" not in response.headers

        # Regular GET from disallowed origin
        get_res = client.get("/", headers={"Origin": "http://evil.com"})
        assert get_res.status_code == 200
        assert "access-control-allow-origin" not in get_res.headers

    def test_actual_post_job_creation_with_distinct_ids_and_cors(self, app_with_db, test_db_session, monkeypatch):
        """
        POST /api/v1/artifacts/generate:
        - Distinct document.id, upload_id, and knowledge_version_id.
        - Background tasks suppressed to prevent any live LLM calls.
        - Verifies 200 status, job row creation, and single matching CORS origin header.
        """
        # Suppress background generation task in route
        monkeypatch.setattr("app.api.routes.artifact.background_artifact_generation", lambda job_id: None)

        # Seed distinct IDs
        doc_id = f"doc-{uuid.uuid4()}"
        upload_id = f"upload-{uuid.uuid4()}"
        kv_id = f"kv-{uuid.uuid4()}"

        assert doc_id != upload_id
        assert upload_id != kv_id

        doc = Document(
            id=doc_id,
            upload_id=upload_id,
            status="processed",
            extraction_timestamp=datetime.now(timezone.utc),
            processing_time=0.5,
        )
        test_db_session.add(doc)

        kv = KnowledgeVersion(
            id=kv_id,
            upload_id=upload_id,
            snapshot_id=f"snap-{uuid.uuid4()}",
            status=KnowledgeVersionStatus.FINALIZED.value,
        )
        test_db_session.add(kv)
        test_db_session.commit()

        client = TestClient(app_with_db)

        # Test POST from http://localhost:5173
        payload = {
            "upload_id": upload_id,
            "knowledge_version_id": kv_id,
            "artifact_type": "PPTX",
            "config": {"audience": "advanced", "selected_topics": ["Unit 2", "Unit 4"]},
        }
        res_local = client.post(
            "/api/v1/artifacts/generate",
            json=payload,
            headers={"Origin": "http://localhost:5173"},
        )
        assert res_local.status_code == 200
        assert res_local.headers["access-control-allow-origin"] == "http://localhost:5173"
        data = res_local.json()
        assert data["status"] == "PENDING"
        assert data["upload_id"] == upload_id
        assert data["knowledge_version_id"] == kv_id
        assert "id" in data

        # Test POST from http://127.0.0.1:5173
        res_ip = client.post(
            "/api/v1/artifacts/generate",
            json=payload,
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert res_ip.status_code == 200
        assert res_ip.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    def test_invalid_upload_version_ownership_rejected_with_cors(self, app_with_db, test_db_session):
        """Invalid upload/version ownership is rejected with HTTP 400 and preserves CORS header."""
        upload_1 = f"upload-1-{uuid.uuid4()}"
        upload_2 = f"upload-2-{uuid.uuid4()}"
        kv_id = f"kv-{uuid.uuid4()}"

        kv = KnowledgeVersion(
            id=kv_id,
            upload_id=upload_1,
            snapshot_id=f"snap-{uuid.uuid4()}",
            status=KnowledgeVersionStatus.FINALIZED.value,
        )
        test_db_session.add(kv)
        test_db_session.commit()

        client = TestClient(app_with_db)

        # Send request with upload_2 (which does not match kv.upload_id)
        response = client.post(
            "/api/v1/artifacts/generate",
            json={
                "upload_id": upload_2,
                "knowledge_version_id": kv_id,
                "artifact_type": "PPTX",
                "config": {},
            },
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 400
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        data = response.json()
        assert "does not belong" in (data.get("message") or data.get("detail", ""))

    def test_validation_error_preserves_cors(self, app_with_db):
        """Handled validation error (422) preserves CORS headers."""
        client = TestClient(app_with_db)

        response = client.post(
            "/api/v1/artifacts/generate",
            json={"invalid_field": 123},
            headers={"Origin": "http://localhost:5173"},
        )
        assert response.status_code == 422
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Validation Error"

    def test_isolated_unhandled_500_cors_visibility(self):
        """
        Isolated unhandled 500 error must:
        - Return HTTP 500 (never turned into 200).
        - Include Access-Control-Allow-Origin header matching the caller.
        - Client configured with raise_server_exceptions=False.
        """
        fastapi_app = create_fastapi_app()
        fault_router = APIRouter()

        @fault_router.get("/test-fault")
        def trigger_fault():
            raise ZeroDivisionError("Simulated unhandled exception at boundary")

        fastapi_app.include_router(fault_router)
        wrapped_app = CORSAppProxy(fastapi_app, ALLOWED_DEVELOPMENT_ORIGINS)

        client = TestClient(wrapped_app, raise_server_exceptions=False)

        response = client.get("/test-fault", headers={"Origin": "http://localhost:5173"})
        # Must be 500, never masked as 200
        assert response.status_code == 500
        # Must have CORS header so browser does not block error response visibility
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
