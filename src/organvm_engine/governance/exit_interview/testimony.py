"""Phase 1: V1 Testimony — exit interview generator.

For each V1 artifact in the supply map, generate a V2-native testimony
using the 7 interrogation dimensions adapted for source code and
documentation-corpus analysis.

Automated extraction (no human input):
  - existence: file stats, line count, modification time, class/function count
  - structure: AST analysis (classes, functions, imports)
  - relation: import graph (what it imports, what would import it)
  - process: CLI entry point detection, signal type annotations
  - documentation: word count, section structure, links, YAML/JSON coverage,
    SOP-to-module coverage

Heuristic extraction (best-effort, may need human review):
  - identity: module docstring + top-level class names
  - law: docstring references to governance rules, enforcement language
  - teleology: axiom mapping from naming conventions + purpose signals
  - axiom_alignment: best-effort from naming + docstrings
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

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

_DOCUMENTATION_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}
_STRUCTURED_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml"}
_DOC_SUFFIXES = _DOCUMENTATION_SUFFIXES | _STRUCTURED_SUFFIXES

_IGNORED_DOC_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_REFERENCE_LINK_RE = re.compile(r"^\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
_BARE_URL_RE = re.compile(r"https?://[^\s<>)]+")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")
_BACKTICK_PATH_RE = re.compile(r"`([^`]+)`")
_BARE_CODE_PATH_RE = re.compile(r"\b[\w./-]+\.(?:py|json|ya?ml|md)\b")

_SOP_FILENAME_RE = re.compile(
    r"^(SOP--|sop--|sop-|METADOC--|metadoc--|APPENDIX--|appendix--)",
    re.IGNORECASE,
)

_SCHEMA_MARKER_KEYS = {
    "$defs",
    "$id",
    "$schema",
    "definitions",
    "properties",
    "required",
    "schema",
    "type",
}

_GOVERNANCE_DATA_KEYS = {
    "consumes",
    "constraints",
    "defect",
    "dependencies",
    "dna",
    "gate",
    "governance",
    "identity",
    "metrics",
    "organ",
    "organs",
    "produces",
    "registry",
    "rules",
    "signal_inputs",
    "signal_outputs",
    "signals",
    "sources",
    "state",
}

_SOP_MODULE_FIELDS = {
    "applies_to",
    "code_modules",
    "governs",
    "modules",
    "paths",
    "targets",
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
# Documentation-level analysis
# ---------------------------------------------------------------------------


def _safe_read_text(path: Path) -> str:
    """Read text for analysis, replacing undecodable characters."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _display_path(path: Path, root: Path) -> str:
    """Stable path label for serialized evidence."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_analysis_files(path: Path) -> list[Path]:
    """List files under an artifact path, preserving .sops/ but skipping caches."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []

    files: list[Path] = []
    try:
        children = sorted(path.iterdir())
    except PermissionError:
        return []

    for child in children:
        if child.is_dir():
            if child.name in _IGNORED_DOC_DIRS:
                continue
            if child.name.startswith(".") and child.name != ".sops":
                continue
            files.extend(_iter_analysis_files(child))
        elif child.is_file():
            files.append(child)
    return files


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return YAML frontmatter and body for a Markdown document."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    frontmatter_lines = []
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            raw = "\n".join(frontmatter_lines)
            try:
                data = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                data = {}
            if not isinstance(data, dict):
                data = {}
            return data, "\n".join(lines[index + 1:])
        frontmatter_lines.append(line)

    return {}, text


def _extract_markdown_links(text: str) -> list[str]:
    """Extract Markdown, reference-style, and bare URL links from text."""
    links: list[str] = []

    for raw in _MARKDOWN_LINK_RE.findall(text):
        target = raw.strip().strip("<>")
        if " " in target:
            target = target.split()[0].strip("\"'")
        if target:
            links.append(target)

    links.extend(target.strip().strip("<>") for target in _REFERENCE_LINK_RE.findall(text))
    links.extend(target.rstrip(".,;:") for target in _BARE_URL_RE.findall(text))

    deduped: list[str] = []
    seen = set()
    for link in links:
        if link not in seen:
            deduped.append(link)
            seen.add(link)
    return deduped


def _is_external_link(target: str) -> bool:
    scheme = urlparse(target).scheme.lower()
    return scheme in {"http", "https", "mailto", "tel"}


