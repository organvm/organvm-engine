# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Core Python package for the ORGANVM eight-organ system: registry, governance, seed discovery, metrics, dispatch, git superproject management, context file sync, session analysis, plan atomization, prompt narrative extraction, and the unified `organvm` CLI.

## Commands

```bash
# Install (use the workspace venv at meta-organvm/.venv)
pip install -e ".[dev]"

# Test
pytest tests/ -v                              # all tests
pytest tests/test_registry.py -v              # one module
pytest tests/test_registry.py::test_name -v   # one test

# Lint
ruff check src/

# Typecheck
pyright
```

## Architecture

### Foundation modules

Every other module imports from these; change them carefully.

- **`organ_config.py`** — Single source of truth for organ key/directory/registry-key/GitHub-org mappings. The `ORGANS` dict maps CLI short keys (`"I"`, `"META"`, `"LIMINAL"`) to metadata. All organ lookups across the codebase derive from helper functions here (`organ_dir_map`, `organ_aliases`, `registry_key_to_dir`, etc.).

- **`paths.py`** — Resolves canonical filesystem paths (`workspace_root`, `corpus_dir`, `registry_path`, `governance_rules_path`, `soak_dir`, `atoms_dir`). Reads `ORGANVM_WORKSPACE_DIR` and `ORGANVM_CORPUS_DIR` env vars, falls back to `~/Workspace` conventions.

- **`domain.py`** — Content-based identity for atomic units. `domain_fingerprint()` produces a SHA256[:16] digest from tags + file refs. `domain_set()` builds prefixed sets for Jaccard similarity comparison. Used by both `atoms/` and `prompts/` to link tasks and prompts by content DNA.

- **`project_slug.py`** — Canonical project slug derivation (`meta-organvm/organvm-engine` form). Converts filesystem paths, plan directory names, and raw slugs to a normalized slash-separated format. Shared across `prompts/`, `plans/`, and `session/`.

### Domain modules (23)

| Module | Role |
|--------|------|
| `registry/` | Load/save/query/validate/update `registry-v2.json` |
| `governance/` | Promotion state machine, dependency graph validation, audit, blast-radius impact |
| `seed/` | Discover `seed.yaml` files across workspace, read them, build produces/consumes graph |
| `metrics/` | Calculate system metrics, propagate into markdown/JSON, timeseries, variable resolution |
| `dispatch/` | Event payload validation, routing, cascade |
| `git/` | Superproject init/sync, submodule status/drift, workspace reproduction |
| `contextmd/` | Auto-generate CLAUDE.md/GEMINI.md/AGENTS.md across all repos from templates |
| `omega/` | 17-criterion binary scorecard for system maturity |
| `ci/` | CI health triage from soak-test data |
| `deadlines/` | Parse deadlines from `rolling-todo.md` |
| `pitchdeck/` | HTML pitch deck generation per repo |
| `session/` | Multi-agent session transcript parsing (Claude, Gemini, Codex), plan auditing, prompt analysis |
| `plans/` | Plan file atomization, indexing, hygiene checks, overlap detection, and per-organ synthesis |
| `prompts/` | Prompt extraction, classification, narrative threading, and clipboard history analysis |
| `atoms/` | Cross-system linking pipeline: Jaccard matching tasks↔prompts, git reconciliation, per-organ rollups |
| `coordination/` | Multi-agent claims registry (punch-in/out), tool checkout line for concurrent command traffic |
| `distill/` | Operational pattern taxonomy, SOP-to-pattern coverage analysis, scaffold generation |
| `ecosystem/` | Product business profiles, competitive matrix, gap analysis, action generation |
| `prompting/` | Agent-specific prompting guidelines and provider standards |
| `sop/` | SOP/METADOC discovery, inventory audit, tiered resolver (T4→T3→T2 cascade), and governed-code staleness checks |
| `irf/` | Parse, query, AND write back INST-INDEX-RERUM-FACIENDARUM.md — the universal work registry. IRFItem dataclass, priority/domain/status filtering, parse-completeness diagnostics, and tooled mutations (`irf add` / `irf complete` / `irf stats --write`, dry-run by default, hardlink-inode-preserving) |
| `fossil/` | Living Stratigraphy — archaeological reconstruction of system history. Excavates git commits, classifies by Jungian archetype (8 types), generates epoch chronicles, captures intentions, detects drift, real-time witness hooks, testament bridge |
| `cli/` | One module per command group (24 modules), wired together in `cli/__init__.py` |

