"""Load and save the canonical repo-registry.json payload."""

import json
from pathlib import Path

from organvm_engine.paths import registry_path as _default_registry_path

# Minimum repo count to accept a registry write.  The production registry
# has 100+ repos; anything dramatically smaller is almost certainly test
# fixture data being written to the real path by accident.
_MIN_REPO_COUNT = 50


def _count_repos(data: dict) -> int:
    """Count total repositories across all organs."""
    total = 0
    for organ in data.get("organs", {}).values():
        if isinstance(organ, dict):
            total += len(organ.get("repositories", []))
    return total


def _validate_loaded_registry(data: object, source: Path) -> dict:
    """Reject compatibility markers and empty payloads at the read boundary."""
    if not isinstance(data, dict):
        raise ValueError(f"Registry at {source} must be a JSON object")
    if "_redirect" in data:
        raise ValueError(
            f"Registry at {source} is a compatibility redirect, not repo-registry.json",
        )
    organs = data.get("organs")
    if not isinstance(organs, dict) or not organs:
        raise ValueError(f"Registry at {source} has no non-empty organs object")
    if _count_repos(data) == 0:
        raise ValueError(f"Registry at {source} contains zero repositories")
    return data


def load_registry(path: Path | str | None = None) -> dict:
    """Load registry from a file or per-organ directory.

    If path points to a directory containing _meta.json, merges
    the per-organ files. Otherwise loads the single JSON file.

    Args:
        path: Path to registry file or split-registry directory.
            Defaults to the corpus repo location.

    Returns:
        Parsed registry dict.
    """
    registry_path = Path(path) if path else _default_registry_path()

    if registry_path.is_dir():
        from organvm_engine.registry.split import merge_registry

        return _validate_loaded_registry(merge_registry(registry_path), registry_path)

    with registry_path.open() as f:
        return _validate_loaded_registry(json.load(f), registry_path)


def save_registry(data: dict, path: Path | str | None = None) -> None:
    """Write repo-registry.json back to disk with consistent formatting.

    Guards against accidental overwrites: if writing to the default
    production path and the data contains far fewer repos than expected,
    raises ValueError instead of silently clobbering the file.

    Args:
        data: Registry dict to write.
        path: Path to write to. Defaults to the corpus repo location.

    Raises:
        ValueError: If the data looks like test fixture data being written
            to the production registry path.
    """
    default_path = _default_registry_path()
    registry_path = Path(path) if path else default_path

    # Guard: only enforce on the default production path
    if path is None or Path(path).resolve() == default_path.resolve():
        repo_count = _count_repos(data)
        if repo_count < _MIN_REPO_COUNT:
            raise ValueError(
                f"Refusing to write registry with only {repo_count} repos "
                f"to production path {registry_path}. This looks like test "
                f"fixture data. Pass an explicit path to override.",
            )

    with registry_path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
