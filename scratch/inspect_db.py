import sys, os, sqlite3
sys.path.insert(0, ".")
from app.core.config import settings

db_path = os.path.abspath("lectureai.db")
print("Configured DATABASE_URL:", settings.DATABASE_URL)
print("Resolved DB file path:", db_path)

uri = f"file:{db_path}?mode=ro"
conn = sqlite3.connect(uri, uri=True)

# 1. Table schema
table_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='artifact_jobs'").fetchone()
print("\n--- Table SQL ---")
print(table_sql[0] if table_sql else "None")

# 2. Columns via table_info
cols = conn.execute("PRAGMA table_info(artifact_jobs)").fetchall()
print("\n--- Columns (cid, name, type, notnull, dflt_value, pk) ---")
for c in cols:
    print(c)

# 3. Foreign keys
fks = conn.execute("PRAGMA foreign_key_list(artifact_jobs)").fetchall()
print("\n--- Foreign Keys (id, seq, table, from, to, on_update, on_delete, match) ---")
for fk in fks:
    print(fk)

# 4. Indexes
indexes = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='artifact_jobs'").fetchall()
print("\n--- Indexes on artifact_jobs ---")
for idx in indexes:
    print(idx)

# 5. Triggers
triggers = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='artifact_jobs'").fetchall()
print("\n--- Triggers on artifact_jobs ---")
for trg in triggers:
    print(trg)

# 6. Incoming references (tables that have FKs pointing to artifact_jobs)
tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
incoming = []
for t in tables:
    try:
        t_fks = conn.execute(f"PRAGMA foreign_key_list({t})").fetchall()
        for fk in t_fks:
            if fk[2] == "artifact_jobs":
                incoming.append((t, fk))
    except Exception as e:
        print(f"Error checking {t}: {e}")
print("\n--- Incoming Foreign Keys to artifact_jobs ---")
print(incoming if incoming else "None")

# 7. Row count
count = conn.execute("SELECT COUNT(*) FROM artifact_jobs").fetchone()[0]
print("\n--- Current row count ---:", count)
conn.close()
