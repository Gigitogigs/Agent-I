import psycopg2

conn = psycopg2.connect('postgresql://postgres:ForcaBarca%402026!@localhost:5432/support_system')
conn.autocommit = True
cur = conn.cursor()

# 1. Drop the empty checkpoint tables in the checkpoints schema (that were accidentally created)
empty_tables = ["checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"]
for table in empty_tables:
    cur.execute(f"DROP TABLE IF EXISTS checkpoints.{table} CASCADE")

# 2. Move populated checkpoint tables from public to checkpoints
for table in empty_tables:
    try:
        cur.execute(f"ALTER TABLE public.{table} SET SCHEMA checkpoints")
        print(f"Moved {table} to checkpoints schema.")
    except Exception as e:
        print(f"Error moving {table}: {e}")

# 3. Move store tables from public to memory_store
store_tables = ["store", "store_migrations"]
for table in store_tables:
    try:
        cur.execute(f"ALTER TABLE public.{table} SET SCHEMA memory_store")
        print(f"Moved {table} to memory_store schema.")
    except Exception as e:
        print(f"Error moving {table}: {e}")

# 4. Move pgvector tables from public to rag
rag_tables = ["langchain_pg_collection", "langchain_pg_embedding"]
for table in rag_tables:
    try:
        cur.execute(f"ALTER TABLE public.{table} SET SCHEMA rag")
        print(f"Moved {table} to rag schema.")
    except Exception as e:
        print(f"Error moving {table}: {e}")

print("Database schema migration complete.")