### The atomization pipeline

The `atoms/`, `plans/`, and `prompts/` modules form a three-stage pipeline that can run independently or chained via `organvm atoms pipeline`:

1. **Atomize** (`plans/atomizer.py`) — Parse plan `.md` files into atomic tasks with tags, file refs, status, and project metadata. Discovers plans across `~/.claude/plans/`, `.gemini/plans/`, `.codex/plans/` in every workspace project.

2. **Narrate** (`prompts/narrator.py`) — Extract user prompts from session transcripts, classify them (`prompts/classifier.py`), assign domain fingerprints, and thread them into narrative episodes (`prompts/threading.py`).

3. **Link** (`atoms/linker.py`) — Jaccard-match atomized tasks against annotated prompts using `domain.py` domain sets. Produces `atom-links.jsonl`.

4. **Reconcile** (`atoms/reconciler.py`) — Cross-reference tasks against git commit history to detect completed work. Verdicts: `likely_completed`, `partially_done`, `stale`, `unknown`.

5. **Fanout** (`atoms/rollup.py`) — Aggregate centralized atom data into per-organ rollup JSON files in each organ superproject's `.atoms/` directory.

All pipeline outputs go to `corpus_dir/data/atoms/` with a `pipeline-manifest.json` tracking file hashes and counts.

### CLI dispatch pattern

`cli/__init__.py` builds an argparse tree with `build_parser()`. Commands with subcommands that are in the original tuple-dict (`registry`, `governance`, `seed`, `metrics`, etc.) dispatch via `{(command, subcommand): handler}`. Newer command groups (`session`, `plans`, `prompts`, `atoms`, `organism`, `irf`) use per-group inline dispatch dicts in explicit `if args.command == ...` branches. Top-level commands without subcommands (`status`, `deadlines`, `refresh`, `lint-vars`) dispatch via standalone `if` branches. Each CLI module exports `cmd_*` functions taking `argparse.Namespace` and returning `int`.

### Registry data safety

`registry/loader.py` → `save_registry()` refuses to write fewer than 50 repos to the production path. This prevents test fixtures from accidentally overwriting the real `registry-v2.json` (2,200+ lines).

### Test isolation

`tests/conftest.py` has an **autouse** fixture `_block_production_paths` that monkeypatches `paths._DEFAULT_WORKSPACE` and `loader._default_registry_path` to `/nonexistent/organvm-test-guard`. Every test runs in this sandbox — any test needing real file I/O must use `tmp_path` or `tests/fixtures/`. The `registry` fixture loads `fixtures/registry-minimal.json`.

## Key conventions

