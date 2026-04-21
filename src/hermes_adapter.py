import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings


class HermesAdapterError(Exception):
    pass


class HermesDownstreamError(HermesAdapterError):
    pass


class HermesImportError(HermesAdapterError):
    pass


class HermesAdapter:
    def __init__(self) -> None:
        source = Path(settings.hermes_source_dir)
        if not source.exists():
            raise HermesImportError(f"hermes source not found: {source}")

        # Make hermes-agent's top-level modules discoverable (run_agent.py, model_tools.py, etc.)
        source_str = str(source.resolve())
        if source_str not in sys.path:
            sys.path.insert(0, source_str)

        try:
            from run_agent import AIAgent
            from model_tools import get_toolset_for_tool
        except Exception as exc:
            raise HermesImportError(f"failed to import hermes run_agent modules: {exc}")

        self.AIAgent = AIAgent
        self.get_toolset_for_tool = get_toolset_for_tool
        self._provider_base_url = settings.hermes_base_url
        self._provider_api_key = settings.hermes_api_key
        self._provider_model = settings.hermes_model

    def _tenant_toolsets(self, allowed_tools: List[str]) -> List[str]:
        """
        Convert tool whitelist to toolsets.
        If resolution fails, fallback to an empty list and let strict filtering catch it.
        """
        toolsets = set()
        for tool_name in allowed_tools:
            try:
                ts = self.get_toolset_for_tool(tool_name)
                if ts:
                    toolsets.add(ts)
            except Exception:
                pass
        return sorted(toolsets)

    def _filter_tools(
        self,
        tool_defs: List[Dict[str, Any]],
        allowed_tools: List[str],
    ) -> List[Dict[str, Any]]:
        if not allowed_tools:
            return []
        allowed = set(allowed_tools)
        out = []
        for tool in tool_defs:
            try:
                name = tool.get("function", {}).get("name")
                if name in allowed:
                    out.append(tool)
            except Exception:
                continue
        return out

    def _offline_response(self, tenant_id: str, user_message: str, conversation_history: List[dict]) -> dict:
        return {
            "final_response": f"[offline-dev-hermes] tenant={tenant_id} received: {user_message}",
            "messages": conversation_history + [{"role": "user", "content": user_message}],
            "api_calls": 0,
            "completed": True,
            "model": "offline-dev-hermes",
            "provider": "offline_stub",
            "request_id": str(uuid.uuid4()),
        }

    async def invoke(
        self,
        tenant_id: str,
        messages: List[dict],
        tenant_allowed_tools: List[str],
        tools: Optional[List[str]] = None,
        model: str = "",
        base_url: str = "",
    ) -> dict:
        if not messages:
            raise HermesDownstreamError("no messages")

        last_user_idx = None
        for idx in range(len(messages) - 1, -1, -1):
            role = str(messages[idx].get("role", "")).lower()
            if role == "user":
                last_user_idx = idx
                break

        if last_user_idx is None:
            raise HermesDownstreamError("no user message in chat payload")

        user_message = str(messages[last_user_idx].get("content", "")).strip()
        if not user_message:
            raise HermesDownstreamError("user message is empty")

        conversation_history = [m for i, m in enumerate(messages) if i != last_user_idx]

        allowed_tools = tools if tools else tenant_allowed_tools
        allowed_tools = allowed_tools or []
        enabled_toolsets = self._tenant_toolsets(allowed_tools)
        provider_model = model or self._provider_model
        provider_base_url = base_url or self._provider_base_url

        if settings.environment != "production" and not provider_model and not provider_base_url:
            return self._offline_response(tenant_id, user_message, conversation_history)

        def _run() -> dict:
            from model_tools import get_tool_definitions

            raw_tools = get_tool_definitions(
                enabled_toolsets=enabled_toolsets or None,
                quiet_mode=True,
            )
            # Double-guard: keep only explicit tenant allowlist.
            # If no tools are enabled for this tenant/request, disable tools.
            if not allowed_tools:
                filtered_tools = []
            else:
                filtered_tools = self._filter_tools(raw_tools, allowed_tools)

            agent = self.AIAgent(
                base_url=provider_base_url,
                api_key=self._provider_api_key,
                model=provider_model,
                max_iterations=90,
                enabled_toolsets=enabled_toolsets or None,
                session_id=f"tenant:{tenant_id}:{uuid.uuid4()}",
                quiet_mode=True,
                verbose_logging=False,
                pass_session_id=False,
                persist_session=False,
            )

            # Make sure both tool schemas and validation set are tenant-restricted.
            if hasattr(agent, "tools"):
                agent.tools = filtered_tools or []
            if hasattr(agent, "valid_tool_names"):
                agent.valid_tool_names = set(tool["function"]["name"] for tool in filtered_tools)

            result = agent.run_conversation(
                user_message=user_message,
                conversation_history=conversation_history,
                task_id=f"tenant-{tenant_id}-{uuid.uuid4()}",
                persist_user_message=user_message,
            )

            if not isinstance(result, dict):
                return {
                    "final_response": str(result),
                    "completed": False,
                    "messages": conversation_history + [{"role": "user", "content": user_message}],
                }
            result.setdefault("final_response", None)
            result.setdefault("messages", [])
            result.setdefault("api_calls", 0)
            result.setdefault("completed", False)
            result.setdefault("model", provider_model)
            result.setdefault("provider", "")
            result.setdefault("request_id", str(uuid.uuid4()))

            if "messages" in result and isinstance(result["messages"], list):
                result["messages"] = result["messages"][-240:]
            return result

        try:
            return await asyncio.to_thread(_run)
        except RuntimeError as exc:
            if settings.environment != "production" and "No LLM provider configured" in str(exc):
                return self._offline_response(tenant_id, user_message, conversation_history)
            raise HermesDownstreamError(str(exc))
        except Exception as exc:
            if settings.environment != "production" and "No LLM provider configured" in str(exc):
                return self._offline_response(tenant_id, user_message, conversation_history)
            raise HermesDownstreamError(str(exc))

    async def close(self) -> None:
        # Kept for compatibility with FastAPI lifecycle.
        return
