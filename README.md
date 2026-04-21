# Hermes Agent Base

Hermes Agent Base is a multi-tenant integration and automation foundation built on top of `NousResearch/hermes-agent`.

It is designed for hostile-tenant isolation, provider aggregation, containerized execution, and commercial deployment scenarios where one platform API brokers access to many downstream ecosystems.

## Project License

This repository is offered under a dual-license model:

- `AGPL-3.0-only` for open-source use, modification, and network deployment
- Commercial licensing is available separately for teams that need to embed, redistribute, or operate this software under non-AGPL terms

Read:

- [LICENSE](/C:/Users/wushe/Desktop/Main%20Agent/LICENSE)
- [COMMERCIAL_LICENSE.md](/C:/Users/wushe/Desktop/Main%20Agent/COMMERCIAL_LICENSE.md)
- [NOTICE](/C:/Users/wushe/Desktop/Main%20Agent/NOTICE)
- [AGPL_AUDIT.md](/C:/Users/wushe/Desktop/Main%20Agent/AGPL_AUDIT.md)

Important:

- Third-party components included or referenced in this workspace keep their own original licenses, copyright notices, and ownership.
- This repository does not claim ownership over upstream projects or their original source code.
- Only the repository's own original code and repository-specific modifications are intended to be offered under the repository licensing model, except where a file or dependency states otherwise.

## Provenance and Rights

For source origins and licensing boundaries, see:

- [NOTICE](/C:/Users/wushe/Desktop/Main%20Agent/NOTICE)
- [AGPL_AUDIT.md](/C:/Users/wushe/Desktop/Main%20Agent/AGPL_AUDIT.md)
- [third_party/COMPONENTS.md](/C:/Users/wushe/Desktop/Main%20Agent/third_party/COMPONENTS.md)

## What This Base Does

- Builds on `Hermes Agent`
- Adds multi-tenant isolation and policy enforcement
- Adds context optimization and semantic retrieval
- Wraps tool execution in sandboxed runtime layers
- Aggregates external providers behind a unified router-style API
- Leaves OAuth, billing, and provider onboarding slots ready for later activation

## Architecture

- `hermes-base`: FastAPI gateway and Hermes adapter
- `opa`: authorization and capability policy sidecar
- `valkey`: rate limit, cache, and tenant state services
- `qdrant`: semantic recall and vector memory
- `sandbox`: isolated tool execution path
- `integrations/*`: provider connectors for Google, Microsoft, AWS, Telegram, WhatsApp, LinkedIn, and X

These services are wired in [docker-compose.yml](/C:/Users/wushe/Desktop/Main%20Agent/docker-compose.yml).

## Included Third-Party Components

- `hermes-agent` (MIT)
- `OPA` (Apache-2.0)
- `sentence-transformers` (Apache-2.0)
- `Qdrant client` (Apache-2.0)
- `Valkey client/server` (MIT + BSD-3-Clause)
- `gVisor` source (Apache-2.0)

## Runtime Notes

- `OPA`, `Qdrant`, and `Valkey` are wired into the request path
- Tenant chat memory is persisted under `data/tenant-memory`
- Audit events are appended under `data/audit/events.jsonl`
- Health endpoints:
  - `/healthz` for liveness
  - `/readyz` for strict readiness
  - `/metricsz` for operational counters

## Provider Integrations

Current provider packages under `src/integrations/`:

- `google`: Google Chat outbound, OAuth, webhook normalization
- `microsoft`: Teams and Graph outbound, OAuth, webhook normalization
- `aws`: operational tooling for selected AWS services
- `telegram`: Bot API outbound and webhook verification
- `whatsapp`: Cloud API outbound and webhook verification
- `linkedin`: marketing onboarding and campaign access path
- `x`: X and X Ads onboarding and campaign/posting path

Provider configuration is tenant-scoped inside `TENANTS_JSON.providers`, and production deployments are expected to use cloud secret backends:

- `aws_secrets_manager`
- `azure_key_vault`
- `gcp_secret_manager`

## Commercial Licensing

If you need to:

- keep your server-side modifications private
- bundle this software into a proprietary platform
- redistribute it inside a commercial appliance or SaaS without AGPL obligations
- obtain custom support, warranty, indemnity, or negotiated deployment terms

you should seek a separate commercial license.

See [COMMERCIAL_LICENSE.md](/C:/Users/wushe/Desktop/Main%20Agent/COMMERCIAL_LICENSE.md).
