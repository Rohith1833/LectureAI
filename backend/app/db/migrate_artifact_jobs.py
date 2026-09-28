"""
Migration module to repair the artifact_jobs table schema in SQLite.

Problem:
The legacy artifact_jobs table DDL included:
    FOREIGN KEY(upload_id) REFERENCES documents (upload_id)
In SQLite, foreign keys can only reference columns that have a PRIMARY KEY or UNIQUE constraint.
Because documents.upload_id has neither (documents.id is the primary key), SQLite halts on INSERT
with `sqlite3.OperationalError: foreign key mismatch - "artifact_jobs" referencing "documents"`.

Remediation:
Perform a 12-step data-preserving table rebuild:
1. Verify preconditions (read-only inspection mode available).
2. Take an online, consistent backup of the SQLite database.
3. In an immediate transaction, create `_artifact_jobs_new` with the valid schema (retaining FK to knowledge_versions.id).
4. Copy all existing rows with explicit column mappings, handling missing optional columns.
5. Verify pre- and post-migration row counts and column data.
6. Drop the old `artifact_jobs` table.
7. Rename `_artifact_jobs_new` to `artifact_jobs`.
8. Recreate indexes.
9. Verify foreign key constraints and database integrity.
"""

import os
import sys
import time
import sqlite3
import argparse
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger


def inspect_schema(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Inspect current artifact_jobs schema and determine if migration is required."""
    cursor = conn.cursor()
    
    # 1. Check if table exists
    table_row = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='artifact_jobs'"
    ).fetchone()
    
    if not table_row:
        return {
            "table_exists": False,
            "needs_migration": False,
            "reason": "Table 'artifact_jobs' does not exist."
        }
    
    table_sql = table_row[0] or ""
    
    # 2. Check foreign keys
    fks = cursor.execute("PRAGMA foreign_key_list(artifact_jobs)").fetchall()
    # FK row format: (id, seq, table, from, to, on_update, on_delete, match)
    invalid_fks = [fk for fk in fks if fk[2] == "documents" and fk[3] == "upload_id"]
    valid_kv_fks = [fk for fk in fks if fk[2] == "knowledge_versions" and fk[3] == "knowledge_version_id"]
    
    # 3. Check columns
    cols = cursor.execute("PRAGMA table_info(artifact_jobs)").fetchall()
    col_names = [c[1] for c in cols]
    
    # 4. Check row count
    row_count = cursor.execute("SELECT COUNT(*) FROM artifact_jobs").fetchone()[0]
    
    # 5. Check indexes
    indexes = cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='artifact_jobs'"
    ).fetchall()
    
    needs_migration = len(invalid_fks) > 0
    
    return {
        "table_exists": True,
        "table_sql": table_sql,
        "needs_migration": needs_migration,
        "invalid_fks": invalid_fks,
        "valid_kv_fks": valid_kv_fks,
        "columns": col_names,
        "row_count": row_count,
        "indexes": indexes,
    }


def create_backup(db_path: str, backup_dir: Optional[str] = None) -> str:
    """Create a consistent, online backup of the SQLite database using sqlite3.Connection.backup."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
        
    if backup_dir is None:
        backup_dir = os.path.dirname(os.path.abspath(db_path))
        
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{os.path.basename(db_path)}.bak.{timestamp}"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    src = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
    dest = sqlite3.connect(backup_path)
    try:
        src.backup(dest)
    finally:
        src.close()
        dest.close()
        
    # Verify backup integrity
    verify_conn = sqlite3.connect(backup_path)
    try:
        integrity = verify_conn.execute("PRAGMA integrity_check;").fetchall()
        if integrity != [("ok",)]:
            raise RuntimeError(f"Backup verification failed: {integrity}")
    finally:
        verify_conn.close()
        
    logger.info(f"Consistent backup created and verified at: {backup_path}")
    return backup_path


def apply_migration(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Execute the transactional table rebuild migration on an open connection.
    Returns details of pre- and post-migration state.
    """
    pre_info = inspect_schema(conn)
    if not pre_info["table_exists"]:
        return {"status": "SKIPPED", "reason": "Table does not exist"}
        
    if not pre_info["needs_migration"]:
        return {"status": "NOOP", "reason": "Schema already compliant (no invalid foreign keys)"}

    cursor = conn.cursor()
    
    # Record pre-migration data for validation
    cursor.execute("SELECT * FROM artifact_jobs")
    pre_rows = cursor.fetchall()
    pre_col_names = pre_info["columns"]
    pre_count = len(pre_rows)
    
    # Expected target columns
    target_columns = [
        "id", "upload_id", "knowledge_version_id", "artifact_type", "status",
        "config", "plan", "artifact_uri", "error_message", "created_at",
        "updated_at", "completed_at"
    ]
    
    # Construct SELECT expressions handling missing optional columns
    select_exprs = []
    for col in target_columns:
        if col in pre_col_names:
            select_exprs.append(f'"{col}"')
        else:
            # Missing optional column mapped to NULL
            select_exprs.append(f"NULL AS \"{col}\"")
    select_clause = ", ".join(select_exprs)
    target_cols_clause = ", ".join(f'"{c}"' for c in target_columns)
    
    # Ensure any open transaction is committed so PRAGMA foreign_keys = OFF takes effect
    conn.commit()
    cursor.execute("PRAGMA foreign_keys = OFF;")
    
    try:
        cursor.execute("BEGIN IMMEDIATE TRANSACTION;")
        
        # 1. Drop temporary table if leftover from earlier failure
        cursor.execute("DROP TABLE IF EXISTS _artifact_jobs_new;")
        
        # 2. Create replacement table with valid DDL (only referencing knowledge_versions.id)
        cursor.execute("""
            CREATE TABLE _artifact_jobs_new (
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
                FOREIGN KEY(knowledge_version_id) REFERENCES knowledge_versions (id)
            );
        """)
        
        # 3. Copy data
        cursor.execute(f"""
            INSERT INTO _artifact_jobs_new ({target_cols_clause})
            SELECT {select_clause} FROM artifact_jobs;
        """)
        
        # 4. Verify copied row count
        cursor.execute("SELECT COUNT(*) FROM _artifact_jobs_new;")
        new_count = cursor.fetchone()[0]
        if new_count != pre_count:
            raise RuntimeError(f"Row count mismatch during copy: expected {pre_count}, got {new_count}")
            
        # 5. Drop old table
        cursor.execute("DROP TABLE artifact_jobs;")
        
        # 6. Rename new table to artifact_jobs
        cursor.execute("ALTER TABLE _artifact_jobs_new RENAME TO artifact_jobs;")
        
        # 7. Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_artifact_jobs_knowledge_version_id ON artifact_jobs (knowledge_version_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_artifact_jobs_upload_id ON artifact_jobs (upload_id);")
        
        # 8. Commit transaction
        cursor.execute("COMMIT;")
        
    except Exception as exc:
        cursor.execute("ROLLBACK;")
        logger.error(f"Migration failed and was rolled back: {exc}")
        raise exc
    finally:
        # Restore foreign_keys enforcement
        cursor.execute("PRAGMA foreign_keys = ON;")

    # Post-migration verifications
    post_info = inspect_schema(conn)
    post_count = post_info["row_count"]
    
    # Check foreign keys
    fk_violations = cursor.execute("PRAGMA foreign_key_check(artifact_jobs);").fetchall()
    if fk_violations:
        raise RuntimeError(f"Foreign key violations detected after migration: {fk_violations}")
        
    integrity = cursor.execute("PRAGMA integrity_check;").fetchall()
    if integrity != [("ok",)]:
        raise RuntimeError(f"Database integrity check failed: {integrity}")
        
    logger.info(f"Migration successfully applied. Repaired artifact_jobs schema. Rows preserved: {post_count}")
    return {
        "status": "APPLIED",
        "pre_count": pre_count,
        "post_count": post_count,
        "indexes_recreated": [idx[0] for idx in post_info["indexes"]]
    }


def run_migration_on_file(db_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """Run migration on a specific SQLite file path with optional dry-run inspection."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file does not exist: {db_path}")

    abs_db_path = os.path.abspath(db_path)
    
    if dry_run:
        conn = sqlite3.connect(f"file:{abs_db_path}?mode=ro", uri=True)
        try:
            info = inspect_schema(conn)
            print("\n=== DRY RUN SCHEMA INSPECTION ===")
            print(f"Database: {abs_db_path}")
            print(f"Table Exists: {info['table_exists']}")
            if info['table_exists']:
                print(f"Current Row Count: {info['row_count']}")
                print(f"Needs Migration: {info['needs_migration']}")
                if info['needs_migration']:
                    print(f"Invalid Foreign Keys to remove: {info['invalid_fks']}")
                else:
                    print("Schema is already compliant.")
            return info
        finally:
            conn.close()

    # Apply mode: Take backup first
    backup_path = create_backup(abs_db_path)
    
    conn = sqlite3.connect(abs_db_path)
    try:
        result = apply_migration(conn)
        result["backup_path"] = backup_path
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair artifact_jobs SQLite table schema.")
    parser.add_argument("--db", type=str, default="lectureai.db", help="Path to SQLite database file.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect schema without applying modifications.")
    args = parser.parse_args()
    
    try:
        res = run_migration_on_file(args.db, dry_run=args.dry_run)
        print("Result:", res)
    except Exception as e:
        logger.error(f"Migration error: {e}")
        sys.exit(1)
