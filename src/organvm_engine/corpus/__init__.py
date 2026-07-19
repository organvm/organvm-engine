"""Corpus knowledge graph — computational bridge between theory and implementation.

Connects the post-flood constitutional corpus (.zettel-index.yaml) to ORGAN-I
implementation repos via seed.yaml `implements` fields. Produces a navigable
JSON graph of concept → document → implementation relationships.

Pipeline: scan → extract → link → render
  1. Scanner reads .zettel-index.yaml for transcript/concept nodes
  2. Extractor reads Layer 2 frontmatter for EXTRACTED_FROM edges
  3. Linker reads seed.yaml implements[] for IMPLEMENTS edges
  4. Renderer produces corpus-graph.json + gap report
"""

from organvm_engine.corpus.governance_lineage import (
    REVIEWED_EDGE_TYPES,
    ZOOM_LEVELS,
    finalize_state,
    process_child,
)
from organvm_engine.corpus.graph import CorpusGraph
from organvm_engine.corpus.scanner import scan_corpus

__all__ = [
    "CorpusGraph",
    "REVIEWED_EDGE_TYPES",
    "ZOOM_LEVELS",
    "finalize_state",
    "process_child",
    "scan_corpus",
]
