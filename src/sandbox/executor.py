from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from ..config import settings
from ..context.policy import ToolPolicyViolation
from ..tools.tool_registry import ToolDescriptor
from ..tools.handlers import now_utc


@dataclass
class ToolExecutionResult:
    tool: str
    ok: bool
    payload: dict


def execute_tool_locally(handler, arguments: dict, max_bytes: int = 4096) -> ToolExecutionResult:
    public_args = {key: value for key, value in (arguments or {}).items() if not str(key).startswith("_")}
    raw = json.dumps(public_args)
    if len(raw.encode("utf-8")) > max_bytes:
        raise ToolPolicyViolation("tool_arguments_too_large")
    out = handler(arguments or {})
    if not isinstance(out, dict):
        out = {"ok": False, "error_code": "non_dict_payload", "reason": "tool returned non-dict payload"}
    return ToolExecutionResult(tool="", ok=bool(out.get("ok", True)), payload=out)


class SandboxExecutor:
    def __init__(self, mode: str = "LOCAL") -> None:
        self.mode = mode.upper()

    @staticmethod
    def _truncate_stderr(stderr_text: str, limit: int = 512) -> str:
        text = (stderr_text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    def _docker_command(self, tool: ToolDescriptor, arguments: dict) -> list[str]:
        src_dir = str(Path(__file__).resolve().parents[1])
        seccomp_profile = settings.sandbox_seccomp_profile
        arg_blob = json.dumps(arguments or {})
        schema_blob = json.dumps({key: value.__name__ for key, value in tool.input_schema.items()})
        runtime_args: list[str] = []
        if settings.environment == "production" and settings.sandbox_runtime == "runsc" and os.name != "nt":
            runtime_args.extend(["--runtime", "runsc"])
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpus",
            "0.50",
            "--memory",
            "128m",
            "--pids-limit",
            "64",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--security-opt",
            f"seccomp={seccomp_profile}",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--user",
            "65532:65532",
            "-v",
            f"{src_dir}:/workspace/src:ro",
            "-w",
            "/workspace",
            *runtime_args,
            settings.sandbox_image,
            "python",
            "-m",
            "src.sandbox.runner",
            tool.name,
            tool.handler.__module__,
            tool.handler.__name__,
            schema_blob,
            arg_blob,
        ]

    async def _run_in_container(self, tool: ToolDescriptor, arguments: dict) -> ToolExecutionResult:
        public_args = {key: value for key, value in (arguments or {}).items() if not str(key).startswith("_")}
        raw = json.dumps(public_args)
        if len(raw.encode("utf-8")) > settings.max_tool_args_bytes:
            raise ToolPolicyViolation("tool_arguments_too_large")
        command = self._docker_command(tool, public_args)

        def _execute() -> ToolExecutionResult:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return ToolExecutionResult(
                    tool=tool.name,
                    ok=False,
                    payload={"ok": False, "error_code": "tool_timeout", "reason": "sandbox timeout"},
                )
            except OSError as exc:
                return ToolExecutionResult(
                    tool=tool.name,
                    ok=False,
                    payload={"ok": False, "error_code": "sandbox_runtime_unavailable", "reason": str(exc)},
                )
            if completed.returncode != 0:
                payload = {
                    "ok": False,
                    "error_code": "sandbox_failed",
                    "reason": "containerized tool failed",
                    "stderr": self._truncate_stderr(completed.stderr),
                }
                return ToolExecutionResult(tool=tool.name, ok=False, payload=payload)
            try:
                payload = json.loads((completed.stdout or "").strip() or "{}")
            except json.JSONDecodeError:
                payload = {"ok": False, "error_code": "invalid_sandbox_output", "reason": "invalid sandbox output"}
            return ToolExecutionResult(tool=tool.name, ok=bool(payload.get("ok", True)), payload=payload)

        return await asyncio.to_thread(_execute)

    async def run(self, tool: ToolDescriptor, arguments: dict) -> ToolExecutionResult:
        if self.mode == "LOCAL":
            return execute_tool_locally(tool.handler, arguments, max_bytes=settings.max_tool_args_bytes)
        if self.mode == "CONTAINER":
            return await self._run_in_container(tool, arguments)
        raise NotImplementedError(f"sandbox mode {self.mode} not implemented yet")

    def probe(self) -> Tuple[bool, str]:
        if settings.environment == "production" and self.mode == "LOCAL":
            return False, "LOCAL sandbox not allowed in production"
        if self.mode == "LOCAL":
            try:
                result = execute_tool_locally(now_utc, {}, max_bytes=settings.max_tool_args_bytes)
                if result.ok:
                    return True, "mode=local,probe=ok"
                return False, str(result.payload.get("error_code", "probe_failed"))
            except Exception as exc:
                return False, str(exc)
        if self.mode == "CONTAINER":
            seccomp_path = Path(settings.sandbox_seccomp_profile)
            if not seccomp_path.exists():
                return False, "seccomp profile missing"
            try:
                completed = subprocess.run(
                    ["docker", "version", "--format", "{{.Server.Version}}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except OSError as exc:
                return False, str(exc)
            except subprocess.TimeoutExpired:
                return False, "docker probe timeout"
            if completed.returncode != 0:
                return False, self._truncate_stderr(completed.stderr) or "docker probe failed"
            return True, f"mode=container,runtime={settings.sandbox_runtime}"
        return False, f"unsupported sandbox mode {self.mode}"
