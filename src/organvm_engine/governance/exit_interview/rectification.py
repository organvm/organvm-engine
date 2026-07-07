"""Phase 3: Rectification — three-voice symmetrical diff.

Compares V1 testimony against V2 counter-testimony, verified against
actuality (what's actually on disk / in git). Produces per-dimension
verdicts for each V1 module within each gate contract.

Three voices:
  1. V1 says (testimony): "Here's what I am"
  2. V2 says (counter-testimony): "Here's what I expect you to be"
  3. Reality says (actuality check): "Here's what's actually true"

Six verdicts:
  ALIGNED          — all three agree
  V1_OVERCLAIMS    — V1 claims more than reality shows
  V2_UNDERSPECS    — V2 expects less than V1 provides (knowledge loss risk)
  CONTRADICTED     — V1 and V2 disagree, reality confirms one
  UNVERIFIABLE     — claim can't be checked automatically
  ORPHANED         — V1 artifact not referenced by any gate
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from organvm_engine.governance.exit_interview.schemas import (
    CounterTestimony,
    DimensionVerdict,
    GateContract,
    OrphanEntry,
    RectificationReport,
    RemediationItem,
    RemediationPriority,
    RemediationType,
    Testimony,
    Verdict,
)

# ---------------------------------------------------------------------------
# Actuality checks
# ---------------------------------------------------------------------------


def _check_existence_actuality(
    testimony: Testimony,
    workspace_root: Path,
) -> str:
    """Verify existence claims against the filesystem."""
    v1_path = testimony.v1_path
    # Parse repo/module from v1_path
    parts = v1_path.split("/", 2)
    if len(parts) < 3:
        return "cannot resolve path"

    # Build filesystem path
    repo_dir = "/".join(parts[:2])
    module = parts[2]

    if "organvm-engine" in repo_dir:
        fs_path = workspace_root / repo_dir / "src" / "organvm_engine" / module
    elif "organvm-ontologia" in repo_dir:
        fs_path = workspace_root / repo_dir / "src" / "organvm_ontologia" / module
    else:
        fs_path = workspace_root / repo_dir / module

    if fs_path.exists():
        if fs_path.is_dir():
            py_files = list(fs_path.rglob("*.py"))
            total_lines = 0
            for f in py_files:
                with contextlib.suppress(OSError, UnicodeDecodeError):
                    total_lines += len(f.read_text(encoding="utf-8").splitlines())
            return f"exists, {len(py_files)} files, {total_lines} lines"
        try:
            lines = len(fs_path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            lines = 0
        return f"exists, {lines} lines"
    return "NOT FOUND on disk"


# ---------------------------------------------------------------------------
# Per-dimension rectification
# ---------------------------------------------------------------------------


def _rectify_existence(
    testimony: Testimony,
    counter: CounterTestimony,
    workspace_root: Path,
) -> DimensionVerdict:
    """Rectify the existence dimension."""
    v1_says = testimony.existence.get("evidence", "unknown")
    v2_says = f"required={counter.existence.get('required', True)}, expected_lines={counter.existence.get('expected_lines', '?')}"
    actuality = _check_existence_actuality(testimony, workspace_root)

    if "NOT FOUND" in actuality:
        verdict = Verdict.V1_OVERCLAIMS
        remediation = "V1 artifact no longer exists on disk"
    elif testimony.existence.get("score", 0) > 0 and counter.existence.get("required"):
        verdict = Verdict.ALIGNED
        remediation = ""
    else:
        verdict = Verdict.UNVERIFIABLE
        remediation = ""

    return DimensionVerdict(
        dimension="existence",
        verdict=verdict,
        v1_says=v1_says,
        v2_says=v2_says,
        actuality=actuality,
        remediation=remediation,
    )


def _rectify_text_dimension(
    dimension: str,
    v1_text: str,
    v2_text: str,
) -> DimensionVerdict:
    """Rectify a text-based dimension (identity, structure, law, process, relation, teleology).

    Heuristic: if both sides have content and share keywords, ALIGNED.
    If V1 has content but V2 doesn't, V2_UNDERSPECS.
    If V2 has content but V1 doesn't, V1_OVERCLAIMS (V1 failed to self-describe).
    If neither has meaningful content, UNVERIFIABLE.
    """
    v1_has = bool(v1_text and "not detected" not in v1_text.lower() and "no " not in v1_text.lower()[:5])
    v2_has = bool(v2_text and "not specified" not in v2_text.lower() and "no " not in v2_text.lower()[:5])

    if v1_has and v2_has:
        # Check for keyword overlap as rough alignment signal
        v1_words = set(v1_text.lower().split())
        v2_words = set(v2_text.lower().split())
        overlap = v1_words & v2_words
        # Filter out common stop words
        meaningful_overlap = overlap - {
            "the", "a", "an", "is", "are", "in", "of", "to", "and", "for",
            "from", "with", "no", "not", "must", "should", "can", "may",
        }
        if len(meaningful_overlap) >= 2:
            return DimensionVerdict(
                dimension=dimension,
                verdict=Verdict.ALIGNED,
                v1_says=v1_text,
                v2_says=v2_text,
                actuality="keyword alignment detected",
            )
        return DimensionVerdict(
            dimension=dimension,
            verdict=Verdict.CONTRADICTED,
            v1_says=v1_text,
            v2_says=v2_text,
            actuality="V1 and V2 descriptions diverge",
            remediation="Manual review needed — descriptions share few keywords",
        )
    if v1_has and not v2_has:
        return DimensionVerdict(
            dimension=dimension,
            verdict=Verdict.V2_UNDERSPECS,
            v1_says=v1_text,
            v2_says=v2_text or "(no expectation)",
            actuality="V1 has content, V2 does not — potential knowledge loss",
        )
    if not v1_has and v2_has:
        return DimensionVerdict(
            dimension=dimension,
            verdict=Verdict.V1_OVERCLAIMS,
            v1_says=v1_text or "(no testimony)",
            v2_says=v2_text,
            actuality="V2 has expectations, V1 failed to testify",
            remediation="V1 artifact needs manual testimony for this dimension",
        )
    return DimensionVerdict(
        dimension=dimension,
        verdict=Verdict.UNVERIFIABLE,
        v1_says=v1_text or "(empty)",
        v2_says=v2_text or "(empty)",
        actuality="Neither side provided meaningful content",
    )


def _rectify_signals(
    testimony: Testimony,
    counter: CounterTestimony,
) -> DimensionVerdict:
    """Compare signal type declarations between V1 and V2."""
    v1_consumes = set(testimony.signals_consumes)
    v1_produces = set(testimony.signals_produces)
    v2_consumes = set(counter.expected_consumes)
    v2_produces = set(counter.expected_produces)

    v1_text = f"consumes: {sorted(v1_consumes)}, produces: {sorted(v1_produces)}"
    v2_text = f"consumes: {sorted(v2_consumes)}, produces: {sorted(v2_produces)}"

    # Check alignment
    consume_match = v1_consumes & v2_consumes
    produce_match = v1_produces & v2_produces

    if consume_match or produce_match:
        missing_in_v1 = (v2_consumes - v1_consumes) | (v2_produces - v1_produces)
        extra_in_v1 = (v1_consumes - v2_consumes) | (v1_produces - v2_produces)

        if not missing_in_v1 and not extra_in_v1:
            verdict = Verdict.ALIGNED
            remediation = ""
        elif missing_in_v1:
            verdict = Verdict.CONTRADICTED
            remediation = f"V2 expects signals V1 doesn't declare: {sorted(missing_in_v1)}"
        else:
            verdict = Verdict.V2_UNDERSPECS
            remediation = f"V1 produces signals V2 doesn't expect: {sorted(extra_in_v1)}"
    elif not v1_consumes and not v1_produces:
        verdict = Verdict.UNVERIFIABLE
        remediation = "V1 could not infer signal types — manual annotation needed"
    else:
        verdict = Verdict.CONTRADICTED
        remediation = "No signal overlap between V1 inference and V2 declaration"

    return DimensionVerdict(
        dimension="signals",
        verdict=verdict,
        v1_says=v1_text,
        v2_says=v2_text,
        actuality="signal comparison (heuristic — V1 signals are inferred, not declared)",
        remediation=remediation,
    )


# ---------------------------------------------------------------------------
# Per-module rectification
# ---------------------------------------------------------------------------


def rectify_module(
    testimony: Testimony,
    counter: CounterTestimony,
    workspace_root: Path,
) -> list[DimensionVerdict]:
    """Rectify a single V1 module across all dimensions.

    Returns a list of DimensionVerdict objects, one per dimension.
    """
    return [
        _rectify_existence(testimony, counter, workspace_root),
        _rectify_text_dimension("identity", testimony.identity, counter.identity),
        _rectify_text_dimension("structure", testimony.structure, counter.structure),
        _rectify_text_dimension("law", testimony.law, counter.law),
        _rectify_text_dimension("process", testimony.process, counter.process),
        _rectify_text_dimension("relation", testimony.relation, counter.relation),
        _rectify_text_dimension("teleology", testimony.teleology, counter.teleology),
        _rectify_signals(testimony, counter),
    ]


# ---------------------------------------------------------------------------
# Remediation extraction
# ---------------------------------------------------------------------------


def _verdicts_to_remediation(
    module_path: str,
    verdicts: list[DimensionVerdict],
    counter: CounterTestimony,
) -> list[RemediationItem]:
    """Extract remediation items from non-ALIGNED verdicts."""
    items = []
    for v in verdicts:
        if v.verdict == Verdict.ALIGNED:
            continue

        # Determine priority from verdict type
        if v.verdict in {Verdict.CONTRADICTED, Verdict.V1_OVERCLAIMS}:
            priority = RemediationPriority.HIGH
        elif v.verdict == Verdict.V2_UNDERSPECS:
            priority = RemediationPriority.MEDIUM
        else:
            priority = RemediationPriority.LOW

        # Determine type
        if "isotope" in (v.remediation or "").lower():
            rtype = RemediationType.ISOTOPE_RESOLUTION
        elif "test" in v.dimension or "test" in (v.remediation or "").lower():
            rtype = RemediationType.TEST_ADAPTATION
        elif v.dimension == "signals":
            rtype = RemediationType.SIGNAL_DECLARATION
        elif v.verdict == Verdict.V2_UNDERSPECS:
            rtype = RemediationType.KNOWLEDGE_PRESERVATION
        else:
            rtype = RemediationType.DISSOLUTION

        action = v.remediation or f"{v.verdict.value} on {v.dimension} — needs review"
        gate_ref = counter.gates_served[0] if counter.gates_served else counter.gate_source

        items.append(
            RemediationItem(
                action=action,
                gate=gate_ref,
                priority=priority,
                item_type=rtype,
                source_path=module_path,
            ),
        )
    return items


# ---------------------------------------------------------------------------
# Full rectification per gate
# ---------------------------------------------------------------------------


def rectify_gate(
    contract: GateContract,
    testimonies: dict[str, Testimony],
    counter_testimonies: dict[str, CounterTestimony],
    workspace_root: Path,
    orphans: list[OrphanEntry] | None = None,
) -> RectificationReport:
    """Rectify all V1 modules for a single gate contract.

    Args:
        contract: The gate contract being rectified.
        testimonies: All V1 testimonies, keyed by module path.
        counter_testimonies: All V2 counter-testimonies, keyed by module path.
        workspace_root: Filesystem root.
        orphans: Orphan list from discovery (for the orphan report).
    """
    # Find modules claimed by this gate
    claimed_modules = set()
    for source in contract.sources:
        for module in source.modules:
            key = f"{source.repo}/{module.rstrip('/')}"
            claimed_modules.add(key)

    # Rectify each module that has both testimony and counter-testimony
    module_verdicts: dict[str, list[DimensionVerdict]] = {}
    all_remediation: list[RemediationItem] = []
    testified_count = 0
    counter_count = 0

    for module_key in sorted(claimed_modules):
        testimony = testimonies.get(module_key)
        counter = counter_testimonies.get(module_key)

        if testimony:
            testified_count += 1
        if counter:
            counter_count += 1

        if testimony and counter:
            verdicts = rectify_module(testimony, counter, workspace_root)
            module_verdicts[module_key] = verdicts
            all_remediation.extend(
                _verdicts_to_remediation(module_key, verdicts, counter),
            )

    # Filter orphans relevant to this gate's source repos
    gate_repos = {source.repo for source in contract.sources}
    relevant_orphans = []
    if orphans:
        relevant_orphans = [o for o in orphans if o.repo in gate_repos]

    return RectificationReport(
        gate_name=contract.name,
        gate_status=contract.state,
        v1_modules_claimed=len(claimed_modules),
        testified=testified_count,
        counter_testified=counter_count,
        orphaned=len(relevant_orphans),
        module_verdicts=module_verdicts,
        remediation=all_remediation,
        orphan_report=relevant_orphans,
    )


def rectify_all(
    contracts: list[GateContract],
    testimonies: dict[str, Testimony],
    counter_testimonies: dict[str, CounterTestimony],
    workspace_root: Path,
    orphans: list[OrphanEntry] | None = None,
) -> list[RectificationReport]:
    """Rectify all gate contracts."""
    return [
        rectify_gate(contract, testimonies, counter_testimonies, workspace_root, orphans)
        for contract in contracts
    ]
