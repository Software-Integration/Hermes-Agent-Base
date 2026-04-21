from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import TenantConfig, settings
from .context.context_optimizer import optimize_context
from .context.memory_store import ChatMessage, TenantMemoryStore
from .context.policy import ToolPolicyViolation
from .context.semantic_index import SemanticContextIndex
from .hermes_adapter import HermesAdapter, HermesDownstreamError
from .sandbox.executor import SandboxExecutor
from .security.middleware import TenantContext, get_tenant, state_store
from .services.audit_log import AuditLogger
from .services.metrics import SecurityMetrics
from .services.oauth_state import OAuthStateService
from .services.payment_service import PaymentService
from .services.policy_engine import PolicyDecision, PolicyEngine
from .services.router_service import RouterService
from .services.runtime_health import DependencyStatus, RuntimeHealth
from .services.wallet_store import WalletStore
from .tools.handlers import math_evaluate, now_utc
from .tools.tool_registry import ToolDescriptor, ToolRegistry
from .integrations.registry import IntegrationManager


def _error_payload(
    request_id: str,
    error_code: str,
    reason: str,
    status_code: int,
    policy_source: str = "",
    dependency: str = "",
) -> dict[str, Any]:
    payload = {
        "request_id": request_id,
        "error_code": error_code,
        "reason": reason,
    }
    if policy_source:
        payload["policy_source"] = policy_source
    if dependency:
        payload["dependency"] = dependency
    return {"status_code": status_code, "error": payload}


@asynccontextmanager
async def lifespan(app: FastAPI):
    audit_logger.prune()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
memory_store = TenantMemoryStore(max_turns=200)
semantic_index = SemanticContextIndex()
registry = ToolRegistry()
sandbox = SandboxExecutor(mode=settings.sandbox_mode)
hermes_adapter = HermesAdapter()
policy_engine = PolicyEngine()
audit_logger = AuditLogger()
metrics = SecurityMetrics()
integration_manager = IntegrationManager(audit_logger=audit_logger, metrics=metrics)
runtime_health = RuntimeHealth(semantic_index=semantic_index, sandbox=sandbox, integrations=integration_manager)
wallet_store = WalletStore()
payment_service = PaymentService(wallet_store)
router_service = RouterService(integration_manager, wallet_store)
oauth_state_service = OAuthStateService()

registry.register(
    ToolDescriptor(
        name="math.evaluate",
        description="Evaluate simple arithmetic expression",
        handler=math_evaluate,
        capabilities=("compute.arithmetic",),
        input_schema={"expression": str},
        max_output_chars=4096,
    )
)
integration_manager.register_tools(registry)
registry.register(
    ToolDescriptor(
        name="time.now_utc",
        description="Get current UTC time",
        handler=now_utc,
        capabilities=("time.read",),
        input_schema={},
        max_output_chars=256,
    )
)


