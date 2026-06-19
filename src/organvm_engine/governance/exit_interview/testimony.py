"""Phase 1: V1 Testimony — exit interview generator.

For each V1 artifact in the supply map, generate a V2-native testimony
using the 7 interrogation dimensions adapted for source code analysis.

Automated extraction (no human input):
  - existence: file stats, line count, modification time, class/function count
  - structure: AST analysis (classes, functions, imports)
  - relation: import graph (what it imports, what would import it)
  - process: CLI entry point detection, signal type annotations

Heuristic extraction (best-effort, may need human review):
  - identity: module docstring + top-level class names
  - law: docstring references to governance rules, enforcement language
  - teleology: axiom mapping from naming conventions + purpose signals
  - axiom_alignment: best-effort from naming + docstrings

Documentation-only artifacts (repos/directories with markdown but no Python)
are analyzed as prose rather than source: headings become structure, the H1
title becomes identity, normative/axiom language becomes law/teleology, and
markdown links become relations. This keeps the seven dimensions populated for
spec, SEED, and corpus repos that carry their governance in documents.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path

from organvm_engine.governance.exit_interview.schemas import (
    AxiomClaim,
    SupplyEntry,
    Testimony,
)

# Axiom keywords — heuristics for mapping modules to SEED.md axioms
_AXIOM_SIGNALS: dict[str, list[str]] = {
    "A1": ["transform", "work", "output", "input", "pipeline"],
    "A2": ["compose", "chain", "pipe", "cascade", "dispatch"],
    "A3": ["persist", "maintain", "heal", "repair", "daemon"],
    "A4": ["adapt", "evolve", "migrate", "evolut", "mutate"],
    "A5": ["minimal", "prune", "remove", "clean", "simplif"],
    "A6": ["govern", "rule", "constrain", "enforce", "promot", "audit", "sanction"],
    "A7": ["individual", "primacy", "operator", "user", "human"],
    "A8": ["topolog", "plast", "fuse", "split", "dissolve", "restructur"],
    "A9": ["lineage", "inherit", "history", "preserve", "alchemi", "testament"],
}


# ---------------------------------------------------------------------------
# File-level analysis
# ---------------------------------------------------------------------------


def _file_stats(path: Path) -> dict:
    """Basic file statistics."""
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    try:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        line_count = 0
    return {
        "exists": True,
        "lines": line_count,
        "size_bytes": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _ast_summary(path: Path) -> dict:
    """AST analysis: count classes, functions, imports."""
    if not path.exists() or path.suffix != ".py":
        return {}
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return {"parse_error": True}

    classes = []
    functions = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if not isinstance(getattr(node, "_parent", None), ast.ClassDef):
                functions.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    return {
        "classes": classes,
        "functions": functions,
        "imports": imports,
        "class_count": len(classes),
        "function_count": len(functions),
    }


def _extract_docstring(path: Path) -> str:
    """Extract the module-level docstring."""
    if not path.exists() or path.suffix != ".py":
        return ""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        return ast.get_docstring(tree) or ""
    except (SyntaxError, OSError, UnicodeDecodeError):
        return ""


def _dir_stats(dir_path: Path) -> dict:
    """Aggregate stats for a directory of Python files."""
    if not dir_path.is_dir():
        return {"exists": False}

    total_lines = 0
    total_files = 0
    all_classes: list[str] = []
    all_functions: list[str] = []
    all_imports: list[str] = []

    for py_file in sorted(dir_path.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        total_files += 1
        stats = _file_stats(py_file)
        total_lines += stats.get("lines", 0)
        ast_info = _ast_summary(py_file)
        all_classes.extend(ast_info.get("classes", []))
        all_functions.extend(ast_info.get("functions", []))
        all_imports.extend(ast_info.get("imports", []))

    # Get the package docstring from __init__.py
    init_doc = _extract_docstring(dir_path / "__init__.py")

    return {
        "exists": True,
        "files": total_files,
        "lines": total_lines,
        "classes": all_classes,
        "functions": all_functions,
        "imports": sorted(set(all_imports)),
        "class_count": len(all_classes),
        "function_count": len(all_functions),
        "docstring": init_doc,
    }


# ---------------------------------------------------------------------------
# Dimension extractors
# ---------------------------------------------------------------------------


def _extract_existence(stats: dict) -> dict:
    """DIAG-001 adapted: does this artifact physically exist?"""
    if not stats.get("exists"):
        return {"score": 0.0, "evidence": "file/directory not found"}
    parts = []
    if "lines" in stats:
        parts.append(f"{stats['lines']} lines")
    if "files" in stats:
        parts.append(f"{stats['files']} files")
    if "class_count" in stats:
        parts.append(f"{stats['class_count']} classes")
    if "function_count" in stats:
        parts.append(f"{stats['function_count']} functions")
    if "last_modified" in stats:
        parts.append(f"modified {stats['last_modified']}")
    return {"score": 1.0, "evidence": ", ".join(parts)}


def _extract_identity(stats: dict) -> str:
    """DIAG-002 adapted: what is this artifact's semantic identity?"""
    docstring = stats.get("docstring", "")
    if docstring:
        # Take first line/sentence of docstring
        return docstring.split("\n")[0].strip().rstrip(".")

    classes = stats.get("classes", [])
    if classes:
        return f"Defines: {', '.join(classes[:5])}"

    return "No docstring or class definitions found"


