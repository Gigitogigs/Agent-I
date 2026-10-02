import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from fastapi.openapi.utils import get_openapi
from backend.main import app
import json
import yaml

openapi_schema = get_openapi(
    title=app.title,
    version=app.version,
    openapi_version=app.openapi_version,
    description=app.description,
    routes=app.routes,
)

with open('openapi.json', 'w') as f:
    json.dump(openapi_schema, f, indent=2)

with open('openapi.yaml', 'w') as f:
    yaml.dump(openapi_schema, f, sort_keys=False)
