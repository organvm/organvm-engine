"""Compute system-wide metrics from registry."""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter (between --- markers) from markdown text."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3 :]
    return text


def _count_file_words(path: Path) -> int:
    """Count words in a single file, stripping frontmatter and HTML tags."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return 0
    text = _strip_frontmatter(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(text.split())


def _normalize_candidates(
    candidates: list[Path] | None,
    workspace: Path | None,
) -> list[Path]:
    """Build the final probe list from either ``candidates`` or legacy ``workspace``."""
    if candidates is not None:
        raw = list(candidates)
    elif workspace is not None:
        raw = [workspace]
    else:
        return []
    seen: set[Path] = set()
    out: list[Path] = []
    for c in raw:
        if c is None:
            continue
        p = Path(c)
        if not p.is_dir():
            continue
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(rp)
    return out


def _resolve_repo_path(
    org_dir_hint: str,
    repo_name: str,
    candidates: list[Path],
) -> Path | None:
    """Probe candidate roots for a repo's filesystem location.

    For each root, tries organ-grouped layout first
    (``<root>/<org_dir_hint>/<repo_name>``), then flat layout
    (``<root>/<repo_name>``). Returns the first existing directory, or None.
    """
    if not repo_name:
        return None
    for root in candidates:
        if org_dir_hint:
            grouped = root / org_dir_hint / repo_name
            if grouped.is_dir():
                return grouped
        flat = root / repo_name
        if flat.is_dir():
            return flat
    return None


def _resolve_named_dir(
    org_dir_hint: str,
    sub_path: str,
    candidates: list[Path],
) -> Path | None:
    """Probe candidate roots for a named subdirectory.

    Like ``_resolve_repo_path`` but for known relative paths such as
    ``public-process/_posts``. Tries organ-grouped first, then flat.
    """
    for root in candidates:
        if org_dir_hint:
            grouped = root / org_dir_hint / sub_path
            if grouped.is_dir():
                return grouped
        flat = root / sub_path
        if flat.is_dir():
            return flat
    return None


def _legacy_count_words_filesystem(workspace: Path) -> dict:
    """Legacy filesystem-walker — iterates ORGANS dirs under a single root.

    Preserved for backward compat with existing tests and cli/metrics.py callers
    that pass a single workspace Path. New code should use the registry-driven
    path via ``count_words(registry, candidates=...)``.
    """
    from organvm_engine.organ_config import ORGANS

    readme_words = 0
    for organ_info in ORGANS.values():
        organ_dir = workspace / organ_info["dir"]
        if not organ_dir.is_dir():
            continue
        for entry in sorted(organ_dir.iterdir()):
            if not entry.is_dir():
                continue
            readme = entry / "README.md"
            if readme.is_file():
                readme_words += _count_file_words(readme)

    essay_words = 0
    essays_dir = workspace / "organvm-v-logos" / "public-process" / "_posts"
    if essays_dir.is_dir():
        for md in sorted(essays_dir.glob("*.md")):
            essay_words += _count_file_words(md)

    corpus_words = 0
    corpus_target = workspace / "meta-organvm" / "organvm-corpvs-testamentvm" / "docs"
    if corpus_target.is_dir():
        for md in sorted(corpus_target.rglob("*.md")):
            corpus_words += _count_file_words(md)

    profile_words = 0
    for organ_info in ORGANS.values():
        profile = workspace / organ_info["dir"] / ".github" / "profile" / "README.md"
        if profile.is_file():
            profile_words += _count_file_words(profile)

    total = readme_words + essay_words + corpus_words + profile_words
    return {
        "readmes": readme_words,
        "essays": essay_words,
        "corpus": corpus_words,
        "org_profiles": profile_words,
        "total": total,
    }


def count_words(
    registry_or_workspace,
    *,
    candidates: list[Path] | None = None,
    workspace: Path | None = None,
) -> dict:
    """Count words across the workspace by category, registry-driven.

    Iterates ``registry["organs"][*]["repositories"]``, resolves each repo to
    a filesystem location by probing ``candidates`` (organ-grouped layout first,
    flat-namespace fallback), and counts ``README.md`` + ``.github/profile/README.md``.
    Essays and corpus docs are resolved via known canonical sub-paths.

    Args:
        registry: Loaded registry-v2.json dict.
        candidates: Priority-ordered list of candidate workspace roots. Each repo
            is probed against these in order.
        workspace: Legacy single-root parameter. Used only when ``candidates`` is
            None; equivalent to ``candidates=[workspace]``.

    Returns:
        Dict with keys: readmes, essays, corpus, org_profiles, total.
    """
    # Backward-compat: legacy callers pass a single workspace Path positionally
    if isinstance(registry_or_workspace, (str, Path)):
        return _legacy_count_words_filesystem(Path(registry_or_workspace))
    registry = registry_or_workspace
    roots = _normalize_candidates(candidates, workspace)

    readme_words = 0
    profile_words = 0
    for organ_data in registry.get("organs", {}).values():
        for repo in organ_data.get("repositories", []):
            if repo.get("implementation_status") == "ARCHIVED":
                continue
            name = repo.get("name", "")
            org_dir = repo.get("org", "")
            repo_path = _resolve_repo_path(org_dir, name, roots)
            if repo_path is None:
                continue
            readme = repo_path / "README.md"
            if readme.is_file():
                readme_words += _count_file_words(readme)
            profile = repo_path / ".github" / "profile" / "README.md"
            if profile.is_file():
                profile_words += _count_file_words(profile)

    essay_words = 0
    essays_dir = _resolve_named_dir("organvm-v-logos", "public-process/_posts", roots)
    if essays_dir is None:
        essays_dir = _resolve_named_dir("", "public-process/_posts", roots)
    if essays_dir is not None:
        for md in sorted(essays_dir.glob("*.md")):
            essay_words += _count_file_words(md)

    corpus_words = 0
    corpus_target = _resolve_named_dir("meta-organvm", "organvm-corpvs-testamentvm/docs", roots)
    if corpus_target is None:
        corpus_target = _resolve_named_dir("", "organvm-corpvs-testamentvm/docs", roots)
    if corpus_target is not None:
        for md in sorted(corpus_target.rglob("*.md")):
            corpus_words += _count_file_words(md)

    total = readme_words + essay_words + corpus_words + profile_words

    return {
        "readmes": readme_words,
        "essays": essay_words,
        "corpus": corpus_words,
        "org_profiles": profile_words,
        "total": total,
    }


def format_word_count(total: int) -> tuple[str, int, str]:
    """Format a word count into display strings.

    Display strings are rounded to the nearest 1K to reduce propagation
    churn — the numeric value stays precise.

    Args:
        total: Total word count.

    Returns:
        Tuple of (total_words, total_words_numeric, total_words_short).
        e.g. ("~842,000+", 842000, "842K+")
    """
    rounded = round(total, -3) if total >= 500 else total
    total_words = f"~{rounded:,}+"
    total_words_numeric = total
    k = rounded // 1000
    total_words_short = f"{k}K+"
    return total_words, total_words_numeric, total_words_short


_CODE_EXTENSIONS = {".py", ".ts", ".js", ".go", ".rs", ".tsx", ".jsx"}
_TEST_PATTERNS = {"test_", "_test.", ".test.", ".spec."}
_SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".tox", "dist", "build"}


def _count_repo_code(repo_path: Path) -> tuple[int, int, bool]:
    """Walk a single repo dir; return (code_files, test_files, has_tests_dir)."""
    code = 0
    tests = 0
    has_tests = (repo_path / "tests").is_dir()
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(skip in path.parts for skip in _SKIP_DIRS):
            continue
        if path.suffix in _CODE_EXTENSIONS:
            code += 1
            if any(pat in path.name for pat in _TEST_PATTERNS):
                tests += 1
    return code, tests, has_tests


def _legacy_count_code_files_filesystem(workspace: Path) -> dict:
    """Legacy filesystem-walker for code/test file counts. See ``_legacy_count_words_filesystem``."""
    from organvm_engine.organ_config import ORGANS

    code_files = 0
    test_files = 0
    repos_with_tests = 0
    for organ_info in ORGANS.values():
        organ_dir = workspace / organ_info["dir"]
        if not organ_dir.is_dir():
            continue
        for repo_dir in sorted(organ_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            repo_code, repo_tests, has_tests = _count_repo_code(repo_dir)
            code_files += repo_code
            test_files += repo_tests
            if has_tests:
                repos_with_tests += 1
    return {
        "code_files": code_files,
        "test_files": test_files,
        "repos_with_tests": repos_with_tests,
    }


def _legacy_count_code_files_per_repo_filesystem(workspace: Path) -> dict[str, dict[str, int]]:
    """Legacy filesystem-walker per-repo. See ``_legacy_count_words_filesystem``."""
    from organvm_engine.organ_config import ORGANS

    per_repo: dict[str, dict[str, int]] = {}
    for organ_info in ORGANS.values():
        organ_dir = workspace / organ_info["dir"]
        if not organ_dir.is_dir():
            continue
        for repo_dir in sorted(organ_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            repo_code, repo_tests, _ = _count_repo_code(repo_dir)
            key = f"{organ_dir.name}/{repo_dir.name}"
            per_repo[key] = {"code_files": repo_code, "test_files": repo_tests}
    return per_repo


def count_code_files(
    registry_or_workspace,
    *,
    candidates: list[Path] | None = None,
    workspace: Path | None = None,
) -> dict:
    """Count code and test files across the workspace, registry-driven.

    Iterates ``registry["organs"][*]["repositories"]``, resolves each repo's
    path via the candidate-root probe, and aggregates code/test file counts.

    Args:
        registry: Loaded registry-v2.json dict.
        candidates: Priority-ordered list of candidate workspace roots.
        workspace: Legacy single-root fallback when ``candidates`` is None.

    Returns:
        Dict with keys: code_files, test_files, repos_with_tests.
    """
    if isinstance(registry_or_workspace, (str, Path)):
        return _legacy_count_code_files_filesystem(Path(registry_or_workspace))
    registry = registry_or_workspace
    roots = _normalize_candidates(candidates, workspace)

    code_files = 0
    test_files = 0
    repos_with_tests = 0

    for organ_data in registry.get("organs", {}).values():
        for repo in organ_data.get("repositories", []):
            if repo.get("implementation_status") == "ARCHIVED":
                continue
            name = repo.get("name", "")
            org_dir = repo.get("org", "")
            repo_path = _resolve_repo_path(org_dir, name, roots)
            if repo_path is None:
                continue
            repo_code, repo_tests, has_tests = _count_repo_code(repo_path)
            code_files += repo_code
            test_files += repo_tests
            if has_tests:
                repos_with_tests += 1

    return {
        "code_files": code_files,
        "test_files": test_files,
        "repos_with_tests": repos_with_tests,
    }


def count_code_files_per_repo(
    registry_or_workspace,
    *,
    candidates: list[Path] | None = None,
    workspace: Path | None = None,
) -> dict[str, dict[str, int]]:
    """Count code and test files per repository, registry-driven.

    Keys are ``<org>/<repo-name>`` (e.g. ``organvm-i-theoria/recursive-engine``),
    matching the format ``propagate_repo_metrics`` expects.

    Args:
        registry: Loaded registry-v2.json dict.
        candidates: Priority-ordered list of candidate workspace roots.
        workspace: Legacy single-root fallback when ``candidates`` is None.

    Returns:
        Dict mapping ``org/repo-name`` to ``{"code_files": N, "test_files": N}``.
    """
    if isinstance(registry_or_workspace, (str, Path)):
        return _legacy_count_code_files_per_repo_filesystem(Path(registry_or_workspace))
    registry = registry_or_workspace
    roots = _normalize_candidates(candidates, workspace)

    per_repo: dict[str, dict[str, int]] = {}
    for organ_data in registry.get("organs", {}).values():
        for repo in organ_data.get("repositories", []):
            if repo.get("implementation_status") == "ARCHIVED":
                continue
            name = repo.get("name", "")
            org_dir = repo.get("org", "")
            if not (name and org_dir):
                continue
            repo_path = _resolve_repo_path(org_dir, name, roots)
            if repo_path is None:
                continue
            repo_code, repo_tests, _ = _count_repo_code(repo_path)
            key = f"{org_dir}/{name}"
            per_repo[key] = {"code_files": repo_code, "test_files": repo_tests}

    return per_repo


def propagate_repo_metrics(registry: dict, per_repo: dict[str, dict[str, int]]) -> int:
    """Write per-repo code_files/test_files counts into registry entries.

    For each repository in the registry, looks up its filesystem counts from
    *per_repo* and stores them under a ``metrics`` key on the repo dict.

    Args:
        registry: Mutable registry dict (modified in place).
        per_repo: Output of :func:`count_code_files_per_repo`.

    Returns:
        Number of registry entries updated.
    """
    updated = 0
    for organ_data in registry.get("organs", {}).values():
        for repo in organ_data.get("repositories", []):
            org = repo.get("org", "")
            name = repo.get("name", "")
            key = f"{org}/{name}"
            counts = per_repo.get(key)
            if counts is not None:
                metrics = repo.setdefault("metrics", {})
                metrics["code_files"] = counts["code_files"]
                metrics["test_files"] = counts["test_files"]
                updated += 1
    return updated


def compute_metrics(
    registry: dict,
    workspace: Path | None = None,
    *,
    candidates: list[Path] | None = None,
) -> dict:
    """Derive all computable metrics from registry-v2.json.

    Args:
        registry: Loaded registry dict.
        workspace: Legacy single-root parameter. Used only when ``candidates``
            is None.
        candidates: Priority-ordered list of candidate workspace roots. When
            provided, the metric walkers probe each root in order (organ-grouped
            layout first, flat-namespace fallback). Required for environments
            where the workspace is split across multiple roots.

    Returns:
        Dict with computed metrics (total_repos, per_organ, status distribution, etc.).
    """
    organs = registry.get("organs", {})
    repos = []
    per_organ = {}

    for organ_key, organ_data in organs.items():
        organ_repos = organ_data.get("repositories", [])
        repos.extend(organ_repos)
        per_organ[organ_key] = {
            "name": organ_data.get("name", organ_key),
            "repos": len(organ_repos),
        }

    status_dist: dict[str, int] = defaultdict(int)
    ci_count = 0
    dep_count = 0

    for repo in repos:
        status_dist[repo.get("implementation_status", "UNKNOWN")] += 1
        if repo.get("ci_workflow"):
            ci_count += 1
        dep_count += len(repo.get("dependencies", []))

    operational = sum(1 for o in organs.values() if o.get("launch_status") == "OPERATIONAL")

    result = {
        "total_repos": len(repos),
        "active_repos": status_dist.get("ACTIVE", 0),
        "archived_repos": status_dist.get("ARCHIVED", 0),
        "total_organs": len(organs),
        "operational_organs": operational,
        "ci_workflows": ci_count,
        "dependency_edges": dep_count,
        "per_organ": per_organ,
        "implementation_status": dict(sorted(status_dist.items())),
    }

    if candidates is not None or workspace is not None:
        wc = count_words(registry, candidates=candidates, workspace=workspace)
        result["word_counts"] = wc
        tw, tw_num, tw_short = format_word_count(wc["total"])
        result["total_words"] = tw
        result["total_words_numeric"] = tw_num
        result["total_words_short"] = tw_short

        cf = count_code_files(registry, candidates=candidates, workspace=workspace)
        result["code_files"] = cf["code_files"]
        result["test_files"] = cf["test_files"]
        result["repos_with_tests"] = cf["repos_with_tests"]

    return result


def write_metrics(
    computed: dict,
    output_path: Path | str,
    manual: dict | None = None,
) -> None:
    """Write system-metrics.json with computed and manual sections.

    Args:
        computed: Computed metrics dict.
        output_path: Output file path.
        manual: Manual section to preserve. Loaded from existing file if None.
    """
    out = Path(output_path)

    resolved_manual: dict
    if manual is not None:
        resolved_manual = manual
    elif out.exists():
        with out.open() as f:
            existing = json.load(f)
        resolved_manual = existing.get("manual", {})
    else:
        resolved_manual = {
            "_note": "Edit these by hand. calculate-metrics.py preserves this section.",
        }

    # Migrate fields from manual to computed when auto-computed
    if "word_counts" in computed:
        for key in ("total_words", "total_words_numeric", "total_words_short"):
            resolved_manual.pop(key, None)
    if "code_files" in computed:
        for key in ("code_files", "test_files", "repos_with_tests"):
            resolved_manual.pop(key, None)

    metrics = {
        "schema_version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "computed": computed,
        "manual": resolved_manual,
    }

    with out.open("w") as f:
        json.dump(metrics, f, indent=2)
        f.write("\n")
