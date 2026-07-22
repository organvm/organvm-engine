"""Discover SOP and METADOC files across the workspace."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from organvm_engine.organ_config import ORGANS
from organvm_engine.paths import workspace_root

# All org directories including PERSONAL (4444J99).
# Use dict.fromkeys to deduplicate while preserving insertion order
# (LIMINAL and SIGMA_E share dir "4444J99").
ALL_ORG_DIRS = list(dict.fromkeys(v["dir"] for v in ORGANS.values()))

# Filename patterns (case-insensitive matching)
_SOP_PATTERNS = re.compile(
    r"^(SOP--|sop--|sop-|METADOC--|metadoc--|APPENDIX--|appendix--).*\.md$",
    re.IGNORECASE,
)

# Directory segments to skip entirely
_EXCLUDED_SEGMENTS = frozenset({
    "node_modules", ".venv", ".git", ".tox", "__pycache__",
    "ARCHIVE_RK01", "vault_backup", "zip_fossils",
})

# Directory names to skip at any depth within a repo
_EXCLUDED_ANY_DEPTH = frozenset({"archive"})

# Top-level directories under an org/repo to skip
_EXCLUDED_TOPLEVEL = frozenset({"intake"})

# Repo-level directories to skip entirely (e.g. meta-organvm/intake/)
_EXCLUDED_REPOS = frozenset({"intake"})


@dataclass
class SOPEntry:
    path: Path
    org: str
    repo: str
    filename: str
    title: str | None
    doc_type: str  # "SOP" | "METADOC" | "APPENDIX" | "SOP-SKILL" | "unknown"
    canonical: bool  # True if in praxis-perpetua/standards/
    has_canonical_header: bool  # True if starts with '> **Canonical location:**'
    scope: str = "unknown"  # "system" | "organ" | "repo" | "unknown"
    phase: str = "any"  # genesis | foundation | hardening | graduation | sustaining | any
    triggers: list[str] = field(default_factory=list)
    overrides: str | None = None
    complements: list[str] = field(default_factory=list)
    sop_name: str | None = None  # from frontmatter 'name' or derived from filename
    governs: list[str] = field(default_factory=list)


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file.

    Looks for content between opening and closing '---' markers.
    Returns empty dict if no frontmatter found or on parse error.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            if first_line != "---":
                return {}
            lines = []
            for raw in f:
                line = raw.rstrip("\n")
                if line.strip() == "---":
                    break
                lines.append(line)
            else:
                # Never found closing ---
                return {}
        return yaml.safe_load("\n".join(lines)) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _derive_sop_name(filename: str) -> str:
    """Derive a SOP name from a filename.

    'SOP--structural-integrity-audit.md' → 'structural-integrity-audit'
    'registry-update-protocol.md' → 'registry-update-protocol'
    """
    stem = Path(filename).stem
    # Strip SOP--, sop--, METADOC--, etc. prefixes
    return re.sub(r"^(SOP--|sop--|sop-|METADOC--|metadoc--|APPENDIX--|appendix--)", "", stem)


def _normalize_string_list(value: object) -> list[str]:
    """Normalize a frontmatter scalar/list/dict into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, dict):
        for key in ("path", "paths", "file", "files", "code", "items"):
            if key in value:
                return _normalize_string_list(value[key])
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_normalize_string_list(item))
        return result
    return []


def _extract_governs(fm: dict) -> list[str]:
    """Extract governed code references from SOP frontmatter.

    ``governs`` is the canonical key. The aliases keep older or hand-authored
    frontmatter useful while the ecosystem converges on one spelling.
    """
    for key in ("governs", "governed_code", "code_refs", "source_files"):
        values = _normalize_string_list(fm.get(key))
        if values:
            return values
    return []


