"""System context file sync — walks workspace, updates auto-generated sections.

The sync process:
1. Load registry + seeds once
2. Walk each organ directory looking for CLAUDE.md, GEMINI.md, and AGENTS.md files
3. For each file, inject or replace the auto-generated section
4. Optionally update the workspace-level context files

Preserves all manually-written content outside the AUTO markers.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.generator import (
    generate_agents_section,
    generate_organ_section,
    generate_repo_section,
    generate_workspace_section,
    precompute_ammoi,
)


def sync_all(
    workspace: Path | str | None = None,
    registry_path: str | None = None,
    dry_run: bool = False,
    organs: list[str] | None = None,
    additional_workspace_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Sync auto-generated sections across all context files."""
    from organvm_engine.git.superproject import REGISTRY_KEY_MAP
    from organvm_engine.paths import additional_workspace_roots as resolve_additional_roots
    from organvm_engine.paths import workspace_root
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.validator import validate_registry
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.reader import read_seed

    ws = Path(workspace).expanduser() if workspace else workspace_root()
    extra_roots = (
        [Path(p).expanduser() for p in additional_workspace_roots]
        if additional_workspace_roots is not None
        else resolve_additional_roots(workspace=ws)
    )
    reg = load_registry(registry_path)

    # Pre-flight: Validate registry before sync to prevent breaking 100+ files
    val_result = validate_registry(reg)
    if not val_result.passed:
        raise RuntimeError(
            f"Registry validation failed. Refusing to sync context files.\n{val_result.summary()}",
        )

    # 1. Discover all seeds to have edge data
    seed_paths = discover_seeds(ws)
    for root in extra_roots:
        seed_paths.extend(discover_seeds(root))
        seed_paths.extend(_discover_flat_seeds(root))
    all_seeds = []
    repo_to_seed = {}
    for p in seed_paths:
        try:
            s = read_seed(p)
            all_seeds.append(s)
            repo_to_seed[s.get("repo")] = s
        except Exception:
            continue

    # 1b. Discover all SOPs for directive injection
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.resolver import promotion_to_phase
    from organvm_engine.sop.resolver import resolve_all as resolve_all_sops

    all_sops = discover_sops(workspace=ws)
    for root in extra_roots:
        all_sops.extend(discover_sops(workspace=root))
        all_sops.extend(_discover_flat_sops(root))

    # Pre-compute AMMOI once for all context files
    precompute_ammoi()

    updated = []
    created = []
    skipped = []
    errors = []
    changes = []

    target_organs = organs or list(REGISTRY_KEY_MAP.keys())

    for organ_key in target_organs:
        organ_dir_name = REGISTRY_KEY_MAP.get(organ_key)
        if not organ_dir_name:
            continue

        organ_data = reg.get("organs", {}).get(organ_key, {})
        organ_path = ws / organ_dir_name

        if organ_path.is_dir():
            # 2. Sync organ-level context files
            for filename in ["CLAUDE.md", "GEMINI.md", "AGENTS.md"]:
                try:
                    organ_section = generate_organ_section(organ_key, reg, all_seeds)
                    res = _inject_section_result(organ_path / filename, organ_section, dry_run)
                    _record_sync_result(res, updated, created, skipped, changes)
                except Exception as e:
                    errors.append({"path": str(organ_path / filename), "error": str(e)})

            # 3. Sync repo-level context files for the hierarchical workspace layout.
            for repo_entry in organ_data.get("repositories", []):
                repo_name = repo_entry.get("name")
                repo_path = organ_path / repo_name
                if not repo_path.is_dir():
                    continue
                _sync_repo_context_files(
                    repo_path=repo_path,
                    repo_entry=repo_entry,
                    organ_dir_name=organ_dir_name,
                    registry=reg,
                    repo_to_seed=repo_to_seed,
                    all_sops=all_sops,
                    dry_run=dry_run,
                    updated=updated,
                    created=created,
                    skipped=skipped,
                    changes=changes,
                    errors=errors,
                    promotion_to_phase=promotion_to_phase,
                    resolve_all_sops=resolve_all_sops,
                )

        # 3b. Sync repo-level context files for additive flat workspace roots.
        for repo_entry in organ_data.get("repositories", []):
            repo_name = repo_entry.get("name")
            if not repo_name:
                continue
            for root in extra_roots:
                repo_path = root / repo_name
                if not repo_path.is_dir():
                    continue
                if organ_path.is_dir() and repo_path.resolve() == (organ_path / repo_name).resolve():
                    continue
                _sync_repo_context_files(
                    repo_path=repo_path,
                    repo_entry=repo_entry,
                    organ_dir_name=organ_dir_name,
                    registry=reg,
                    repo_to_seed=repo_to_seed,
                    all_sops=all_sops,
                    dry_run=dry_run,
                    updated=updated,
                    created=created,
                    skipped=skipped,
                    changes=changes,
                    errors=errors,
                    promotion_to_phase=promotion_to_phase,
                    resolve_all_sops=resolve_all_sops,
                )

    # 4. Sync workspace-level context files
    for filename in ["CLAUDE.md", "GEMINI.md", "AGENTS.md"]:
        try:
            ws_section = generate_workspace_section(reg, all_seeds)
            res = _inject_section_result(ws / filename, ws_section, dry_run)
            _record_sync_result(res, updated, created, skipped, changes)
        except Exception as e:
            errors.append({"path": str(ws / filename), "error": str(e)})

    result = {
        "updated": updated,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "changes": changes,
        "changelog": changes,
    }

    # Emit context sync event
    if not dry_run:
        if changes:
            import json
            import time

            from organvm_engine.paths import PathConfig, context_changelog_path

            sync_timestamp = int(time.time())
            # Use explicit config based on the passed workspace, to support tests.
            config = PathConfig(workspace_dir=workspace) if workspace else None
            changelog_file = context_changelog_path(config)
            try:
                changelog_file.parent.mkdir(parents=True, exist_ok=True)
                with changelog_file.open("a", encoding="utf-8") as f:
                    for change in changes:
                        record = {
                            "timestamp": sync_timestamp,
                            "path": change["path"],
                            "action": change["action"],
                            "diff": change.get("diff", ""),
                            "old_section": change.get("old_section", ""),
                            "new_section": change.get("new_section", ""),
                        }
                        f.write(json.dumps(record) + "\n")
            except Exception:
                # Fallback or silent failure if no corpus repo exists in test envs
                pass

        try:
            from organvm_engine.pulse.emitter import emit_engine_event
            from organvm_engine.pulse.types import CONTEXT_SYNCED

            emit_engine_event(
                event_type=CONTEXT_SYNCED,
                source="contextmd",
                payload={
                    "updated_count": len(updated),
                    "created_count": len(created),
                    "changed_count": len(changes),
                    "error_count": len(errors),
                },
            )
        except Exception:
            pass

        # Emit to Testament Chain
        from organvm_engine.ledger.emit import testament_emit
        testament_emit(
            event_type="context.sync",
            source_organ="META-ORGANVM",
            source_repo="organvm-engine",
            actor="cli",
            payload={
                "updated": len(updated),
                "created": len(created),
                "changed": len(changes),
                "errors": len(errors),
            },
        )

    return result

