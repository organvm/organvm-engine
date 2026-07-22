# Changelog

## Unreleased

- ci: Add CodeQL security analysis workflow (content-path-scoped triggers plus a
  weekly baseline scan) — satisfies the GRADUATED-tier `codeql` requirement of
  the Descent Protocol infrastructure audit.
- ci: Add publish-on-tag release workflow that validates the tag against the
  pyproject version, builds distributions, and publishes a GitHub Release —
  complements the existing release-drafter draft automation.

## 0.1.0 (2026-02-17)

- Initial release: 5 modules (registry, governance, seed, metrics, dispatch)
- Unified CLI with `organvm` entry point
- Registry: load, save, query, validate, update
- Governance: state machine, dependency graph, full audit
- Seed: workspace discovery, YAML parsing, produces/consumes graph
- Metrics: calculator, propagator, timeseries from soak tests
- Dispatch: payload creation/validation, event routing, cascade planning
- 30+ tests with fixture data
