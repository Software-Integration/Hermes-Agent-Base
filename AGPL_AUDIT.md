# License Audit

This foundation is intentionally built from permissive or commercially usable components.
The goal is to avoid `AGPL`, `SSPL`, and similar network-copyleft or source-available traps.

## Accepted Components

- `NousResearch/hermes-agent`
  - Source: https://github.com/NousResearch/hermes-agent
  - License: MIT
  - Purpose: agent runtime

- `open-policy-agent/opa`
  - Source: https://github.com/open-policy-agent/opa
  - License: Apache-2.0
  - Purpose: tenant policy and authorization sidecar

- `UKPLab/sentence-transformers`
  - Source: https://github.com/UKPLab/sentence-transformers
  - License: Apache-2.0
  - Purpose: embedding-based context optimization

- `qdrant/qdrant`
  - Source: https://github.com/qdrant/qdrant
  - License: Apache-2.0
  - Purpose: vector retrieval and tenant-scoped semantic memory

- `valkey-io/valkey`
  - Source: https://github.com/valkey-io/valkey
  - License: BSD-3-Clause
  - Purpose: cache, rate limiting, ephemeral tenant state

- `valkey-io/valkey-py`
  - Source: https://github.com/valkey-io/valkey-py
  - License: MIT
  - Purpose: Python client for Valkey

- `google/gvisor`
  - Source: https://github.com/google/gvisor
  - License: Apache-2.0
  - Purpose: stronger container sandboxing on Linux hosts

## Rejected Components

- `redis` newer server releases
  - Reason: newer Redis releases moved away from the older BSD-only posture and introduced `RSAL`, `SSPL`, and later `AGPL` options.
  - Decision: use `Valkey` instead.

- Random community RAG loaders
  - Reason: several convenient loaders around Qdrant are `GPL` or `AGPL`.
  - Decision: use official `qdrant-client` and build our own ingestion path.

## Downloaded Into This Workspace

- `third_party/bin/opa.exe`
- `third_party/pypi/sentence_transformers-5.4.1-py3-none-any.whl`
- `third_party/pypi/sentence_transformers-5.4.1.tar.gz`
- `third_party/pypi/qdrant_client-1.17.1-py3-none-any.whl`
- `third_party/pypi/valkey-6.1.1-py3-none-any.whl`
- `third_party/src/gvisor`
- `third_party/src/sentence-transformers`

## Notes

- This file is a practical engineering audit, not legal advice.
- Before production distribution, generate a full SBOM and transitive dependency report for the lockfile and container images.
