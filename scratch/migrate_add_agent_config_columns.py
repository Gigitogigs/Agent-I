import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.session import get_legacy_sync_pool
import psycopg

def main():
    pool = get_legacy_sync_pool()
    conn = pool.getconn()
    cur = conn.cursor()
    
    try:
        cur.execute("ALTER TABLE workspace_agent_config ADD COLUMN IF NOT EXISTS custom_tools JSONB;")
        cur.execute("ALTER TABLE workspace_agent_config ADD COLUMN IF NOT EXISTS custom_guardrails JSONB;")
        cur.execute("ALTER TABLE workspace_agent_config ADD COLUMN IF NOT EXISTS custom_hitl_breakpoints JSONB;")
        conn.commit()
        print("Successfully added JSONB columns to workspace_agent_config.")
    except psycopg.errors.DuplicateColumn:
        print("Columns already exist.")
        conn.rollback()
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cur.close()
        pool.putconn(conn)
        pool.close()

if __name__ == "__main__":
    main()
