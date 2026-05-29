"""CLI handler for `organvm relay draft`.

Validates a sister-agent relay file (typically a HANDOFF markdown doc) against
current disk state. For each claim (file path, commit SHA, DONE-ID, status
assertion), verifies the claim and reports CONFIRMED / STALE / DROP. Catches
the stale-propagation pattern that produced DONE-475/476 incidents.

Built as part of DIWS Stream Τ. Implements the Hermes sub-titan relay-draft
mechanism per titan-keeper architecture (~/.claude/plans/2026-04-25-titan-keeper-architecture.md).

Usage:
    organvm relay draft <path-to-relay-md>
    organvm relay draft <path> --json
    organvm relay draft <path> --reject-on-stale
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DONE_COUNTER_PATH = (
    Path.home()
    / "Workspace"
    / "organvm"
    / "organvm-corpvs-testamentvm"
    / "data"
    / "done-id-counter.json"
)


@dataclass
class ClaimVerification:
    """One claim from a relay + its verification status."""

    claim_type: str  # "file" / "commit" / "done_id" / "irf_id"
    raw_text: str
    verdict: str  # "CONFIRMED" / "STALE" / "DROP"
    evidence: str


_FILE_PATH_RE = re.compile(r"`([^`]+\.[a-z]{1,8})`")  # backticked filenames
_COMMIT_SHA_RE = re.compile(r"\b(commit\s+)?([0-9a-f]{7,40})\b")
_DONE_ID_RE = re.compile(r"\b(DONE-\d+)\b")
_IRF_ID_RE = re.compile(r"\b(IRF-[A-Z]+-\d+|PRT-\d+|SYS-\d+)\b")


def _scan_relay(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Extract distinct file paths, commit SHAs, DONE-IDs, IRF-IDs from relay text."""
    files = sorted({m.group(1) for m in _FILE_PATH_RE.finditer(text)})
    commits = sorted({m.group(2) for m in _COMMIT_SHA_RE.finditer(text) if not m.group(2).isdigit()})
    done_ids = sorted({m.group(1) for m in _DONE_ID_RE.finditer(text)})
    irf_ids = sorted({m.group(1) for m in _IRF_ID_RE.finditer(text)})
    return files, commits, done_ids, irf_ids


def _verify_file(claim: str) -> ClaimVerification:
    """Treat as path-claim if backticked filename. Resolve relative to home if not absolute."""
    p = Path(claim).expanduser()
    if not p.is_absolute():
        p = Path.home() / claim
    if p.exists():
        return ClaimVerification(
            claim_type="file",
            raw_text=claim,
            verdict="CONFIRMED",
            evidence=f"exists at {p}",
        )
    return ClaimVerification(
        claim_type="file",
        raw_text=claim,
        verdict="STALE",
        evidence=f"not found at {p}",
    )


def _verify_commit(sha: str) -> ClaimVerification:
    """Look for the SHA in any of the known repos."""
    repos = [
        Path.home() / "Workspace" / "organvm" / "organvm-corpvs-testamentvm",
        Path.home() / "Workspace" / "organvm" / "a-i--skills",
        Path.home() / "Workspace" / "4444J99" / "domus-semper-palingenesis",
        Path.home() / "Workspace" / "4444J99" / "hokage-chess",
    ]
    for repo in repos:
        if not (repo / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "-t", sha],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0 and result.stdout.strip() == "commit":
            return ClaimVerification(
                claim_type="commit",
                raw_text=sha,
                verdict="CONFIRMED",
                evidence=f"found in {repo.name}",
            )
    return ClaimVerification(
        claim_type="commit",
        raw_text=sha,
        verdict="STALE",
        evidence="not found in any known repo",
    )