def _infer_scope(path: Path, workspace: Path) -> str:
    """Infer scope (system/organ/repo) from file location.

    - praxis-perpetua/standards/ → system
    - {org}/.sops/ (at org superproject level) → organ
    - {org}/{repo}/.sops/ → repo
    - Otherwise → unknown (legacy SOP, user should add frontmatter)
    """
    try:
        rel = path.relative_to(workspace)
    except ValueError:
        return "unknown"

    parts = rel.parts
    if len(parts) < 2:
        return "unknown"

    # system: praxis-perpetua/standards/
    if (
        len(parts) >= 4
        and parts[0] == "meta-organvm"
        and parts[1] == "praxis-perpetua"
        and parts[2] == "standards"
    ):
        return "system"

    # organ: {org}/.sops/foo.md (exactly 3 parts: org/.sops/file.md)
    if len(parts) == 3 and parts[1] == ".sops":
        return "organ"

    # repo: {org}/{repo}/.sops/foo.md (exactly 4 parts)
    if len(parts) == 4 and parts[2] == ".sops":
        return "repo"

    return "unknown"


def _should_skip(path: Path) -> bool:
    """Check if any path segment matches exclusion rules."""
    parts = path.parts
    for part in parts:
        if part in _EXCLUDED_SEGMENTS:
            return True
        # Skip vault backups by substring
        if "vault_backup" in part:
            return True
    return False


def _extract_title(path: Path) -> str | None:
    """Extract title from first heading line (first 10 lines)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, raw_line in enumerate(f):
                if i >= 10:
                    break
                line = raw_line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return None


def _has_canonical_header(path: Path) -> bool:
    """Check if file starts with canonical location blockquote."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            return first_line.startswith("> **Canonical location:**")
    except OSError:
        return False


def _classify_doc_type(filename: str) -> str:
    lower = filename.lower()
    if lower.startswith(("sop--", "sop-")):
        return "SOP"
    if lower.startswith("metadoc--"):
        return "METADOC"
    if lower.startswith("appendix--"):
        return "APPENDIX"
    return "unknown"


def _is_in_praxis_standards(path: Path, workspace: Path) -> bool:
    """Check if path is under praxis-perpetua/standards/."""
    try:
        rel = path.relative_to(workspace)
        parts = rel.parts
        return (
            len(parts) >= 4
            and parts[0] == "meta-organvm"
            and parts[1] == "praxis-perpetua"
            and parts[2] == "standards"
        )
    except ValueError:
        return False


