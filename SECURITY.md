# Security Policy

## Reporting Security Issues

If you discover a security issue, please report it privately to the repository operator or security contact before public disclosure.

Please include:

- a clear description of the issue
- affected components or endpoints
- reproduction steps if safe to share
- impact assessment
- suggested mitigations if known

## Scope

Security-sensitive areas of this repository include:

- tenant isolation
- policy enforcement
- sandboxed tool execution
- secret handling
- OAuth flows
- provider webhooks
- billing and wallet flows
- audit and metrics integrity

## Disclosure Expectations

Please avoid public issue disclosure for vulnerabilities that could reasonably affect deployed tenants or operators before a fix is available.

## Supported Security Posture

This repository aims to maintain:

- fail-closed authorization for critical policy paths
- tenant-scoped credentials and provider access
- structured audit logging
- readiness checks aligned with runtime reality
- minimized sandbox exposure for tool execution

## Hardening Notes

Operators should review:

- secret backend configuration
- provider credential isolation
- webhook signature verification
- container and sandbox runtime settings
- data retention and audit handling
- dependency and image provenance

## Third-Party Components

Some security characteristics depend on upstream components and cloud providers.
Their ownership and licenses remain with their respective rights holders.
See `NOTICE` and `AGPL_AUDIT.md` for provenance details.