def _extract_structure(stats: dict) -> str:
    """DIAG-003 adapted: internal organization."""
    parts = []
    if stats.get("class_count"):
        parts.append(f"{stats['class_count']} classes ({', '.join(stats['classes'][:5])})")
    if stats.get("function_count"):
        parts.append(f"{stats['function_count']} top-level functions")
    if stats.get("files"):
        parts.append(f"{stats['files']} Python files")
    return "; ".join(parts) if parts else "No internal structure detected"


def _extract_law(stats: dict) -> str:
    """DIAG-004 adapted: what rules does this artifact enforce or obey?"""
    docstring = stats.get("docstring", "")
    imports = stats.get("imports", [])

    law_signals = []
    # Check for governance-related imports
    gov_imports = [i for i in imports if "governance" in i or "rules" in i or "constraint" in i]
    if gov_imports:
        law_signals.append(f"imports from: {', '.join(gov_imports[:3])}")

    # Check docstring for enforcement language
    enforcement_words = ["enforce", "validate", "constrain", "prohibit", "require", "must"]
    doc_lower = docstring.lower()
    found = [w for w in enforcement_words if w in doc_lower]
    if found:
        law_signals.append(f"enforcement language in docstring: {', '.join(found)}")

    return "; ".join(law_signals) if law_signals else "No explicit governance references detected"


def _extract_relation(stats: dict) -> str:
    """DIAG-006 adapted: import graph connections."""
    imports = stats.get("imports", [])
    # Filter to organvm_engine imports only
    internal = sorted({i for i in imports if "organvm_engine" in i})
    if internal:
        # Simplify to module names
        modules = sorted({i.split(".")[-1] for i in internal if len(i.split(".")) > 1})
        return f"imports from: {', '.join(modules[:10])}"
    return "No internal imports detected"


def _extract_process(stats: dict) -> str:
    """DIAG-005 adapted: CLI/workflow participation."""
    functions = stats.get("functions", [])
    # Look for cmd_ prefixed functions (CLI entry points)
    cli_funcs = [f for f in functions if f.startswith("cmd_")]
    if cli_funcs:
        return f"CLI entry points: {', '.join(cli_funcs[:5])}"

    # Look for public API functions
    public = [f for f in functions if not f.startswith("_")]
    if public:
        return f"Public API: {', '.join(public[:5])}"

    return "No CLI or public API functions detected"


def _extract_teleology(stats: dict) -> str:
    """DIAG-007 adapted: which axiom does this serve?"""
    docstring = (stats.get("docstring", "") or "").lower()
    classes = " ".join(stats.get("classes", [])).lower()
    functions = " ".join(stats.get("functions", [])).lower()
    combined = f"{docstring} {classes} {functions}"

    matches = []
    for axiom, signals in _AXIOM_SIGNALS.items():
        if any(sig in combined for sig in signals):
            matches.append(axiom)

    if matches:
        return f"Serves {', '.join(matches)}"
    return "No axiom alignment detected from naming/docstrings"