def _discover_flat_seeds(root: Path) -> list[Path]:
    """Find seed.yaml files in a flat root shaped as <root>/<repo>/seed.yaml."""
    if not root.is_dir():
        return []
    seeds = []
    for repo_dir in sorted(root.iterdir()):
        if not repo_dir.is_dir():
            continue
        seed_file = repo_dir / "seed.yaml"
        if seed_file.is_file():
            seeds.append(seed_file)
    return seeds


def _discover_flat_sops(root: Path) -> list:
    """Find SOPs in a flat root shaped as <root>/<repo>/..."""
    if not root.is_dir():
        return []

    from organvm_engine.sop.discover import _scan_repo, _scan_sops_dir

    entries = []
    for repo_dir in sorted(root.iterdir()):
        if not repo_dir.is_dir():
            continue
        _scan_repo(root.parent, root.name, repo_dir.name, repo_dir, entries)
        _scan_sops_dir(root.parent, root.name, repo_dir.name, repo_dir / ".sops", entries)
    return entries


def _sync_repo_context_files(
    *,
    repo_path: Path,
    repo_entry: dict[str, Any],
    organ_dir_name: str,
    registry: dict,
    repo_to_seed: dict,
    all_sops: list,
    dry_run: bool,
    updated: list[str],
    created: list[str],
    skipped: list[str],
    changes: list[dict[str, Any]] | None = None,
    errors: list[dict[str, str]],
    promotion_to_phase,
    resolve_all_sops,
) -> None:
    repo_name = repo_entry.get("name")
    if not repo_name:
        return

    org_name = repo_entry.get("org") or organ_dir_name
    promo_status = repo_entry.get("promotion_status", "LOCAL")
    repo_phase = promotion_to_phase(promo_status)
    repo_sops = resolve_all_sops(
        all_sops, repo=repo_name, organ=organ_dir_name, phase=repo_phase,
    )

    for filename in ["CLAUDE.md", "GEMINI.md"]:
        try:
            res = sync_repo(
                repo_path,
                repo_name,
                org_name,
                registry,
                repo_to_seed.get(repo_name),
                dry_run,
                filename=filename,
                sop_entries=repo_sops,
            )
            _record_sync_result(res, updated, created, skipped, changes)
        except Exception as e:
            errors.append({"path": str(repo_path / filename), "error": str(e)})

    try:
        agents_section = generate_agents_section(
            repo_name, org_name, registry, repo_to_seed.get(repo_name),
        )
        res = _inject_section_result(repo_path / "AGENTS.md", agents_section, dry_run)
        _record_sync_result(res, updated, created, skipped, changes)
    except Exception as e:
        errors.append({"path": str(repo_path / "AGENTS.md"), "error": str(e)})


