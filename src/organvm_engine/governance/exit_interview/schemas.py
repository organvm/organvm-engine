"""Data types for the exit interview protocol.

Every type is a plain dataclass with to_dict() for YAML serialization.
No external dependencies beyond the standard library.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Verdict(enum.Enum):
    """Per-dimension rectification verdict."""

    ALIGNED = "ALIGNED"  # all three voices agree
    V1_OVERCLAIMS = "V1_OVERCLAIMS"  # V1 claims more than reality shows
    V2_UNDERSPECS = "V2_UNDERSPECS"  # V2 expects less than V1 provides
    CONTRADICTED = "CONTRADICTED"  # V1 and V2 disagree, reality confirms one
    UNVERIFIABLE = "UNVERIFIABLE"  # claim can't be checked automatically
    ORPHANED = "ORPHANED"  # V1 artifact not referenced by any gate


class RemediationPriority(enum.Enum):
    """Priority for remediation items."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RemediationType(enum.Enum):
    """Classification of remediation action."""

    ISOTOPE_RESOLUTION = "isotope_resolution"
    TEST_ADAPTATION = "test_adaptation"
    SIGNAL_DECLARATION = "signal_declaration"
    KNOWLEDGE_PRESERVATION = "knowledge_preservation"
    DISSOLUTION = "dissolution"
    DISCOVERY = "discovery"  # gate contracts incomplete, not the artifact


# ---------------------------------------------------------------------------
# Gate contract types (parsed from a-organvm YAML)
# ---------------------------------------------------------------------------


@dataclass
class GateCheck:
    """A single gate check within a gate contract."""

    id: str
    check: str
    condition: str
    status: str  # PENDING | PASS
    note: str = ""

    def to_dict(self) -> dict:
        d = {"id": self.id, "check": self.check, "condition": self.condition, "status": self.status}
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class GateSource:
    """A V1 source reference within a gate contract."""

    repo: str
    modules: list[str] = field(default_factory=list)
    lines: int = 0
    note: str = ""
    isotope: bool = False
    resolution: str = ""

    def to_dict(self) -> dict:
        d = {"repo": self.repo, "modules": self.modules, "lines": self.lines}
        if self.note:
            d["note"] = self.note
        if self.isotope:
            d["isotope"] = True
            d["resolution"] = self.resolution
        return d


@dataclass
class GateContract:
    """Parsed gate contract from a-organvm."""

    name: str
    mechanism: str
    verb: str
    signal_inputs: list[str] = field(default_factory=list)
    signal_outputs: list[str] = field(default_factory=list)
    sources: list[GateSource] = field(default_factory=list)
    gates: list[GateCheck] = field(default_factory=list)
    dna: list[str] = field(default_factory=list)
    defects: list[str] = field(default_factory=list)
    state: str = "CALLING"
    file_path: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mechanism": self.mechanism,
            "verb": self.verb,
            "signal_inputs": self.signal_inputs,
            "signal_outputs": self.signal_outputs,
            "sources": [s.to_dict() for s in self.sources],
            "gates": [g.to_dict() for g in self.gates],
            "dna": self.dna,
            "defects": self.defects,
            "state": self.state,
        }


# ---------------------------------------------------------------------------
# Discovery types (demand/supply maps)
# ---------------------------------------------------------------------------


@dataclass
class DemandEntry:
    """A demand from a gate contract for a specific V1 module."""

    gate_name: str
    gate_ids: list[str]  # which specific gate checks reference this
    mechanism: str
    verb: str
    expected_signals: list[str]
    expected_lines: int = 0
    isotope: bool = False
    resolution: str = ""

    def to_dict(self) -> dict:
        d = {
            "gate_name": self.gate_name,
            "gate_ids": self.gate_ids,
            "mechanism": self.mechanism,
            "verb": self.verb,
            "expected_signals": self.expected_signals,
        }
        if self.expected_lines:
            d["expected_lines"] = self.expected_lines
        if self.isotope:
            d["isotope"] = True
            d["resolution"] = self.resolution
        return d


@dataclass
class SupplyEntry:
    """A V1 module's mapping to one or more gate contracts."""

    v1_path: str  # relative path within workspace, e.g. "organvm-engine/governance/"
    repo: str
    demands: list[DemandEntry] = field(default_factory=list)

    @property
    def gate_names(self) -> list[str]:
        return sorted({d.gate_name for d in self.demands})

    def to_dict(self) -> dict:
        return {
            "v1_path": self.v1_path,
            "repo": self.repo,
            "demands": [d.to_dict() for d in self.demands],
            "gate_names": self.gate_names,
        }


@dataclass
class OrphanEntry:
    """A V1 governance artifact not referenced by any gate contract."""

    v1_path: str
    repo: str
    artifact_type: str  # module | seed | governance_rule | sop | claude_md
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "v1_path": self.v1_path,
            "repo": self.repo,
            "artifact_type": self.artifact_type,
            "recommendation": self.recommendation,
        }


# ---------------------------------------------------------------------------
# Testimony types (V1 exit interview)
# ---------------------------------------------------------------------------


@dataclass
class AxiomClaim:
    """A claim about alignment with a SEED.md axiom."""

    axiom: str  # e.g. "A6"
    claim: str
    evidence: str = ""

    def to_dict(self) -> dict:
        d = {"axiom": self.axiom, "claim": self.claim}
        if self.evidence:
            d["evidence"] = self.evidence
        return d