class ChatRequest(BaseModel):
    messages: List[dict] = Field(
        ...,
        json_schema_extra={"example": [{"role": "user", "content": "hello"}]},
    )
    requested_tools: Optional[List[str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    tenant_id: str
    request_id: str
    context_summary: str
    rate_limit_remaining: int = 0
    rate_limit_reset_after_seconds: int = 0
    tenant_status: str = "unknown"
    auth_source: str = "tenant_provider"
    policy_version: str = "unknown"
    degraded_retrieval: bool = False
    final_response: str | None = None
    messages: List[dict] = Field(default_factory=list)
    api_calls: int = 0
    completed: bool = False
    response: dict


class ToolRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResponse(BaseModel):
    tenant_id: str
    tool: str
    ok: bool
    result: dict


class HealthResponse(BaseModel):
    ok: bool
    sandbox_mode: str
    sandbox_runtime: str
    hermes_source_dir: str


class ReadyDependency(BaseModel):
    name: str
    ok: bool
    required: bool
    detail: str


class ReadyResponse(BaseModel):
    ok: bool
    critical_ok: bool
    degraded: bool
    dependencies: List[ReadyDependency]


class MetricsResponse(BaseModel):
    counters: dict[str, int]


class WipeResponse(BaseModel):
    tenant_id: str
    wiped: bool


class RouterRequest(BaseModel):
    provider: str
    action: str
    execution_scope: str = "tenant"
    arguments: dict = Field(default_factory=dict)


class RouterResponse(BaseModel):
    tenant_id: str
    provider: str
    action: str
    execution_scope: str
    billed_cents: int
    result: dict


class WalletResponse(BaseModel):
    tenant_id: str
    balance_cents: int
    currency: str
    transactions: list[dict]


class TopupRequest(BaseModel):
    amount_cents: int
    currency: str = "usd"


class TopupResponse(BaseModel):
    tenant_id: str
    checkout_session_id: str
    checkout_url: str
    amount_cents: int
    currency: str


class OAuthStartResponse(BaseModel):
    provider: str
    tenant_id: str
    authorization_url: str


class OAuthCallbackResponse(BaseModel):
    provider: str
    tenant_id: str
    stored: bool
    detail: str


def _platform_tenant() -> TenantConfig:
    return TenantConfig(
        tenant_id="platform",
        api_key=settings.platform_admin_api_key or "platform",
        name="Platform",
        status="active",
        allowed_tools=[],
        allowed_capabilities=["*"],
        allowed_model_classes=["default"],
        providers=settings.platform_providers,
        metadata={},
    )


async def require_platform_admin(request: Request) -> None:
    if not settings.platform_admin_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error_code": "platform_admin_not_configured", "reason": "PLATFORM_ADMIN_API_KEY missing"})
    provided = request.headers.get("X-Platform-Admin-Key", "")
    if provided != settings.platform_admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error_code": "invalid_platform_admin_key", "reason": "invalid platform admin key"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"error_code": "http_error", "reason": str(exc.detail)}
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={"request_id": request_id, **detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    audit_logger.write("unhandled_exception", {"request_id": request_id, "error_type": type(exc).__name__})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "request_id": request_id,
            "error_code": "internal_server_error",
            "reason": "unexpected internal error",
        },
    )


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(
        ok=True,
        sandbox_mode=settings.sandbox_mode,
        sandbox_runtime=settings.sandbox_runtime,
        hermes_source_dir=settings.hermes_source_dir,
    )


@app.get("/readyz", response_model=ReadyResponse)
async def readyz() -> ReadyResponse:
    checks: list[DependencyStatus] = [
        runtime_health.check_tenant_config(),
        runtime_health.check_sandbox(),
        await runtime_health.check_opa(),
        runtime_health.check_valkey(),
        runtime_health.check_qdrant(),
        runtime_health.check_embedder(),
    ]
    checks.extend(integration_manager.provider_dependency_statuses(settings.tenants))
    critical_ok = all(item.ok for item in checks if item.required)
    degraded = any((not item.ok) and (not item.required) for item in checks)
    return ReadyResponse(
        ok=critical_ok,
        critical_ok=critical_ok,
        degraded=degraded,
        dependencies=[
            ReadyDependency(name=item.name, ok=item.ok, required=item.required, detail=item.detail)
            for item in checks
        ],
    )


@app.get("/metricsz", response_model=MetricsResponse)
async def metricsz() -> MetricsResponse:
    return MetricsResponse(counters=metrics.snapshot())


def _deny_with_policy(decision: PolicyDecision, request_id: str, dependency: str = "") -> None:
    metrics.incr("denied_requests")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_error_payload(
            request_id=request_id,
            error_code="policy_denied",
            reason=decision.reason,
            status_code=status.HTTP_403_FORBIDDEN,
            policy_source=decision.source,
            dependency=dependency,
        )["error"],
    )


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, tenant_ctx: TenantContext = Depends(get_tenant)) -> ChatResponse:
    tenant = tenant_ctx.tenant
    request_id = str(uuid.uuid4())

    decision = await policy_engine.authorize_chat(tenant, settings.hermes_model)
    tenant_ctx.policy_version = decision.policy_version
    if not decision.allowed:
        if decision.reason == "opa_unavailable":
            metrics.incr("policy_backend_failures")
        audit_logger.write(
            "chat_denied",
            {"tenant_id": tenant.tenant_id, "request_id": request_id, "reason": decision.reason},
        )
        _deny_with_policy(decision, request_id, dependency="opa")

    for msg in body.messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user"))
        content = str(msg.get("content", ""))
        memory_store.append(tenant.tenant_id, ChatMessage(role=role, content=content))

    semantic_query = ""
    for msg in reversed(body.messages):
        if isinstance(msg, dict) and str(msg.get("role", "")).lower() == "user":
            semantic_query = str(msg.get("content", ""))
            break

    try:
        recalled_context, degraded_retrieval = semantic_index.search(
            tenant.tenant_id,
            semantic_query,
            limit=settings.semantic_top_k,
        )
    except Exception:
        recalled_context, degraded_retrieval = [], True
    if degraded_retrieval:
        metrics.incr("retrieval_degradation_count")
        audit_logger.write(
            "retrieval_degraded",
            {"tenant_id": tenant.tenant_id, "request_id": request_id},
        )

    history = memory_store.get_history(tenant.tenant_id, limit=settings.default_context_turns * 2)
    optimized = optimize_context(
        tenant_id=tenant.tenant_id,
        incoming_messages=body.messages,
        mem_history=history[:-len(body.messages)] if history else [],
        retrieved_contexts=recalled_context,
        char_limit=tenant.context_char_limit,
        max_turns=settings.default_context_turns,
        max_summary_words=settings.max_context_recap_words,
    )
    if optimized.summary:
        memory_store.set_summary(tenant.tenant_id, optimized.summary)
    try:
        semantic_index.upsert_messages(tenant.tenant_id, body.messages)
    except Exception:
        metrics.incr("retrieval_degradation_count")
        audit_logger.write(
            "retrieval_degraded",
            {"tenant_id": tenant.tenant_id, "request_id": request_id, "phase": "upsert"},
        )

    try:
        if body.requested_tools:
            bad = [name for name in body.requested_tools if name not in tenant.allowed_tools]
            if bad:
                raise ToolPolicyViolation(f"tenant_tool_not_allowed:{bad}")
            tool_snapshot = body.requested_tools
        else:
            tool_snapshot = []

        response_payload = await hermes_adapter.invoke(
            tenant.tenant_id,
            optimized.compact_messages,
            tenant_allowed_tools=tenant.allowed_tools,
            tools=tool_snapshot,
            model=settings.hermes_model,
        )
    except HermesDownstreamError as exc:
        audit_logger.write(
            "chat_failed",
            {"tenant_id": tenant.tenant_id, "request_id": request_id, "reason": "hermes_downstream_error"},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_payload(
                request_id=request_id,
                error_code="hermes_downstream_error",
                reason=str(exc),
                status_code=status.HTTP_502_BAD_GATEWAY,
                dependency="hermes",
            )["error"],
        )
    except ToolPolicyViolation as exc:
        audit_logger.write(
            "chat_failed",
            {"tenant_id": tenant.tenant_id, "request_id": request_id, "reason": str(exc.detail)},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error_payload(
                request_id=request_id,
                error_code="tool_policy_violation",
                reason=str(exc.detail),
                status_code=status.HTTP_403_FORBIDDEN,
            )["error"],
        )

    audit_logger.write(
        "chat_completed",
        {
            "tenant_id": tenant.tenant_id,
            "request_id": request_id,
            "api_calls": response_payload.get("api_calls", 0),
            "completed": response_payload.get("completed", False),
            "tool_request_count": len(tool_snapshot),
            "degraded_retrieval": degraded_retrieval,
        },
    )
    return ChatResponse(
        tenant_id=tenant.tenant_id,
        request_id=request_id,
        context_summary=optimized.summary,
        rate_limit_remaining=tenant_ctx.rate_limit_remaining,
        rate_limit_reset_after_seconds=tenant_ctx.rate_limit_reset_after_seconds,
        tenant_status=tenant_ctx.tenant_status,
        auth_source=tenant_ctx.auth_source,
        policy_version=decision.policy_version,
        degraded_retrieval=degraded_retrieval,
        final_response=response_payload.get("final_response"),
        messages=response_payload.get("messages", []),
        api_calls=response_payload.get("api_calls", 0),
        completed=response_payload.get("completed", False),
        response=response_payload,
    )


