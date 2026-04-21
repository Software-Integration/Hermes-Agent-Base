# Contributing

Thanks for contributing to Hermes Agent Base.

This project mixes repository-controlled original work with separately licensed third-party components, so contributions need to stay clean on provenance and licensing.

## Before You Contribute

Please make sure your contribution:

- is work you have the right to contribute
- does not copy code from third-party projects unless their license allows it and attribution is preserved
- does not remove upstream license notices from bundled or referenced third-party components
- does not misstate ownership of upstream projects or dependencies

## Contribution Scope

Contributions are welcome for repository-controlled material such as:

- source code authored for this repository
- tests and fixtures authored for this repository
- documentation
- deployment files
- repository-specific integrations and adapters

Contributions should avoid introducing dependency or licensing surprises.

## Licensing of Contributions

Unless explicitly agreed otherwise in writing, contributions to repository-controlled material are accepted on the basis that they may be distributed under:

- `AGPL-3.0-only`
- and, where applicable, the repository's separate commercial licensing model for repository-controlled portions

This statement applies only to material you have the right to contribute.
It does not override the original license of third-party material.

## Dependency Rules

When adding or changing dependencies:

- prefer permissive or commercially usable upstream licenses
- document source and license impact in `AGPL_AUDIT.md`
- preserve upstream attribution in `NOTICE` where relevant
- avoid pulling in copyleft or source-available dependencies without explicit review

## Pull Request Guidance

Please keep pull requests focused and easy to review.

Helpful changes include:

- a short summary of what changed
- why the change is needed
- any tenant-isolation, security, or policy impact
- any license or provenance impact

## Security-Sensitive Changes

For changes involving:

- authentication or OAuth
- sandboxing
- secrets handling
- billing or wallet logic
- tenant isolation
- policy enforcement

please document the risk model and expected failure behavior.

## Code of Origin

Do not submit code copied from proprietary products, closed repositories, or incompatible open-source projects.

If a change is derived from an upstream open-source implementation, preserve attribution and verify compatibility before submission.

## Related Documents

- `LICENSE`
- `NOTICE`
- `COMMERCIAL_LICENSE.md`
- `COPYRIGHT.md`
- `AGPL_AUDIT.md`
- `SECURITY.md`
