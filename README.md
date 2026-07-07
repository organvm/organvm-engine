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
```

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
| `registry` | Load, query, validate, update registry-v2.json |
| `governance` | Rules enforcement, state machine, dependency graph, audit |
| `seed` | Discover, parse, and graph seed.yaml files |
| `metrics` | Compute and propagate system-wide metrics |
| `dispatch` | Cross-organ event routing and cascade planning |
| `contextmd` | Sync AI context files and discover exported conversation-corpus surfaces |

## Part of the Eight-Organ System

This repo belongs to **meta-organvm** (ORGAN VIII) and serves as the operational backbone for the entire system.
# Webhook test at Thu Feb 26 13:28:17 EST 2026
# Webhook test 2 at Thu Feb 26 13:28:55 EST 2026