@app.post("/v1/tools/execute", response_model=ToolResponse)
async def execute_tool(body: ToolRequest, tenant_ctx: TenantContext = Depends(get_tenant)) -> ToolResponse:
    tenant = tenant_ctx.tenant
    request_id = str(uuid.uuid4())
    descriptor = registry.get(body.name)
    decision = await policy_engine.authorize_tool(tenant, body.name, descriptor.capabilities)
    if not decision.allowed:
        if decision.reason == "opa_unavailable":
            metrics.incr("policy_backend_failures")
        audit_logger.write(
            "tool_denied",
            {"tenant_id": tenant.tenant_id, "tool": body.name, "request_id": request_id, "reason": decision.reason},
        )
        _deny_with_policy(decision, request_id, dependency="opa")

    registry.validate_arguments(descriptor, body.arguments)
    tool_arguments = dict(body.arguments)
    tool_arguments["_tenant"] = tenant
    result = await sandbox.run(descriptor, tool_arguments)
    if not result.ok:
        metrics.incr("sandbox_failures")
    audit_logger.write(
        "tool_executed",
        {"tenant_id": tenant.tenant_id, "tool": body.name, "ok": result.ok, "request_id": request_id},
    )
    return ToolResponse(
        tenant_id=tenant.tenant_id,
        tool=body.name,
        ok=result.ok,
        result=result.payload,
    )


