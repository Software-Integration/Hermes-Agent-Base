# License and Dependency Audit

This repository is intentionally published under `AGPL-3.0-only`, with a separate commercial licensing path available for the repository-controlled portions of the codebase.

At the dependency level, the goal remains to avoid pulling in third-party components whose terms would create unnecessary extra licensing conflicts beyond the project's chosen top-level model.

## Repository-Level Boundary

- This repository's own original code and repository-specific modifications are intended to be offered under:
  - `AGPL-3.0-only`
  - a separate commercial license where granted by the rights holder
- Third-party components keep their original licenses, notices, and ownership.
- This repository does not claim ownership of upstream projects.
- This audit is about dependency posture; it does not relicense upstream dependencies.

## Accepted Components

- `NousResearch/hermes-agent`
  - Source: https://github.com/NousResearch/hermes-agent
  - License: MIT
  - Purpose: agent runtime
  - Ownership: upstream rights holders

- `open-policy-agent/opa`
  - Source: https://github.com/open-policy-agent/opa
  - License: Apache-2.0
  - Purpose: tenant policy and authorization sidecar
  - Ownership: upstream rights holders

- `UKPLab/sentence-transformers`
  - Source: https://github.com/UKPLab/sentence-transformers
  - License: Apache-2.0
  - Purpose: embedding-based context optimization
  - Ownership: upstream rights holders

- `qdrant/qdrant`
  - Source: https://github.com/qdrant/qdrant
  - License: Apache-2.0
  - Purpose: vector retrieval and tenant-scoped semantic memory
  - Ownership: upstream rights holders

- `valkey-io/valkey`
  - Source: https://github.com/valkey-io/valkey
  - License: BSD-3-Clause
  - Purpose: cache, rate limiting, ephemeral tenant state
  - Ownership: upstream rights holders

- `valkey-io/valkey-py`
  - Source: https://github.com/valkey-io/valkey-py
  - License: MIT
  - Purpose: Python client for Valkey
  - Ownership: upstream rights holders

- `google/gvisor`
  - Source: https://github.com/google/gvisor
  - License: Apache-2.0
  - Purpose: stronger container sandboxing on Linux hosts
  - Ownership: upstream rights holders

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
- For repository ownership and provenance wording, see `NOTICE`.
- If you need proprietary deployment terms for the repository-controlled portions of this project, see [COMMERCIAL_LICENSE.md](/C:/Users/wushe/Desktop/Main%20Agent/COMMERCIAL_LICENSE.md).