def _internal_target_exists(source: Path, target: str) -> bool:
    clean_target = unquote(target.split("#", 1)[0].split("?", 1)[0]).strip()
    if not clean_target:
        return True

    candidate = Path(clean_target)
    if not candidate.is_absolute():
        candidate = source.parent / candidate

    if candidate.exists():
        return True
    if candidate.suffix:
        return False
    return candidate.with_suffix(".md").exists() or (candidate / "README.md").exists()


def _load_structured_data(path: Path) -> tuple[object | None, str]:
    """Parse YAML/JSON/JSONL files and return data plus an error string."""
    text = _safe_read_text(path)
    if not text:
        return None, "empty or unreadable"

    try:
        if path.suffix == ".json":
            return json.loads(text), ""
        if path.suffix == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            return rows, ""
        return yaml.safe_load(text), ""
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        return None, str(exc).splitlines()[0]


def _collect_mapping_keys(data: object) -> set[str]:
    """Collect top-level keys from structured data for schema/governance coverage."""
    if isinstance(data, dict):
        return {str(key) for key in data}
    if isinstance(data, list):
        keys: set[str] = set()
        for item in data[:100]:
            if isinstance(item, dict):
                keys.update(str(key) for key in item)
        return keys
    return set()


def _flatten_metadata_values(value: object) -> list[str]:
    """Flatten frontmatter fields into string values."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_metadata_values(item))
        return flattened
    if isinstance(value, dict):
        flattened = []
        for item in value.values():
            flattened.extend(_flatten_metadata_values(item))
        return flattened
    return [str(value)]


def _looks_like_module_path(value: str) -> bool:
    """Heuristic for paths that can identify governed code or data modules."""
    value = value.strip().strip("`").strip()
    if not value or "://" in value or value.startswith("#"):
        return False
    if any(char.isspace() for char in value):
        return False
    if value.endswith((".py", ".json", ".yaml", ".yml", ".md")):
        return True
    return "/" in value and not value.startswith(("http:", "https:", "mailto:"))


def _extract_governed_modules(text: str, frontmatter: dict) -> list[str]:
    """Infer which code/data modules a SOP governs."""
    candidates: list[str] = []

    for field in _SOP_MODULE_FIELDS:
        candidates.extend(_flatten_metadata_values(frontmatter.get(field)))

    searchable_text = _MARKDOWN_LINK_RE.sub("", text)
    searchable_text = _REFERENCE_LINK_RE.sub("", searchable_text)
    candidates.extend(match.group(1) for match in _BACKTICK_PATH_RE.finditer(searchable_text))
    candidates.extend(match.group(0) for match in _BARE_CODE_PATH_RE.finditer(searchable_text))

    modules = {
        candidate.strip().strip("`").strip()
        for candidate in candidates
        if _looks_like_module_path(candidate)
    }
    return sorted(modules)


def _is_sop_document(path: Path) -> bool:
    return path.parent.name == ".sops" or bool(_SOP_FILENAME_RE.match(path.name))


def _analyze_documentation(path: Path, workspace_root: Path) -> dict:
    """Analyze Markdown/YAML/JSON artifacts for documentation testimony."""
    if not path.exists():
        return {}

    files = [p for p in _iter_analysis_files(path) if p.suffix.lower() in _DOC_SUFFIXES]
    if not files:
        return {}

    markdown_files = [p for p in files if p.suffix.lower() in _DOCUMENTATION_SUFFIXES]
    structured_files = [p for p in files if p.suffix.lower() in _STRUCTURED_SUFFIXES]

    doc_lines = 0
    word_count = 0
    headings: list[tuple[int, str]] = []
    frontmatter_files: list[str] = []
    semantic_snippets: list[str] = []
    link_graph = {
        "internal": 0,
        "external": 0,
        "anchors": 0,
        "broken_internal": [],
        "external_domains": {},
        "internal_targets": [],
    }
    sop_files: list[str] = []
    governed_modules: dict[str, list[str]] = {}

    domain_counter: Counter[str] = Counter()
    internal_targets: list[str] = []
    broken_internal: list[str] = []

    for doc_path in markdown_files:
        text = _safe_read_text(doc_path)
        frontmatter, body = _split_frontmatter(text)
        rel_path = _display_path(doc_path, workspace_root)
        doc_lines += len(text.splitlines())
        word_count += len(_WORD_RE.findall(body))

        if frontmatter:
            frontmatter_files.append(rel_path)
            semantic_snippets.extend(str(key) for key in frontmatter)

        file_headings = [
            (len(match.group(1)), match.group(2).strip())
            for match in _HEADING_RE.finditer(body)
        ]
        headings.extend(file_headings)
        semantic_snippets.extend(title for _level, title in file_headings[:10])
        semantic_snippets.append(Path(doc_path.stem).name)
        semantic_snippets.append(body[:2000])

        for link in _extract_markdown_links(body):
            if link.startswith("#"):
                link_graph["anchors"] += 1
                continue
            if _is_external_link(link):
                link_graph["external"] += 1
                hostname = urlparse(link).hostname
                if hostname:
                    domain_counter[hostname] += 1
                continue

            link_graph["internal"] += 1
            internal_targets.append(link)
            if not _internal_target_exists(doc_path, link):
                broken_internal.append(f"{rel_path} -> {link}")

        if _is_sop_document(doc_path):
            sop_files.append(rel_path)
            for module in _extract_governed_modules(body, frontmatter):
                governed_modules.setdefault(module, []).append(rel_path)

    structured_valid = 0
    structured_invalid: list[str] = []
    schema_marked_files: list[str] = []
    governance_data_files: list[str] = []
    structured_key_counter: Counter[str] = Counter()

    for structured_path in structured_files:
        rel_path = _display_path(structured_path, workspace_root)
        text = _safe_read_text(structured_path)
        doc_lines += len(text.splitlines())
        semantic_snippets.append(Path(structured_path.stem).name)

        data, error = _load_structured_data(structured_path)
        if error:
            structured_invalid.append(f"{rel_path}: {error}")
            continue

        structured_valid += 1
        keys = _collect_mapping_keys(data)
        structured_key_counter.update(keys)
        semantic_snippets.extend(sorted(keys))

        if keys & _SCHEMA_MARKER_KEYS:
            schema_marked_files.append(rel_path)
        if keys & _GOVERNANCE_DATA_KEYS:
            governance_data_files.append(rel_path)

    link_total = link_graph["internal"] + link_graph["external"] + link_graph["anchors"]
    link_graph["broken_internal"] = broken_internal[:10]
    link_graph["external_domains"] = dict(domain_counter.most_common(10))
    link_graph["internal_targets"] = internal_targets[:20]
    link_graph["cross_reference_density"] = (
        round((link_total / word_count) * 1000, 2) if word_count else 0.0
    )

    covered_structured = len(set(schema_marked_files) | set(governance_data_files))
    coverage_ratio = round(covered_structured / structured_valid, 3) if structured_valid else 0.0

    heading_titles = [title for _level, title in headings]
    primary_title = next((title for level, title in headings if level == 1), "")
    if not primary_title and heading_titles:
        primary_title = heading_titles[0]

    return {
        "file_count": len(files),
        "markdown_file_count": len(markdown_files),
        "structured_file_count": len(structured_files),
        "line_count": doc_lines,
        "word_count": word_count,
        "section_count": len(headings),
        "max_heading_depth": max((level for level, _title in headings), default=0),
        "primary_title": primary_title,
        "heading_titles": heading_titles[:20],
        "frontmatter_files": frontmatter_files[:20],
        "link_graph": link_graph,
        "schema_coverage": {
            "structured_files": len(structured_files),
            "valid_files": structured_valid,
            "invalid_files": structured_invalid[:10],
            "schema_marked_files": schema_marked_files[:20],
            "governance_data_files": governance_data_files[:20],
            "coverage_ratio": coverage_ratio,
            "top_level_keys": dict(structured_key_counter.most_common(20)),
        },
        "sop_coverage": {
            "sop_count": len(sop_files),
            "sop_files": sop_files[:20],
            "governed_module_count": len(governed_modules),
            "governed_modules": {
                module: sources[:10]
                for module, sources in sorted(governed_modules.items())
            },
        },
        "semantic_text": " ".join(semantic_snippets)[:12000],
    }


def _documentation(stats: dict) -> dict:
    doc = stats.get("documentation")
    return doc if isinstance(doc, dict) else {}


def _preview(values: list[str], limit: int = 5) -> str:
    return ", ".join(values[:limit])


def _semantic_basis(stats: dict) -> str:
    """Combined code and documentation text for heuristic classification."""
    doc = _documentation(stats)
    parts: list[str] = [
        stats.get("docstring", ""),
        " ".join(stats.get("classes", [])),
        " ".join(stats.get("functions", [])),
        " ".join(stats.get("imports", [])),
        doc.get("semantic_text", ""),
        " ".join(doc.get("heading_titles", [])),
    ]

    schema = doc.get("schema_coverage", {})
    if isinstance(schema, dict):
        top_level_keys = schema.get("top_level_keys", {})
        if isinstance(top_level_keys, dict):
            parts.append(" ".join(str(key) for key in top_level_keys))

    sop = doc.get("sop_coverage", {})
    if isinstance(sop, dict):
        governed_modules = sop.get("governed_modules", {})
        if isinstance(governed_modules, dict):
            parts.append(" ".join(str(module) for module in governed_modules))

    return " ".join(part for part in parts if part).lower()


# ---------------------------------------------------------------------------
# Dimension extractors
# ---------------------------------------------------------------------------


def _extract_existence(stats: dict) -> dict:
    """DIAG-001 adapted: does this artifact physically exist?"""
    if not stats.get("exists"):
        return {"score": 0.0, "evidence": "file/directory not found"}
    doc = _documentation(stats)
    parts = []
    if "lines" in stats and (stats["lines"] or not doc):
        parts.append(f"{stats['lines']} lines")
    if "files" in stats and (stats["files"] or not doc):
        parts.append(f"{stats['files']} files")
    if "class_count" in stats and (stats["class_count"] or not doc):
        parts.append(f"{stats['class_count']} classes")
    if "function_count" in stats and (stats["function_count"] or not doc):
        parts.append(f"{stats['function_count']} functions")
    if "last_modified" in stats:
        parts.append(f"modified {stats['last_modified']}")
    if doc:
        parts.append(f"{doc.get('file_count', 0)} documentation files")
        if doc.get("word_count"):
            parts.append(f"{doc['word_count']} words")
        if doc.get("structured_file_count"):
            parts.append(f"{doc['structured_file_count']} YAML/JSON files")
        if doc.get("line_count") and "lines" not in stats:
            parts.append(f"{doc['line_count']} documentation lines")
    return {"score": 1.0, "evidence": ", ".join(parts) if parts else "present on disk"}


def _extract_identity(stats: dict) -> str:
    """DIAG-002 adapted: what is this artifact's semantic identity?"""
    docstring = stats.get("docstring", "")
    if docstring:
        # Take first line/sentence of docstring
        return docstring.split("\n")[0].strip().rstrip(".")

    classes = stats.get("classes", [])
    if classes:
        return f"Defines: {', '.join(classes[:5])}"

    doc = _documentation(stats)
    if doc:
        title = doc.get("primary_title")
        sop = doc.get("sop_coverage", {})
        schema = doc.get("schema_coverage", {})
        if title:
            return f"Documentation: {title}"
        if sop.get("sop_count"):
            sop_files = [Path(path).stem for path in sop.get("sop_files", [])]
            return f"SOP corpus: {_preview(sop_files)}"
        if schema.get("governance_data_files"):
            return "Governance data corpus"
        return "Documentation corpus"

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
    doc = _documentation(stats)
    if doc:
        parts.append(f"{doc.get('file_count', 0)} documentation files")
        if doc.get("markdown_file_count"):
            parts.append(
                f"{doc.get('section_count', 0)} sections across "
                f"{doc.get('markdown_file_count', 0)} Markdown files"
            )
        if doc.get("max_heading_depth"):
            parts.append(f"max heading depth H{doc['max_heading_depth']}")
        headings = doc.get("heading_titles", [])
        if headings:
            parts.append(f"top sections: {_preview(headings)}")
        schema = doc.get("schema_coverage", {})
        if doc.get("structured_file_count"):
            ratio = schema.get("coverage_ratio", 0.0)
            parts.append(
                f"{doc.get('structured_file_count', 0)} YAML/JSON files "
                f"({schema.get('valid_files', 0)} valid, {ratio:.0%} schema/governance coverage)"
            )
    return "; ".join(parts) if parts else "No internal structure detected"