@app.post("/v1/router/execute", response_model=RouterResponse)
async def router_execute(
    body: RouterRequest,
    request: Request,
    tenant_ctx: TenantContext = Depends(get_tenant),
) -> RouterResponse:
    request_id = str(uuid.uuid4())
    execution_scope = body.execution_scope.lower()
    tenant = tenant_ctx.tenant
    if execution_scope == "platform":
        await require_platform_admin(request)
    elif execution_scope != "tenant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error_code": "invalid_execution_scope", "reason": "execution_scope must be tenant or platform"})
    route_result = router_service.execute(
        tenant=tenant,
        provider=body.provider,
        action=body.action,
        arguments=body.arguments,
        execution_scope=execution_scope,
    )
    audit_logger.write(
        "router_executed",
        {
            "tenant_id": tenant.tenant_id,
            "request_id": request_id,
            "provider": body.provider,
            "action": body.action,
            "execution_scope": execution_scope,
            "billed_cents": route_result.billed_cents,
            "ok": route_result.payload.get("ok", False),
        },
    )
    return RouterResponse(
        tenant_id=tenant.tenant_id,
        provider=route_result.provider,
        action=route_result.action,
        execution_scope=route_result.execution_scope,
        billed_cents=route_result.billed_cents,
        result=route_result.payload,
    )


@app.get("/v1/router/catalog")
async def router_catalog(tenant_ctx: TenantContext = Depends(get_tenant)) -> dict:
    tenant = tenant_ctx.tenant
    catalog = []
    for provider_name, provider_cfg in tenant.providers.items():
        if not provider_cfg.enabled:
            continue
        catalog.append(
            {
                "provider": provider_name,
                "capabilities": provider_cfg.capabilities,
                "approval_state": provider_cfg.approval_state,
            }
        )
    return {"tenant_id": tenant.tenant_id, "providers": catalog, "pricing": settings.router_pricing}


