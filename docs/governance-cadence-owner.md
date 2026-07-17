# Engine Governance Cadence Owner

Engine owns two bounded stages in Limen's nine-stage governance-memory cadence:

`distill`

: Compiles the exact native source envelopes, normalized events, reviewed
  lineage, assertion evidence, candidate testament, coverage, and ideal-form
  register into a non-ratified candidate testament and candidate receipt.

`render`

: Requires a CORPVS-ratified testament plus the reconciled self-image set and
  renders the public/private Iceberg Atlas with `strict=False`. Source,
  assertion, ideal-form, self-image, citation, timeline, or zoom debt remains
  typed in the Atlas receipt; it can never be converted into `ready` by the
  adapter.

Both commands consume direct predecessor and snapshot-anchor files. They do
not consume or manufacture a final governance snapshot bundle, so the cadence
remains acyclic. Source/provider names are data in those inputs; there is no
provider catalog or model fallback in Engine.

## Owner commands

Invoke the owner through its module entry point from the Engine worktree. The
runtime command must pass every direct file explicitly:

```bash
python -m organvm_engine.testament.governance_cadence distill \
  --source-envelopes "$SOURCE_ENVELOPES" \
  --normalized-events "$NORMALIZED_EVENTS" \
  --lineage-graph "$LINEAGE_GRAPH" \
  --assertion-evidence "$ASSERTION_EVIDENCE" \
  --coverage "$COVERAGE_RECEIPT" \
  --ideal-form-register "$IDEAL_FORM_REGISTER" \
  --governance-testament "$CANDIDATE_TESTAMENT" \
  --snapshot-digest "$LIMEN_GOV_SNAPSHOT_DIGEST" \
  --output-dir "$LIMEN_GOV_RUN_ROOT/distill"
```

```bash
python -m organvm_engine.testament.governance_cadence render \
  --source-envelopes "$SOURCE_ENVELOPES" \
  --normalized-events "$NORMALIZED_EVENTS" \
  --lineage-graph "$LINEAGE_GRAPH" \
  --assertion-evidence "$ASSERTION_EVIDENCE" \
  --coverage "$COVERAGE_RECEIPT" \
  --ideal-form-register "$IDEAL_FORM_REGISTER" \
  --governance-testament "$RATIFIED_TESTAMENT" \
  --node-self-image-set "$NODE_SELF_IMAGE_SET" \
  --snapshot-digest "$LIMEN_GOV_SNAPSHOT_DIGEST" \
  --output-dir "$LIMEN_GOV_RUN_ROOT/render"
```

Limen supplies `LIMEN_GOV_STAGE`, `LIMEN_GOV_STAGE_ATTEMPT`,
`LIMEN_GOV_TRAVERSAL`, `LIMEN_GOV_PROOF_MODE`,
`LIMEN_GOV_STAGE_METRICS_OUT`, `LIMEN_GOV_STAGE_RECEIPTS`,
`LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST`,
`LIMEN_GOV_PRIOR_STAGE_RECEIPT`, `LIMEN_GOV_MAX_ITEMS`,
`LIMEN_GOV_SNAPSHOT_ID`, and `LIMEN_GOV_SNAPSHOT_AT`. Missing, contradictory,
or unbounded values fail closed.

`LIMEN_GOV_MAX_ITEMS` limits the complete source/event/node/edge/assertion/
ideal/self-image denominator, not merely the number of output files. Owner
outputs are assembled in temporary custody and installed atomically only
after their internal predicate passes.

## Independent predicates

Configure a separately revision-pinned predicate command for each stage:

```bash
python -m organvm_engine.testament.governance_cadence_predicate distill \
  ...the same direct inputs and output directory...
```

```bash
python -m organvm_engine.testament.governance_cadence_predicate render \
  ...the same direct inputs and output directory...
```

The predicate process requires `LIMEN_GOV_PREDICATE_MODE=1`, reads only, and
does not import the mutating owner adapter. It independently verifies snapshot
bindings, exact file digests, candidate/ratification state, readiness
derivation, Atlas/cursor/receipt cohesion, timeline and six-zoom counts, and
the verified-event disposition.

On proof traversals the owner recompiles in temporary custody, compares every
governed byte, binds the exact prior child-receipt digest, reports
`skipped_completed`, emits zero durable events, and performs no governed output
write. Any changed direct input, prior receipt, output byte, or event
disposition fails the proof.
