"""Resolve Engine-owned durable receipts without a hard-coded catalog."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from organvm_engine.corpus.governance_lineage import content_digest

ENGINE_RECEIPT_PREFIX = "receipt:engine:"
_RECEIPT_KEY = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class ReceiptResolutionError(ValueError):
    """Raised when a durable Engine receipt reference cannot resolve exactly."""


@dataclass(frozen=True)
class ResolvedEngineReceipt:
    reference: str
    path: Path
    document: dict[str, Any]
    digest: str


def resolve_engine_receipt(
    reference: str,
    *,
    repository_root: Path | None = None,
) -> ResolvedEngineReceipt:
    """Resolve ``receipt:engine:<key>`` to its tracked canonical JSON document."""

    if not reference.startswith(ENGINE_RECEIPT_PREFIX):
        raise ReceiptResolutionError("Engine receipt reference has the wrong owner")
    key = reference.removeprefix(ENGINE_RECEIPT_PREFIX)
    if not _RECEIPT_KEY.fullmatch(key):
        raise ReceiptResolutionError("Engine receipt reference key is invalid")
    root = (
        repository_root.resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[3]
    )
    path = root / "receipts" / "engine" / f"{key}.json"
    if path.is_symlink() or not path.is_file():
        raise ReceiptResolutionError(f"Engine receipt is not tracked: {reference}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptResolutionError(
            f"Engine receipt is not canonical JSON: {reference}",
        ) from exc
    if not isinstance(document, dict):
        raise ReceiptResolutionError(f"Engine receipt is not an object: {reference}")
    return ResolvedEngineReceipt(
        reference=reference,
        path=path,
        document=document,
        digest=content_digest(document),
    )


__all__ = [
    "ENGINE_RECEIPT_PREFIX",
    "ReceiptResolutionError",
    "ResolvedEngineReceipt",
    "resolve_engine_receipt",
]
