# Technical dossier implementation — 2026-09-11

Record ID: ORGANVM-RESEARCH-20260911. Implementation date: 2026-09-13.
Owner: existing `organvm/organvm-engine` maintainers. Status: source implementation;
scoped verification only; independent review and hosted integration are outstanding.

## Synthesis

Intent, observed behavior, evaluation, and authorization are different artifacts.
Represent a workflow as a dependency-ordered sequence of recorded state transitions;
apply externally pinned, deterministic acceptance criteria; preserve unknowns and
abstention; propose source-bound repairs; let existing review and execution authorities
decide what may run. A passing report is not evidence that an action actually executed,
that an observer was authentic, or that a release was authorized.

This extends the existing Engine `ci` package, alongside `ci.audit` and `ci.triage`.
It creates no scheduler, registry, broker, hosted service, model dependency, or alternative
release gate. Limen/keeper/Relay remain the execution and trusted-evidence authorities.
Existing Engine #175 and #172 paths and integration obligations are unchanged.

## Research-to-implementation map

| ID | Source and verified scope | Engineering translation | Not established here |
| --- | --- | --- | --- |
| A1 | ABLE, arXiv:2609.05818, 2026-09-05; primary abstract/search evidence | Five distinct dimensions: tool choice, parameters, state, outcome, policy. Separate refused/abstained/error outcomes. | Protein-design implementation, benchmark reproduction, general model ranking, safe autonomous capability. |
| A2 | ARISE-RL, arXiv:2609.01058, 2026-09-01; primary abstract | Caller-pinned rubric, paired fixed-case gain gate, per-case/per-dimension no-regression rule, required-check veto, internally consistent score evidence. | RL training, automatic memory insertion, unbiased generated rubrics, independent held-out provenance or statistical significance. |
| A3 | AgentJudgeBench, arXiv:2608.26623, 2026-08-27; primary abstract/search evidence | Deterministic predicates are the only pass/fail oracle; no executable Python or model-judge operator in the contract. | Reproduced judge ceiling, semantic evaluation, with/without-ground-truth calibration experiment. |
| A4 | ECP, arXiv:2608.19263, 2026-08-18; primary abstract/search evidence, work in progress | Strict, independently versioned JSON trace/rubric contracts with evaluator-visible observations, source identities, digests and bounded CLI input. | ECP conformance, JSON-RPC server, production framework adapters, cross-framework interoperability. |
| B1 | Dark Software Factories v3.48, allegedly 2026-09-09 | Separate intent, implementation, verification receipt, source evidence, and authorization; recommendations never mutate. | Exact gist/version not independently located. User-supplied architectural inspiration, not an established research result or operating doctrine. |
| B2 | LLM-Driven CI-CD Workflow Intelligence, arXiv:2607.04579, 2026-07-06; primary abstract/search evidence | Bounded workflow normalization, eight finding classes, explicit retrieval coverage, source-bound repair proposals. | The authors' full taxonomy reproduced; all-estate collection; semantic YAML validity; production-safe generated patches. |
| B3 | Workflow evolution study, arXiv:2602.14572, submitted 2026-02-16, revised 2026-03-01; JSS 236, 112824 | Identity-bound timestamped snapshots; distinguish representation-only changes, declaration changes, missing retrieval, and removal from enumeration. | Historical estate mining or automatic inference of migration/emergency intent. |
| B4 | Modern code review roadmap, ACM DOI 10.1145/3800963, 2026-08-21; primary publication metadata, not a full-text read | Owner-aware proposal metadata, severity/criticality/downstream risk vector, observed review latency/rework/participation metrics; retained rationale and approval requirement. | Measured review quality, automatically discovered owners, real review telemetry ingestion, enacted review routing. |

### Corrections to the supplied dossier

ARISE-RL, AgentJudgeBench and ECP are outside the stated September 4–11 window.
They are useful context, not newly published items in that window. No material update
within that window was independently established. The workflow-evolution preprint is
also older; its current primary record supplies the March 1 revision and JSS reference.
The CI/CD study's 75,201 workflows and 59,906 stage-analysis configurations are distinct
reported denominators; 96.1% YAML-valid snippets is not 96.1% correct/safe remediation.
The exact Dark Software Factories v3.48 source remains unverified, not disproved.
All engineering choices below are our implementation decisions, not replicated results.

