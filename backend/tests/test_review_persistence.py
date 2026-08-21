import unittest
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.document import Base
from app.models.review import AcademicOverride, AcademicAuditEntry
from app.repositories.review_repository import ReviewRepository


class TestReviewPersistence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Setup clean SQLite in-memory database for testing
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()
        self.repo = ReviewRepository(self.db)

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        # Clean up database tables for isolation
        self.db = self.SessionLocal()
        self.db.query(AcademicOverride).delete()
        # To delete audit entries, we must bypass the trigger!
        # Since triggers prevent DELETE, we drop and recreate the table or disable trigger,
        # or we just recreate the tables for test cleanups.
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def test_create_and_retrieve_override(self):
        """Test override record creation, retrieval, and inactive filtering."""
        upload_id = "upload_doc_1"
        anchor_key = "anchor_def_1"
        payload = {"new_category": "DEFINITION", "new_parent_id": "p_1"}

        override = self.repo.create_override(
            upload_id=upload_id,
            target_anchor_key=anchor_key,
            action_type="CHANGE_CATEGORY",
            payload=payload,
            target_block_id="b_1",
        )
        self.db.commit()

        self.assertIsNotNone(override.id)
        
        # Retrieve by ID
        fetched = self.repo.get_override_by_id(override.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.upload_id, upload_id)
        self.assertEqual(fetched.target_anchor_key, anchor_key)
        self.assertEqual(fetched.payload, payload)
        self.assertTrue(fetched.is_active)

        # Retrieve active overrides list
        active_list = self.repo.get_active_overrides(upload_id)
        self.assertEqual(len(active_list), 1)
        self.assertEqual(active_list[0].id, override.id)

        # Test inactive overrides filtering
        override.is_active = False
        self.db.commit()
        active_list_empty = self.repo.get_active_overrides(upload_id)
        self.assertEqual(len(active_list_empty), 0)

    def test_override_ordering(self):
        """Ensure active overrides are fetched in deterministic chronological order."""
        upload_id = "order_upload"
        
        # Create overrides with slight time offsets
        ov1 = self.repo.create_override(upload_id, "anchor_1", "REPARENT_NODE", {})
        self.db.commit()
        time.sleep(0.01)
        ov2 = self.repo.create_override(upload_id, "anchor_2", "CHANGE_CATEGORY", {})
        self.db.commit()

        active = self.repo.get_active_overrides(upload_id)
        self.assertEqual(len(active), 2)
        self.assertEqual(active[0].id, ov1.id)
        self.assertEqual(active[1].id, ov2.id)

    def test_audit_log_structured_persistence(self):
        """Verify structured audit entries are persisted and listed correctly."""
        upload_id = "upload_audit_doc"
        prev_state = {"category": "EXAMPLE", "parent_id": "sec_1"}
        new_state = {"category": "DEFINITION", "parent_id": "sec_1"}

        audit = self.repo.create_audit_entry(
            upload_id=upload_id,
            user_id="user_admin_99",
            action_type="CHANGE_CATEGORY",
            node_id="node_def_4",
            previous_state=prev_state,
            new_state=new_state,
            comment="Updated to match exact academic pattern",
        )
        self.db.commit()

        self.assertIsNotNone(audit.id)

        # Retrieve audit list
        logs = self.repo.list_audit_entries_for_document(upload_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].user_id, "user_admin_99")
        self.assertEqual(logs[0].previous_state, prev_state)
        self.assertEqual(logs[0].new_state, new_state)
        self.assertEqual(logs[0].comment, "Updated to match exact academic pattern")

    def test_audit_immutability_trigger(self):
        """Verify database-level trigger prevents UPDATE, DELETE, or TRUNCATE of audit entries."""
        upload_id = "upload_immutable_doc"
        audit = self.repo.create_audit_entry(
            upload_id=upload_id,
            user_id="user_1",
            action_type="REPARENT_NODE",
            node_id="node_1",
            previous_state={},
            new_state={},
        )
        self.db.commit()

        # Attempt UPDATE (should raise database OperationalError/IntegrityError due to trigger failure)
        audit.comment = "Malicious update attempt"
        with self.assertRaises((OperationalError, IntegrityError)):
            self.db.commit()
        self.db.rollback()

        # Attempt DELETE (should raise database OperationalError/IntegrityError due to trigger failure)
        # Re-fetch node after rollback to ensure clean session
        audit_entry = self.db.query(AcademicAuditEntry).filter(AcademicAuditEntry.upload_id == upload_id).first()
        self.db.delete(audit_entry)
        with self.assertRaises((OperationalError, IntegrityError)):
            self.db.commit()
        self.db.rollback()

    def test_transaction_integrity_rollback(self):
        """Ensure atomicity: if audit entry creation fails, override creation is rolled back."""
        upload_id = "upload_tx_doc"
        anchor_key = "anchor_tx"

        # Start transaction block manually
        try:
            # 1. Create override
            self.repo.create_override(
                upload_id=upload_id,
                target_anchor_key=anchor_key,
                action_type="DELETE_NODE",
                payload={},
            )
            # Flush so it registers in session
            self.db.flush()

            # 2. Trigger constraint failure by trying to write audit entry with null fields
            # (which SQLite rejects because of NOT NULL database constraints on previous_state or user_id)
            invalid_audit = AcademicAuditEntry(
                upload_id=upload_id,
                user_id=None,  # Null violates non-nullable constraint
                action_type="DELETE_NODE",
                node_id="node_tx",
                previous_state=None, # Null violates non-nullable JSON constraint
                new_state=None,      # Null violates non-nullable JSON constraint
            )
            self.db.add(invalid_audit)
            self.db.commit()
        except Exception:
            self.db.rollback()

        # Verify that because of the failure/rollback, the override was NOT committed
        override_check = self.db.query(AcademicOverride).filter(AcademicOverride.upload_id == upload_id).first()
        self.assertIsNone(override_check)

    def test_database_constraints(self):
        """Ensure database constraint rejections on invalid schemas input."""
        # Null target_anchor_key constraint
        with self.assertRaises(IntegrityError):
            invalid_override = AcademicOverride(
                upload_id="upload_test",
                target_anchor_key=None,  # Invalid
                action_type="RENAME_TITLE",
                payload={},
            )
            self.db.add(invalid_override)
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
