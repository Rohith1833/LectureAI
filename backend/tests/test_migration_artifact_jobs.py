"""
Tests for artifact_jobs SQLite migration.
Verifies data preservation, constraint removal, repeat execution, and rollback.
"""

import os
import sqlite3
import tempfile
import pytest
from app.db.migrate_artifact_jobs import (
    inspect_schema,
    apply_migration,
    run_migration_on_file,
    create_backup,
)


def create_legacy_schema(conn: sqlite3.Connection, missing_plan_col: bool = False):
    """Set up legacy schema mimicking the defective artifact_jobs table."""
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # 1. Base documents table
    conn.execute("""
        CREATE TABLE documents (
            id VARCHAR(36) PRIMARY KEY,
            upload_id VARCHAR(36) NOT NULL,
            status VARCHAR(32)
        );
    """)
    conn.execute("CREATE INDEX ix_documents_upload_id ON documents (upload_id);")

    # 2. Base knowledge_versions table
    conn.execute("""
        CREATE TABLE knowledge_versions (
            id VARCHAR(36) PRIMARY KEY,
            upload_id VARCHAR(36) NOT NULL,
            status VARCHAR(32) NOT NULL
        );
    """)

    # 3. Defective legacy artifact_jobs table
    if missing_plan_col:
        conn.execute("""
            CREATE TABLE artifact_jobs (
                id VARCHAR NOT NULL PRIMARY KEY,
                upload_id VARCHAR NOT NULL,
                knowledge_version_id VARCHAR NOT NULL,
                artifact_type VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                config JSON NOT NULL,
                artifact_uri VARCHAR,
                error_message TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                completed_at DATETIME,
                FOREIGN KEY(upload_id) REFERENCES documents (upload_id),
                FOREIGN KEY(knowledge_version_id) REFERENCES knowledge_versions (id)
            );
        """)
    else:
        conn.execute("""
            CREATE TABLE artifact_jobs (
                id VARCHAR NOT NULL PRIMARY KEY,
                upload_id VARCHAR NOT NULL,
                knowledge_version_id VARCHAR NOT NULL,
                artifact_type VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                config JSON NOT NULL,
                "plan" JSON,
                artifact_uri VARCHAR,
                error_message TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                completed_at DATETIME,
                FOREIGN KEY(upload_id) REFERENCES documents (upload_id),
                FOREIGN KEY(knowledge_version_id) REFERENCES knowledge_versions (id)
            );
        """)

    conn.execute("CREATE INDEX ix_artifact_jobs_upload_id ON artifact_jobs (upload_id);")
    conn.execute("CREATE INDEX ix_artifact_jobs_knowledge_version_id ON artifact_jobs (knowledge_version_id);")