def _extract_axiom_claims(stats: dict) -> list[AxiomClaim]:
    """Best-effort axiom alignment from code analysis."""
    docstring = (stats.get("docstring", "") or "").lower()
    classes = " ".join(stats.get("classes", [])).lower()
    functions = " ".join(stats.get("functions", [])).lower()
    combined = f"{docstring} {classes} {functions}"

    claims = []
    for axiom, signals in _AXIOM_SIGNALS.items():
        matching_signals = [sig for sig in signals if sig in combined]
        if matching_signals:
            claims.append(
                AxiomClaim(
                    axiom=axiom,
                    claim=f"Code references: {', '.join(matching_signals)}",
                    evidence=f"Found in {'docstring' if any(s in docstring for s in matching_signals) else 'code identifiers'}",
                ),
            )
    return claims


# ---------------------------------------------------------------------------
# Signal type inference
# ---------------------------------------------------------------------------

# Map module-level patterns to V2 signal types
_SIGNAL_TYPE_PATTERNS: dict[str, list[str]] = {
    "RULE": ["rule", "governance", "constraint", "policy", "enforce"],
    "KNOWLEDGE": ["registry", "schema", "ontolog", "config", "definition"],
    "STATE": ["state", "status", "metric", "score", "health"],
    "VALIDATION": ["validate", "check", "verify", "audit", "test"],
    "TRACE": ["log", "history", "trace", "record", "fossil"],
    "CONTRACT": ["schema", "seed", "contract", "spec"],
    "REPORT": ["report", "summary", "digest", "overview"],
    "SYNTHESIS": ["synthesize", "merge", "compose", "combine", "aggregate"],
    "CONSTRAINT": ["constraint", "limit", "bound", "prohibit", "sanction"],
    "SOURCE": ["source", "ingest", "intake", "import", "read"],
}


def _infer_signals(stats: dict) -> tuple[list[str], list[str]]:
    """Infer consumed and produced signal types from code patterns."""
    imports = " ".join(stats.get("imports", [])).lower()
    functions = " ".join(stats.get("functions", [])).lower()
    docstring = (stats.get("docstring", "") or "").lower()
    combined = f"{imports} {functions} {docstring}"

    # Heuristic: imports suggest consumption, exports suggest production
    consumes = []
    produces = []
    for signal_type, patterns in _SIGNAL_TYPE_PATTERNS.items():
        if any(p in combined for p in patterns):
            # If it's in imports, it consumes; if in functions, it produces
            if any(p in imports for p in patterns):
                consumes.append(signal_type)
            if any(p in functions for p in patterns):
                produces.append(signal_type)
            # If only in docstring, assume both
            if signal_type not in consumes and signal_type not in produces:
                consumes.append(signal_type)

    return sorted(set(consumes)), sorted(set(produces))


# ---------------------------------------------------------------------------
# Documentation analysis (documentation-only repos)
# ---------------------------------------------------------------------------

# Suffixes that mark an artifact as documentation rather than source code.
_DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}

# Directories pruned when classifying/scanning a candidate documentation tree.
_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_AXIOM_REF_RE = re.compile(r"\bA[1-9]\b")

# RFC-2119-style normative keywords — the "law" a document imposes.
_NORMATIVE_WORDS = [
    "must not", "must", "shall not", "shall", "required", "should not",
    "should", "prohibited", "forbidden", "may not", "mandatory",
]


def _is_doc_file(path: Path) -> bool:
    """True if a path is a documentation file by suffix."""
    return path.suffix.lower() in _DOC_SUFFIXES


def _walk_files(dir_path: Path):
    """Yield files under dir_path, pruning vendored/hidden directories."""
    for p in dir_path.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(dir_path).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        yield p


def _is_doc_directory(dir_path: Path) -> bool:
    """True if a directory contains documentation but no Python source.

    Short-circuits to False on the first ``.py`` file found — a tree with any
    Python is analyzed as source, not documentation.
    """
    has_doc = False
    for p in _walk_files(dir_path):
        if p.suffix == ".py":
            return False
        if _is_doc_file(p):
            has_doc = True
    return has_doc


def _parse_markdown(text: str) -> tuple[list[tuple[int, str]], list[str], int]:
    """Extract (headings, links, fenced-code-block count) from markdown text.

    Headings inside fenced code blocks are ignored.
    """
    headings: list[tuple[int, str]] = []
    code_blocks = 0
    in_fence = False
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith(("```", "~~~")):
            if not in_fence:
                code_blocks += 1
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(raw.rstrip())
        if match:
            headings.append((len(match.group(1)), match.group(2).strip()))
    links = _LINK_RE.findall(text)
    return headings, links, code_blocks


