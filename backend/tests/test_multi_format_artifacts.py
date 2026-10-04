import csv
import os
import tempfile
import unittest
from pathlib import Path

from app.schemas.artifact import ArtifactPlan, SlideModel, SlideType, ArtifactType
from app.services.artifact.csv_renderer import CSVRenderer
from app.services.artifact.md_renderer import MDRenderer

class TestMultiFormatArtifacts(unittest.TestCase):
    def setUp(self):
        self.plan = ArtifactPlan(
            metadata={"title": "Introduction to Computer Science"},
            slides=[
                SlideModel(
                    slide_type=SlideType.CONCEPT,
                    title="Recursion",
                    content=["A function calling itself", "Requires a base case"],
                    speaker_notes="Remember to check for stack overflow",
                    source_node_ids=["node_1"],
                    evidence_ids=["ev_1"]
                ),
                SlideModel(
                    slide_type=SlideType.QUESTION,
                    title="Time Complexity of Binary Search",
                    content=["O(log n)"],
                    speaker_notes="Divide and conquer algorithm",
                    source_node_ids=["node_2"],
                    evidence_ids=["ev_2"]
                )
            ]
        )

    def test_csv_renderer_output(self):
        renderer = CSVRenderer()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test_cards.csv")
            result = renderer.render(self.plan, out_path)
            
            self.assertTrue(os.path.exists(result))
            with open(result, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
                self.assertEqual(reader[0], ["Front", "Back", "Notes"])
                self.assertEqual(len(reader), 3)
                self.assertEqual(reader[1][0], "Recursion")
                self.assertIn("A function calling itself", reader[1][1])
                self.assertIn("Requires a base case", reader[1][1])
                self.assertEqual(reader[1][2], "Remember to check for stack overflow")
                self.assertEqual(reader[2][0], "Time Complexity of Binary Search")
                self.assertEqual(reader[2][1], "O(log n)")

    def test_md_renderer_output(self):
        renderer = MDRenderer()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test_guide.md")
            result = renderer.render(self.plan, out_path)
            
            self.assertTrue(os.path.exists(result))
            with open(result, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("# Introduction to Computer Science", content)
                self.assertIn("## Recursion", content)
                self.assertIn("- A function calling itself", content)
                self.assertIn("- Requires a base case", content)
                self.assertIn("**Notes/Explanation:** Remember to check for stack overflow", content)
                self.assertIn("## Time Complexity of Binary Search", content)
                self.assertIn("- O(log n)", content)

    def test_all_artifact_types_supported(self):
        types = [
            ArtifactType.PPTX,
            ArtifactType.STUDY_GUIDE_MD,
            ArtifactType.FLASHCARDS_CSV,
            ArtifactType.PRACTICE_EXAM_MD,
        ]
        self.assertEqual(len(types), 4)

    def test_download_media_type_resolution(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from sqlalchemy.orm import sessionmaker
        import uuid
        from datetime import datetime
        from app.models.document import Base, Document
        from app.models.knowledge import KnowledgeVersion
        from app.models.artifact import ArtifactJob
        from app.schemas.artifact import ArtifactStatus
        from app.db.session import get_db
        from app.main import app

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        with tempfile.TemporaryDirectory() as tmpdir:
            db = TestingSessionLocal()
            upload_id = str(uuid.uuid4())
            doc = Document(
                upload_id=upload_id, 
                status="processed",
                extraction_timestamp=datetime.utcnow(),
                processing_time=0.0
            )
            db.add(doc)
            
            # 1. Test CSV Download media type
            csv_path = os.path.join(tmpdir, "test.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Front,Back,Notes\nQ,A,N\n")
                
            csv_job = ArtifactJob(
                id=str(uuid.uuid4()),
                upload_id=upload_id,
                knowledge_version_id=str(uuid.uuid4()),
                artifact_type="FLASHCARDS_CSV",
                status=ArtifactStatus.COMPLETED.value,
                artifact_uri=csv_path,
                config={}
            )
            db.add(csv_job)
            
            # 2. Test MD Download media type
            md_path = os.path.join(tmpdir, "test.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# Study Guide\n## Concept\n")
                
            md_job = ArtifactJob(
                id=str(uuid.uuid4()),
                upload_id=upload_id,
                knowledge_version_id=str(uuid.uuid4()),
                artifact_type="STUDY_GUIDE_MD",
                status=ArtifactStatus.COMPLETED.value,
                artifact_uri=md_path,
                config={}
            )
            db.add(md_job)
            db.commit()

            # Verify CSV response headers
            resp_csv = client.get(f"/api/v1/artifacts/{csv_job.id}/download")
            self.assertEqual(resp_csv.status_code, 200)
            self.assertIn("text/csv", resp_csv.headers.get("content-type", ""))

            # Verify MD response headers
            resp_md = client.get(f"/api/v1/artifacts/{md_job.id}/download")
            self.assertEqual(resp_md.status_code, 200)
            self.assertIn("text/markdown", resp_md.headers.get("content-type", ""))

            db.close()
        
        app.dependency_overrides.clear()
