"""Resolve and verify artifact references in a frozen governance snapshot."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from organvm_engine.corpus.governance_lineage import (
    SCHEMA_SNAPSHOT_BUNDLE,
    content_digest,
    schema_id,
)

_ARTIFACT_FIELDS = (
    "lineage_graph",
    "governance_testament",
    "coverage",
    "ideal_form_register",
    "node_self_image_set",
)


def _load_json(path: Path, max_bytes: int) -> Any:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"governance artifact exceeds max bytes: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(reference: str, base_dir: Path) -> tuple[Path, str]:
    file_reference, separator, fragment = reference.partition("#")
    parsed = urlsplit(file_reference)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(f"artifact reference requires an external resolver: {parsed.scheme}")
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
    else:
        path = Path(file_reference)
        if not path.is_absolute():
            path = base_dir / path
    if not file_reference:
        raise ValueError("artifact reference cannot point back into the reference bundle")
    return path.resolve(), fragment if separator else ""


def _json_pointer(value: Any, fragment: str) -> Any:
    if not fragment:
        return value
    if not fragment.startswith("/"):
        raise ValueError("artifact JSON pointer must begin with '/'")
    current = value
    for raw_token in fragment.removeprefix("/").split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, Mapping):
            current = current[token]
        else:
            raise ValueError("artifact JSON pointer traverses a scalar")
    return current


def _materialize_reference(
    reference: Mapping[str, Any],
    *,
    base_dir: Path,
    snapshot_id: str,
    max_artifact_bytes: int,
) -> dict[str, Any]:
    contract_name = reference.get("contract_name")
    location = reference.get("reference")
    expected_digest = reference.get("digest")
    if (
        not isinstance(contract_name, str)
        or not contract_name
        or not isinstance(location, str)
        or not location
        or not isinstance(expected_digest, str)
        or not expected_digest
        or reference.get("snapshot_id") != snapshot_id
    ):
        raise ValueError("invalid governance artifact reference")
    path, fragment = _resolve_path(location, base_dir)
    document = _json_pointer(_load_json(path, max_artifact_bytes), fragment)
    if not isinstance(document, dict) or schema_id(document) != contract_name:
        raise ValueError(f"artifact reference contract mismatch: {contract_name}")
    if content_digest(document) != expected_digest:
        raise ValueError(f"artifact reference digest mismatch: {contract_name}")
    return document


def load_materialized_snapshot_bundle(
    path: Path,
    *,
    max_input_bytes: int = 16_777_216,
    max_artifact_bytes: int = 16_777_216,
) -> dict[str, Any]:
    """Load one exact snapshot and resolve all compiler-owned artifact refs.

    References stay resolver-neutral in the public contract.  This local CLI
    resolver accepts plain paths and ``file:`` references, verifies each exact
    digest, and fails closed for connectors or custody schemes it cannot read.
    """
    raw = _load_json(path, max_input_bytes)
    if (
        not isinstance(raw, dict)
        or schema_id(raw) != SCHEMA_SNAPSHOT_BUNDLE
        or raw.get("contract_version") != 1
    ):
        raise ValueError("invalid governance snapshot bundle")
    snapshot_id = raw.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("governance snapshot bundle lacks snapshot_id")
    materialized = deepcopy(raw)
    references: dict[str, Any] = {}
    for field_name in _ARTIFACT_FIELDS:
        value = raw.get(field_name)
        if not isinstance(value, Mapping):
            raise ValueError(f"governance snapshot field {field_name} must be an object")
        if value.get("contract_version") == 1:
            # Internal/tests may already hold a resolved exact document.
            continue
        references[field_name] = deepcopy(dict(value))
        materialized[field_name] = _materialize_reference(
            value,
            base_dir=path.parent,
            snapshot_id=snapshot_id,
            max_artifact_bytes=max_artifact_bytes,
        )
    materialized["_artifact_references"] = references
    materialized["_snapshot_bundle_digest"] = content_digest(raw)
    return materialized


__all__ = ["load_materialized_snapshot_bundle"]
