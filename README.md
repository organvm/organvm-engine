# organvm-engine

Core governance, registry, and orchestration engine for the organvm eight-organ system. Consolidates ~30 standalone scripts into a proper installable Python package.

## Install

```bash
pip install -e .
```

## CLI

```bash
# Registry
organvm registry show recursive-engine--generative-entity
organvm registry list --organ ORGAN-I --tier flagship
organvm registry list --format json
organvm registry validate
organvm registry update <repo> <field> <value>

# Governance
organvm governance audit
organvm governance check-deps
organvm governance promote <repo> <target-state>

# Seed
organvm seed discover
organvm seed validate
organvm seed graph

# Metrics
organvm metrics calculate

# Dispatch
organvm dispatch validate payload.json

# Context
organvm context sync --dry-run
organvm context surfaces --workspace ~/Workspace --json

# Reader-mode documentation
organvm docs validate project-record.yml \
  --schema path/to/project-record-v1.schema.json \
  --actual-repository owner/repository
organvm docs audit . --format markdown
organvm docs audit --workspace ~/Workspace --format json --output docs-audit.json
```

The [2026-08-31 documentation estate audit](docs/audits/reader-mode-estate-audit.md)
shows how installation-scoped and search-scoped repository inventories are
normalized without publishing private repository identities.

## Library Usage

```python
from organvm_engine.registry import load_registry, find_repo, validate_registry
from organvm_engine.governance import validate_dependencies, run_audit
from organvm_engine.seed import discover_seeds, build_seed_graph
from organvm_engine.metrics import compute_metrics

registry = load_registry()
result = validate_registry(registry)
print(result.summary())
```

## Modules

| Module | Purpose |
|--------|---------|
| `registry` | Load, query, validate, update canonical `repo-registry.json` |
| `governance` | Rules enforcement, state machine, dependency graph, audit |
| `seed` | Discover, parse, and graph seed.yaml files |
| `metrics` | Compute and propagate system-wide metrics |
| `dispatch` | Cross-organ event routing and cascade planning |
| `contextmd` | Sync AI context files and discover exported conversation-corpus surfaces |
| `documentation` | Validate canonical project records and audit reader-mode documentation across seven dimensions |
| `mcp` | JSON-serializable tool wrappers exposing the 5 core CLIs to `organvm-mcp-server` |

## Repository authority and system role

The canonical GitHub authority is
[`organvm/organvm-engine`](https://github.com/organvm/organvm-engine). The engine
serves as a cross-organ operational backbone; its historical description as an
ORGAN VIII/meta-system component describes function, not current repository
ownership.
# Webhook test at Thu Feb 26 13:28:17 EST 2026
# Webhook test 2 at Thu Feb 26 13:28:55 EST 2026
