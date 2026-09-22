import re
import os

file_path = None
# find the single alembic version file just generated
for file in os.listdir(r"C:\Users\user\Documents\Agent-I\alembic\versions"):
    if file.endswith("add_remaining_domain_models.py"):
        file_path = os.path.join(r"C:\Users\user\Documents\Agent-I\alembic\versions", file)

if not file_path:
    print("Could not find migration file!")
    exit(1)

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove drops for external schemas
lines = content.split('\n')
new_lines = []
for line in lines:
    if "schema='checkpoints'" in line or "schema='memory_store'" in line or "schema='rag'" in line:
        if "op.drop_table" in line or "op.drop_index" in line:
            continue
    
    # We DO want it to drop approvals.* tables, so we don't filter them out here.
    
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(new_lines))
