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
"""

from __future__ import annotations

import ast
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

    # Analyze the artifact
    if fs_path.is_dir():
        stats = _dir_stats(fs_path)
    elif fs_path.exists():
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

    # Infer signals
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