def sync_repo(
    repo_path: Path,
    repo_name: str,
    org: str,
    registry: dict,
    seed: dict | None = None,
    dry_run: bool = False,
    filename: str = "CLAUDE.md",
    sop_entries: list | None = None,
) -> dict[str, Any]:
    """Sync a single repo's context file."""
    agent = filename.replace(".md", "").lower() if filename else None
    section = generate_repo_section(
        repo_name,
        org,
        registry,
        seed,
        sop_entries=sop_entries,
        agent=agent,
        repo_path=str(repo_path),
    )
    file_path = repo_path / filename
    res = _inject_section_result(file_path, section, dry_run)
    return {
        "path": res["path"],
        "action": res["action"],
        "dry_run": dry_run,
        "change": res.get("change"),
    }


def _inject_section(file_path: Path, new_section: str, dry_run: bool = False) -> str:
    """Inject or replace the auto-generated section in a markdown file."""
    return _inject_section_result(file_path, new_section, dry_run)["action"]


def _inject_section_result(
    file_path: Path,
    new_section: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Inject or replace the auto-generated section and describe the generated diff."""
    import re

    if not file_path.exists():
        change = _build_change_record(file_path, "created", "", new_section)
        if not dry_run:
            file_path.write_text(new_section + "\n")
        return {
            "path": str(file_path),
            "action": "created",
            "dry_run": dry_run,
            "change": change,
        }

    content = file_path.read_text()

    # Pre-emptive strike: remove redundant handoff blocks that were previously stacked
    # outside the auto-managed block. This heals files from the non-idempotent bug.
    # We remove ALL instances from the existing content; the new sync will re-inject
    # exactly one instance inside the AUTO markers.
    # We stop before the next header, the AUTO_END marker, or end of string.
    handoff_pattern = r"\n+## Active Handoff Protocol.*?(?=\n+##|" + re.escape(AUTO_END) + r"|$)"
    content = re.sub(handoff_pattern, "", content, flags=re.DOTALL)

    # Heal stale error lines injected without AUTO markers (pre-fix accumulation)
    error_pattern = r"\n*<!-- ERROR: (?:Organ|Repo) '[^']+' not found -->"
    content = re.sub(error_pattern, "", content)

    # Clean up any trailing whitespace left by the removal
    content = content.strip()

    if AUTO_START in content and AUTO_END in content:
        # Replace existing section. Using greedy match '.*' instead of '.*?' to ensure
        # that if multiple START/END blocks exist, the entire range is collapsed.
        pattern = re.escape(AUTO_START) + r".*" + re.escape(AUTO_END)
        match = re.search(pattern, content, flags=re.DOTALL)
        old_section = match.group(0) if match else ""
        new_content = re.sub(pattern, new_section, content, flags=re.DOTALL)
        if new_content == content:
            return {
                "path": str(file_path),
                "action": "unchanged",
                "dry_run": dry_run,
                "change": None,
            }
        if not dry_run:
            file_path.write_text(new_content)
        return {
            "path": str(file_path),
            "action": "updated",
            "dry_run": dry_run,
            "change": _build_change_record(file_path, "updated", old_section, new_section),
        }

    # Append to end
    new_content = content.rstrip() + "\n\n" + new_section + "\n"
    if not dry_run:
        file_path.write_text(new_content)
    return {
        "path": str(file_path),
        "action": "updated",
        "dry_run": dry_run,
        "change": _build_change_record(file_path, "updated", "", new_section),
    }


def _record_sync_result(
    res: dict[str, Any],
    updated: list[str],
    created: list[str],
    skipped: list[str],
    changes: list[dict[str, Any]] | None,
) -> None:
    """Route an injection result into sync counters and changelog entries."""
    action = res["action"]
    path = res["path"]
    if action == "created":
        created.append(path)
    elif action == "updated":
        updated.append(path)
    else:
        skipped.append(path)

    change = res.get("change")
    if change and changes is not None:
        changes.append(change)


def _build_change_record(
    file_path: Path,
    action: str,
    old_section: str,
    new_section: str,
) -> dict[str, Any]:
    """Build a compact changelog record for one generated context section."""
    old_lines = old_section.splitlines()
    new_lines = new_section.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{file_path}:before",
            tofile=f"{file_path}:after",
            lineterm="",
        ),
    )
    added = sum(
        1
        for line in diff_lines
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1
        for line in diff_lines
        if line.startswith("-") and not line.startswith("---")
    )

    return {
        "path": str(file_path),
        "action": action,
        "added_lines": added,
        "removed_lines": removed,
        "before_hash": _section_hash(old_section),
        "after_hash": _section_hash(new_section),
        "diff": "\n".join(diff_lines),
        "old_section": old_section,
        "new_section": new_section,
    }


def _section_hash(section: str) -> str | None:
    if not section:
        return None
    return hashlib.sha256(section.encode("utf-8")).hexdigest()[:12]
