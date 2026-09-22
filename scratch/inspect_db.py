import psycopg2

conn = psycopg2.connect('postgresql://postgres:ForcaBarca%402026!@localhost:5432/support_system')
cur = conn.cursor()

# Get all user schemas
cur.execute("""
    SELECT schema_name 
    FROM information_schema.schemata 
    WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
""")
schemas = [row[0] for row in cur.fetchall()]
print(f"Schemas found: {schemas}\n")

for schema in schemas:
    cur.execute(f"""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = '{schema}'
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"Schema '{schema}':")
    if not tables:
        print("  (empty)")
    for table in tables:
        # Check row count
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        count = cur.fetchone()[0]
        print(f"  - {table} ({count} rows)")
