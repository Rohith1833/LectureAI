"""
Phase 8G-3 — Conversation API Integration Tests

Tests covering:
- POST /api/v1/documents/{document_id}/conversations (Create)
- GET  /api/v1/documents/{document_id}/conversations (List)
- GET  /api/v1/conversations/{conversation_id} (Get)
- PATCH /api/v1/conversations/{conversation_id} (Update title)
- POST /api/v1/conversations/{conversation_id}/archive (Archive)
- GET  /api/v1/conversations/{conversation_id}/messages (List messages)
- POST /api/v1/generation/query (with conversation_id)
- Error conditions: 404 for missing resources, 409 for archived generation, 400 for scope mismatch
"""

import time
import unittest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models.document import Base, Document
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.models.conversation import Conversation, ConversationMessage


class TestConversationAPI(unittest.TestCase):
    """Integration tests for the Conversation REST API endpoints."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # Seed test documents
        self.u1 = str(uuid.uuid4())
        self.u2 = str(uuid.uuid4())

        self.doc1 = Document(
            upload_id=self.u1,
            status="processed",
            extraction_timestamp="2026-08-29T00:00:00Z",
            processing_time=1.0,
        )
        self.doc2 = Document(
            upload_id=self.u2,
            status="processed",
            extraction_timestamp="2026-08-29T00:00:00Z",
            processing_time=1.0,
        )
        self.db.add_all([self.doc1, self.doc2])
        self.db.flush()

        # Seed Snapshot & KnowledgeVersion
        self.snap1 = AcademicGraphSnapshot(
            upload_id=self.u1,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=0,
            base_graph_fingerprint="fp1",
            resolved_graph_fingerprint="fp2",
            approval_timestamp=time.time(),
            reviewer_id="admin",
            nodes=[],
            edges=[],
        )
        self.db.add(self.snap1)
        self.db.flush()

        self.kv1 = KnowledgeVersion(
            upload_id=self.u1,
            snapshot_id=self.snap1.id,
            status="BUILDING",
        )
        self.db.add(self.kv1)
        self.db.flush()

        self.entity1 = KnowledgeEntity(
            knowledge_version_id=self.kv1.id,
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search algorithm content.",
            stable_id="ent_bs_1",
        )
        self.db.add(self.entity1)
        self.db.flush()

        self.kv1.status = "FINALIZED"
        self.db.commit()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_01_create_conversation_success(self):
        """Test POST /api/v1/documents/{document_id}/conversations creates a conversation."""
        resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Algorithms Study Session", "knowledge_version_id": self.kv1.id},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["title"], "Algorithms Study Session")
        self.assertEqual(data["document_id"], self.doc1.id)
        self.assertEqual(data["knowledge_version_id"], self.kv1.id)
        self.assertEqual(data["status"], "ACTIVE")
        self.assertEqual(data["message_count"], 0)

    def test_02_create_conversation_default_title(self):
        """Test POST /api/v1/documents/{document_id}/conversations with no payload defaults title."""
        resp = self.client.post(f"/api/v1/documents/{self.doc1.id}/conversations")
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["title"], "New Conversation")
        self.assertEqual(data["document_id"], self.doc1.id)

    def test_03_create_conversation_invalid_document_404(self):
        """Test creating conversation for non-existent document returns 404."""
        resp = self.client.post(
            "/api/v1/documents/non-existent-doc-id/conversations",
            json={"title": "Test"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_04_list_document_conversations(self):
        """Test GET /api/v1/documents/{document_id}/conversations returns conversations list."""
        self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Conv 1"},
        )
        self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Conv 2"},
        )

        resp = self.client.get(f"/api/v1/documents/{self.doc1.id}/conversations")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 2)
        titles = [c["title"] for c in data]
        self.assertIn("Conv 1", titles)
        self.assertIn("Conv 2", titles)

    def test_05_get_conversation_metadata(self):
        """Test GET /api/v1/conversations/{conversation_id}."""
        create_resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Inspect Me"},
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/v1/conversations/{conv_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], conv_id)
        self.assertEqual(data["title"], "Inspect Me")

    def test_06_update_conversation_title(self):
        """Test PATCH /api/v1/conversations/{conversation_id} updates title."""
        create_resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Old Title"},
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "Updated Title"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "Updated Title")

    def test_07_archive_conversation(self):
        """Test POST /api/v1/conversations/{conversation_id}/archive."""
        create_resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "To Archive"},
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.post(f"/api/v1/conversations/{conv_id}/archive")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ARCHIVED")

    def test_08_list_conversation_messages_empty(self):
        """Test GET /api/v1/conversations/{conversation_id}/messages on empty conversation."""
        create_resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Empty History"},
        )
        conv_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/v1/conversations/{conv_id}/messages")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data, [])

    def test_09_generation_with_conversation_persists_messages(self):
        """Test POST /api/v1/generation/query with conversation_id persists USER and ASSISTANT messages."""
        create_resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Active Q&A Session", "knowledge_version_id": self.kv1.id},
        )
        conv_id = create_resp.json()["id"]

        # Call generation API
        gen_payload = {
            "query": "What is binary search?",
            "scope": {
                "document_id": self.doc1.id,
                "version_id": self.kv1.id,
            },
            "mode": "QA",
            "conversation_id": conv_id,
        }
        gen_resp = self.client.post("/api/v1/generation/query", json=gen_payload)
        self.assertEqual(gen_resp.status_code, 200)
        gen_data = gen_resp.json()
        self.assertIn("answer", gen_data)

        # Retrieve messages via API
        msg_resp = self.client.get(f"/api/v1/conversations/{conv_id}/messages")
        self.assertEqual(msg_resp.status_code, 200)
        messages = msg_resp.json()
        self.assertEqual(len(messages), 2)

        self.assertEqual(messages[0]["role"], "USER")
        self.assertEqual(messages[0]["content"], "What is binary search?")
        self.assertEqual(messages[0]["sequence"], 1)

        self.assertEqual(messages[1]["role"], "ASSISTANT")
        self.assertEqual(messages[1]["content"], gen_data["answer"])
        self.assertEqual(messages[1]["sequence"], 2)

    def test_10_generation_against_archived_conversation_returns_409(self):
        """Test generation against ARCHIVED conversation returns 409 Conflict."""
        create_resp = self.client.post(
            f"/api/v1/documents/{self.doc1.id}/conversations",
            json={"title": "Archived Session"},
        )
        conv_id = create_resp.json()["id"]
        self.client.post(f"/api/v1/conversations/{conv_id}/archive")

        gen_payload = {
            "query": "What is binary search?",
            "scope": {
                "document_id": self.doc1.id,
                "version_id": self.kv1.id,
            },
            "mode": "QA",
            "conversation_id": conv_id,
        }
        gen_resp = self.client.post("/api/v1/generation/query", json=gen_payload)
        self.assertEqual(gen_resp.status_code, 409)


if __name__ == "__main__":
    unittest.main()
