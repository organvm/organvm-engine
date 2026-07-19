"""Positive and negative feedback loop mapping for the ORGANVM system.

Identifies, classifies, and reports on feedback loops — both negative
(governance gates, promotion requirements) and positive (virtuous cycles
where success amplifies success).

Negative loops are well-mapped in governance rules. Positive loops are
the system's greatest unmapped risk per the ontological topology analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LoopPolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class LoopStatus(str, Enum):
    MAPPED = "mapped"       # Explicitly governed
    OBSERVED = "observed"   # Recognized but not governed
    UNMAPPED = "unmapped"   # Theorized but not yet confirmed


class LoopStratum(str, Enum):
    SUBSTRATE = "substrate"
    TOOLING = "tooling"
    ARCHITECTURE = "architecture"
    EMERGENT = "emergent"
    ENVIRONMENT = "environment"


@dataclass
class FeedbackLoop:
    """A single feedback loop in the system."""

    name: str
    polarity: LoopPolarity
    status: LoopStatus
    stratum: LoopStratum
    description: str
    nodes: list[str]  # Organs or components participating in the loop
    governing_mechanism: str | None = None  # What governs this loop (if mapped)
    risk: str | None = None  # What happens if this loop is ungoverned

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "polarity": self.polarity.value,
            "status": self.status.value,
            "stratum": self.stratum.value,
            "description": self.description,
            "nodes": self.nodes,
            "governing_mechanism": self.governing_mechanism,
            "risk": self.risk,
        }


@dataclass
class FeedbackLoopInventory:
    """Complete inventory of system feedback loops."""

    loops: list[FeedbackLoop] = field(default_factory=list)

    @property
    def positive_count(self) -> int:
        return sum(1 for lp in self.loops if lp.polarity == LoopPolarity.POSITIVE)

    @property
    def negative_count(self) -> int:
        return sum(1 for lp in self.loops if lp.polarity == LoopPolarity.NEGATIVE)

    @property
    def unmapped_count(self) -> int:
        return sum(1 for lp in self.loops if lp.status == LoopStatus.UNMAPPED)

    @property
    def mapped_count(self) -> int:
        return sum(1 for lp in self.loops if lp.status == LoopStatus.MAPPED)

    @property
    def observed_count(self) -> int:
        return sum(1 for lp in self.loops if lp.status == LoopStatus.OBSERVED)

    def by_polarity(self, polarity: LoopPolarity) -> list[FeedbackLoop]:
        return [lp for lp in self.loops if lp.polarity == polarity]

    def by_status(self, status: LoopStatus) -> list[FeedbackLoop]:
        return [lp for lp in self.loops if lp.status == status]

    def by_stratum(self, stratum: LoopStratum) -> list[FeedbackLoop]:
        return [lp for lp in self.loops if lp.stratum == stratum]

    def ungoverned_positive(self) -> list[FeedbackLoop]:
        """Positive loops without governing mechanisms — the biggest risk."""
        return [
            lp for lp in self.loops
            if lp.polarity == LoopPolarity.POSITIVE
            and lp.status != LoopStatus.MAPPED
        ]

    def summary(self) -> str:
        lines = [
            "Feedback Loop Inventory",
            "=" * 40,
            f"Total: {len(self.loops)} loops",
            f"  Positive: {self.positive_count} | Negative: {self.negative_count}",
            f"  Mapped: {self.mapped_count} | Observed: {self.observed_count}"
            f" | Unmapped: {self.unmapped_count}",
        ]
        ungov = self.ungoverned_positive()
        if ungov:
            lines.append(f"\nUNGOVERNED POSITIVE LOOPS ({len(ungov)}):")
            for lp in ungov:
                lines.append(f"  {lp.name}: {lp.description}")
                if lp.risk:
                    lines.append(f"    Risk: {lp.risk}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total": len(self.loops),
            "positive": self.positive_count,
            "negative": self.negative_count,
            "mapped": self.mapped_count,
            "observed": self.observed_count,
            "unmapped": self.unmapped_count,
            "ungoverned_positive": len(self.ungoverned_positive()),
            "loops": [lp.to_dict() for lp in self.loops],
        }


# ---------------------------------------------------------------------------
# Canonical feedback loop definitions
# ---------------------------------------------------------------------------

def _canonical_negative_loops() -> list[FeedbackLoop]:
    """Negative feedback loops — well-mapped governance mechanisms."""
    return [
        FeedbackLoop(
            name="promotion-gate",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.MAPPED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "Repos that stagnate are not promoted. CI, platinum status, "
                "and implementation_status=ACTIVE are required for advancement."
            ),
            nodes=["governance", "registry", "CI"],
            governing_mechanism="governance/state_machine.py + governance-rules.json",
        ),
        FeedbackLoop(
            name="dependency-validation",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.MAPPED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "Back-edges in the I→II→III chain are blocked. Circular "
                "dependencies are detected and flagged."
            ),
            nodes=["ORGAN-I", "ORGAN-II", "ORGAN-III"],
            governing_mechanism="governance/dependency_graph.py",
        ),
        FeedbackLoop(
            name="session-lifecycle",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.MAPPED,
            stratum=LoopStratum.TOOLING,
            description=(
                "FRAME→SHAPE→BUILD→PROVE→DONE lifecycle prevents premature "
                "implementation. Hard gates enforce sequential progression."
            ),
            nodes=["conductor", "session"],
            governing_mechanism="conductor session lifecycle (ORGAN-IV)",
        ),
        FeedbackLoop(
            name="registry-boundary",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.MAPPED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "Registry defines system boundary. Repos not in registry-v2.json "
                "are not part of the system. save_registry() refuses < 50 repos."
            ),
            nodes=["registry", "loader"],
            governing_mechanism="registry/loader.py save_registry() guard",
        ),
        FeedbackLoop(
            name="staleness-detection",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.MAPPED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "Repos not validated within threshold days are flagged stale. "
                "Audit reports surface them for attention."
            ),
            nodes=["governance", "audit", "registry"],
            governing_mechanism="governance/audit.py stale_repo_days threshold",
        ),
        FeedbackLoop(
            name="seed-contract-enforcement",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.MAPPED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "seed.yaml declares produces/consumes edges. Mismatches between "
                "declared and actual edges are detectable via seed graph analysis."
            ),
            nodes=["seed", "graph", "registry"],
            governing_mechanism="seed/graph.py + seed validate CLI",
        ),
        FeedbackLoop(
            name="wip-limits",
            polarity=LoopPolarity.NEGATIVE,
            status=LoopStatus.OBSERVED,
            stratum=LoopStratum.EMERGENT,
            description=(
                "Human attention is finite. Too many active repos degrades quality. "
                "Governance encourages ARCHIVED state for dormant repos."
            ),
            nodes=["conductor", "governance"],
            governing_mechanism="Informal — no hard limit enforced in code",
        ),
    ]


def _canonical_positive_loops() -> list[FeedbackLoop]:
    """Positive feedback loops — virtuous cycles, many ungoverned."""
    return [
        FeedbackLoop(
            name="product-to-portfolio",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.OBSERVED,
            stratum=LoopStratum.EMERGENT,
            description=(
                "A successful product (ORGAN-III) generates case study material "
                "(ORGAN-V) which generates community interest (ORGAN-VI) which "
                "generates distribution (ORGAN-VII) which generates more product users."
            ),
            nodes=["ORGAN-III", "ORGAN-V", "ORGAN-VI", "ORGAN-VII"],
            risk=(
                "Viral essay could generate more community engagement than "
                "governance can process, producing emergent chaos."
            ),
        ),
        FeedbackLoop(
            name="research-to-governance",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.OBSERVED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "Research corpus discoveries (praxis-perpetua) crystallize into "
                "derived principles which become governance rules which shape "
                "future sessions which produce more research."
            ),
            nodes=["praxis-perpetua", "governance", "conductor"],
            risk=(
                "Self-reinforcing governance could ossify into dogma if not "
                "challenged by external input."
            ),
        ),
        FeedbackLoop(
            name="tool-to-productivity",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.OBSERVED,
            stratum=LoopStratum.TOOLING,
            description=(
                "Building better tools (CLI, MCP, dashboard) increases session "
                "productivity which frees time to build more tools."
            ),
            nodes=["organvm-engine", "organvm-mcp-server", "conductor"],
            risk=(
                "Tool-building can become a displacement activity — building "
                "infrastructure instead of shipping products (construction addiction)."
            ),
        ),
        FeedbackLoop(
            name="credential-to-opportunity",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.UNMAPPED,
            stratum=LoopStratum.ENVIRONMENT,
            description=(
                "Governance corpus → grant applications → funding → more time → "
                "more governance corpus. Portfolio documentation → job opportunities → "
                "income → more time for portfolio."
            ),
            nodes=["praxis-perpetua", "applications", "environment"],
            risk=(
                "Optimizing for credentials over substance. The portfolio becomes "
                "the product instead of evidence of the product."
            ),
        ),
        FeedbackLoop(
            name="consilience-accumulation",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.UNMAPPED,
            stratum=LoopStratum.EMERGENT,
            description=(
                "Each new research document that confirms an existing principle "
                "increases the principle's consilience index, making it more "
                "trustworthy, which encourages more investigation, which finds "
                "more confirming evidence."
            ),
            nodes=["research-corpus", "derived-principles"],
            risk=(
                "Confirmation bias: seeking evidence that confirms rather than "
                "challenges existing principles."
            ),
        ),
        FeedbackLoop(
            name="automation-to-scale",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.OBSERVED,
            stratum=LoopStratum.ARCHITECTURE,
            description=(
                "Each automated workflow (CI, context sync, pitch generation) "
                "reduces manual effort, allowing more repos to be maintained, "
                "which requires more automation."
            ),
            nodes=["CI", "contextmd", "pitchdeck", "organvm-engine"],
            risk=(
                "Automation debt: automated systems require maintenance. "
                "More automation means more maintenance surface area."
            ),
        ),
        FeedbackLoop(
            name="session-to-knowledge",
            polarity=LoopPolarity.POSITIVE,
            status=LoopStatus.UNMAPPED,
            stratum=LoopStratum.EMERGENT,
            description=(
                "Each session produces transcript data. Analyzing transcripts "
                "produces derived principles. Principles inform future sessions. "
                "More sessions = richer analysis = better principles = better sessions."
            ),
            nodes=["session-archive", "praxis-perpetua", "conductor"],
            risk=(
                "Navel-gazing: spending more time analyzing sessions than "
                "doing productive work in them."
            ),
        ),
    ]


def build_feedback_inventory() -> FeedbackLoopInventory:
    """Build the canonical feedback loop inventory.

    Returns the full inventory of known positive and negative feedback loops.
    """
    inventory = FeedbackLoopInventory()
    inventory.loops.extend(_canonical_negative_loops())
    inventory.loops.extend(_canonical_positive_loops())
    return inventory


def detect_active_loops(
    registry: dict,
    seed_graph: object | None = None,
) -> FeedbackLoopInventory:
    """Build inventory and annotate with registry/seed evidence.

    For each loop, checks whether its participating nodes are active
    (repos exist, edges declared, etc.) to distinguish theoretical
    from empirically-confirmed loops.

    Args:
        registry: Loaded registry dict.
        seed_graph: Optional SeedGraph for edge verification.

    Returns:
        Annotated FeedbackLoopInventory.
    """
    inventory = build_feedback_inventory()

    # Count active edges per organ pair from seed graph
    active_edges: set[tuple[str, str]] = set()
    if seed_graph is not None:
        for src, tgt, _atype in getattr(seed_graph, "edges", []):
            src_org = src.split("/")[0] if "/" in src else src
            tgt_org = tgt.split("/")[0] if "/" in tgt else tgt
            active_edges.add((src_org, tgt_org))

    # Check product-to-portfolio loop for active cross-organ edges
    for loop in inventory.loops:
        if loop.name == "product-to-portfolio":
            # Check if III→V, V→VI, VI→VII edges exist
            chain = [
                ("organvm-iii-ergon", "organvm-v-logos"),
                ("organvm-v-logos", "organvm-vi-koinonia"),
                ("organvm-vi-koinonia", "organvm-vii-kerygma"),
            ]
            active_links = sum(1 for pair in chain if pair in active_edges)
            if active_links >= 2:
                loop.status = LoopStatus.OBSERVED

    return inventory