@app.get("/v1/billing/wallet", response_model=WalletResponse)
async def billing_wallet(tenant_ctx: TenantContext = Depends(get_tenant)) -> WalletResponse:
    balance = wallet_store.get_balance(tenant_ctx.tenant.tenant_id)
    return WalletResponse(
        tenant_id=balance.tenant_id,
        balance_cents=balance.balance_cents,
        currency=balance.currency,
        transactions=balance.transactions[-100:],
    )


@app.post("/v1/billing/topups/checkout-session", response_model=TopupResponse)
async def billing_topup_checkout(body: TopupRequest, tenant_ctx: TenantContext = Depends(get_tenant)) -> TopupResponse:
    request_id = str(uuid.uuid4())
    session = payment_service.create_topup_checkout_session(
        tenant_id=tenant_ctx.tenant.tenant_id,
        amount_cents=body.amount_cents,
        currency=body.currency,
    )
    audit_logger.write(
        "billing_topup_checkout_created",
        {
            "tenant_id": tenant_ctx.tenant.tenant_id,
            "request_id": request_id,
            "amount_cents": body.amount_cents,
            "currency": body.currency,
            "checkout_session_id": session["id"],
        },
    )
    return TopupResponse(
        tenant_id=tenant_ctx.tenant.tenant_id,
        checkout_session_id=session["id"],
        checkout_url=session["url"],
        amount_cents=session["amount_cents"],
        currency=session["currency"],
    )


@app.get("/v1/oauth/google/start", response_model=OAuthStartResponse)
async def oauth_google_start(tenant_ctx: TenantContext = Depends(get_tenant)) -> OAuthStartResponse:
    from .integrations.google.auth import google_oauth_start

    tenant = tenant_ctx.tenant
    state = oauth_state_service.create(tenant.tenant_id, "google")
    redirect_uri = f"{settings.app_base_url}/oauth/google/callback"
    authorization_url = google_oauth_start(integration_manager.providers["google"], tenant, state, redirect_uri)
    return OAuthStartResponse(provider="google", tenant_id=tenant.tenant_id, authorization_url=authorization_url)


@app.get("/v1/oauth/microsoft/start", response_model=OAuthStartResponse)
async def oauth_microsoft_start(tenant_ctx: TenantContext = Depends(get_tenant)) -> OAuthStartResponse:
    from .integrations.microsoft.auth import microsoft_oauth_start

    tenant = tenant_ctx.tenant
    state = oauth_state_service.create(tenant.tenant_id, "microsoft")
    redirect_uri = f"{settings.app_base_url}/oauth/microsoft/callback"
    authorization_url = microsoft_oauth_start(integration_manager.providers["microsoft"], tenant, state, redirect_uri)
    return OAuthStartResponse(provider="microsoft", tenant_id=tenant.tenant_id, authorization_url=authorization_url)


@app.delete("/v1/tenants/{tenant_id}/state", response_model=WipeResponse)
async def wipe_tenant_state(tenant_id: str, tenant_ctx: TenantContext = Depends(get_tenant)) -> WipeResponse:
    request_id = str(uuid.uuid4())
    if tenant_ctx.tenant.tenant_id != tenant_id:
        metrics.incr("cross_tenant_guard_violations")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_error_payload(
                request_id=request_id,
                error_code="tenant_scope_violation",
                reason="cannot wipe another tenant state",
                status_code=status.HTTP_403_FORBIDDEN,
            )["error"],
        )

    memory_store.clear(tenant_id)
    try:
        semantic_index.clear_tenant(tenant_id)
    except Exception:
        metrics.incr("retrieval_degradation_count")
        audit_logger.write("retrieval_degraded", {"tenant_id": tenant_id, "request_id": request_id, "phase": "wipe"})
    state_store.clear_tenant_state(tenant_id)
    audit_logger.write("tenant_wiped", {"tenant_id": tenant_id, "request_id": request_id})
    return WipeResponse(tenant_id=tenant_id, wiped=True)