- **`src/` layout** — all imports are `from organvm_engine.X import Y`
- **No default exports** — CLI entry point is `organvm_engine.cli:main` (declared in `pyproject.toml`)
- **ruff config** — line-length 100, py311, rules: E/F/W/I/B/PTH/RET/SIM/COM/PL (see `pyproject.toml` for ignores)
- **pyright** — basic mode, py311
- **Commit prefixes** — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- **Dry-run by default** — destructive CLI commands (`context sync`, `omega update`, `plans tidy`, `atoms pipeline`) default to `--dry-run=True` and require `--write` to execute

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORGANVM_WORKSPACE_DIR` | `~/Workspace` | Workspace root for all organ directories |
| `ORGANVM_CORPUS_DIR` | `<workspace>/meta-organvm/organvm-corpvs-testamentvm` | Path to corpus repo (registry, governance rules) |

<!-- ORGANVM:AUTO:START -->
## System Context (auto-generated — do not edit)

**Organ:** META-ORGANVM (Meta) | **Tier:** flagship | **Status:** GRADUATED
**Org:** `meta-organvm` | **Repo:** `organvm-engine`

### Edges
- **Produces** → `ORGAN-IV, META-ORGANVM`: governance-policy
- **Produces** → `ORGAN-IV, META-ORGANVM`: registry
- **Produces** → `META-ORGANVM`: metrics
- **Produces** → `META-ORGANVM`: omega-scorecard
- **Produces** → `ORGAN-I, ORGAN-II, ORGAN-III, ORGAN-IV, ORGAN-V, ORGAN-VI, ORGAN-VII, META-ORGANVM`: context-files
- **Produces** → `META-ORGANVM`: session-analysis
- **Produces** → `META-ORGANVM`: plan-atoms
- **Produces** → `META-ORGANVM`: prompt-narratives
- **Produces** → `META-ORGANVM`: atom-links
- **Produces** → `META-ORGANVM`: testament-artifacts
- **Produces** → `META-ORGANVM`: ci-reports
- **Produces** → `META-ORGANVM`: pitch-decks
- **Produces** → `META-ORGANVM`: ecosystem-profiles
- **Produces** → `META-ORGANVM`: fossil-record
- **Produces** → `ALL`: witness-hooks
- **Consumes** ← `META-ORGANVM`: registry
- **Consumes** ← `META-ORGANVM`: schema
- **Consumes** ← `META-ORGANVM`: governance-rules
- **Consumes** ← `META-ORGANVM`: soak-data
- **Consumes** ← `META-ORGANVM`: seed-files
- **Consumes** ← `META-ORGANVM`: session-transcripts
- **Consumes** ← `META-ORGANVM`: plan-files

### Siblings in Meta
`.github`, `organvm-corpvs-testamentvm`, `alchemia-ingestvm`, `schema-definitions`, `system-dashboard`, `organvm-mcp-server`, `praxis-perpetua`, `stakeholder-portal`, `materia-collider`, `organvm-ontologia`, `vigiles-aeternae--agon-cosmogonicum`, `cvrsvs-honorvm`, `custodia-securitatis`

### Governance
- *Standard ORGANVM governance applies*

*Last synced: 2026-06-08T16:26:25Z*

## Active Handoff Protocol

If `.conductor/active-handoff.md` exists, **READ IT FIRST** before doing any work.
It contains constraints, locked files, conventions, and completed work from the
originating agent. You MUST honor all constraints listed there.

If the handoff says "CROSS-VERIFICATION REQUIRED", your self-assessment will
NOT be trusted. A different agent will verify your output against these constraints.

## Session Review Protocol

At the end of each session that produces or modifies files:
1. Run `organvm session review --latest` to get a session summary
2. Check for unimplemented plans: `organvm session plans --project .`
3. Export significant sessions: `organvm session export <id> --slug <slug>`
4. Run `organvm prompts distill --dry-run` to detect uncovered operational patterns

Transcripts are on-demand (never committed):
- `organvm session transcript <id>` — conversation summary
- `organvm session transcript <id> --unabridged` — full audit trail
- `organvm session prompts <id>` — human prompts only


## System Library

Plans: 269 indexed | Chains: 5 available | SOPs: 18 active
Discover: `organvm plans search <query>` | `organvm chains list` | `organvm sop lifecycle`
Library: `/Users/4jp/Code/organvm/praxis-perpetua/library`


## Active Directives

| Scope | Phase | Name | Description |
|-------|-------|------|-------------|
| repo | any | cli-module-pattern | cli-module-pattern |
| system | any | atomic-clock | The Atomic Clock |
| system | any | execution-sequence | Execution Sequence |
| system | any | multi-agent-dispatch | Multi-Agent Dispatch |
| system | any | session-handoff-avalanche | Session Handoff Avalanche |
| system | any | system-loops | System Loops |
| system | any | prompting-standards | Prompting Standards |
| system | any | prompting-standards | Prompting Standards |
| system | any | prompting-standards | Prompting Standards |
| system | any | background-task-resilience | background-task-resilience |
| system | any | context-window-conservation | context-window-conservation |
| system | any | session-self-critique | session-self-critique |
| system | any | the-descent-protocol | the-descent-protocol |
| system | any | the-membrane-protocol | the-membrane-protocol |
| system | any | theory-to-concrete-gate | theory-to-concrete-gate |
| system | any | triangulation-protocol | triangulation-protocol |

Linked skills: SOP-TRIADIC-REVIEW-PROTOCOL, cicd-resilience-and-recovery, continuous-learning-agent, evaluation-to-growth, genesis-dna, multi-agent-workforce-planner, promotion-and-state-transitions, quality-gate-baseline-calibration, repo-onboarding-and-habitat-creation, session-self-critique, structural-integrity-audit, the-membrane-protocol, triple-reference


**Prompting (Anthropic)**: context 200K tokens, format: XML tags, thinking: extended thinking (budget_tokens)


## Task Queue (from pipeline)

**249** pending tasks | Last pipeline: unknown

- `d50cf45b4bb3` Cross-Surface Prompt-Archaeology Sweep — hanging work from the past week's prompts (ALL agent surfaces) [aws, bash]
- `e5543c56458b` /Users/4jp/Code/organvm/organvm-engine/src/organvm_engine/cli/session.py — Add `cmd_session_digest(args)` function after [chezmoi, pytest, rollup]
- `439d2089820b` /Users/4jp/Code/organvm/organvm-engine/src/organvm_engine/cli/__init__.py — Register subparser (~line 1500): `sess_sub.a [chezmoi, pytest, rollup]
- `2d23ae5722a3` /Users/4jp/Code/organvm/organvm-engine/tests/test_session_digest.py — New test file. Fixtures: synthetic day with one su [chezmoi, pytest, rollup]
- `cd2642802178` organvm-engine/src/organvm_engine/contextmd/generator.py — Wrap 3 error returns in AUTO markers [bash, pytest, python]
- `447a3e18398d` organvm-engine/src/organvm_engine/contextmd/sync.py — Add error-line cleanup regex [bash, pytest, python]
- `4b7711e57972` concept — Named theoretical construct (AMMOI, SVSE, Formation Protocol, etc.) [node, pytest]
- `424e33f0a45e` spec — Formal specification (SPEC-000 through SPEC-023, named specs) [node, pytest]
- ... and 241 more