def _extract_law(stats: dict) -> str:
    """DIAG-004 adapted: what rules does this artifact enforce or obey?"""
    docstring = stats.get("docstring", "")
    imports = stats.get("imports", [])
    doc = _documentation(stats)

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

    if doc:
        sop = doc.get("sop_coverage", {})
        schema = doc.get("schema_coverage", {})
        if sop.get("sop_count"):
            law_signals.append(f"{sop['sop_count']} SOP files")
        if schema.get("governance_data_files"):
            law_signals.append(
                f"{len(schema['governance_data_files'])} governance data files"
            )
        if schema.get("schema_marked_files"):
            law_signals.append(f"{len(schema['schema_marked_files'])} schema-marked files")

        doc_lower = doc.get("semantic_text", "").lower()
        found = [w for w in enforcement_words if w in doc_lower]
        if found:
            law_signals.append(f"enforcement language in documentation: {', '.join(found)}")

    return "; ".join(law_signals) if law_signals else "No explicit governance references detected"


def _extract_relation(stats: dict) -> str:
    """DIAG-006 adapted: import graph connections."""
    relation_parts = []
    imports = stats.get("imports", [])
    # Filter to organvm_engine imports only
    internal = sorted({i for i in imports if "organvm_engine" in i})
    if internal:
        # Simplify to module names
        modules = sorted({i.split(".")[-1] for i in internal if len(i.split(".")) > 1})
        relation_parts.append(f"imports from: {', '.join(modules[:10])}")

    doc = _documentation(stats)
    if doc:
        link_graph = doc.get("link_graph", {})
        relation_parts.append(
            "link graph: "
            f"{link_graph.get('internal', 0)} internal, "
            f"{link_graph.get('external', 0)} external, "
            f"{link_graph.get('anchors', 0)} anchors, "
            f"{link_graph.get('cross_reference_density', 0.0)} refs/1k words"
        )
        broken = link_graph.get("broken_internal", [])
        if broken:
            relation_parts.append(f"broken internal links: {_preview(broken, limit=3)}")
        domains = list((link_graph.get("external_domains") or {}).keys())
        if domains:
            relation_parts.append(f"external domains: {_preview(domains)}")

    return "; ".join(relation_parts) if relation_parts else "No internal imports detected"


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

    doc = _documentation(stats)
    if doc:
        sop = doc.get("sop_coverage", {})
        if sop.get("sop_count"):
            governed_modules = sorted((sop.get("governed_modules") or {}).keys())
            if governed_modules:
                return (
                    f"SOP coverage: {sop['sop_count']} SOP files govern "
                    f"{sop.get('governed_module_count', 0)} modules "
                    f"({_preview(governed_modules)})"
                )
            return f"SOP corpus: {sop['sop_count']} SOP files with no module mapping"

        section_count = doc.get("section_count", 0)
        structured_count = doc.get("structured_file_count", 0)
        return (
            f"Documentation workflow: {section_count} sections, "
            f"{structured_count} structured data files"
        )

    return "No CLI or public API functions detected"