def _doc_title(text: str, headings: list[tuple[int, str]]) -> str:
    """Best-effort document title: first H1, else first heading, else first line.

    Skips a leading YAML frontmatter block when falling back to the first line.
    """
    for level, heading in headings:
        if level == 1:
            return heading
    if headings:
        return headings[0][1]

    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                start = idx + 1
                break
    for line in lines[start:]:
        stripped = line.strip()
        if stripped:
            return stripped.lstrip("#").strip()
    return ""


def _doc_file_stats(path: Path) -> dict:
    """Documentation-aware stats for a single markdown/doc file."""
    if not path.exists():
        return {"exists": False, "doc": True}
    stat = path.stat()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = ""
    headings, links, code_blocks = _parse_markdown(text)
    return {
        "exists": True,
        "doc": True,
        "files": 1,
        "lines": len(text.splitlines()),
        "size_bytes": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "title": _doc_title(text, headings),
        "headings": headings,
        "heading_count": len(headings),
        "links": links,
        "code_blocks": code_blocks,
        "scan_text": text,
    }


def _doc_dir_stats(dir_path: Path) -> dict:
    """Aggregate documentation stats across a directory of doc files.

    Prefers a README/index title for the directory's identity, then any H1.
    """
    if not dir_path.is_dir():
        return {"exists": False, "doc": True}

    doc_files = sorted(p for p in _walk_files(dir_path) if _is_doc_file(p))
    if not doc_files:
        return {"exists": True, "doc": True, "files": 0, "lines": 0}

    total_lines = 0
    all_headings: list[tuple[int, str]] = []
    all_links: list[str] = []
    code_blocks = 0
    last_modified = ""
    preferred_title = ""
    scan_parts: list[str] = []

    for doc in doc_files:
        stats = _doc_file_stats(doc)
        total_lines += stats.get("lines", 0)
        all_headings.extend(stats.get("headings", []))
        all_links.extend(stats.get("links", []))
        code_blocks += stats.get("code_blocks", 0)
        scan_parts.append(stats.get("scan_text", ""))
        modified = stats.get("last_modified", "")
        if modified > last_modified:
            last_modified = modified
        if not preferred_title and doc.stem.lower() in {"readme", "index"}:
            preferred_title = stats.get("title", "")

    title = preferred_title
    if not title:
        title = next((h for level, h in all_headings if level == 1), "")
    if not title and all_headings:
        title = all_headings[0][1]

    return {
        "exists": True,
        "doc": True,
        "files": len(doc_files),
        "lines": total_lines,
        "last_modified": last_modified,
        "title": title,
        "headings": all_headings,
        "heading_count": len(all_headings),
        "links": all_links,
        "code_blocks": code_blocks,
        "scan_text": "\n".join(scan_parts),
    }


def _normative_terms(text: str) -> list[str]:
    """Return RFC-2119 normative keywords present in text (word-boundary match)."""
    low = text.lower()
    found = []
    for word in _NORMATIVE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            found.append(word)
    return found


def _doc_axioms(text: str) -> list[str]:
    """Axioms a document touches: keyword signals plus explicit A1–A9 references."""
    low = text.lower()
    matches = {ax for ax, signals in _AXIOM_SIGNALS.items() if any(s in low for s in signals)}
    matches.update(_AXIOM_REF_RE.findall(text))
    return sorted(matches)


def _extract_doc_existence(stats: dict) -> dict:
    """DIAG-001 adapted for documentation: does this prose physically exist?"""
    if not stats.get("exists") or not stats.get("files"):
        return {"score": 0.0, "evidence": "documentation not found"}
    parts = [f"{stats['files']} doc file{'s' if stats['files'] != 1 else ''}"]
    if "lines" in stats:
        parts.append(f"{stats['lines']} lines")
    if stats.get("heading_count"):
        parts.append(f"{stats['heading_count']} headings")
    if stats.get("last_modified"):
        parts.append(f"modified {stats['last_modified']}")
    return {"score": 1.0, "evidence": ", ".join(parts)}


def _extract_doc_identity(stats: dict) -> str:
    """DIAG-002 adapted: the document title is its semantic identity."""
    title = stats.get("title", "")
    if title:
        return title.rstrip(".")
    return "Documentation artifact (no title or headings found)"


