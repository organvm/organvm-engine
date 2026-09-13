# Research evidence: integration and healing receipt

Program: #177. Verification: #181 / #182. False-evidence family: #183.
GitHub execution adapter: #189. Owning implementation: existing PR #176.
This is a source and observed-data integration tranche, not a release or operational completion.

## What changed

Completed tool workflows now require nonempty, successful step evidence. The v1
contract does not encode compensation/retry recovery, so a successful output cannot
implicitly erase a failed/denied attempt. Refusal and abstention remain separate.
Paired improvement eligibility compares observable check identity, dimension, weight,
required status and applicability; a shared claimed rubric hash cannot hide mismatches.
Equivalent check ordering is accepted. Digests still do not authenticate a producer.

Workflow snapshots now carry `enumeration_complete`, default false, separately from
analyzed-file coverage. `drift` validates identity, paths, counts, statuses and hashes.
Only explicitly complete relevant enumeration can support added/removed conclusions.
Old snapshots without the field are unknown, not silently complete. These are
pre-release contract corrections; no supported release is retagged or history rewritten.

`ci/runtime_evidence.py` is a bounded pure adapter for captured GitHub run/job pages.
Caller-pinned repository, commit, workflow, run, attempt and required step contracts
are checked independently of which rows happen to exist. Totals, duplicate identities,
ambiguous job/step names, wrong-head/mixed-attempt records and incomplete pagination
cannot become success. Outcomes separate missing evidence, pending work, nonexecution,
executed failure and executed pass. The adapter makes no network calls, creates no
status/check, launches no workflow, and never authorizes execution or release.

## Actual observations and their limits

The connected GitHub run 34762163480 and all three jobs were read. The committed
input is a **public-safe field projection transcribed from those actual responses**,
not a byte-for-byte raw-response archive. Its projection provenance identifies the
endpoints, observation time and source workflow blob. The adapter computed
`not_executed`: every required job had runner ID zero and no steps.
This is a real one-time read/normalization, not a synthetic successful CI run, a
continuous collector, authenticated replay protection, or two framework adapters.
The observed run belongs to parent head `9d891bb9718d517ce764618e08ce8e21589cbcde`;
it is not claimed as verification of the new source commit.

```sh
PYTHONPATH=src python -m organvm_engine.ci.runtime_evidence docs/research/evidence/github-ci-34762163480.input.json
```

Expected exit: **1**, decision `not_executed`. No rerun or merge is triggered.
JSON object order is immaterial; report arrays preserve the supplied requirement order.
The producer authentication and trusted check identity remain the existing collector/
Relay/governor responsibility, not a flag this adapter can establish for itself.

## Executed verification

In the isolated seven-source/test-file workspace, the batch executed at
2026-09-13T14:51:57Z on Python 3.13.5: **170 passed, zero failures/errors/skips**.
This comprises 114 prior tests, 20 healing/contract cases, and 36 adapter cases.
Three false-success probes reproduced before repair. At the original parent, 17
of the 20 new healing checks failed and three passed; those failures include new
interface expectations and are not 17 independently proven production defects.

`evidence/integration-2026-09-13.json` binds all seven source/test Git blob IDs and
SHA-256 hashes, commands, runtime, log and JUnit hashes. The published text log is
`evidence/integration-2026-09-13.txt`. All seven files also parsed with Python 3.11
grammar; that is not Python 3.11 runtime verification.

The isolated workspace did not contain the full Engine checkout/conftest or optional
dependencies. Ruff, Pyright, native Python 3.11/3.12, full Engine integration,
independent review, trusted scheduled ingestion and deployment remain unverified.
The original receipt remains historical; no old evidence was overwritten to manufacture
current-head approval. Use the repository-native admitted environment in #182 to finish.

## Repository-native reproduction and remaining gates

```sh
PYTHONPATH=src python -m pytest tests/test_agent_eval.py tests/test_workflow_intelligence.py tests/test_evidence_false_success.py tests/test_runtime_evidence.py -q
```

In a full checkout this command includes Engine's real fixtures; this narrower-session
receipt does not predict its outcome. Follow CONTRIBUTING and the actual CI contract
for Ruff, Pyright and the complete supported matrix. Do not treat `done.sh` as a
universal Engine predicate: its historical owning feature is the BIFRONS loop.

The question-led program #177–#200 retains the remaining operational integration,
private boundary, release, lifecycle, distributed-agent, source reconciliation,
onboarding and business decisions. Existing #172 owns canonical paths and #175 owns
reader/privacy integration. No competing path/privacy implementation, scheduler,
broker/task projection, social launch, release, deletion or protected-branch write
was added by this tranche. The strongest current verdict is **source repaired and
observed payload integrated; repository and operational acceptance still blocked**.