def _verify_done_id(done_id: str) -> ClaimVerification:
    """Verify DONE-NNN is below counter ceiling."""
    if not DONE_COUNTER_PATH.exists():
        return ClaimVerification(
            claim_type="done_id",
            raw_text=done_id,
            verdict="DROP",
            evidence="counter file missing",
        )
    try:
        data = json.loads(DONE_COUNTER_PATH.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return ClaimVerification(
            claim_type="done_id",
            raw_text=done_id,
            verdict="DROP",
            evidence=f"counter unreadable: {e}",
        )
    next_id = int(data.get("next_id", 0))
    n = int(done_id.split("-")[1])
    if n < next_id:
        return ClaimVerification(
            claim_type="done_id",
            raw_text=done_id,
            verdict="CONFIRMED",
            evidence=f"below counter ceiling ({next_id})",
        )
    return ClaimVerification(
        claim_type="done_id",
        raw_text=done_id,
        verdict="STALE",
        evidence=f"≥ counter ceiling ({next_id}) — possibly future / unclaimed",
    )


def _verify_irf_id(irf_id: str) -> ClaimVerification:
    """Look for the IRF id in INST-INDEX-RERUM-FACIENDARUM.md."""
    irf_path = (
        Path.home()
        / "Workspace"
        / "organvm"
        / "organvm-corpvs-testamentvm"
        / "INST-INDEX-RERUM-FACIENDARUM.md"
    )
    if not irf_path.exists():
        return ClaimVerification(
            claim_type="irf_id",
            raw_text=irf_id,
            verdict="DROP",
            evidence="IRF file missing",
        )
    try:
        text = irf_path.read_text(errors="replace")
    except OSError as e:
        return ClaimVerification(
            claim_type="irf_id",
            raw_text=irf_id,
            verdict="DROP",
            evidence=f"IRF unreadable: {e}",
        )
    if irf_id in text:
        return ClaimVerification(
            claim_type="irf_id",
            raw_text=irf_id,
            verdict="CONFIRMED",
            evidence="present in IRF",
        )
    return ClaimVerification(
        claim_type="irf_id",
        raw_text=irf_id,
        verdict="STALE",
        evidence="not found in IRF",
    )


def cmd_relay_draft(args) -> int:
    """Validate a sister-agent relay against current disk state."""
    arg = getattr(args, "relay_file", None)
    if not arg:
        sys.stderr.write("usage: organvm relay draft <path-to-relay-md>\n")
        return 2

    path = Path(arg).expanduser()
    if not path.exists():
        sys.stderr.write(f"relay file not found: {path}\n")
        return 1

    text = path.read_text(errors="replace")
    files, commits, done_ids, irf_ids = _scan_relay(text)

    verifications: list[ClaimVerification] = []
    verifications.extend(_verify_file(f) for f in files)
    verifications.extend(_verify_commit(s) for s in commits)
    verifications.extend(_verify_done_id(d) for d in done_ids)
    verifications.extend(_verify_irf_id(i) for i in irf_ids)

    confirmed = sum(1 for v in verifications if v.verdict == "CONFIRMED")
    stale = sum(1 for v in verifications if v.verdict == "STALE")
    drop = sum(1 for v in verifications if v.verdict == "DROP")
    total = len(verifications)
    staleness_pct = (stale / total * 100) if total else 0.0

    if getattr(args, "json", False):
        sys.stdout.write(
            json.dumps(
                {
                    "relay_path": str(path),
                    "total_claims": total,
                    "confirmed": confirmed,
                    "stale": stale,
                    "drop": drop,
                    "staleness_pct": staleness_pct,
                    "claims": [asdict(v) for v in verifications],
                },
                indent=2,
            )
            + "\n",
        )
    else:
        print(f"Relay validation — {path.name}")
        print(f"Total claims: {total} | CONFIRMED: {confirmed} | STALE: {stale} | DROP: {drop}")
        print(f"Staleness: {staleness_pct:.1f}%")
        print()
        for v in verifications:
            print(f"[{v.verdict:<9}] {v.claim_type:<8} {v.raw_text}")
            print(f"             evidence: {v.evidence}")

    if getattr(args, "reject_on_stale", False) and stale > 0:
        sys.stderr.write(f"\nrelay REJECTED — {stale} stale claim(s) detected\n")
        return 3
    return 0
