import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "opa" / "policies"


def _eval_policy(payload: dict) -> dict:
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{POLICY_DIR}:/policies:ro",
            "openpolicyagent/opa:1.15.2-static",
            "eval",
            "-f",
            "json",
            "-d",
            "/policies",
            "data.hermes.authz.decision",
            "-I",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    body = json.loads(completed.stdout)
    return body["result"][0]["expressions"][0]["value"]


@pytest.mark.skipif(not POLICY_DIR.exists(), reason="opa policy directory missing")
def test_opa_policy_denies_inactive_tenant():
    decision = _eval_policy(
        {
            "tenant_id": "tenant-a",
            "action": "chat.invoke",
            "environment": "production",
            "resource": {"tenant_id": "tenant-a", "model_class": "default"},
            "tenant": {"status": "suspended", "allowed_tools": [], "allowed_model_classes": ["default"]},
        }
    )
    assert decision["allow"] is False
    assert decision["reason"] == "tenant_inactive"


@pytest.mark.skipif(not POLICY_DIR.exists(), reason="opa policy directory missing")
def test_opa_policy_allows_listed_tool():
    decision = _eval_policy(
        {
            "tenant_id": "tenant-a",
            "action": "tool.execute",
            "environment": "production",
            "resource": {"tenant_id": "tenant-a", "tool": "math.evaluate"},
            "tenant": {
                "status": "active",
                "allowed_tools": ["math.evaluate"],
                "allowed_model_classes": ["default"],
            },
        }
    )
    assert decision["allow"] is True
    assert decision["reason"] == "tool_allowed"
