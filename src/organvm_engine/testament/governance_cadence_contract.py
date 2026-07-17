"""Pure contracts shared by the Engine governance cadence owner and predicate.

This module only reads and validates direct owner artifacts.  It does not run
the candidate compiler, render the Atlas, write governed outputs, or emit
cadence metrics.  Keeping mutation in the owner command lets the independently
revision-pinned predicate reuse the wire contract without importing the
mutating adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from organvm_engine.corpus.governance_lineage import (
    READINESS_DEBT_FIELDS,
    SCHEMA_ASSERTION_EVIDENCE,
    SCHEMA_COVERAGE,
    SCHEMA_IDEAL_FORM_REGISTER,
    SCHEMA_LINEAGE,
    SCHEMA_NORMALIZED_EVENT,
    SCHEMA_SELF_IMAGE_SET,
    SCHEMA_SNAPSHOT_BUNDLE,
    SCHEMA_SOURCE_ENVELOPE,
    SCHEMA_TESTAMENT,
    ZOOM_LEVELS,
    content_digest,
    schema_id,
    validate_bundle_headers,
)
from organvm_engine.ledger.chain import verify_chain

OWNER_REFERENCE = "repo:organvm-iv-taxis/organvm-engine"
DISTILL_CONTRACT = "engine-governance-distill.v1"
RENDER_CONTRACT = "engine-governance-render.v1"
PROJECTION_DIGEST_ALGORITHM = "sha256-rfc8785-excluding-projection-digest-v1"
SNAPSHOT_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PUBLIC_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,255}$")

DISTILL_OUTPUT_NAMES = (
    "governance-testament.candidate.json",
    "candidate-testament-receipt.json",
)
RENDER_OUTPUT_NAMES = (
    "iceberg-atlas.public.json",
    "iceberg-atlas.private.json",
    "governance-atlas-receipt.json",
    "governance-atlas-cursor.v1.json",
    "governance-atlas-events.jsonl",
)
DISTILL_PROJECTION_NAME = "engine-governance-distill.v1.json"
RENDER_PROJECTION_NAME = "engine-governance-render.v1.json"


class EngineCadenceError(RuntimeError):
    """One Engine-owned cadence artifact or runtime binding is invalid."""


@dataclass(frozen=True)
class CadenceRuntime:
    """Fail-closed subset of the Limen owner runtime."""

    stage: str
    attempt: int
    traversal: int
    proof_mode: bool
    metrics_path: Path
    prior_stage_receipt: Path | None
    stage_receipts_path: Path
    predecessor_receipt_digest: str
    max_items: int
    snapshot_id: str
    snapshot_at: str


@dataclass(frozen=True)
class DirectArtifactPaths:
    """Direct predecessor and snapshot-anchor artifacts consumed by Engine."""

    source_envelopes: Path
    normalized_events: Path
    lineage_graph: Path
    assertion_evidence: Path
    coverage: Path
    ideal_form_register: Path
    governance_testament: Path
    node_self_image_set: Path | None = None

    def observations(self) -> list[dict[str, Any]]:
        values: tuple[tuple[str, Path | None], ...] = (
            ("source_envelopes", self.source_envelopes),
            ("normalized_events", self.normalized_events),
            ("lineage_graph", self.lineage_graph),
            ("assertion_evidence", self.assertion_evidence),
            ("coverage", self.coverage),
            ("ideal_form_register", self.ideal_form_register),
            ("governance_testament", self.governance_testament),
            ("node_self_image_set", self.node_self_image_set),
        )
        observations = []
        for artifact_id, path in values:
            if path is None:
                continue
            digest, size = digest_file(path)
            observations.append(
                {
                    "artifact_id": artifact_id,
                    "digest": digest,
                    "size_bytes": size,
                },
            )
        return observations


def digest_file(path: Path) -> tuple[str, int]:
    """Return an explicit SHA-256 digest and byte count for one exact file."""
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise EngineCadenceError(f"cannot hash direct artifact {path.name}") from exc
    return f"sha256:{digest.hexdigest()}", size


def canonical_document(value: Any) -> bytes:
    """Return deterministic human-readable owner bytes."""
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineCadenceError(f"{path.name} must contain a valid JSON object") from exc
    if not isinstance(value, dict):
        raise EngineCadenceError(f"{path.name} must contain a JSON object")
    return value


def load_rows(
    path: Path,
    *,
    wrapper_fields: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Load JSONL, a JSON array/object, or one explicitly wrapped array."""
    rows: Any
    if path.suffix.lower() == ".jsonl":
        rows = []
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise EngineCadenceError(
                            f"{path.name}:{line_number} contains malformed JSONL",
                        ) from exc
                    rows.append(row)
        except (OSError, UnicodeDecodeError) as exc:
            raise EngineCadenceError(f"cannot read direct artifact {path.name}") from exc
    else:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EngineCadenceError(f"{path.name} contains malformed JSON") from exc
        if isinstance(rows, Mapping):
            matched = [rows[field] for field in wrapper_fields if field in rows]
            if len(matched) > 1:
                raise EngineCadenceError(
                    f"{path.name} contains multiple recognized wrapper fields",
                )
            rows = matched[0] if matched else [dict(rows)]
    if not isinstance(rows, list) or not rows:
        raise EngineCadenceError(f"{path.name} must contain a nonempty record set")
    if not all(isinstance(row, dict) for row in rows):
        raise EngineCadenceError(f"{path.name} records must all be objects")
    return [dict(row) for row in rows]


