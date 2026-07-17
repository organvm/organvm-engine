"""Durable Engine receipt reference and custody checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.testament.receipt_registry import (
    ReceiptResolutionError,
    resolve_engine_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "receipt:engine:candidate-testament-governance-native-20260716"
RECEIPT_DIGEST = (
    "sha256:36ec614c71412b666fa4a7161c3c71cdaa04f72c6d73736dc0166c961120a2e0"
)
CANDIDATE_DIGEST = (
    "sha256:1082c824d2608eefef63de75963a47289fafb44663ee358aa259381f6197cd6c"
)


def test_ratification_candidate_receipt_resolves_to_exact_public_custody() -> None:
    resolved = resolve_engine_receipt(REFERENCE, repository_root=ROOT)

    assert resolved.path.relative_to(ROOT).as_posix() == (
        "receipts/engine/candidate-testament-governance-native-20260716.json"
    )
    assert resolved.digest == RECEIPT_DIGEST
    assert resolved.document["contract_name"] == "candidate-testament-receipt.v1"
    assert resolved.document["candidate_digest"] == CANDIDATE_DIGEST
    assert resolved.document["snapshot_id"] == "governance-native-20260716"
    rendered = resolved.path.read_text(encoding="utf-8")
    assert not any(
        marker in rendered
        for marker in ("/Users/", "/Volumes/", "private-cas://", "prompt_body")
    )


def test_receipt_resolution_is_convention_driven_not_catalog_driven(
    tmp_path: Path,
) -> None:
    root = tmp_path / "engine"
    receipt_root = root / "receipts" / "engine"
    receipt_root.mkdir(parents=True)
    document = {
        "contract_name": "candidate-testament-receipt.v1",
        "contract_version": 1,
    }
    (receipt_root / "provider-renamed-without-code-change.json").write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    resolved = resolve_engine_receipt(
        "receipt:engine:provider-renamed-without-code-change",
        repository_root=root,
    )
    assert resolved.document == document


@pytest.mark.parametrize(
    "reference",
    (
        "receipt:other:wrong-owner",
        "receipt:engine:../escape",
        "receipt:engine:Missing-Catalog-Key",
        "receipt:engine:",
    ),
)
def test_receipt_resolution_fails_closed(reference: str, tmp_path: Path) -> None:
    with pytest.raises(ReceiptResolutionError):
        resolve_engine_receipt(reference, repository_root=tmp_path)
