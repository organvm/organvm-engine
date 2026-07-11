"""Automated stack analysis for technical mirror discovery.

Scans dependency files (pyproject.toml, package.json, go.mod, Cargo.toml)
and extracts the external projects that a repo depends on. These become
technical mirror candidates.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from organvm_engine.network.schema import MirrorEntry

# Well-known package → GitHub repo mappings
# Expanded by research; this is the seed set
KNOWN_REPOS: dict[str, str] = {
    # Python
    "fastapi": "tiangolo/fastapi",
    "uvicorn": "encode/uvicorn",
    "pydantic": "pydantic/pydantic",
    "pytest": "pytest-dev/pytest",
    "ruff": "astral-sh/ruff",
    "click": "pallets/click",
    "rich": "Textualize/rich",
    "httpx": "encode/httpx",
    "jinja2": "pallets/jinja",
    "pyyaml": "yaml/pyyaml",
    "starlette": "encode/starlette",
    "sqlalchemy": "sqlalchemy/sqlalchemy",
    "alembic": "sqlalchemy/alembic",
    "celery": "celery/celery",
    "redis": "redis/redis-py",
    "boto3": "boto/boto3",
    "requests": "psf/requests",
    "aiohttp": "aio-libs/aiohttp",
    "numpy": "numpy/numpy",
    "pandas": "pandas-dev/pandas",
    "pillow": "python-pillow/Pillow",
    "pyright": "microsoft/pyright",
    # JavaScript/TypeScript
    "react": "facebook/react",
    "next": "vercel/next.js",
    "tailwindcss": "tailwindlabs/tailwindcss",
    "typescript": "microsoft/TypeScript",
    "vite": "vitejs/vite",
    "vitest": "vitest-dev/vitest",
    "eslint": "eslint/eslint",
    "prettier": "prettier/prettier",
    "astro": "withastro/astro",
    "htmx.org": "bigskysoftware/htmx",
    # Go
    "github.com/gorilla/mux": "gorilla/mux",
    "github.com/gin-gonic/gin": "gin-gonic/gin",
    # Rust
    "tokio": "tokio-rs/tokio",
    "serde": "serde-rs/serde",
    "clap": "clap-rs/clap",
}


def scan_pyproject(repo_path: Path) -> list[MirrorEntry]:
    """Extract dependencies from pyproject.toml.

    Parses [project.dependencies] and [project.optional-dependencies]
    sections using tomllib. Maps known packages to their GitHub repos.
    """
    toml_path = repo_path / "pyproject.toml"
    if not toml_path.exists():
        return []

    try:
        data = tomllib.loads(toml_path.read_text())
    except tomllib.TOMLDecodeError:
        return []

    mirrors: list[MirrorEntry] = []
    seen: set[str] = set()

    # Collect all dependency strings from [project.dependencies]
    # and [project.optional-dependencies.*]
    dep_strings: list[str] = []
    project = data.get("project", {})
    dep_strings.extend(project.get("dependencies", []))
    for group_deps in project.get("optional-dependencies", {}).values():
        dep_strings.extend(group_deps)

    # PEP 508: package name is everything before the first version specifier or extra marker
    name_pattern = re.compile(r'^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)')

    for dep in dep_strings:
        match = name_pattern.match(dep.strip())
        if not match:
            continue
        # PEP 503: normalize by lowercasing and collapsing runs of [-_.] to single hyphen
        raw_name = re.sub(r'[-_.]+', '-', match.group(1)).lower()
        if raw_name in seen:
            continue
        seen.add(raw_name)

        github_repo = KNOWN_REPOS.get(raw_name)
        if github_repo:
            mirrors.append(MirrorEntry(
                project=github_repo,
                platform="github",
                relevance=f"Python dependency: {raw_name}",
                engagement=["presence"],
                tags=["auto-discovered", "python-dep"],
            ))

    return mirrors


def scan_package_json(repo_path: Path) -> list[MirrorEntry]:
    """Extract dependencies from package.json."""
    pkg_path = repo_path / "package.json"
    if not pkg_path.exists():
        return []

    try:
        data = json.loads(pkg_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    mirrors: list[MirrorEntry] = []
    seen: set[str] = set()

    for dep_key in ("dependencies", "devDependencies"):
        deps = data.get(dep_key, {})
        if not isinstance(deps, dict):
            continue
        for pkg_name in deps:
            clean = pkg_name.lstrip("@").replace("/", "-").lower()
            if clean in seen:
                continue
            seen.add(clean)

            github_repo = KNOWN_REPOS.get(clean) or KNOWN_REPOS.get(pkg_name)
            if github_repo:
                mirrors.append(MirrorEntry(
                    project=github_repo,
                    platform="github",
                    relevance=f"JS/TS dependency: {pkg_name}",
                    engagement=["presence"],
                    tags=["auto-discovered", "js-dep"],
                ))

    return mirrors


def scan_go_mod(repo_path: Path) -> list[MirrorEntry]:
    """Extract dependencies from go.mod."""
    go_mod = repo_path / "go.mod"
    if not go_mod.exists():
        return []

    content = go_mod.read_text()
    mirrors: list[MirrorEntry] = []
    seen: set[str] = set()

    in_require = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "require (":
            in_require = True
            continue
        if stripped == ")" and in_require:
            in_require = False
            continue
        if stripped.startswith("require ") and "(" not in stripped:
            # Single-line require
            parts = stripped.split()
            if len(parts) >= 2:
                mod_path = parts[1]
                segments = mod_path.split("/")
                if len(segments) >= 3 and segments[0] == "github.com":
                        github_repo = f"{segments[1]}/{segments[2]}"
                        if github_repo not in seen:
                            seen.add(github_repo)
                            mirrors.append(MirrorEntry(
                                project=github_repo,
                                platform="github",
                                relevance=f"Go dependency: {mod_path}",
                                engagement=["presence"],
                                tags=["auto-discovered", "go-dep"],
                            ))
            continue

        if in_require:
            parts = stripped.split()
            if len(parts) >= 2:
                mod_path = parts[0]
                segments = mod_path.split("/")
                if len(segments) >= 3 and segments[0] == "github.com":
                        github_repo = f"{segments[1]}/{segments[2]}"
                        if github_repo not in seen:
                            seen.add(github_repo)
                            mirrors.append(MirrorEntry(
                                project=github_repo,
                                platform="github",
                                relevance=f"Go dependency: {mod_path}",
                                engagement=["presence"],
                                tags=["auto-discovered", "go-dep"],
                            ))

    return mirrors


def scan_cargo_toml(repo_path: Path) -> list[MirrorEntry]:
    """Extract dependencies from Cargo.toml."""
    cargo_path = repo_path / "Cargo.toml"
    if not cargo_path.exists():
        return []

    content = cargo_path.read_text()
    mirrors: list[MirrorEntry] = []
    seen: set[str] = set()

    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in ("[dependencies]", "[dev-dependencies]", "[build-dependencies]"):
            in_deps = True
            continue
        if stripped.startswith("[") and "dependencies" not in stripped:
            in_deps = False
            continue

        if in_deps and "=" in stripped:
            crate_name = stripped.split("=")[0].strip().strip('"')
            if crate_name and not crate_name.startswith("#"):
                github_repo = KNOWN_REPOS.get(crate_name)
                if github_repo and github_repo not in seen:
                    seen.add(github_repo)
                    mirrors.append(MirrorEntry(
                        project=github_repo,
                        platform="github",
                        relevance=f"Rust dependency: {crate_name}",
                        engagement=["presence"],
                        tags=["auto-discovered", "rust-dep"],
                    ))

    return mirrors


def scan_repo_dependencies(repo_path: Path) -> list[MirrorEntry]:
    """Scan all dependency files in a repo for technical mirrors.

    Aggregates results from pyproject.toml, package.json, go.mod, Cargo.toml.
    Deduplicates by project name.
    """
    all_mirrors: list[MirrorEntry] = []
    seen_projects: set[str] = set()

    for scanner in (scan_pyproject, scan_package_json, scan_go_mod, scan_cargo_toml):
        for mirror in scanner(repo_path):
            if mirror.project not in seen_projects:
                all_mirrors.append(mirror)
                seen_projects.add(mirror.project)

    return all_mirrors
