"""
Phase 8G-1 — Conversation Contracts & Persistence Unit Tests

Tests validating:
- Conversation lifecycle (create, retrieve, list, archive, delete)
- Safe document and knowledge-version scope enforcement
- Append-only message history with deterministic sequence numbering
- Input validations (empty content, whitespace, invalid roles, archived status)
- Bounded history pagination
- Database constraints and isolation (knowledge preservation on cascade)
"""

import unittest
import time
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.document import Base, Document
from app.models.review import AcademicGraphSnapshot
from app.models.knowledge import KnowledgeVersion, KnowledgeEntity
from app.models.conversation import Conversation, ConversationMessage
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)


class TestConversationPersistence(unittest.TestCase):
    """Unit tests for Conversation and Message repository persistence."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        from sqlalchemy import event
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

        self.u1 = str(uuid.uuid4())
        self.u2 = str(uuid.uuid4())

        # Seed test document 1
        self.doc1 = Document(
            upload_id=self.u1,
            status="processed",
            extraction_timestamp="2026-08-28T00:00:00Z",
            processing_time=1.0,
        )
        # Seed test document 2 (different upload)
        self.doc2 = Document(
            upload_id=self.u2,
            status="processed",
            extraction_timestamp="2026-08-28T00:00:00Z",
            processing_time=1.0,
        )
        self.db.add_all([self.doc1, self.doc2])
        self.db.flush()

        # Seed Snapshot & KnowledgeVersion for doc1
        self.snap1 = AcademicGraphSnapshot(
            upload_id=self.u1,
            pipeline_run_id="run_1",
            approval_version=1,
            approved_revision=0,
            base_graph_fingerprint="fp1",
            resolved_graph_fingerprint="fp2",
            approval_timestamp=time.time(),
            reviewer_id="user_admin",
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

        # Seed an entity under kv1
        self.entity1 = KnowledgeEntity(
            knowledge_version_id=self.kv1.id,
            entity_type="CONCEPT",
            title="Binary Search",
            content="Binary search runs in O(log n) time.",
            stable_id="ent_binary_search",
        )
        self.db.add(self.entity1)
        self.db.flush()

        self.kv1.status = "FINALIZED"
        self.db.commit()

        self.conv_repo = ConversationRepository(self.db)
        self.msg_repo = MessageRepository(self.db)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    # =========================================================================
    # 1. Conversation Lifecycle & Scope Tests
    # =========================================================================

    def test_01_create_and_retrieve_conversation(self):
        """Verify conversation creation and retrieval with title and version scope."""
        conv = self.conv_repo.create_conversation(
            document_id=self.doc1.id,
            knowledge_version_id=self.kv1.id,
            title="Algorithms Discussion",
        )
        self.assertIsNotNone(conv.id)
        self.assertEqual(conv.document_id, self.doc1.id)
        self.assertEqual(conv.knowledge_version_id, self.kv1.id)
        self.assertEqual(conv.title, "Algorithms Discussion")
        self.assertEqual(conv.status, "ACTIVE")
        self.assertGreater(conv.created_at, 0)

        fetched = self.conv_repo.get_conversation(conv.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, conv.id)
        self.assertEqual(fetched.title, "Algorithms Discussion")

    def test_02_default_title_handling(self):
        """Verify omitting title or providing whitespace defaults to 'New Conversation'."""
        conv_none = self.conv_repo.create_conversation(document_id=self.doc1.id, title=None)
        conv_empty = self.conv_repo.create_conversation(document_id=self.doc1.id, title="   ")

        self.assertEqual(conv_none.title, "New Conversation")
        self.assertEqual(conv_empty.title, "New Conversation")

    def test_03_list_conversations_by_document(self):
        """Verify conversations are listed by document ordered by updated_at descending."""
        conv1 = self.conv_repo.create_conversation(document_id=self.doc1.id, title="Conv 1")
        time.sleep(0.01)
        conv2 = self.conv_repo.create_conversation(document_id=self.doc1.id, title="Conv 2")
        time.sleep(0.01)
        # Touch conv1
        self.conv_repo.update_conversation(conv1.id, title="Conv 1 Updated")

        convs = self.conv_repo.list_conversations(self.doc1.id)
        self.assertEqual(len(convs), 2)
        # conv1 was updated last, so it should be first
        self.assertEqual(convs[0].id, conv1.id)
        self.assertEqual(convs[1].id, conv2.id)

    def test_04_archive_conversation(self):
        """Verify active conversation can be archived."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        self.assertEqual(conv.status, "ACTIVE")

        archived = self.conv_repo.archive_conversation(conv.id)
        self.assertIsNotNone(archived)
        self.assertEqual(archived.status, "ARCHIVED")

        fetched = self.conv_repo.get_conversation(conv.id)
        self.assertEqual(fetched.status, "ARCHIVED")

    def test_05_invalid_document_rejection(self):
        """Verify creating conversation for non-existent document raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.conv_repo.create_conversation(document_id="non_existent_doc_id")
        self.assertIn("does not exist", str(ctx.exception))

    def test_06_knowledge_version_scope_matching(self):
        """Verify knowledge version from different document is rejected."""
        # doc2 has upload_id u2, while kv1 belongs to u1
        with self.assertRaises(ValueError) as ctx:
            self.conv_repo.create_conversation(
                document_id=self.doc2.id,
                knowledge_version_id=self.kv1.id,
            )
        self.assertIn("does not belong to Document", str(ctx.exception))

    def test_07_invalid_knowledge_version_rejection(self):
        """Verify non-existent knowledge version ID raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.conv_repo.create_conversation(
                document_id=self.doc1.id,
                knowledge_version_id="non_existent_kv_id",
            )
        self.assertIn("does not exist", str(ctx.exception))

    def test_08_delete_conversation(self):
        """Verify deleting conversation removes conversation and messages without touching academic knowledge."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        self.msg_repo.append_message(conv.id, role="USER", content="Hello")

        deleted = self.conv_repo.delete_conversation(conv.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.conv_repo.get_conversation(conv.id))

        # Academic knowledge entity and version remain completely intact
        self.assertIsNotNone(self.db.query(KnowledgeVersion).filter(KnowledgeVersion.id == self.kv1.id).first())
        self.assertIsNotNone(self.db.query(KnowledgeEntity).filter(KnowledgeEntity.id == self.entity1.id).first())

    # =========================================================================
    # 2. Message Persistence & Ordering Tests
    # =========================================================================

    def test_09_append_user_and_assistant_messages(self):
        """Verify sequential message appending with incrementing sequence IDs."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)

        m1 = self.msg_repo.append_message(conv.id, role="USER", content="What is binary search?")
        m2 = self.msg_repo.append_message(conv.id, role="ASSISTANT", content="Binary search is O(log n).")

        self.assertEqual(m1.sequence, 1)
        self.assertEqual(m1.role, "USER")
        self.assertEqual(m1.content, "What is binary search?")

        self.assertEqual(m2.sequence, 2)
        self.assertEqual(m2.role, "ASSISTANT")
        self.assertEqual(m2.content, "Binary search is O(log n).")

        self.assertEqual(self.msg_repo.count_messages(conv.id), 2)

    def test_10_deterministic_message_history_ordering(self):
        """Verify message history is deterministically ordered by sequence."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)

        for i in range(5):
            self.msg_repo.append_message(conv.id, role="USER", content=f"Message {i+1}")

        messages = self.msg_repo.list_messages(conv.id)
        self.assertEqual(len(messages), 5)
        self.assertEqual([m.sequence for m in messages], [1, 2, 3, 4, 5])
        self.assertEqual([m.content for m in messages], [f"Message {i+1}" for i in range(5)])

    def test_11_empty_and_whitespace_content_rejection(self):
        """Verify empty and whitespace-only message contents are rejected."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)

        with self.assertRaises(ValueError) as ctx1:
            self.msg_repo.append_message(conv.id, role="USER", content="")
        self.assertIn("cannot be empty", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            self.msg_repo.append_message(conv.id, role="USER", content="   \n\t  ")
        self.assertIn("cannot be empty", str(ctx2.exception))

    def test_12_invalid_role_rejection(self):
        """Verify invalid roles outside USER and ASSISTANT are rejected."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)

        with self.assertRaises(ValueError) as ctx:
            self.msg_repo.append_message(conv.id, role="SYSTEM", content="System instruction")
        self.assertIn("Invalid message role", str(ctx.exception))

    def test_13_append_to_archived_conversation_rejection(self):
        """Verify appending messages to an ARCHIVED conversation is rejected."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        self.conv_repo.archive_conversation(conv.id)

        with self.assertRaises(ValueError) as ctx:
            self.msg_repo.append_message(conv.id, role="USER", content="New query")
        self.assertIn("Cannot append message to ARCHIVED", str(ctx.exception))

    def test_14_non_existent_conversation_rejection(self):
        """Verify appending message to non-existent conversation raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.msg_repo.append_message("fake_conv_id", role="USER", content="Hello")
        self.assertIn("does not exist", str(ctx.exception))

    def test_15_bounded_history_pagination(self):
        """Verify list_messages supports limit and offset pagination."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)

        for i in range(10):
            self.msg_repo.append_message(conv.id, role="USER", content=f"Msg {i+1}")

        # Page 1: limit 3, offset 0
        page1 = self.msg_repo.list_messages(conv.id, limit=3, offset=0)
        self.assertEqual(len(page1), 3)
        self.assertEqual([m.sequence for m in page1], [1, 2, 3])

        # Page 2: limit 3, offset 3
        page2 = self.msg_repo.list_messages(conv.id, limit=3, offset=3)
        self.assertEqual(len(page2), 3)
        self.assertEqual([m.sequence for m in page2], [4, 5, 6])

    def test_16_unique_sequence_constraint(self):
        """Verify unique sequence per conversation constraint is enforced."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        m1 = self.msg_repo.append_message(conv.id, role="USER", content="Msg 1")

        # Manually try inserting duplicate sequence for same conversation
        duplicate = ConversationMessage(
            conversation_id=conv.id,
            role="ASSISTANT",
            content="Duplicate sequence",
            sequence=1,
            created_at=time.time(),
        )
        self.db.add(duplicate)
        with self.assertRaises(Exception):
            self.db.commit()
        self.db.rollback()

    def test_17_document_deletion_cascades_to_conversations(self):
        """Verify deleting a Document cascades to its conversations and messages."""
        conv = self.conv_repo.create_conversation(document_id=self.doc1.id)
        self.msg_repo.append_message(conv.id, role="USER", content="Msg")

        # Delete document 1
        self.db.delete(self.doc1)
        self.db.commit()

        self.assertIsNone(self.conv_repo.get_conversation(conv.id))
        self.assertEqual(self.msg_repo.count_messages(conv.id), 0)


if __name__ == "__main__":
    unittest.main()