class TestArtifactJobsMigration:

    def test_populated_legacy_migration_and_data_preservation(self):
        """Verify migration on populated legacy schema preserves all data and fixes the FK defect."""
        conn = sqlite3.connect(":memory:")
        create_legacy_schema(conn)

        # Seed valid reference rows
        conn.execute("INSERT INTO documents (id, upload_id, status) VALUES ('doc1', 'up1', 'processed');")
        conn.execute("INSERT INTO knowledge_versions (id, upload_id, status) VALUES ('kv1', 'up1', 'FINALIZED');")
        conn.commit()

        # Temporarily disable FKs to seed defective table
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("""
            INSERT INTO artifact_jobs (id, upload_id, knowledge_version_id, artifact_type, status, config, "plan", artifact_uri, error_message, created_at, updated_at, completed_at)
            VALUES ('job-1', 'up1', 'kv1', 'PPTX', 'COMPLETED', '{"num_units": 2}', '{"slides": []}', '/data/out.pptx', NULL, '2026-09-28 10:00:00', '2026-09-28 10:05:00', '2026-09-28 10:05:00');
        """)
        conn.execute("""
            INSERT INTO artifact_jobs (id, upload_id, knowledge_version_id, artifact_type, status, config, "plan", artifact_uri, error_message, created_at, updated_at, completed_at)
            VALUES ('job-2', 'up1', 'kv1', 'PPTX', 'FAILED', '{"num_units": 1}', NULL, NULL, 'LLM timeout', '2026-09-28 11:00:00', '2026-09-28 11:01:00', NULL);
        """)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON;")

        # Pre-check: inspect_schema detects migration needed
        info = inspect_schema(conn)
        assert info["needs_migration"] is True
        assert len(info["invalid_fks"]) == 1

        # Apply migration
        result = apply_migration(conn)
        assert result["status"] == "APPLIED"
        assert result["pre_count"] == 2
        assert result["post_count"] == 2

        # Post-check: invalid FK is removed, valid FK to kv remains
        post_info = inspect_schema(conn)
        assert post_info["needs_migration"] is False
        assert len(post_info["invalid_fks"]) == 0
        assert len(post_info["valid_kv_fks"]) == 1

        # Verify data preservation
        cursor = conn.cursor()
        rows = cursor.execute("SELECT id, upload_id, knowledge_version_id, status, error_message FROM artifact_jobs ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0] == ("job-1", "up1", "kv1", "COMPLETED", None)
        assert rows[1] == ("job-2", "up1", "kv1", "FAILED", "LLM timeout")

        # CRITICAL TEST: INSERT now succeeds under PRAGMA foreign_keys = ON!
        # (Before migration, this exact statement raised OperationalError: foreign key mismatch)
        cursor.execute("""
            INSERT INTO artifact_jobs (id, upload_id, knowledge_version_id, artifact_type, status, config, "plan", artifact_uri, error_message, created_at, updated_at, completed_at)
            VALUES ('job-new', 'up1', 'kv1', 'PPTX', 'PENDING', '{}', NULL, NULL, NULL, '2026-09-28 12:00:00', '2026-09-28 12:00:00', NULL);
        """)
        assert cursor.execute("SELECT COUNT(*) FROM artifact_jobs").fetchone()[0] == 3

    def test_legacy_missing_plan_column(self):
        """Verify migration safely handles a legacy schema missing an optional column."""
        conn = sqlite3.connect(":memory:")
        create_legacy_schema(conn, missing_plan_col=True)

        conn.execute("INSERT INTO documents (id, upload_id, status) VALUES ('doc1', 'up1', 'processed');")
        conn.execute("INSERT INTO knowledge_versions (id, upload_id, status) VALUES ('kv1', 'up1', 'FINALIZED');")
        conn.commit()

        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("""
            INSERT INTO artifact_jobs (id, upload_id, knowledge_version_id, artifact_type, status, config, artifact_uri, error_message, created_at, updated_at, completed_at)
            VALUES ('job-legacy', 'up1', 'kv1', 'PPTX', 'PENDING', '{}', NULL, NULL, '2026-09-28 10:00:00', '2026-09-28 10:00:00', NULL);
        """)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON;")

        res = apply_migration(conn)
        assert res["status"] == "APPLIED"

        cols = [c[1] for c in conn.execute("PRAGMA table_info(artifact_jobs)").fetchall()]
        assert "plan" in cols
        
        row = conn.execute("SELECT id, plan FROM artifact_jobs WHERE id='job-legacy'").fetchone()
        assert row == ("job-legacy", None)

    def test_repeat_execution_is_noop(self):
        """Verify running migration repeatedly is a safe no-op."""
        conn = sqlite3.connect(":memory:")
        create_legacy_schema(conn)

        res1 = apply_migration(conn)
        assert res1["status"] == "APPLIED"

        res2 = apply_migration(conn)
        assert res2["status"] == "NOOP"

    def test_file_migration_with_backup_and_dry_run(self):
        """Verify file-based migration, dry-run inspection, and backup creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = sqlite3.connect(db_path)
            create_legacy_schema(conn)
            conn.close()

            # Dry-run
            dry_info = run_migration_on_file(db_path, dry_run=True)
            assert dry_info["needs_migration"] is True

            # Apply
            res = run_migration_on_file(db_path, dry_run=False)
            assert res["status"] == "APPLIED"
            assert "backup_path" in res
            assert os.path.exists(res["backup_path"])

            # Verify backup can be opened
            chk = sqlite3.connect(res["backup_path"])
            assert chk.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            chk.close()

            # Running again is NOOP
            res2 = run_migration_on_file(db_path, dry_run=False)
            assert res2["status"] == "NOOP"

    def test_controlled_failure_triggers_rollback(self):
        """Verify transactional rollback if an error occurs during migration."""
        class FaultyCursor(sqlite3.Cursor):
            def execute(self, sql, *args, **kwargs):
                if "INSERT INTO _artifact_jobs_new" in sql:
                    raise sqlite3.DatabaseError("Simulated write failure")
                return super().execute(sql, *args, **kwargs)

        class FaultyConnection(sqlite3.Connection):
            def cursor(self):
                return super().cursor(FaultyCursor)

        conn = sqlite3.connect(":memory:", factory=FaultyConnection)
        create_legacy_schema(conn)

        with pytest.raises(sqlite3.DatabaseError, match="Simulated write failure"):
            apply_migration(conn)

        # Table artifact_jobs must still exist in its original state
        info = inspect_schema(conn)
        assert info["table_exists"] is True
        assert info["needs_migration"] is True  # Did not commit partial change