def _extract_doc_structure(stats: dict) -> str:
    """DIAG-003 adapted: sections and code examples as internal organization."""
    headings = stats.get("headings", [])
    parts = []
    if stats.get("files"):
        parts.append(f"{stats['files']} documents")
    if headings:
        top = [h for level, h in headings if level <= 2][:5]
        section_part = f"{len(headings)} sections"
        if top:
            section_part += f" ({', '.join(top)})"
        parts.append(section_part)
    if stats.get("code_blocks"):
        parts.append(f"{stats['code_blocks']} code blocks")
    return "; ".join(parts) if parts else "No document structure detected"


def _extract_doc_law(stats: dict) -> str:
    """DIAG-004 adapted: normative language and axiom references as imposed law."""
    text = stats.get("scan_text", "")
    signals = []
    normative = _normative_terms(text)
    if normative:
        signals.append(f"normative language: {', '.join(normative[:5])}")
    axioms = _AXIOM_REF_RE.findall(text)
    if axioms:
        signals.append(f"axiom references: {', '.join(sorted(set(axioms)))}")
    low = text.lower()
    gov_terms = [t for t in ("governance", "policy", "sanction", "promotion", "audit") if t in low]
    if gov_terms:
        signals.append(f"governance terms: {', '.join(gov_terms)}")
    return "; ".join(signals) if signals else "No normative or governance language detected"


def _extract_doc_process(stats: dict) -> str:
    """DIAG-005 adapted: documented procedures and runnable examples."""
    blocks = stats.get("code_blocks", 0)
    if blocks:
        return f"Documents {blocks} code/command example{'s' if blocks != 1 else ''}"
    procedural_words = ("usage", "install", "setup", "run", "command", "workflow", "step", "how to")
    procedural = [
        h for _level, h in stats.get("headings", [])
        if any(w in h.lower() for w in procedural_words)
    ]
    if procedural:
        return f"Procedural sections: {', '.join(procedural[:5])}"
    return "No procedural or executable content detected"


def _extract_doc_relation(stats: dict) -> str:
    """DIAG-006 adapted: markdown links as the document's connections."""
    links = stats.get("links", [])
    internal = sorted({
        link for link in links
        if not link.startswith(("http://", "https://", "mailto:", "#"))
    })
    if internal:
        names = sorted({Path(link).name or link for link in internal})
        return f"references: {', '.join(names[:10])}"
    external = [link for link in links if link.startswith(("http://", "https://"))]
    if external:
        return f"{len(external)} external link{'s' if len(external) != 1 else ''}"
    return "No document references detected"


def _extract_doc_teleology(stats: dict) -> str:
    """DIAG-007 adapted: which axiom does this documentation serve?"""
    axioms = _doc_axioms(stats.get("scan_text", ""))
    if axioms:
        return f"Serves {', '.join(axioms)}"
    return "No axiom alignment detected from documentation"


def _extract_doc_axiom_claims(stats: dict) -> list[AxiomClaim]:
    """Best-effort axiom alignment from documentation prose."""
    text = stats.get("scan_text", "")
    low = text.lower()
    claims = []
    for axiom, signals in _AXIOM_SIGNALS.items():
        matching = [s for s in signals if s in low]
        if matching:
            claims.append(
                AxiomClaim(
                    axiom=axiom,
                    claim=f"Documentation references: {', '.join(matching)}",
                    evidence="Found in documentation prose",
                ),
            )
    claimed = {c.axiom for c in claims}
    for axiom in sorted(set(_AXIOM_REF_RE.findall(text))):
        if axiom not in claimed:
            claims.append(
                AxiomClaim(
                    axiom=axiom,
                    claim="Explicit axiom reference in documentation",
                    evidence="Direct A-number mention",
                ),
            )
    return claims


def _infer_doc_signals(stats: dict) -> tuple[list[str], list[str]]:
    """Infer signal types a documentation artifact produces.

    Documentation is treated as a producer of KNOWLEDGE (and any other signal
    types its prose describes); it consumes nothing on its own.
    """
    text = stats.get("scan_text", "").lower()
    produces = {"KNOWLEDGE"}
    for signal_type, patterns in _SIGNAL_TYPE_PATTERNS.items():
        if any(p in text for p in patterns):
            produces.add(signal_type)
    return [], sorted(produces)


