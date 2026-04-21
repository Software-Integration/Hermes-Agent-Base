# Hermes Commercial Foundation

This workspace is building a commercial multi-tenant foundation on top of `NousResearch/hermes-agent`.

## Goals

- Base the system on `Hermes Agent`
- Support hostile multi-tenant workloads safely
- Add context optimization and retrieval components
- Wrap execution in container or sandbox layers
- Prefer existing permissive open-source projects and avoid `AGPL`-style licensing traps

## Downloaded Components

- `hermes-agent` (MIT)
- `OPA` for policy enforcement (Apache-2.0)
- `sentence-transformers` for embeddings and retrieval prep (Apache-2.0)
- `Qdrant client` for vector index integration (Apache-2.0)
- `Valkey client` plus selected Valkey server image for cache and tenant state (MIT + BSD-3-Clause)
- `gVisor` source for stronger Linux sandboxing (Apache-2.0)

See [third_party/COMPONENTS.md](/C:/Users/wushe/Desktop/Main%20Agent/third_party/COMPONENTS.md) and [AGPL_AUDIT.md](/C:/Users/wushe/Desktop/Main%20Agent/AGPL_AUDIT.md).

## Local Paths

- Hermes source: [hermes-agent](/C:/Users/wushe/Desktop/Main%20Agent/hermes-agent)
- Downloaded third-party assets: [third_party/COMPONENTS.md](/C:/Users/wushe/Desktop/Main%20Agent/third_party/COMPONENTS.md)
- OPA starter policy: [opa/policies/tenant.rego](/C:/Users/wushe/Desktop/Main%20Agent/opa/policies/tenant.rego)

## Runtime Layout

- `hermes-base`: FastAPI gateway and Hermes adapter
- `valkey`: cache, limiter, tenant state
- `qdrant`: vector memory and retrieval
- `opa`: tenant and tool authorization sidecar
- `integrations/*`: provider-aware connectors for Google, Microsoft, AWS, Telegram, WhatsApp, LinkedIn, and X

These services are wired in [docker-compose.yml](/C:/Users/wushe/Desktop/Main%20Agent/docker-compose.yml).

## Notes

- `OPA`, `Qdrant`, and `Valkey` are now wired into the request path:
  - `OPA` for authorization checks
  - `Valkey` for rate-limiting state with in-memory fallback
  - `Qdrant` and `sentence-transformers` for semantic recall with local fallback
- Tenant chat memory is persisted under `data/tenant-memory`
- Audit events are appended under `data/audit/events.jsonl`
- Health endpoints:
  - `/healthz` for process liveness
  - `/readyz` for dependency readiness

## Provider Integrations

The foundation now includes first-wave provider packages under `src/integrations/`:

- `google`: Google Chat outbound + webhook normalization
- `microsoft`: Teams / Graph outbound + webhook normalization
- `aws`: AWS S3 / SNS operational tools
- `telegram`: Bot API outbound + webhook verification
- `whatsapp`: Cloud API outbound + webhook verification
- `linkedin`: Marketing onboarding + campaign listing path
- `x`: X / X Ads onboarding + campaign/posting path

Provider configuration is tenant-scoped inside `TENANTS_JSON.providers`, and production deployments are expected to use cloud secret backends:

- `aws_secrets_manager`
- `azure_key_vault`
- `gcp_secret_manager`

Local development can still use stub provider secrets via `PROVIDER_SECRETS_JSON` for test and dry-run setups.
