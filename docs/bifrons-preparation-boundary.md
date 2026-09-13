# BIFRONS preparation is not submission

`organvm portal prepare` and the inbound step of `organvm portal metabolize`
write a local draft PR body. A successful write advances the inbound exchange
only as far as `INTERNAL_PREPARED`, with proposal status `prepared`. It creates
no branch, commit, GitHub PR, approval, merge, or deployment. If the artifact
write fails, the existing exchange and proposal statuses remain unchanged.

`INTERNAL_PR_OPEN` is reserved for an actual, separately authorized remote PR
operation backed by repository identity, PR number/URL, observed state and
revision evidence. The preparation commands do not implement that remote
operation or revalidate existing PR records.

## Existing records

Earlier preparation code incorrectly assigned `INTERNAL_PR_OPEN` / `pr_open`
after only a Markdown write. This fix does not bulk-rewrite that history.
Re-preparation preserves later, outbound and legacy recorded states, and does
not treat them as freshly verified evidence. A historical open/merged claim
must be reconciled against its actual remote PR before a scheduler can count it
as a contribution or completed internal adoption. Keep the original record and
record the correction with evidence; do not infer a real PR from a local path.

The state machine and low-level store are not remote-evidence validators. This
repair closes the specific false transition made by local preparation; it does
not claim to add a full remote submission/observation adapter or migrate an
operator's live portal database.

## Verification

```bash
PYTHONPATH=src python -m pytest tests/test_portal_state_machine.py tests/test_portal_cli_epic6.py -q
```

The regression tests cover preparation status, absence of submission records,
repeatability, artifact-write failure, stale proposal rows, preservation of
later/outbound states, and the bounded metabolize state snapshot.