# ---------------------------------------------------------------------------
# Testimony generation
# ---------------------------------------------------------------------------


def generate_testimony(
    supply_entry: SupplyEntry,
    workspace_root: Path,
) -> Testimony:
    """Generate V2-native testimony for a single V1 artifact.

    Args:
        supply_entry: V1 module's supply map entry (path + gate claims).
        workspace_root: Filesystem root for resolving paths.
    """
    # Resolve the V1 path to a filesystem path
    repo_parts = supply_entry.repo.split("/")
    module_path = supply_entry.v1_path

    # Build filesystem path: workspace_root / repo / src/package / module
    # Handle engine modules: meta-organvm/organvm-engine → organvm-engine/src/organvm_engine/
    if "organvm-engine" in supply_entry.repo:
        fs_path = (
            workspace_root / repo_parts[0] / repo_parts[1]
            / "src" / "organvm_engine" / module_path
        )
    elif "organvm-ontologia" in supply_entry.repo:
        fs_path = (
            workspace_root / repo_parts[0] / repo_parts[1]
            / "src" / "organvm_ontologia" / module_path
        )
    else:
        fs_path = workspace_root / supply_entry.repo / module_path

    # Analyze the artifact. Documentation-only trees (markdown, no Python) are
    # read as prose; everything else is analyzed as Python source via AST.
    if fs_path.is_dir():
        if _is_doc_directory(fs_path):
            stats = _doc_dir_stats(fs_path)
        else:
            stats = _dir_stats(fs_path)
    elif fs_path.exists():
        if _is_doc_file(fs_path):
            stats = _doc_file_stats(fs_path)
        else:
            stats = _file_stats(fs_path)
            ast_info = _ast_summary(fs_path)
            stats.update(ast_info)
            stats["docstring"] = _extract_docstring(fs_path)
    else:
        stats = {"exists": False}

    # Get mechanism/verb from the primary demand (first gate claiming this)
    primary = supply_entry.demands[0] if supply_entry.demands else None
    mechanism = primary.mechanism if primary else "unknown"
    verb = primary.verb if primary else "unknown"

    # Build gate references
    feeds_gates = []
    for demand in supply_entry.demands:
        for gid in demand.gate_ids:
            feeds_gates.append(f"{demand.gate_name}/{gid}")

    # Infer signals and dimensions — documentation artifacts use prose-aware
    # extractors so the seven dimensions stay populated for doc-only repos.
    if stats.get("doc"):
        consumes, produces = _infer_doc_signals(stats)
        return Testimony(
            v1_path=f"{supply_entry.repo}/{module_path}",
            v2_mechanism=mechanism,
            v2_verb=verb,
            feeds_gates=sorted(set(feeds_gates)),
            existence=_extract_doc_existence(stats),
            identity=_extract_doc_identity(stats),
            structure=_extract_doc_structure(stats),
            law=_extract_doc_law(stats),
            process=_extract_doc_process(stats),
            relation=_extract_doc_relation(stats),
            teleology=_extract_doc_teleology(stats),
            signals_consumes=consumes,
            signals_produces=produces,
            axiom_alignment=_extract_doc_axiom_claims(stats),
        )

    consumes, produces = _infer_signals(stats)

    return Testimony(
        v1_path=f"{supply_entry.repo}/{module_path}",
        v2_mechanism=mechanism,
        v2_verb=verb,
        feeds_gates=sorted(set(feeds_gates)),
        existence=_extract_existence(stats),
        identity=_extract_identity(stats),
        structure=_extract_structure(stats),
        law=_extract_law(stats),
        process=_extract_process(stats),
        relation=_extract_relation(stats),
        teleology=_extract_teleology(stats),
        signals_consumes=consumes,
        signals_produces=produces,
        axiom_alignment=_extract_axiom_claims(stats),
    )


def generate_all_testimonies(
    supply_entries: dict[str, SupplyEntry],
    workspace_root: Path,
) -> dict[str, Testimony]:
    """Generate testimony for all V1 artifacts in the supply map.

    Returns dict keyed by V1 module path.
    """
    testimonies = {}
    for key, entry in supply_entries.items():
        testimonies[key] = generate_testimony(entry, workspace_root)
    return testimonies