Cross-organ links: 1343 | Top tags: `python`, `chezmoi`, `mcp`, `bash`, `pytest`

Run: `organvm atoms pipeline --write && organvm atoms fanout --write`


## System Density (auto-generated)

AMMOI: 25% | Edges: 0 | Tensions: 0 | Clusters: 0 | Adv: 27 | Events(24h): 41370
Structure: 8 organs / 149 repos / 1654 components (depth 17) | Inference: 0% | Organs: META-ORGANVM:63%, ORGAN-I:53%, ORGAN-II:48%, ORGAN-III:55% +5 more
Last pulse: 2026-06-08T16:26:13 | Δ24h: 0.0% | Δ7d: vacuum


## Dialect Identity (Trivium)

**Dialect:** SELF_WITNESSING | **Classical Parallel:** The Eighth Art | **Translation Role:** The Witness — proves all translations compose without loss

Strongest translations: I (formal), IV (structural), V (analogical)

Scan: `organvm trivium scan META <OTHER>` | Matrix: `organvm trivium matrix` | Synthesize: `organvm trivium synthesize`


## Logos Documentation Layer

**Status:** ACTIVE | **Symmetry:** 1.0 (SYMMETRIC)

Nature demands a documentation counterpart. This formation maintains its narrative record in `docs/logos/`.

### The Tetradic Counterpart
- **[Telos (Idealized Form)](../docs/logos/telos.md)** — The dream and theoretical grounding.
- **[Pragma (Concrete State)](../docs/logos/pragma.md)** — The honest account of what exists.
- **[Praxis (Remediation Plan)](../docs/logos/praxis.md)** — The attack vectors for evolution.
- **[Receptio (Reception)](../docs/logos/receptio.md)** — The account of the constructed polis.

### Alchemical I/O
- **[Source & Transmutation](../docs/logos/alchemical-io.md)** — Narrative of inputs, process, and returns.

- **[Public Essay](https://organvm-v-logos.github.io/public-process/)** — System-wide narrative entry.

*Compliance: Nature and Counterpart are in balance.*

<!-- ORGANVM:AUTO:END -->