def discover_sops(
    workspace: Path | str | None = None,
    organ: str | None = None,
) -> list[SOPEntry]:
    """Walk the workspace and find all SOP/METADOC files.

    Args:
        workspace: Root workspace directory. Defaults to ~/Workspace.
        organ: If set, only scan this organ's directory (CLI key like "I", "META").

    Returns:
        Sorted list of SOPEntry objects.
    """
    ws = Path(workspace) if workspace else workspace_root()

    if organ:
        org_meta = ORGANS.get(organ.upper())
        if not org_meta:
            return []
        scan_dirs = [org_meta["dir"]]
    else:
        scan_dirs = ALL_ORG_DIRS

    entries: list[SOPEntry] = []

    for org_name in scan_dirs:
        org_dir = ws / org_name
        if not org_dir.is_dir():
            continue

        # Scan organ-level .sops/ directory (T3)
        _scan_sops_dir(ws, org_name, org_name, org_dir / ".sops", entries)

        for repo_dir in sorted(org_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            if repo_dir.name in _EXCLUDED_REPOS:
                continue
            # Walk the repo looking for SOP files
            _scan_repo(ws, org_name, repo_dir.name, repo_dir, entries)
            # Scan repo-level .sops/ directory (T4)
            _scan_sops_dir(ws, org_name, repo_dir.name, repo_dir / ".sops", entries)

    return sorted(entries, key=lambda e: (e.org, e.repo, e.filename))


def discover_repo_sops(
    repo_root: Path | str,
    org: str = "local",
    repo: str | None = None,
) -> list[SOPEntry]:
    """Find SOP files inside a single repository checkout.

    This is the flat-layout counterpart to ``discover_sops()``, which expects
    the full ORGANVM workspace shape (``<workspace>/<org>/<repo>``). It scans
    legacy SOP-pattern files and the repo-level ``.sops/`` directory.
    """
    root = Path(repo_root)
    repo_name = repo or root.name
    entries: list[SOPEntry] = []
    _scan_repo(root, org, repo_name, root, entries)
    _scan_sops_dir(root, org, repo_name, root / ".sops", entries)
    return sorted(entries, key=lambda e: (e.org, e.repo, e.filename, str(e.path)))


def _scan_repo(
    workspace: Path,
    org_name: str,
    repo_name: str,
    repo_dir: Path,
    entries: list[SOPEntry],
) -> None:
    """Recursively scan a repo directory for SOP files."""
    for item in _walk_safe(repo_dir):
        if not item.is_file():
            continue
        if not _SOP_PATTERNS.match(item.name):
            continue
        if _should_skip(item):
            continue

        # Skip excluded directories
        try:
            rel_to_repo = item.relative_to(repo_dir)
            parts_lower = [p.lower() for p in rel_to_repo.parts]
            # Skip intake/ at repo top level
            if parts_lower and parts_lower[0] in _EXCLUDED_TOPLEVEL:
                continue
            # Skip archive/ at any depth
            if any(p in _EXCLUDED_ANY_DEPTH for p in parts_lower):
                continue
        except ValueError:
            continue

        entries.append(_build_entry(item, workspace, org_name, repo_name))


def _scan_sops_dir(
    workspace: Path,
    org_name: str,
    repo_name: str,
    sops_dir: Path,
    entries: list[SOPEntry],
) -> None:
    """Scan a .sops/ directory for SOP-skill files.

    Any .md file in .sops/ is treated as an SOP-skill regardless of filename.
    """
    if not sops_dir.is_dir():
        return
    try:
        for item in sorted(sops_dir.iterdir()):
            if item.is_file() and item.suffix == ".md":
                entries.append(_build_entry(
                    item, workspace, org_name, repo_name, doc_type_override="SOP-SKILL",
                ))
    except PermissionError:
        pass


def _build_entry(
    item: Path,
    workspace: Path,
    org_name: str,
    repo_name: str,
    doc_type_override: str | None = None,
) -> SOPEntry:
    """Build a fully-enriched SOPEntry from a file path."""
    fm = _parse_frontmatter(item)
    scope_from_fm = fm.get("scope")
    scope = scope_from_fm if scope_from_fm in ("system", "organ", "repo") else _infer_scope(
        item, workspace,
    )
    sop_name = fm.get("name") or _derive_sop_name(item.name)
    phase = fm.get("phase", "any")

    return SOPEntry(
        path=item,
        org=org_name,
        repo=repo_name,
        filename=item.name,
        title=_extract_title(item),
        doc_type=doc_type_override or _classify_doc_type(item.name),
        canonical=_is_in_praxis_standards(item, workspace),
        has_canonical_header=_has_canonical_header(item),
        scope=scope,
        phase=phase,
        triggers=fm.get("triggers") or [],
        overrides=fm.get("overrides"),
        complements=fm.get("complements") or [],
        sop_name=sop_name,
        governs=_extract_governs(fm),
    )


def _walk_safe(root: Path) -> list[Path]:
    """Walk directory tree, skipping excluded segments."""
    results: list[Path] = []
    try:
        for item in sorted(root.iterdir()):
            if item.name in _EXCLUDED_SEGMENTS:
                continue
            if item.name.startswith("."):
                continue
            if "vault_backup" in item.name:
                continue
            if item.name.lower() in _EXCLUDED_ANY_DEPTH:
                continue
            if item.is_file():
                results.append(item)
            elif item.is_dir():
                results.extend(_walk_safe(item))
    except PermissionError:
        pass
    return results