@app.post("/webhooks/google/chat")
async def webhook_google_chat(request: Request):
    return await integration_manager.handle_webhook("google", request)


@app.post("/webhooks/microsoft/teams")
async def webhook_microsoft_teams(request: Request):
    return await integration_manager.handle_webhook("microsoft", request)


@app.post("/webhooks/telegram")
async def webhook_telegram(request: Request):
    return await integration_manager.handle_webhook("telegram", request)


@app.get("/webhooks/whatsapp")
async def webhook_whatsapp_verify(request: Request):
    return await integration_manager.handle_webhook("whatsapp", request)


@app.post("/webhooks/whatsapp")
async def webhook_whatsapp(request: Request):
    return await integration_manager.handle_webhook("whatsapp", request)


@app.post("/webhooks/stripe")
async def webhook_stripe(request: Request):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    result = payment_service.verify_and_process_webhook(body, signature)
    audit_logger.write("stripe_webhook_processed", result)
    return result


@app.get("/oauth/google/callback", response_model=OAuthCallbackResponse)
async def oauth_google_callback(code: str, state: str) -> OAuthCallbackResponse:
    from .integrations.google.auth import google_exchange_code

    parsed = oauth_state_service.verify(state)
    if parsed["provider"] != "google" or parsed["tenant_id"] not in settings.tenants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error_code": "invalid_oauth_state", "reason": "google state invalid"})
    tenant = settings.tenants[parsed["tenant_id"]]
    provider_cfg = tenant.providers.get("google")
    if provider_cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "provider_not_configured", "reason": "google provider missing"})
    redirect_uri = f"{settings.app_base_url}/oauth/google/callback"
    tokens = google_exchange_code(integration_manager.providers["google"], tenant, code, redirect_uri)
    current = integration_manager.secret_manager.resolve(provider_cfg)
    payload = dict(current.data if current.ok else {})
    payload.update(tokens)
    stored = integration_manager.secret_manager.upsert(provider_cfg, payload)
    audit_logger.write("oauth_connected", {"tenant_id": tenant.tenant_id, "provider": "google", "stored": stored.ok})
    return OAuthCallbackResponse(provider="google", tenant_id=tenant.tenant_id, stored=stored.ok, detail=stored.detail)


@app.get("/oauth/microsoft/callback", response_model=OAuthCallbackResponse)
async def oauth_microsoft_callback(code: str, state: str) -> OAuthCallbackResponse:
    from .integrations.microsoft.auth import microsoft_exchange_code

    parsed = oauth_state_service.verify(state)
    if parsed["provider"] != "microsoft" or parsed["tenant_id"] not in settings.tenants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error_code": "invalid_oauth_state", "reason": "microsoft state invalid"})
    tenant = settings.tenants[parsed["tenant_id"]]
    provider_cfg = tenant.providers.get("microsoft")
    if provider_cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error_code": "provider_not_configured", "reason": "microsoft provider missing"})
    redirect_uri = f"{settings.app_base_url}/oauth/microsoft/callback"
    tokens = microsoft_exchange_code(integration_manager.providers["microsoft"], tenant, code, redirect_uri)
    current = integration_manager.secret_manager.resolve(provider_cfg)
    payload = dict(current.data if current.ok else {})
    payload.update(tokens)
    stored = integration_manager.secret_manager.upsert(provider_cfg, payload)
    audit_logger.write("oauth_connected", {"tenant_id": tenant.tenant_id, "provider": "microsoft", "stored": stored.ok})
    return OAuthCallbackResponse(provider="microsoft", tenant_id=tenant.tenant_id, stored=stored.ok, detail=stored.detail)
