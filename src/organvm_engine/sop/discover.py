"""Discover SOP and METADOC files across the workspace."""

from __future__ import annotations

import re
import subprocess
import tomllib
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
    governed_paths: list[str] = field(default_factory=list)
    last_reviewed: str | None = None


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


def _coerce_str_list(value: object) -> list[str]:
    """Normalize frontmatter values that can be strings, lists, or path dicts."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        paths: list[str] = []
        for key in ("path", "paths", "file", "files", "code", "modules"):
            paths.extend(_coerce_str_list(value.get(key)))
        return paths
    if isinstance(value, list):
        paths: list[str] = []
        for item in value:
            paths.extend(_coerce_str_list(item))
        return paths
    return []


def _extract_governed_paths(frontmatter: dict) -> list[str]:
    """Extract governed code paths from supported SOP frontmatter shapes."""
    paths: list[str] = []
    for key in ("governed_paths", "governed_code", "code_paths", "source_paths"):
        paths.extend(_coerce_str_list(frontmatter.get(key)))

    governs = frontmatter.get("governs")
    if isinstance(governs, dict):
        for key in ("code", "paths", "modules", "files"):
            paths.extend(_coerce_str_list(governs.get(key)))
    else:
        paths.extend(_coerce_str_list(governs))

    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = path.strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def _extract_last_reviewed(frontmatter: dict) -> str | None:
    """Return the first review/validation timestamp declared by the SOP."""
    for key in ("last_reviewed", "reviewed_at", "last_validated", "validated_at"):
        value = frontmatter.get(key)
        if value:
            return str(value)
    return None


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

    if organ is None and _is_local_repo_root(ws):
        org_name, repo_name = _infer_local_repo_identity(ws)
        _scan_repo(ws, org_name, repo_name, ws, entries)
        _scan_sops_dir(ws, org_name, repo_name, ws / ".sops", entries)

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
        governed_paths=_extract_governed_paths(fm),
        last_reviewed=_extract_last_reviewed(fm),
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


def _is_local_repo_root(path: Path) -> bool:
    """True when *path* itself looks like a repo containing local SOPs."""
    if not (path / ".sops").is_dir():
        return False
    return any((path / marker).exists() for marker in (".git", "pyproject.toml", "package.json"))


def _infer_local_repo_identity(path: Path) -> tuple[str, str]:
    """Infer org/repo labels for a standalone repo scan."""
    remote = _git_remote_identity(path)
    if remote is not None:
        return remote

    repo_name = _pyproject_name(path) or path.name
    org_name = path.parent.name or "local"
    return org_name, repo_name


def _git_remote_identity(path: Path) -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "config", "--get", "remote.origin.url"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    remote = result.stdout.strip()
    if not remote:
        return None
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", remote)
    if not match:
        return None
    return match.group(1), match.group(2)


def _pyproject_name(path: Path) -> str | None:
    pyproject = path / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = data.get("project", {}).get("name")
    return name if isinstance(name, str) and name else None
