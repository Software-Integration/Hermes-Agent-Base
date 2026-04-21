import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SECRETS_BACKEND", "env")
os.environ.setdefault(
    "TENANTS_JSON",
    '{"tenant-a":{"api_key":"key-a","name":"Tenant A","status":"active","allowed_tools":["math.evaluate","time.now_utc"],"allowed_model_classes":["default"],"context_char_limit":8000,"rate_limit_per_minute":60},"tenant-b":{"api_key":"key-b","name":"Tenant B","status":"active","allowed_tools":["time.now_utc"],"allowed_model_classes":["default"],"context_char_limit":8000,"rate_limit_per_minute":60}}',
)
os.environ.setdefault("HERMES_SOURCE_DIR", str(ROOT / "hermes-agent"))
os.environ.setdefault("APP_DATA_DIR", str(ROOT / "test-data"))
os.environ.setdefault("SANDBOX_SECCOMP_PROFILE", str(ROOT / "sandbox" / "seccomp" / "default.json"))