def validate_snapshot_digest(value: str) -> str:
    if not SNAPSHOT_DIGEST_PATTERN.fullmatch(value):
        raise EngineCadenceError("snapshot digest must be sha256:<64 lowercase hex>")
    return value


def validate_owner_reference(value: str) -> str:
    if not PUBLIC_REFERENCE_PATTERN.fullmatch(value):
        raise EngineCadenceError("owner reference must be a bounded public-safe identifier")
    return value


def _positive_integer(value: str | None, field: str) -> int:
    try:
        parsed = int(value or "")
    except ValueError as exc:
        raise EngineCadenceError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise EngineCadenceError(f"{field} must be a positive integer")
    return parsed


def cadence_runtime(stage: str, *, predicate: bool = False) -> CadenceRuntime:
    """Read every Limen cadence owner binding needed by this adapter."""
    observed_stage = os.environ.get("LIMEN_GOV_STAGE", "")
    if observed_stage != stage:
        raise EngineCadenceError(
            f"LIMEN_GOV_STAGE must be {stage!r}, got {observed_stage!r}",
        )
    if predicate and os.environ.get("LIMEN_GOV_PREDICATE_MODE") != "1":
        raise EngineCadenceError("predicate command requires LIMEN_GOV_PREDICATE_MODE=1")
    snapshot_id = os.environ.get("LIMEN_GOV_SNAPSHOT_ID", "").strip()
    snapshot_at = os.environ.get("LIMEN_GOV_SNAPSHOT_AT", "").strip()
    metrics = os.environ.get("LIMEN_GOV_STAGE_METRICS_OUT", "").strip()
    stage_receipts = os.environ.get("LIMEN_GOV_STAGE_RECEIPTS", "").strip()
    predecessor = os.environ.get("LIMEN_GOV_PREDECESSOR_RECEIPT_DIGEST", "").strip()
    if not snapshot_id or not snapshot_at or not metrics or not stage_receipts:
        raise EngineCadenceError("cadence snapshot, metrics, and receipt bindings are incomplete")
    validate_snapshot_digest(predecessor)
    attempt = _positive_integer(os.environ.get("LIMEN_GOV_STAGE_ATTEMPT"), "stage attempt")
    traversal = _positive_integer(os.environ.get("LIMEN_GOV_TRAVERSAL"), "traversal")
    max_items = _positive_integer(os.environ.get("LIMEN_GOV_MAX_ITEMS"), "max items")
    proof_mode = os.environ.get("LIMEN_GOV_PROOF_MODE") == "1"
    if proof_mode != (traversal >= 2):
        raise EngineCadenceError("proof mode must agree with the cadence traversal")
    prior_value = os.environ.get("LIMEN_GOV_PRIOR_STAGE_RECEIPT", "").strip()
    if proof_mode and not prior_value:
        raise EngineCadenceError("proof traversal requires a prior stage receipt")
    if not proof_mode and prior_value:
        raise EngineCadenceError("non-proof traversal cannot bind a prior stage receipt")
    return CadenceRuntime(
        stage=stage,
        attempt=attempt,
        traversal=traversal,
        proof_mode=proof_mode,
        metrics_path=Path(metrics),
        prior_stage_receipt=Path(prior_value) if prior_value else None,
        stage_receipts_path=Path(stage_receipts),
        predecessor_receipt_digest=predecessor,
        max_items=max_items,
        snapshot_id=snapshot_id,
        snapshot_at=snapshot_at,
    )


