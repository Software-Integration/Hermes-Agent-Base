from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"
COMPOSE_CWD = str(ROOT)


def load_first_tenant() -> tuple[str, str]:
    env_path = ROOT / ".env"
    data = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    tenants = json.loads(data["TENANTS_JSON"])
    tenant_id, tenant = next(iter(tenants.items()))
    return tenant_id, str(tenant["api_key"])


def request(method: str, path: str, body: dict | None = None, tenant_id: str = "", token: str = "") -> tuple[int, dict]:
    payload = None
    headers = {"Content-Type": "application/json"}
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else {}


def docker_compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=COMPOSE_CWD,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def wait_for_ready(expected_ok: bool, timeout_s: int = 90) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        code, payload = request("GET", "/readyz")
        if code == 200:
            last = payload
            if bool(payload.get("ok")) is expected_ok:
                return payload
        time.sleep(2)
    raise RuntimeError(f"readyz did not reach expected ok={expected_ok}: {last}")


def read_audit_tail() -> str:
    result = subprocess.run(
        ["docker", "exec", "hermes-commercial-base", "sh", "-lc", "tail -n 200 /app/data/audit/events.jsonl 2>/dev/null || true"],
        cwd=COMPOSE_CWD,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.stdout


def expect(condition: bool, label: str, failures: list[str], detail: str = "") -> None:
    if condition:
        return
    failures.append(f"{label}: {detail}".strip())


def main() -> int:
    tenant_id, token = load_first_tenant()
    failures: list[str] = []

    status, health = request("GET", "/healthz")
    expect(status == 200 and health.get("ok") is True, "healthz", failures, str((status, health)))

    ready = wait_for_ready(True)
    deps = {item["name"]: item for item in ready.get("dependencies", [])}
    expect(deps.get("sandbox", {}).get("ok") is True, "readyz.sandbox", failures, json.dumps(deps.get("sandbox", {})))

    status, chat = request(
        "POST",
        "/v1/chat",
        {"messages": [{"role": "user", "content": "hello acceptance"}]},
        tenant_id,
        token,
    )
    expect(status == 200 and bool(chat.get("final_response")), "chat_happy", failures, json.dumps(chat))

    status, tool_time = request(
        "POST",
        "/v1/tools/execute",
        {"name": "time.now_utc", "arguments": {}},
        tenant_id,
        token,
    )
    expect(status == 200 and tool_time.get("ok") is True, "tool_time", failures, json.dumps(tool_time))

    status, tool_math = request(
        "POST",
        "/v1/tools/execute",
        {"name": "math.evaluate", "arguments": {"expression": "2+3*4"}},
        tenant_id,
        token,
    )
    expect(status == 200 and tool_math.get("ok") is True, "tool_math", failures, json.dumps(tool_math))

    status, wipe = request("DELETE", f"/v1/tenants/{tenant_id}/state", None, tenant_id, token)
    expect(status == 200 and wipe.get("wiped") is True, "wipe_happy", failures, json.dumps(wipe))

    status, bad_key = request(
        "POST",
        "/v1/chat",
        {"messages": [{"role": "user", "content": "hello"}]},
        tenant_id,
        "wrong-key",
    )
    expect(status == 401, "invalid_key", failures, json.dumps(bad_key))

    status, cross_wipe = request("DELETE", "/v1/tenants/tenant-other/state", None, tenant_id, token)
    expect(status == 403 and cross_wipe.get("error_code") == "tenant_scope_violation", "cross_tenant_wipe", failures, json.dumps(cross_wipe))

    status, denied_tool = request(
        "POST",
        "/v1/chat",
        {"messages": [{"role": "user", "content": "hello"}], "requested_tools": ["not.allowed"]},
        tenant_id,
        token,
    )
    expect(status == 403 and denied_tool.get("error_code") == "tool_policy_violation", "tool_allowlist", failures, json.dumps(denied_tool))

    stop_result = docker_compose("stop", "opa")
    expect(stop_result.returncode == 0, "stop_opa", failures, stop_result.stderr.strip())
    try:
        time.sleep(3)
        status, opa_denied_chat = request(
            "POST",
            "/v1/chat",
            {"messages": [{"role": "user", "content": "hello while opa down"}]},
            tenant_id,
            token,
        )
        expect(status == 403 and opa_denied_chat.get("error_code") == "policy_denied", "opa_down_chat", failures, json.dumps(opa_denied_chat))

        status, opa_denied_tool = request(
            "POST",
            "/v1/tools/execute",
            {"name": "time.now_utc", "arguments": {}},
            tenant_id,
            token,
        )
        expect(status == 403 and opa_denied_tool.get("error_code") == "policy_denied", "opa_down_tool", failures, json.dumps(opa_denied_tool))

        code, not_ready = request("GET", "/readyz")
        deps_down = {item["name"]: item for item in not_ready.get("dependencies", [])} if code == 200 else {}
        expect(code == 200 and not_ready.get("ok") is False and deps_down.get("opa", {}).get("ok") is False, "readyz_opa_down", failures, json.dumps(not_ready))
    finally:
        start_result = docker_compose("start", "opa")
        expect(start_result.returncode == 0, "start_opa", failures, start_result.stderr.strip())
        wait_for_ready(True)

    status, metrics = request("GET", "/metricsz")
    counters = metrics.get("counters", {}) if status == 200 else {}
    expect(status == 200 and counters.get("denied_requests", 0) >= 2, "metrics_denied", failures, json.dumps(metrics))
    expect(counters.get("policy_backend_failures", 0) >= 1, "metrics_policy_backend_failures", failures, json.dumps(metrics))

    audit_tail = read_audit_tail()
    for event in ("chat_completed", "tool_executed", "chat_denied", "tool_denied", "tenant_wiped"):
        expect(event in audit_tail, f"audit_{event}", failures)

    if failures:
        print(json.dumps({"result": "FAIL", "failures": failures}, ensure_ascii=True, indent=2))
        return 1

    print(json.dumps({"result": "PASS"}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
