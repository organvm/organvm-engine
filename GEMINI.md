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

*Last synced: 2026-05-23T00:26:31Z*

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

Plans: 269 indexed | Chains: 5 available | SOPs: 8 active
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
| system | any | background-task-resilience | background-task-resilience |
| system | any | context-window-conservation | context-window-conservation |
| system | any | session-self-critique | session-self-critique |
| system | any | the-descent-protocol | the-descent-protocol |
| system | any | the-membrane-protocol | the-membrane-protocol |
| system | any | theory-to-concrete-gate | theory-to-concrete-gate |
| system | any | triangulation-protocol | triangulation-protocol |

Linked skills: SOP-TRIADIC-REVIEW-PROTOCOL, cicd-resilience-and-recovery, continuous-learning-agent, evaluation-to-growth, genesis-dna, multi-agent-workforce-planner, promotion-and-state-transitions, quality-gate-baseline-calibration, repo-onboarding-and-habitat-creation, session-self-critique, structural-integrity-audit, the-membrane-protocol, triple-reference


**Prompting (Google)**: context 1M tokens (Gemini 1.5 Pro), format: markdown, thinking: thinking mode (thinkingConfig)


## Task Queue (from pipeline)

**222** pending tasks | Last pipeline: unknown

- `e5543c56458b` /Users/4jp/Code/organvm/organvm-engine/src/organvm_engine/cli/session.py — Add `cmd_session_digest(args)` function after [chezmoi, pytest, rollup]
- `439d2089820b` /Users/4jp/Code/organvm/organvm-engine/src/organvm_engine/cli/__init__.py — Register subparser (~line 1500): `sess_sub.a [chezmoi, pytest, rollup]
- `2d23ae5722a3` /Users/4jp/Code/organvm/organvm-engine/tests/test_session_digest.py — New test file. Fixtures: synthetic day with one su [chezmoi, pytest, rollup]
- `cd2642802178` organvm-engine/src/organvm_engine/contextmd/generator.py — Wrap 3 error returns in AUTO markers [bash, pytest, python]
- `447a3e18398d` organvm-engine/src/organvm_engine/contextmd/sync.py — Add error-line cleanup regex [bash, pytest, python]
- `4b7711e57972` concept — Named theoretical construct (AMMOI, SVSE, Formation Protocol, etc.) [node, pytest]
- `424e33f0a45e` spec — Formal specification (SPEC-000 through SPEC-023, named specs) [node, pytest]
- `73273b8df7b8` transcript — Raw Q&A conversation (Layer 1) [node, pytest]
- ... and 214 more

Cross-organ links: 168 | Top tags: `mcp`, `python`, `rollup`, `chezmoi`, `bash`

Run: `organvm atoms pipeline --write && organvm atoms fanout --write`


## System Density (auto-generated)

AMMOI: 25% | Edges: 0 | Tensions: 0 | Clusters: 0 | Adv: 27 | Events(24h): 37975
Structure: 8 organs / 148 repos / 1654 components (depth 17) | Inference: 0% | Organs: META-ORGANVM:63%, ORGAN-I:53%, ORGAN-II:48%, ORGAN-III:54% +5 more
Last pulse: 2026-05-23T00:26:28 | Δ24h: n/a | Δ7d: n/a


## Dialect Identity (Trivium)

**Dialect:** SELF_WITNESSING | **Classical Parallel:** The Eighth Art | **Translation Role:** The Witness — proves all translations compose without loss

Strongest translations: I (formal), IV (structural), V (analogical)

Scan: `organvm trivium scan META <OTHER>` | Matrix: `organvm trivium matrix` | Synthesize: `organvm trivium synthesize`


## Logos Documentation Layer

**Status:** ACTIVE | **Symmetry:** 0.5 (DREAM)

Nature demands a documentation counterpart. This formation maintains its narrative record in `docs/logos/`.

### The Tetradic Counterpart
- **[Telos (Idealized Form)](../docs/logos/telos.md)** — The dream and theoretical grounding.
- **[Pragma (Concrete State)](../docs/logos/pragma.md)** — The honest account of what exists.
- **[Praxis (Remediation Plan)](../docs/logos/praxis.md)** — The attack vectors for evolution.
- **[Receptio (Reception)](../docs/logos/receptio.md)** — The account of the constructed polis.

### Alchemical I/O
- **[Source & Transmutation](../docs/logos/alchemical-io.md)** — Narrative of inputs, process, and returns.

- **[Public Essay](https://organvm-v-logos.github.io/public-process/)** — System-wide narrative entry.

*Compliance: Record exists without implementation.*

<!-- ORGANVM:AUTO:END -->







## ⚡ Conductor OS Integration
This repository is a managed component of the ORGANVM meta-workspace.
- **Orchestration:** Use `conductor patch` for system status and work queue.
- **Lifecycle:** Follow the `FRAME -> SHAPE -> BUILD -> PROVE` workflow.
- **Governance:** Promotions are managed via `conductor wip promote`.
- **Intelligence:** Conductor MCP tools are available for routing and mission synthesis.