def _require_contract(
    document: Mapping[str, Any],
    contract_name: str,
    *,
    label: str,
) -> None:
    if schema_id(document) != contract_name or document.get("contract_version") != 1:
        raise EngineCadenceError(f"{label} must use {contract_name} contract version 1")


def _validate_core_snapshot(
    bundle: Mapping[str, Any],
    *,
    require_ratified: bool,
) -> None:
    snapshot_id = bundle["snapshot_id"]
    snapshot_digest = bundle["snapshot_digest"]
    lineage = bundle["lineage_graph"]
    coverage = bundle["coverage"]
    ideal = bundle["ideal_form_register"]
    testament = bundle["governance_testament"]
    _require_contract(lineage, SCHEMA_LINEAGE, label="lineage graph")
    _require_contract(coverage, SCHEMA_COVERAGE, label="coverage")
    _require_contract(ideal, SCHEMA_IDEAL_FORM_REGISTER, label="ideal-form register")
    _require_contract(testament, SCHEMA_TESTAMENT, label="governance testament")
    if lineage.get("frozen_snapshot_id") != snapshot_id:
        raise EngineCadenceError("lineage graph does not bind the cadence snapshot")
    if coverage.get("snapshot_id") != snapshot_id:
        raise EngineCadenceError("coverage does not bind the cadence snapshot")
    if ideal.get("snapshot_id") != snapshot_id or ideal.get("snapshot_digest") != snapshot_digest:
        raise EngineCadenceError("ideal-form register does not bind the cadence snapshot")
    if not isinstance(lineage.get("nodes"), list) or not lineage["nodes"]:
        raise EngineCadenceError("lineage graph nodes must be nonempty")
    if not isinstance(ideal.get("ideal_forms"), list) or not ideal["ideal_forms"]:
        raise EngineCadenceError("ideal-form register must be nonempty")
    if require_ratified and testament.get("status") != "ratified":
        raise EngineCadenceError("render requires a CORPVS-ratified testament")

    sources = bundle["source_envelopes"]
    events = bundle["normalized_events"]
    assertions = bundle["assertion_evidence"]
    for source in sources:
        _require_contract(source, SCHEMA_SOURCE_ENVELOPE, label="source envelope")
        custody = source.get("custody_snapshot")
        if not isinstance(custody, Mapping) or custody.get("snapshot_id") != snapshot_id:
            raise EngineCadenceError("source envelope does not bind the cadence snapshot")
    for event in events:
        _require_contract(event, SCHEMA_NORMALIZED_EVENT, label="normalized event")
        if event.get("snapshot_id") != snapshot_id or event.get("snapshot_digest") != snapshot_digest:
            raise EngineCadenceError("normalized event does not bind the cadence snapshot")
    for assertion in assertions:
        _require_contract(assertion, SCHEMA_ASSERTION_EVIDENCE, label="assertion evidence")


def load_direct_bundle(
    paths: DirectArtifactPaths,
    *,
    snapshot_id: str,
    snapshot_at: str,
    snapshot_digest: str,
    require_ratified: bool,
) -> dict[str, Any]:
    """Assemble one in-memory compiler bundle from direct acyclic artifacts."""
    snapshot_digest = validate_snapshot_digest(snapshot_digest)
    bundle: dict[str, Any] = {
        "contract_name": SCHEMA_SNAPSHOT_BUNDLE,
        "contract_version": 1,
        "snapshot_id": snapshot_id,
        "snapshot_at": snapshot_at,
        "snapshot_digest": snapshot_digest,
        "source_envelopes": load_rows(
            paths.source_envelopes,
            wrapper_fields=("source_envelopes",),
        ),
        "normalized_events": load_rows(
            paths.normalized_events,
            wrapper_fields=("normalized_events", "events"),
        ),
        "lineage_graph": load_object(paths.lineage_graph),
        "assertion_evidence": load_rows(
            paths.assertion_evidence,
            wrapper_fields=("assertion_evidence", "assertions"),
        ),
        "coverage": load_object(paths.coverage),
        "ideal_form_register": load_object(paths.ideal_form_register),
        "governance_testament": load_object(paths.governance_testament),
    }
    if paths.node_self_image_set is not None:
        bundle["node_self_image_set"] = load_object(paths.node_self_image_set)
    _validate_core_snapshot(bundle, require_ratified=require_ratified)
    if require_ratified:
        if paths.node_self_image_set is None:
            raise EngineCadenceError("render requires a direct node self-image set")
        assertion_reference = str(
            bundle["governance_testament"]["ratification"][
                "assertion_evidence_reference"
            ],
        )
        assertion_ids = {
            str(assertion["assertion_id"])
            for assertion in bundle["assertion_evidence"]
        }
        assertion_path = paths.assertion_evidence.as_posix()
        if (
            assertion_reference not in assertion_ids
            and not assertion_path.endswith(assertion_reference)
        ):
            raise EngineCadenceError(
                "ratification assertion reference does not resolve to the direct artifact",
            )
        _require_contract(
            bundle["node_self_image_set"],
            SCHEMA_SELF_IMAGE_SET,
            label="node self-image set",
        )
        try:
            validate_bundle_headers(bundle)
        except ValueError as exc:
            raise EngineCadenceError(f"render bundle is invalid: {exc}") from exc
    return bundle