Primary references:

- https://arxiv.org/abs/2609.05818
- https://arxiv.org/abs/2609.01058
- https://arxiv.org/abs/2608.26623
- https://arxiv.org/abs/2608.19263
- https://arxiv.org/abs/2607.04579
- https://arxiv.org/abs/2602.14572
- https://dl.acm.org/doi/10.1145/3800963

## Implemented contracts

`src/organvm_engine/ci/agent_eval.py` contains version `organvm.agent-eval.v2`.
A trace includes case ID, stable repository ID, immutable revision, input/output and
ordered steps: tool, arguments, observation, before/after state, dependency IDs and
status. Hidden model reasoning is not part of the schema. A rubric is a bounded list
of JSON-pointer `exists`/type-sensitive `equals` checks with dimension, applicability,
positive finite weight and required status. Callers must obtain expected identity,
rubric digest and an artifact-scope manifest independently of the untrusted trace.
The trace records which artifacts were observed. A completed trace missing any
caller-requested artifact is `incomplete`; reports expose counts and digests, not
artifact names. Failed/unknown predecessors,
duplicate IDs, stale revisions and changed rubrics are rejected. A completed trace
needs applicable required coverage in all five dimensions. Refusal/abstention needs
policy coverage and stays separate from capability scores.

Reports omit raw prompts, arguments, observations and output. IDs, paths, digests and
case metadata can still be sensitive; the existing reader-mode/privacy gate remains
mandatory before exporting real reports. Digests are local JSON content identities,
not signatures, RFC 8785 interoperability claims, or authenticated execution receipts.
Recorded observations can be dishonest. These checks test consistency of supplied
records, not authenticity or real-world truth.

`promotion_gate` recomputes report score consistency, requires exact paired case
coverage and a common caller-pinned rubric, blocks any candidate required-check failure
or any per-case dimension regression, and requires a positive minimum mean gain.
Its strongest result is `eligible_for_review`; learning and release authorization
remain false. Freeze the held-out manifest outside the generating agent. This gate
does not establish statistical significance, remove selection bias, validate training
provenance, or authorize distillation. Rubric changes require a new separately reviewed
experiment, not reuse of the old comparison.

`src/organvm_engine/ci/workflow_intelligence.py` contains version
`organvm.workflow-intelligence.v1`. It consumes source files supplied by the existing
collector together with an independently enumerated, revision-pinned expected path set.
It does not fetch repositories or run workflow scripts. A copied YAML resolver preserves
GitHub's `on` key without changing process-global PyYAML behavior. Duplicate/non-string
keys, unsupported aliases and bounded-depth/size violations are rejected. This is a
selected static analyzer, not the complete Actions grammar or a security certification.

Finding classes: missing effective permission declarations, write-all permissions,
mutable action references, missing explicit job timeouts, tolerated failures, selected
untrusted event expressions interpolated directly into shell, privileged head checkout,
and unresolved reusable workflows. An immutable reusable reference is not transitive
coverage. Action pin resolution and proposed YAML changes require independent review.
`coverage=complete` means only all declared input files were analyzed; it does not mean
no findings, complete repository enumeration, passing CI, or a safe release.

Snapshots retain repository ID, revision, observation time, byte and normalized hashes,
per-file analysis state and retrieval coverage. `drift` compares snapshots without
mistaking unavailable files for deletion or comments for changed declarations.
`proposals` binds advice to source/revision, records unresolved ownership, and exposes
a risk vector instead of an invented precision score. No mutation is performed.
`review_metrics` separates pending age from observed first-review latency, reports
rework/participation and explicitly refuses a review-quality inference.

## Running the implementation

From an existing admitted Engine environment with its declared dependencies installed:

```sh
PYTHONPATH=src python -m pytest tests/test_agent_eval.py tests/test_workflow_intelligence.py -q
python -m organvm_engine.ci.agent_eval trace.json rubric.json --repository-id 1160447354 --revision FULL_SHA --rubric-digest FROZEN_RUBRIC_SHA256 --scope-manifest scope.json --scope-digest FROZEN_SCOPE_SHA256
python -m organvm_engine.ci.workflow_intelligence inventory-input.json
```