def _extract_teleology(stats: dict) -> str:
    """DIAG-007 adapted: which axiom does this serve?"""
    combined = _semantic_basis(stats)

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
    doc_text = (_documentation(stats).get("semantic_text", "") or "").lower()
    combined = _semantic_basis(stats)

    claims = []
    for axiom, signals in _AXIOM_SIGNALS.items():
        matching_signals = [sig for sig in signals if sig in combined]
        if matching_signals:
            evidence = "documentation" if any(sig in doc_text for sig in matching_signals) else "code identifiers"
            if any(sig in docstring for sig in matching_signals):
                evidence = "docstring"
            claims.append(
                AxiomClaim(
                    axiom=axiom,
                    claim=f"Artifact references: {', '.join(matching_signals)}",
                    evidence=f"Found in {evidence}",
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
    doc = _documentation(stats)
    doc_text = doc.get("semantic_text", "").lower()
    combined = f"{imports} {functions} {docstring} {doc_text}"

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

            # Documentation generally emits the knowledge/rules it encodes.
            if doc and any(p in doc_text for p in patterns):
                if signal_type in {
                    "CONSTRAINT",
                    "CONTRACT",
                    "KNOWLEDGE",
                    "REPORT",
                    "RULE",
                    "STATE",
                    "TRACE",
                    "VALIDATION",
                }:
                    produces.append(signal_type)

    if doc:
        produces.append("KNOWLEDGE")

        link_graph = doc.get("link_graph", {})
        if link_graph.get("internal") or link_graph.get("external"):
            consumes.append("KNOWLEDGE")

        schema = doc.get("schema_coverage", {})
        if schema.get("schema_marked_files") or schema.get("governance_data_files"):
            produces.append("CONTRACT")

        sop = doc.get("sop_coverage", {})
        if sop.get("sop_count"):
            produces.extend(["RULE", "CONSTRAINT"])
        if sop.get("governed_module_count"):
            consumes.append("SOURCE")

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

    if fs_path.exists():
        documentation = _analyze_documentation(fs_path, workspace_root)
        if documentation:
            stats["documentation"] = documentation

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
        documentation=_documentation(stats),
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
