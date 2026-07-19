"""CI triage, infrastructure audit, scaffold, and branch protection CLI commands."""

import argparse
import json


def cmd_ci_scaffold(args: argparse.Namespace) -> int:
    """Generate CI workflow YAML for a repo (lint/test/typecheck steps)."""
    from pathlib import Path

    from organvm_engine.ci.scaffold import scaffold_repo

    repo_path = Path(args.path).resolve()
    if not repo_path.is_dir():
        print(f"Error: {repo_path} is not a directory")
        return 1

    repo_name = getattr(args, "name", None) or repo_path.name
    dry_run = not getattr(args, "write", False)

    result = scaffold_repo(
        repo_path=repo_path,
        repo_name=repo_name,
        lint=args.lint or args.all,
        test=args.test or args.all,
        typecheck=args.typecheck or args.all,
    )

    if args.json:
        out = {
            "repo": result.repo_name,
            "stack": result.stack.value,
        }
        if result.lint_yaml:
            out["lint_step"] = result.lint_yaml
        if result.test_yaml:
            out["test_step"] = result.test_yaml
        if result.typecheck_yaml:
            out["typecheck_step"] = result.typecheck_yaml
        out["combined"] = result.combined_yaml()
        print(json.dumps(out, indent=2))
        return 0

    combined = result.combined_yaml()
    if not combined:
        print(f"Stack: {result.stack.value}")
        print("No steps generated (unknown stack or no flags selected).")
        return 1

    if dry_run:
        print(f"# Stack detected: {result.stack.value}")
        print(f"# Would write to: {repo_path / '.github' / 'workflows' / 'ci.yml'}")
        print()
        print(combined)
    else:
        wf_dir = repo_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        target = wf_dir / "ci.yml"
        target.write_text(combined)
        print(f"Wrote {target}")

    return 0


def cmd_ci_protect(args: argparse.Namespace) -> int:
    """Generate branch protection commands for GRADUATED repos."""
    from organvm_engine.ci.protect import plan_branch_protection
    from organvm_engine.registry.loader import load_registry

    registry_path = getattr(args, "registry", None)
    registry = load_registry(registry_path)

    organ_filter = getattr(args, "organ", None)
    repo_filter = getattr(args, "repo", None)

    dry_run = not getattr(args, "execute", False)

    plan = plan_branch_protection(
        registry,
        organ_filter=organ_filter,
        repo_filter=repo_filter,
    )

    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    print(f"\n{plan.summary()}\n")

    if plan.repos and not dry_run:
        print("\nCommands to execute:")
        print("=" * 50)
        for cmd in plan.commands():
            print()
            print(cmd)
        print()

    if dry_run and plan.repos:
        print("\n[dry-run] Commands that would be generated:")
        for p in plan.repos:
            print(f"  gh api -X PUT repos/{p.org}/{p.repo_name}/branches/main/protection ...")

    return 0


def cmd_ci_triage(args: argparse.Namespace) -> int:
    from organvm_engine.ci.triage import triage

    report = triage()
    print(f"\n{report.summary()}\n")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_ci_audit(args: argparse.Namespace) -> int:
    """Run infrastructure audit (The Descent Protocol)."""
    from organvm_engine.ci.audit import run_infra_audit
    from organvm_engine.registry.loader import load_registry

    registry_path = getattr(args, "registry", None)
    registry = load_registry(registry_path)

    organ_filter = getattr(args, "organ", None)
    repo_filter = getattr(args, "repo", None)

    report = run_infra_audit(
        registry=registry,
        organ_filter=organ_filter,
        repo_filter=repo_filter,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"\n{report.summary()}\n")

    # Exit non-zero if any repos are non-compliant
    return 0 if report.non_compliant_repos == 0 else 1


def cmd_ci_mandate(args: argparse.Namespace) -> int:
    """Verify CI workflow files exist on disk (mandate check)."""
    from organvm_engine.ci.mandate import verify_ci_mandate
    from organvm_engine.registry.loader import load_registry

    registry_path = getattr(args, "registry", None)
    registry = load_registry(registry_path)

    report = verify_ci_mandate(registry)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"\nCI Mandate — {report.has_ci}/{report.total} repos have workflows "
              f"({report.adherence_rate:.0%})\n")
        missing = report.missing_repos()
        if missing:
            print(f"  Missing CI ({len(missing)}):")
            for entry in missing:
                found = "" if entry.repo_path_found else " [NOT ON DISK]"
                print(f"    - {entry.organ}/{entry.repo_name}{found}")
        drift = report.drift_from_registry(registry)
        if drift:
            print(f"\n  Registry Drift ({len(drift)}):")
            for d in drift:
                print(f"    - {d['organ']}/{d['repo']}: "
                      f"registry={d['registry_says']}, disk={d['filesystem_says']}")
    print()
    return 0