Use `TRACE_SCHEMA` and `RUBRIC_SCHEMA` from `agent_eval` for adapters. Synthetic,
executable trace/rubric examples are in `tests/test_agent_eval.py:fixture_pair`.
The workflow input object has `repository_id`, `revision`, `files` (path-to-text map),
`expected_paths`, and timezone-bearing `observed_at`. Keep private input files in
restricted custody rather than publishing them with reports.

Agent CLI exit 0 includes policy-valid refusal/abstention: never treat that process
status as task completion or merge authority. Workflow CLI exit 0 indicates input
analysis coverage, not an empty finding set. Invalid input exits 2; incomplete evidence
or task failure exits 1 as documented in the module. Module CLIs are additive; the
existing top-level `organvm` parser is not changed in this tranche.

## Observed source example

`evidence/engine-ci-sample.json` diagnoses ONE selected public workflow, not the estate.
Source: Engine main `0efc9cf5a9998b179dabe9ef815d59a48a50889d`, `.github/workflows/ci.yml`.
The copied 1,432 bytes reproduce Git blob `259cf89ad7b296c1159365e9578769127e9383b8`.
The analyzer reports two mutable action references and two missing explicit job timeouts.
The four proposal records remain unapproved; source workflow settings are unchanged.
The example intentionally leaves owner resolution unresolved rather than fabricating it.

## Verification boundary and retained work

See `evidence/verification-2026-09-13.json` for source hashes, exact commands, local
runtime and scope. The scoped synthetic tests exercise both valid controls and failing
counterexamples. The initial isolated-workspace limitation was superseded by exact-head
verification in a complete Engine checkout on Python 3.12.14: the scoped suite passed,
Ruff was clean, and Pyright reported zero errors. Independent exact-head review and
required hosted integration remain outstanding. No model inference, training,
deployment, broker reservation, estate policy mutation or release was performed.

| Obligation | Owning surface | Acceptance before claiming completion |
| --- | --- | --- |
| D-01 Repository integration | This Engine PR | Repo-native Ruff/Pyright and full scoped resolver in the admitted environment; independent exact-head review; required hosted checks actually execute. |
| D-02 Authenticated traces | Existing Engine/Relay/Limen adapter owners | Export producer-authenticated observations, policy decisions and revision identity; reject forged/replayed evidence; keep private values in existing custody. No new token or authority service. |
| D-03 Framework comparison | Engine evaluation consumer | Two real adapters, identical frozen cases/rubric, retained traces and failure strata. No ECP conformance claim until tested. |
| D-04 Reward-gated experiment | Existing model/agent experiment owner | Independently held-out manifest, evaluator/generator separation, baseline/candidate runs, uncertainty analysis and explicit training/memory approval. |
| D-05 Estate diagnosis | Existing census/registry/CI-audit owners | Enumerate all authorized installation pages by stable ID, pin workflow source revisions, preserve denied/partial coverage; ingest through `inventory`, preserve restricted evidence. |
| D-06 Review/remediation | Existing governance/review owners | Resolve canonical ownership/criticality/blast radius, ingest real review records, review immutable action pins and finite timeout choices, publish narrow source-bound remediation PRs only after approval. |
| D-07 Historical monitoring | Existing CI-audit schedule owner | Retain successive complete/partial snapshots with source identity and timestamps; use `drift`; reuse the existing schedule, not a second watcher. |
| D-08 Release provenance | Existing trusted check/release owner | Bind independently verified actual check-run identity, executed steps, reviewer decision, merged revision and deployed receipt. No self-reported evaluator flag can replace these gates. |
| D-09 Source verification | This research record | Locate the exact Dark Software Factories gist revision before promoting its date/version/content to verified evidence. |

These are retained obligations, not completed activation. Their owner surfaces remain
the existing systems. This document is not a broker task-state projection and does not
claim a lease, schedule, release approval or gate result on behalf of another worker.