def bounded_unit_count(bundle: Mapping[str, Any], *, render: bool) -> int:
    lineage = bundle["lineage_graph"]
    count = sum(
        len(value)
        for value in (
            bundle["source_envelopes"],
            bundle["normalized_events"],
            lineage["nodes"],
            lineage.get("edges", []),
            bundle["assertion_evidence"],
            bundle["ideal_form_register"]["ideal_forms"],
        )
    )
    count += 1
    if render:
        count += len(bundle["node_self_image_set"]["self_images"])
    return count


def direct_input_digest(
    paths: DirectArtifactPaths,
    runtime: CadenceRuntime,
    *,
    snapshot_digest: str,
    owner_reference: str,
) -> str:
    """Bind content, predecessor receipt, snapshot, and owner without paths."""
    return content_digest(
        {
            "stage": runtime.stage,
            "snapshot_id": runtime.snapshot_id,
            "snapshot_at": runtime.snapshot_at,
            "snapshot_digest": validate_snapshot_digest(snapshot_digest),
            "predecessor_receipt_digest": runtime.predecessor_receipt_digest,
            "owner_reference": validate_owner_reference(owner_reference),
            "inputs": paths.observations(),
        },
    )


def _debt_list(document: Mapping[str, Any], field: str, *, label: str) -> list[str]:
    value = document.get(field, [])
    if (
        not isinstance(value, list)
        or len(value) != len(set(value))
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise EngineCadenceError(f"{label} {field} must be a unique string list")
    return sorted(value)


def standard_readiness(document: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    exact_all = document.get("exact_all")
    ready = document.get("ready")
    if not isinstance(exact_all, bool) or not isinstance(ready, bool):
        raise EngineCadenceError(f"{label} exact_all and ready must be booleans")
    result: dict[str, Any] = {"exact_all": exact_all}
    for field in READINESS_DEBT_FIELDS:
        result[field] = _debt_list(document, field, label=label)
    computed = exact_all and not any(result[field] for field in READINESS_DEBT_FIELDS)
    if ready is not computed:
        raise EngineCadenceError(f"{label} ready contradicts exact_all and declared debt")
    status = document.get("status")
    valid_statuses = {"ready", "blocked", "incomplete", "closed_with_owner_routed_debt"}
    if status is not None and (
        status not in valid_statuses
        or (ready and status != "ready")
        or (not ready and status == "ready")
    ):
        raise EngineCadenceError(f"{label} status contradicts readiness")
    result["ready"] = ready
    result["status"] = (
        str(status)
        if status is not None
        else "ready"
        if ready
        else "blocked"
        if exact_all
        else "incomplete"
    )
    return result


def distill_readiness(
    bundle: Mapping[str, Any],
    candidate_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    coverage = standard_readiness(bundle["coverage"], label="coverage readiness")
    ideal_value = bundle["ideal_form_register"].get("readiness")
    if not isinstance(ideal_value, Mapping):
        raise EngineCadenceError("ideal-form register readiness is missing")
    ideal = standard_readiness(ideal_value, label="ideal-form readiness")
    exact_all = coverage["exact_all"] and ideal["exact_all"]
    result: dict[str, Any] = {"exact_all": exact_all}
    for field in READINESS_DEBT_FIELDS:
        result[field] = sorted(set(coverage[field]) | set(ideal[field]))
    if candidate_receipt.get("ready_for_owner_ratification") is not True:
        result["missing_requirements"] = sorted(
            {*result["missing_requirements"], "candidate-testament-ratification-readiness"},
        )
    result["ready"] = exact_all and not any(
        result[field] for field in READINESS_DEBT_FIELDS
    )
    result["status"] = (
        "ready"
        if result["ready"]
        else "closed_with_owner_routed_debt"
        if exact_all
        else "incomplete"
    )
    return result


def artifact_descriptors(root: Path, names: Sequence[str]) -> list[dict[str, Any]]:
    observations = []
    for name in names:
        digest, size = digest_file(root / name)
        observations.append(
            {
                "artifact_id": name,
                "reference": name,
                "digest": digest,
                "size_bytes": size,
            },
        )
    return observations


def build_projection(
    *,
    contract_name: str,
    stage: str,
    runtime: CadenceRuntime,
    snapshot_digest: str,
    owner_reference: str,
    input_digest: str,
    artifacts: Sequence[Mapping[str, Any]],
    readiness: Mapping[str, Any],
    bounded_units: int,
) -> dict[str, Any]:
    body = {
        "contract_name": contract_name,
        "contract_version": 1,
        "stage": stage,
        "snapshot_id": runtime.snapshot_id,
        "snapshot_at": runtime.snapshot_at,
        "snapshot_digest": validate_snapshot_digest(snapshot_digest),
        "owner_reference": validate_owner_reference(owner_reference),
        "predecessor_receipt_digest": runtime.predecessor_receipt_digest,
        "input_digest": input_digest,
        "bounded_units": bounded_units,
        "artifacts": [dict(value) for value in artifacts],
        "readiness": dict(readiness),
        "digest_algorithm": PROJECTION_DIGEST_ALGORITHM,
    }
    return {**body, "projection_digest": content_digest(body)}


def validate_projection(
    projection: Mapping[str, Any],
    *,
    contract_name: str,
    stage: str,
    runtime: CadenceRuntime,
    snapshot_digest: str,
    owner_reference: str,
    input_digest: str,
    artifacts: Sequence[Mapping[str, Any]],
    bounded_units: int,
) -> dict[str, Any]:
    body = {key: deepcopy(value) for key, value in projection.items() if key != "projection_digest"}
    if (
        projection.get("contract_name") != contract_name
        or projection.get("contract_version") != 1
        or projection.get("stage") != stage
        or projection.get("snapshot_id") != runtime.snapshot_id
        or projection.get("snapshot_at") != runtime.snapshot_at
        or projection.get("snapshot_digest") != snapshot_digest
        or projection.get("owner_reference") != owner_reference
        or projection.get("predecessor_receipt_digest")
        != runtime.predecessor_receipt_digest
        or projection.get("input_digest") != input_digest
        or projection.get("bounded_units") != bounded_units
        or projection.get("artifacts") != list(artifacts)
        or projection.get("digest_algorithm") != PROJECTION_DIGEST_ALGORITHM
        or projection.get("projection_digest") != content_digest(body)
    ):
        raise EngineCadenceError(f"{stage} projection does not match direct owner artifacts")
    readiness_value = projection.get("readiness")
    if not isinstance(readiness_value, Mapping):
        raise EngineCadenceError(f"{stage} projection readiness is missing")
    return standard_readiness(readiness_value, label=f"{stage} projection readiness")


def validate_candidate_outputs(
    *,
    bundle: Mapping[str, Any],
    output_dir: Path,
    projection_path: Path,
    paths: DirectArtifactPaths,
    runtime: CadenceRuntime,
    snapshot_digest: str,
    owner_reference: str,
) -> dict[str, Any]:
    """Independently verify the candidate compiler's complete public result."""
    candidate = load_object(output_dir / DISTILL_OUTPUT_NAMES[0])
    receipt = load_object(output_dir / DISTILL_OUTPUT_NAMES[1])
    expected_candidate = deepcopy(bundle["governance_testament"])
    expected_candidate["status"] = "candidate"
    expected_candidate.pop("ratification", None)
    if candidate != expected_candidate:
        raise EngineCadenceError("candidate testament is not the exact non-ratified projection")
    if (
        receipt.get("contract_name") != "candidate-testament-receipt.v1"
        or receipt.get("contract_version") != 1
        or receipt.get("snapshot_id") != runtime.snapshot_id
        or receipt.get("snapshot_at") != runtime.snapshot_at
        or receipt.get("snapshot_digest") != snapshot_digest
        or receipt.get("input_digest") != content_digest(bundle)
        or receipt.get("candidate_digest") != content_digest(candidate)
        or receipt.get("ready_for_owner_ratification") is not True
    ):
        raise EngineCadenceError("candidate testament receipt is inconsistent")
    counts = receipt.get("counts")
    compiler_units = (
        len(bundle["lineage_graph"]["nodes"])
        + len(bundle["lineage_graph"].get("edges", []))
        + len(bundle["source_envelopes"])
        + len(bundle["normalized_events"])
        + len(bundle["assertion_evidence"])
    )
    if not isinstance(counts, Mapping) or (
        counts.get("bounded_units") != compiler_units
        or counts.get("normalized_events") != len(bundle["normalized_events"])
        or counts.get("source_envelopes") != len(bundle["source_envelopes"])
        or counts.get("candidate_assertions") != len(bundle["assertion_evidence"])
    ):
        raise EngineCadenceError("candidate testament receipt counts are inconsistent")
    sources = {
        str(source["source_id"]): source for source in bundle["source_envelopes"]
    }
    events = {}
    for event in bundle["normalized_events"]:
        source_reference = str(event["source_envelope_reference"]).rsplit("#", 1)[-1]
        source_reference = source_reference.removeprefix("source-envelope:")
        events[source_reference] = event
    assertions = {
        str(assertion["assertion_id"]) for assertion in bundle["assertion_evidence"]
    }
    node_ids = {
        str(node["node_id"]) for node in bundle["lineage_graph"]["nodes"]
    }
    receipt_sources = receipt.get("source_envelope_ids")
    receipt_assertions = receipt.get("assertion_ids")
    receipt_nodes = receipt.get("authority_node_ids")
    if (
        not isinstance(receipt_sources, list)
        or not receipt_sources
        or not set(receipt_sources) <= set(sources)
        or not isinstance(receipt_assertions, list)
        or not receipt_assertions
        or not set(receipt_assertions) <= assertions
        or not isinstance(receipt_nodes, list)
        or not receipt_nodes
        or not set(receipt_nodes) <= node_ids
        or receipt.get("source_envelope_set_digest")
        != content_digest(
            [
                {
                    "source_id": source_id,
                    "body_hash": sources[source_id]["body_hash"],
                }
                for source_id in sorted(sources)
            ],
        )
        or receipt.get("normalized_event_set_digest")
        != content_digest(
            [
                {
                    "source_id": source_id,
                    "event_id": events[source_id]["event_id"],
                }
                for source_id in sorted(events)
            ],
        )
    ):
        raise EngineCadenceError("candidate receipt authority or event-set binding is inconsistent")
    input_digest = direct_input_digest(
        paths,
        runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
    )
    artifacts = artifact_descriptors(output_dir, DISTILL_OUTPUT_NAMES)
    bounded_units = bounded_unit_count(bundle, render=False)
    projection = load_object(projection_path)
    readiness = validate_projection(
        projection,
        contract_name=DISTILL_CONTRACT,
        stage="distill",
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
        input_digest=input_digest,
        artifacts=artifacts,
        bounded_units=bounded_units,
    )
    expected_readiness = distill_readiness(bundle, receipt)
    if readiness != expected_readiness:
        raise EngineCadenceError("distill readiness is not derived from owner evidence")
    return projection


def _validate_event_spine(path: Path, detail: Mapping[str, Any], *, ready: bool) -> None:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineCadenceError("Atlas event spine is unreadable or malformed") from exc
    event_projection = detail.get("event_spine")
    if not isinstance(event_projection, Mapping):
        raise EngineCadenceError("private Atlas has no event-spine disposition")
    verification = verify_chain(path)
    if not verification.valid:
        raise EngineCadenceError("Atlas event spine hash chain is invalid")
    if not ready:
        if rows or event_projection != {
            "status": "not_emitted",
            "reason": "atlas-readiness-blocked",
        }:
            raise EngineCadenceError("blocked Atlas must not emit a verified event")
        return
    event_id = event_projection.get("event_id")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get("event_id") == event_id]
    if len(matches) != 1:
        raise EngineCadenceError("ready Atlas event projection is unresolved")
    event = matches[0]
    if (
        event.get("event_type") != "testament.verified"
        or event.get("hash") != event_projection.get("hash")
        or event.get("sequence") != event_projection.get("sequence")
    ):
        raise EngineCadenceError("ready Atlas event projection is inconsistent")


def validate_render_outputs(
    *,
    bundle: Mapping[str, Any],
    output_dir: Path,
    projection_path: Path,
    paths: DirectArtifactPaths,
    runtime: CadenceRuntime,
    snapshot_digest: str,
    owner_reference: str,
) -> dict[str, Any]:
    """Independently verify the blocked-or-ready Atlas and owner projection."""
    public = load_object(output_dir / RENDER_OUTPUT_NAMES[0])
    detail = load_object(output_dir / RENDER_OUTPUT_NAMES[1])
    receipt = load_object(output_dir / RENDER_OUTPUT_NAMES[2])
    cursor = load_object(output_dir / RENDER_OUTPUT_NAMES[3])
    atlas_body = {key: value for key, value in public.items() if key != "atlas_digest"}
    receipt_body = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    if (
        public.get("snapshot_id") != runtime.snapshot_id
        or public.get("snapshot_digest") != snapshot_digest
        or public.get("atlas_digest") != content_digest(atlas_body)
        or receipt.get("contract_name") != "governance-atlas-receipt.v1"
        or receipt.get("contract_version") != 1
        or receipt.get("snapshot_id") != runtime.snapshot_id
        or receipt.get("snapshot_digest") != snapshot_digest
        or receipt.get("receipt_digest") != content_digest(receipt_body)
        or receipt.get("iceberg_atlas", {}).get("digest") != public.get("atlas_digest")
        or detail.get("atlas") != public
        or detail.get("receipt") != receipt
        or cursor.get("complete") is not True
        or cursor.get("receipt") != receipt
    ):
        raise EngineCadenceError("Atlas artifacts do not form one digest-bound result")
    if (
        receipt.get("owner_reference") != owner_reference
        or receipt.get("generated_at") != runtime.snapshot_at
        or detail.get("coverage") != bundle["coverage"]
        or detail.get("ideal_form_register") != bundle["ideal_form_register"]
        or {
            str(source["source_id"]): source
            for source in detail.get("source_envelopes", [])
            if isinstance(source, Mapping)
        }
        != {
            str(source["source_id"]): source
            for source in bundle["source_envelopes"]
            if isinstance(source, Mapping)
        }
        or detail.get("assertion_evidence") != bundle["assertion_evidence"]
        or detail.get("node_self_image_set", {}).get("set_digest")
        != bundle["node_self_image_set"]["set_digest"]
        or receipt.get("source_envelope_set", {}).get("digest")
        != content_digest(detail["source_envelopes"])
        or receipt.get("assertion_evidence_set", {}).get("digest")
        != content_digest(detail["assertion_evidence"])
        or receipt.get("ideal_form_register", {}).get("artifact_id")
        != bundle["ideal_form_register"]["register_id"]
        or receipt.get("ideal_form_register", {}).get("snapshot_id")
        != bundle["ideal_form_register"]["snapshot_id"]
        or receipt.get("ideal_form_register", {}).get("digest")
        != bundle["ideal_form_register"]["register_digest"]
        or receipt.get("node_self_image_set", {}).get("digest")
        != bundle["node_self_image_set"]["set_digest"]
    ):
        raise EngineCadenceError("Atlas receipt does not bind its direct owner artifacts")
    timelines = public.get("timelines")
    zooms = public.get("zoom_levels")
    ideal_form_ids = sorted(
        str(ideal["ideal_form_id"])
        for ideal in bundle["ideal_form_register"]["ideal_forms"]
    )
    if (
        not isinstance(timelines, Mapping)
        or set(timelines) != {"operator_intent", "artifact"}
        or not isinstance(zooms, Mapping)
        or set(zooms) != set(ZOOM_LEVELS)
        or receipt.get("timeline_counts")
        != {lane: len(timelines[lane]) for lane in ("operator_intent", "artifact")}
        or receipt.get("zoom_counts")
        != {level: len(zooms[level]) for level in ZOOM_LEVELS}
        or public.get("ideal_forms") != ideal_form_ids
        or public.get("coverage", {}).get("ideal_form_count") != len(ideal_form_ids)
    ):
        raise EngineCadenceError("Atlas timelines or zoom counts are inconsistent")
    readiness_value = receipt.get("readiness")
    if not isinstance(readiness_value, Mapping):
        raise EngineCadenceError("Atlas receipt readiness is missing")
    readiness = standard_readiness(readiness_value, label="Atlas receipt readiness")
    rendered_testament = detail.get("governance_testament")
    if (
        rendered_testament is not None
        and rendered_testament != bundle["governance_testament"]
    ) or (
        readiness["ready"] and rendered_testament != bundle["governance_testament"]
    ) or (
        rendered_testament is None
        and "ratified_governance_testament" not in readiness["missing_requirements"]
    ):
        raise EngineCadenceError(
            "Atlas testament projection does not match its blocked-or-ready disposition",
        )
    predicates = receipt.get("predicate_results")
    if not isinstance(predicates, Mapping) or not all(
        isinstance(value, bool) for value in predicates.values()
    ):
        raise EngineCadenceError("Atlas predicate results are invalid")
    computed_ready = readiness["exact_all"] and all(predicates.values()) and not any(
        readiness[field] for field in READINESS_DEBT_FIELDS
    )
    if readiness["ready"] is not computed_ready:
        raise EngineCadenceError("Atlas readiness is not derived from predicates and debt")
    _validate_event_spine(
        output_dir / RENDER_OUTPUT_NAMES[4],
        detail,
        ready=readiness["ready"],
    )
    input_digest = direct_input_digest(
        paths,
        runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
    )
    artifacts = artifact_descriptors(output_dir, RENDER_OUTPUT_NAMES)
    bounded_units = bounded_unit_count(bundle, render=True)
    projection = load_object(projection_path)
    projection_readiness = validate_projection(
        projection,
        contract_name=RENDER_CONTRACT,
        stage="render",
        runtime=runtime,
        snapshot_digest=snapshot_digest,
        owner_reference=owner_reference,
        input_digest=input_digest,
        artifacts=artifacts,
        bounded_units=bounded_units,
    )
    if projection_readiness != readiness:
        raise EngineCadenceError("render projection readiness differs from the Atlas receipt")
    return projection


def child_receipt_digest(child: Mapping[str, Any]) -> str:
    return content_digest(
        {
            "child_id": child["child_id"],
            "status": child["status"],
            "input_digest": child["input_digest"],
            "output_digest": child["output_digest"],
        },
    )


def proof_child(
    *,
    runtime: CadenceRuntime,
    child_id: str,
    input_digest: str,
    output_digest: str,
) -> dict[str, Any]:
    if runtime.prior_stage_receipt is None:
        raise EngineCadenceError("proof child requires a prior stage receipt")
    prior = load_object(runtime.prior_stage_receipt)
    prior_children = prior.get("child_receipts")
    if (
        prior.get("stage") != runtime.stage
        or prior.get("snapshot_id") != runtime.snapshot_id
        or not isinstance(prior_children, list)
    ):
        raise EngineCadenceError("prior stage receipt is incompatible with proof traversal")
    matches = [
        child
        for child in prior_children
        if isinstance(child, Mapping) and child.get("child_id") == child_id
    ]
    if len(matches) != 1:
        raise EngineCadenceError("proof traversal child is absent from the prior receipt")
    prior_child = matches[0]
    if (
        prior_child.get("status") != "completed"
        or prior_child.get("input_digest") != input_digest
        or prior_child.get("output_digest") != output_digest
    ):
        raise EngineCadenceError("proof traversal changed a completed child")
    return {
        "child_id": child_id,
        "status": "skipped_completed",
        "input_digest": input_digest,
        "output_digest": output_digest,
        "prior_receipt_digest": child_receipt_digest(prior_child),
    }


def write_metrics(runtime: CadenceRuntime, child: Mapping[str, Any], *, emitted_events: int) -> None:
    if emitted_events < 0:
        raise EngineCadenceError("emitted event count cannot be negative")
    payload = {
        "resume_token": None,
        "completed_child_ids": [child["child_id"]],
        "pending_child_ids": [],
        "child_receipts": [dict(child)],
        "emitted_events": 0 if runtime.proof_mode else emitted_events,
    }
    runtime.metrics_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = runtime.metrics_path.with_name(
        f".{runtime.metrics_path.name}.{os.getpid()}.tmp",
    )
    temporary.write_bytes(canonical_document(payload))
    temporary.replace(runtime.metrics_path)


__all__ = [
    "CadenceRuntime",
    "DISTILL_CONTRACT",
    "DISTILL_OUTPUT_NAMES",
    "DISTILL_PROJECTION_NAME",
    "DirectArtifactPaths",
    "EngineCadenceError",
    "OWNER_REFERENCE",
    "RENDER_CONTRACT",
    "RENDER_OUTPUT_NAMES",
    "RENDER_PROJECTION_NAME",
    "artifact_descriptors",
    "bounded_unit_count",
    "build_projection",
    "cadence_runtime",
    "canonical_document",
    "child_receipt_digest",
    "digest_file",
    "direct_input_digest",
    "distill_readiness",
    "load_direct_bundle",
    "load_object",
    "proof_child",
    "validate_candidate_outputs",
    "validate_owner_reference",
    "validate_projection",
    "validate_render_outputs",
    "validate_snapshot_digest",
    "write_metrics",
]