@dataclass
class Testimony:
    """V1 artifact's self-description in V2-native format."""

    v1_path: str
    v2_mechanism: str
    v2_verb: str
    feeds_gates: list[str]  # e.g. ["nervous--govern/G1", "nervous--govern/G3"]

    # 7 interrogation dimensions
    existence: dict = field(default_factory=dict)  # {score, evidence}
    identity: str = ""
    structure: str = ""
    law: str = ""
    process: str = ""
    relation: str = ""
    teleology: str = ""

    # Signal mapping
    signals_consumes: list[str] = field(default_factory=list)
    signals_produces: list[str] = field(default_factory=list)

    # Axiom alignment
    axiom_alignment: list[AxiomClaim] = field(default_factory=list)

    # Documentation-specific evidence (Markdown/YAML/JSON/SOP analysis)
    documentation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "identity": {
                "v1_path": self.v1_path,
                "v2_mechanism": self.v2_mechanism,
                "v2_verb": self.v2_verb,
                "feeds_gates": self.feeds_gates,
            },
            "testimony": {
                "existence": self.existence,
                "identity": self.identity,
                "structure": self.structure,
                "law": self.law,
                "process": self.process,
                "relation": self.relation,
                "teleology": self.teleology,
            },
            "signals": {
                "consumes": self.signals_consumes,
                "produces": self.signals_produces,
            },
            "axiom_alignment": [a.to_dict() for a in self.axiom_alignment],
        }
        if self.documentation:
            data["documentation"] = self.documentation
        return data


# ---------------------------------------------------------------------------
# Counter-testimony types (V2 expectations)
# ---------------------------------------------------------------------------


@dataclass
class CounterTestimony:
    """V2 gate contract's expectations for a V1 artifact."""

    v1_path: str
    v2_mechanism: str
    v2_verb: str
    gate_source: str  # filename of the gate contract

    # 7 expectation dimensions (same structure as testimony)
    existence: dict = field(default_factory=dict)  # {required, expected_lines, note}
    identity: str = ""
    structure: str = ""
    law: str = ""
    process: str = ""
    relation: str = ""
    teleology: str = ""

    # Expected signals
    expected_consumes: list[str] = field(default_factory=list)
    expected_produces: list[str] = field(default_factory=list)

    # Flagged defects from gate contract
    defects_flagged: list[str] = field(default_factory=list)

    # Which gates this feeds
    gates_served: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "identity": {
                "v1_path": self.v1_path,
                "v2_mechanism": self.v2_mechanism,
                "v2_verb": self.v2_verb,
                "gate_source": self.gate_source,
            },
            "expectation": {
                "existence": self.existence,
                "identity": self.identity,
                "structure": self.structure,
                "law": self.law,
                "process": self.process,
                "relation": self.relation,
                "teleology": self.teleology,
            },
            "signals": {
                "expected_consumes": self.expected_consumes,
                "expected_produces": self.expected_produces,
            },
            "defects_flagged": self.defects_flagged,
            "gates_served": self.gates_served,
        }


# ---------------------------------------------------------------------------
# Rectification types
# ---------------------------------------------------------------------------


@dataclass
class DimensionVerdict:
    """Rectification result for a single interrogation dimension."""

    dimension: str
    verdict: Verdict
    v1_says: str = ""
    v2_says: str = ""
    actuality: str = ""
    remediation: str = ""

    def to_dict(self) -> dict:
        d = {
            "dimension": self.dimension,
            "verdict": self.verdict.value,
            "v1": self.v1_says,
            "v2": self.v2_says,
            "actuality": self.actuality,
        }
        if self.remediation:
            d["remediation"] = self.remediation
        return d


@dataclass
class RemediationItem:
    """A single actionable item from rectification."""

    action: str
    gate: str  # gate check ID, e.g. "nervous--govern/G1"
    priority: RemediationPriority
    item_type: RemediationType
    source_path: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "gate": self.gate,
            "priority": self.priority.value,
            "type": self.item_type.value,
            "source_path": self.source_path,
        }


@dataclass
class RectificationReport:
    """Full rectification report for a single gate contract."""

    gate_name: str
    gate_status: str
    timestamp: str = ""

    # Coverage
    v1_modules_claimed: int = 0
    testified: int = 0
    counter_testified: int = 0
    orphaned: int = 0

    # Per-dimension verdicts (keyed by V1 module path)
    module_verdicts: dict[str, list[DimensionVerdict]] = field(default_factory=dict)

    # Remediation items
    remediation: list[RemediationItem] = field(default_factory=list)

    # Orphan report
    orphan_report: list[OrphanEntry] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def alignment_score(self) -> float:
        """Fraction of dimension verdicts that are ALIGNED."""
        all_verdicts = [v for vs in self.module_verdicts.values() for v in vs]
        if not all_verdicts:
            return 0.0
        aligned = sum(1 for v in all_verdicts if v.verdict == Verdict.ALIGNED)
        return aligned / len(all_verdicts)

    def to_dict(self) -> dict:
        return {
            "gate": self.gate_name,
            "gate_status": self.gate_status,
            "timestamp": self.timestamp,
            "coverage": {
                "v1_modules_claimed": self.v1_modules_claimed,
                "testified": self.testified,
                "counter_testified": self.counter_testified,
                "orphaned": self.orphaned,
            },
            "alignment_score": round(self.alignment_score, 3),
            "dimensions": {
                path: [v.to_dict() for v in verdicts]
                for path, verdicts in self.module_verdicts.items()
            },
            "remediation": [r.to_dict() for r in self.remediation],
            "orphan_report": [o.to_dict() for o in self.orphan_report],
        }
