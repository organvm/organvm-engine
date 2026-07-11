"""Unified CLI for the organvm system.

Usage:
    organvm status
    organvm registry show <repo>
    organvm registry list [--organ X] [--status X] [--tier X] [--format json]
    organvm registry search <query> [--field X] [--exact]
    organvm registry deps <repo> [--reverse] [--transitive]
    organvm registry stats [--json]
    organvm registry validate
    organvm registry update <repo> <field> <value>
    organvm governance audit
    organvm governance check-deps
    organvm governance promote <repo> <target-state>
    organvm seed discover
    organvm seed validate
    organvm seed graph
    organvm metrics calculate
    organvm metrics count-words [--workspace <path>]
    organvm metrics propagate [--cross-repo] [--dry-run]
    organvm metrics refresh [--cross-repo] [--dry-run]
    organvm dispatch validate <file>
    organvm git init-superproject --organ {I|II|III|IV|V|VI|VII|META|LIMINAL}
    organvm git add-submodule --organ X --repo <name> [--url <url>]
    organvm git sync-organ --organ X [--message "msg"]
    organvm git sync-all [--dry-run]
    organvm git status [--organ X]
    organvm git reproduce-workspace [--organ X] [--shallow] [--manifest <path>]
    organvm git diff-pinned [--organ X]
    organvm git install-hooks [--organ X]
    organvm omega status
    organvm omega check
    organvm pitch generate <repo> [--dry-run]
    organvm pitch sync [--organ X] [--dry-run] [--tier X]
    organvm context sync [--dry-run] [--organ X]
    organvm context surfaces [--workspace <path>] [--repo <name>] [--json]
    organvm handoff list [--workspace <path>] [--json]
    organvm handoff clean [--workspace <path>] [--older-than 7d] [--write]
    organvm prompts narrate [--agent claude|gemini|codex] [--project FILTER] [--output FILE] [--summary FILE] [--dry-run] [--gap-hours 24]
    organvm plans atomize [--plans-dir DIR] [--output FILE] [--summary FILE] [--dry-run]
    organvm atoms link [--threshold 0.25] [--by-thread] [--json] [--output FILE]
"""

import argparse
import sys

from organvm_engine.cli.atoms import (
    cmd_atoms_fanout,
    cmd_atoms_link,
    cmd_atoms_pipeline,
    cmd_atoms_reconcile,
    cmd_atoms_research,
)
from organvm_engine.cli.ci import (
    cmd_ci_audit,
    cmd_ci_mandate,
    cmd_ci_protect,
    cmd_ci_scaffold,
    cmd_ci_triage,
)
from organvm_engine.cli.cmd_audit import (
    cmd_audit_absorption,
    cmd_audit_full,
    cmd_audit_layer,
    cmd_audit_organ,
    cmd_audit_repo,
)
from organvm_engine.cli.cmd_pulse import (
    cmd_pulse_advisories,
    cmd_pulse_ammoi,
    cmd_pulse_blast,
    cmd_pulse_briefing,
    cmd_pulse_clusters,
    cmd_pulse_density,
    cmd_pulse_ecosystem,
    cmd_pulse_edges,
    cmd_pulse_emit,
    cmd_pulse_entity_memory,
    cmd_pulse_events,
    cmd_pulse_flow,
    cmd_pulse_history,
    cmd_pulse_memory,
    cmd_pulse_mood,
    cmd_pulse_nerve,
    cmd_pulse_relations,
    cmd_pulse_scan,
    cmd_pulse_show,
    cmd_pulse_start,
    cmd_pulse_status,
    cmd_pulse_stop,
    cmd_pulse_temporal,
    cmd_pulse_tensions,
)
from organvm_engine.cli.completion import cmd_completion
from organvm_engine.cli.content import (
    cmd_content_list,
    cmd_content_new,
    cmd_content_status,
)
from organvm_engine.cli.context import cmd_context_surfaces, cmd_context_sync
from organvm_engine.cli.corpus import (
    cmd_corpus_coverage,
    cmd_corpus_gaps,
    cmd_corpus_repo,
    cmd_corpus_scan,
    cmd_corpus_stats,
    cmd_corpus_trace,
)
from organvm_engine.cli.deadlines import cmd_deadlines
from organvm_engine.cli.debt import cmd_debt_scan, cmd_debt_stats
from organvm_engine.cli.dispatch import cmd_dispatch_validate
from organvm_engine.cli.ecosystem import (
    cmd_ecosystem_actions,
    cmd_ecosystem_audit,
    cmd_ecosystem_coverage,
    cmd_ecosystem_dna,
    cmd_ecosystem_lifecycle,
    cmd_ecosystem_list,
    cmd_ecosystem_matrix,
    cmd_ecosystem_scaffold,
    cmd_ecosystem_scaffold_dna,
    cmd_ecosystem_show,
    cmd_ecosystem_staleness,
    cmd_ecosystem_sync,
    cmd_ecosystem_sync_dna,
    cmd_ecosystem_validate,
)
from organvm_engine.cli.exit_interview import (
    cmd_exit_interview_counter,
    cmd_exit_interview_discover,
    cmd_exit_interview_full,
    cmd_exit_interview_generate,
    cmd_exit_interview_orphans,
    cmd_exit_interview_plan,
    cmd_exit_interview_rectify,
)
from organvm_engine.cli.formation import (
    cmd_formation_invoke,
    cmd_formation_list,
    cmd_formation_show,
)
from organvm_engine.cli.functions import cmd_functions_list, cmd_functions_resolve
from organvm_engine.cli.git_cmds import (
    cmd_git_add_submodule,
    cmd_git_diff_pinned,
    cmd_git_init_superproject,
    cmd_git_install_hooks,
    cmd_git_reproduce,
    cmd_git_status,
    cmd_git_sync_all,
    cmd_git_sync_organ,
)
from organvm_engine.cli.governance import (
    cmd_governance_audit,
    cmd_governance_authorize,
    cmd_governance_checkdeps,
    cmd_governance_dictums,
    cmd_governance_excavate,
    cmd_governance_graph_history,
    cmd_governance_impact,
    cmd_governance_placement,
    cmd_governance_promote,
)
from organvm_engine.cli.handoff import cmd_handoff_clean, cmd_handoff_list
from organvm_engine.cli.indexer import (
    cmd_index_bridge,
    cmd_index_scan,
    cmd_index_show,
    cmd_index_stats,
)
from organvm_engine.cli.irf import (
    cmd_irf_add,
    cmd_irf_complete,
    cmd_irf_list,
    cmd_irf_stats,
    cmd_irf_status,
)
from organvm_engine.cli.ledger import (
    cmd_ledger_checkpoint,
    cmd_ledger_genesis,
    cmd_ledger_log,
    cmd_ledger_repair,
    cmd_ledger_status,
    cmd_ledger_verify,
)
from organvm_engine.cli.lint_vars import cmd_lint_vars
from organvm_engine.cli.metrics import (
    cmd_metrics_calculate,
    cmd_metrics_count_words,
    cmd_metrics_propagate,
    cmd_metrics_refresh,
)
from organvm_engine.cli.network import (
    cmd_network_log,
    cmd_network_map,
    cmd_network_scan,
    cmd_network_status,
    cmd_network_suggest,
    cmd_network_synthesize,
)
from organvm_engine.cli.omega import cmd_omega_check, cmd_omega_status, cmd_omega_update
from organvm_engine.cli.ontologia import (
    cmd_ontologia_bootstrap,
    cmd_ontologia_events,
    cmd_ontologia_health,
    cmd_ontologia_history,
    cmd_ontologia_list,
    cmd_ontologia_merge,
    cmd_ontologia_policies,
    cmd_ontologia_reclassify,
    cmd_ontologia_relocate,
    cmd_ontologia_resolve,
    cmd_ontologia_revisions,
    cmd_ontologia_runbooks,
    cmd_ontologia_sense,
    cmd_ontologia_snapshot,
    cmd_ontologia_split,
    cmd_ontologia_status,
    cmd_ontologia_tensions,
)
from organvm_engine.cli.organism import cmd_organism, cmd_organism_snapshot
from organvm_engine.cli.pitch import cmd_pitch_generate, cmd_pitch_sync
from organvm_engine.cli.plans import (
    cmd_plans_atomize,
    cmd_plans_audit,
    cmd_plans_index,
    cmd_plans_overlaps,
    cmd_plans_sweep,
    cmd_plans_tidy,
)
from organvm_engine.cli.portal import (
    cmd_portal_convergences,
    cmd_portal_import_stars,
    cmd_portal_propose,
    cmd_portal_status,
)
from organvm_engine.cli.primitives import (
    cmd_primitive_guardian_add_watch,
    cmd_primitive_guardian_check,
    cmd_primitive_guardian_watchlist,
    cmd_primitive_inspect,
    cmd_primitive_invoke,
    cmd_primitive_ledger_entries,
    cmd_primitive_ledger_record,
    cmd_primitive_ledger_snapshot,
    cmd_primitive_list,
)
from organvm_engine.cli.prompts import (
    cmd_prompts_audit,
    cmd_prompts_clipboard,
    cmd_prompts_distill,
    cmd_prompts_narrate,
)
from organvm_engine.cli.refresh import cmd_refresh
from organvm_engine.cli.registry import (
    cmd_registry_deps,
    cmd_registry_list,
    cmd_registry_merge,
    cmd_registry_search,
    cmd_registry_show,
    cmd_registry_split,
    cmd_registry_stats,
    cmd_registry_update,
    cmd_registry_validate,
)
from organvm_engine.cli.resolve_cmd import cmd_resolve, cmd_topology_build
from organvm_engine.cli.seed import (
    cmd_seed_discover,
    cmd_seed_graph,
    cmd_seed_ownership,
    cmd_seed_validate,
)
from organvm_engine.cli.session import (
    cmd_session_agents,
    cmd_session_analyze,
    cmd_session_archive,
    cmd_session_debrief,
    cmd_session_export,
    cmd_session_list,
    cmd_session_plans,
    cmd_session_projects,
    cmd_session_prompts,
    cmd_session_review,
    cmd_session_show,
    cmd_session_transcript,
)
from organvm_engine.cli.sop import (
    cmd_sop_audit,
    cmd_sop_check,
    cmd_sop_discover,
    cmd_sop_init,
    cmd_sop_resolve,
)
from organvm_engine.cli.status import cmd_status
from organvm_engine.cli.study import (
    cmd_study_audit_report,
    cmd_study_consilience,
    cmd_study_feedback,
)
from organvm_engine.cli.taxonomy import cmd_taxonomy_audit, cmd_taxonomy_classify
from organvm_engine.cli.testament import (
    cmd_testament_cascade,
    cmd_testament_catalog,
    cmd_testament_gallery,
    cmd_testament_play,
    cmd_testament_record_session,
    cmd_testament_render,
    cmd_testament_status,
)
from organvm_engine.cli.trivium import (
    cmd_trivium_dialects,
    cmd_trivium_essays,
    cmd_trivium_matrix,
    cmd_trivium_scan,
    cmd_trivium_status,
    cmd_trivium_synthesize,
)
from organvm_engine.cli.verify import (
    cmd_verify_contracts,
    cmd_verify_ledger,
    cmd_verify_system,
    cmd_verify_temporal,
)
from organvm_engine.paths import registry_path as _default_registry_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organvm",
        description="Unified CLI for the organvm eight-organ system",
    )
    parser.add_argument(
        "--registry",
        default=str(_default_registry_path()),
        help="Path to registry-v2.json",
    )
    sub = parser.add_subparsers(dest="command")

    # registry
    reg = sub.add_parser("registry", help="Registry operations")
    reg_sub = reg.add_subparsers(dest="subcommand")

    show = reg_sub.add_parser("show", help="Show a registry entry")
    show.add_argument("repo")

    ls = reg_sub.add_parser("list", help="List repos with filters")
    ls.add_argument("--organ", default=None)
    ls.add_argument("--status", default=None)
    ls.add_argument("--tier", default=None)
    ls.add_argument("--promotion-status", default=None)
    ls.add_argument("--public", action="store_true")
    ls.add_argument("--platinum", action="store_true")
    ls.add_argument("--name-contains", default=None)
    ls.add_argument("--depends-on", default=None, help="Filter repos that depend on this repo")
    ls.add_argument(
        "--dependency-of",
        default=None,
        help="Filter repos that are dependencies of this repo",
    )
    ls.add_argument(
        "--sort-by",
        default="name",
        help="Sort field (name, organ, status, tier, promotion_status, ...)",
    )
    ls.add_argument("--desc", action="store_true", help="Sort descending")
    ls_archived = ls.add_mutually_exclusive_group()
    ls_archived.add_argument("--archived", action="store_true")
    ls_archived.add_argument("--unarchived", action="store_true")
    ls.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format",
    )
    ls.add_argument("--json", action="store_true", help="Output JSON")

    search = reg_sub.add_parser("search", help="Search repos by text query")
    search.add_argument("query")
    search.add_argument(
        "--field",
        action="append",
        default=None,
        help="Field(s) to search (repeatable). Defaults to standard text fields.",
    )
    search.add_argument("--exact", action="store_true")
    search.add_argument("--case-sensitive", action="store_true")
    search.add_argument("--limit", type=int, default=None)
    search.add_argument("--organ", default=None)
    search.add_argument("--status", default=None)
    search.add_argument("--tier", default=None)
    search.add_argument("--promotion-status", default=None)
    search.add_argument("--public", action="store_true")
    search.add_argument("--sort-by", default="name")
    search.add_argument("--desc", action="store_true")
    search.add_argument("--json", action="store_true")

    deps = reg_sub.add_parser("deps", help="Show repo dependencies/dependents")
    deps.add_argument("repo")
    deps.add_argument("--reverse", action="store_true", help="Show dependents")
    deps.add_argument("--both", action="store_true", help="Show dependencies and dependents")
    deps.add_argument("--transitive", action="store_true", help="Include transitive graph")
    deps.add_argument("--max-depth", type=int, default=None)
    deps.add_argument("--json", action="store_true")

    stats = reg_sub.add_parser("stats", help="Show registry summary statistics")
    stats.add_argument("--json", action="store_true")

    reg_sub.add_parser("validate", help="Validate registry")

    upd = reg_sub.add_parser("update", help="Update a registry field")
    upd.add_argument("repo")
    upd.add_argument("field")
    upd.add_argument("value")
    upd.add_argument(
        "--reason", default="", help="Reason for the change (recorded for promotion_status)",
    )

    rsplit = reg_sub.add_parser("split", help="Split registry into per-organ files")
    rsplit.add_argument("output_dir", help="Directory for per-organ files")

    rmerge = reg_sub.add_parser("merge", help="Merge per-organ files into registry")
    rmerge.add_argument("input_dir", help="Directory containing per-organ files")
    rmerge.add_argument("--output", default=None, help="Output file path")

    # governance
    gov = sub.add_parser("governance", help="Governance operations")
    gov_sub = gov.add_subparsers(dest="subcommand")
    aud = gov_sub.add_parser("audit", help="Full governance audit")
    aud.add_argument(
        "--rules",
        default=None,
        help="Path to governance-rules.json",
    )
    aud.add_argument(
        "--signal-closure",
        action="store_true",
        help="Run signal closure validation (AX-6)",
    )
    aud.add_argument(
        "--self-knowledge",
        action="store_true",
        help="Run tetradic self-knowledge validation (AX-7)",
    )
    aud.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    aud.add_argument(
        "--json",
        action="store_true",
        help="Output JSON",
    )

    gov_sub.add_parser("check-deps", help="Validate dependency graph")

    gh_p = gov_sub.add_parser(
        "graph-history",
        help="Temporal dependency graph: snapshots, point-in-time queries, diffs",
    )
    gh_p.add_argument(
        "--snapshot",
        action="store_true",
        help="Record the current registry state as a temporal snapshot",
    )
    gh_p.add_argument(
        "--at",
        default=None,
        help="Show the graph as it was at this ISO-8601 timestamp",
    )
    gh_p.add_argument(
        "--from",
        dest="from_ts",
        default=None,
        help="Start timestamp for diff (use with --to)",
    )
    gh_p.add_argument(
        "--to",
        dest="to_ts",
        default=None,
        help="End timestamp for diff (use with --from)",
    )
    gh_p.add_argument("--json", action="store_true", help="JSON output")
    gh_p.add_argument(
        "--data",
        default=None,
        help="Path to temporal-graph.json (default: corpus/data/temporal-graph.json)",
    )

    auth_p = gov_sub.add_parser("authorize", help="Check actor authorization for a transition")
    auth_p.add_argument("actor", help="Actor handle (e.g. '4jp', 'chris')")
    auth_p.add_argument("repo", help="Repository name")
    auth_p.add_argument("target", help="Target promotion state")
    auth_p.add_argument("--enforce", action="store_true", help="Use enforcing mode")

    prom = gov_sub.add_parser("promote", help="Check promotion eligibility")
    prom.add_argument("repo")
    prom.add_argument("target", help="Target promotion state")
    prom.add_argument("--reason", default="", help="Reason for the promotion (recorded in history)")

    imp = gov_sub.add_parser(
        "impact",
        help="Calculate blast radius of a repo change",
    )
    imp.add_argument("repo", help="Repository name")

    dictums_p = gov_sub.add_parser("dictums", help="List or check constitutional dictums")
    dictums_p.add_argument("--check", action="store_true", help="Run compliance checks")
    dictums_p.add_argument("--id", default=None, help="Show a specific dictum by ID")
    dictums_p.add_argument("--json", action="store_true", help="JSON output")
    dictums_p.add_argument(
        "--level",
        default=None,
        choices=["axiom", "organ", "repo"],
        help="Filter by dictum tier",
    )
    dictums_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace root for filesystem checks",
    )

    place_p = gov_sub.add_parser(
        "placement",
        help="Audit repo-to-organ placement affinity",
    )
    place_p.add_argument("--repo", default=None, help="Single repo to check")
    place_p.add_argument("--json", action="store_true", help="JSON output")
    place_p.add_argument(
        "--audit",
        action="store_true",
        help="Only show flagged repos",
    )

    exc_p = gov_sub.add_parser(
        "excavate",
        help="Scan for buried entities in repos",
    )
    exc_p.add_argument(
        "--type",
        default=None,
        choices=["sub_package", "cross_organ_family", "extractable_module", "misplaced_governance"],
        help="Filter by entity type",
    )
    exc_p.add_argument("--severity", default=None, choices=["info", "warning", "critical"])
    exc_p.add_argument("--json", action="store_true", help="JSON output")
    exc_p.add_argument("--families", action="store_true", help="Only show cross-organ families")
    exc_p.add_argument("--workspace", default=None, help="Workspace root directory")
    exc_p.add_argument(
        "--register",
        action="store_true",
        help="Register sub-packages as ontologia MODULE entities",
    )

    # seed
    seed = sub.add_parser("seed", help="Seed.yaml operations")
    seed.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    seed_sub = seed.add_subparsers(dest="subcommand")
    seed_sub.add_parser("discover", help="Find all seed.yaml files")
    seed_sub.add_parser("validate", help="Validate all seed.yaml files")
    seed_sub.add_parser("graph", help="Build produces/consumes graph")
    seed_own = seed_sub.add_parser("ownership", help="Show ownership declarations for a repo")
    seed_own.add_argument("repo", help="Repository name")

    # metrics
    met = sub.add_parser("metrics", help="Metrics operations")
    met.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    met_sub = met.add_subparsers(dest="subcommand")
    calc = met_sub.add_parser("calculate", help="Compute current metrics")
    calc.add_argument("--output", default=None, help="Output file path")

    met_sub.add_parser(
        "count-words",
        help="Count words across the workspace",
    )

    prop = met_sub.add_parser(
        "propagate",
        help="Propagate metrics to documentation files",
    )
    prop.add_argument(
        "--cross-repo",
        action="store_true",
        help="Read metrics-targets.yaml and propagate to all consumers",
    )
    prop.add_argument(
        "--targets",
        default=None,
        help="Path to metrics-targets.yaml (default: corpus root)",
    )
    prop.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing",
    )

    refresh = met_sub.add_parser(
        "refresh",
        help="Calculate + propagate in one step",
    )
    refresh.add_argument(
        "--cross-repo",
        action="store_true",
        help="Propagate to all registered consumers",
    )
    refresh.add_argument(
        "--targets",
        default=None,
        help="Path to metrics-targets.yaml",
    )
    refresh.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing",
    )

    # dispatch
    dis = sub.add_parser("dispatch", help="Dispatch operations")
    dis_sub = dis.add_subparsers(dest="subcommand")
    val = dis_sub.add_parser("validate", help="Validate a dispatch payload")
    val.add_argument("file", help="Path to dispatch payload JSON")

    # fabrica — Cyclic Dispatch Protocol (SPEC-024)
    fab = sub.add_parser(
        "fabrica",
        help="Cyclic Dispatch Protocol — RELEASE → CATCH → HANDOFF → FORTIFY",
    )
    fab_sub = fab.add_subparsers(dest="subcommand")

    fab_release = fab_sub.add_parser("release", help="Create a RelayPacket (enter RELEASE phase)")
    fab_release.add_argument("--text", required=True, help="Raw intention text")
    fab_release.add_argument("--source", default="cli", help="Source channel (cli|mcp|dashboard)")
    fab_release.add_argument("--organ", default=None, help="Organ hint")
    fab_release.add_argument("--tags", default=None, help="Comma-separated tags")
    fab_release.add_argument("--json", action="store_true", help="Output JSON")

    fab_catch = fab_sub.add_parser("catch", help="Generate/list/select ApproachVectors (CATCH phase)")
    fab_catch.add_argument("--packet-id", dest="packet_id", required=True, help="Packet ID")
    fab_catch.add_argument("--thesis", default=None, help="New vector thesis")
    fab_catch.add_argument("--select", default=None, help="Select a vector by ID prefix")
    fab_catch.add_argument("--list", action="store_true", help="List existing vectors")
    fab_catch.add_argument("--organs", default=None, help="Comma-separated target organs")
    fab_catch.add_argument("--scope", default="medium", help="Resource weight (light|medium|heavy)")
    fab_catch.add_argument("--agents", default=None, help="Comma-separated agent types")
    fab_catch.add_argument("--json", action="store_true", help="Output JSON")

    fab_handoff = fab_sub.add_parser("handoff", help="Dispatch task to agent backend (HANDOFF phase)")
    fab_handoff.add_argument("--packet-id", dest="packet_id", required=True, help="Packet ID")
    fab_handoff.add_argument(
        "--backend", required=True,
        help="Agent backend (copilot|jules|actions|claude|launchagent|human)",
    )
    fab_handoff.add_argument("--repo", required=True, help="Target repo (owner/repo or path)")
    fab_handoff.add_argument("--title", default=None, help="Task title")
    fab_handoff.add_argument("--body", default="", help="Task body/specification")
    fab_handoff.add_argument("--task-id", dest="task_id", default=None, help="Explicit task ID")
    fab_handoff.add_argument("--labels", default=None, help="Comma-separated extra labels")
    fab_handoff.add_argument("--branch", default=None, help="Branch name or ref")
    fab_handoff.add_argument("--execute", action="store_true", help="Actually dispatch (default is dry-run)")
    fab_handoff.add_argument("--json", action="store_true", help="Output JSON")

    fab_fortify = fab_sub.add_parser("fortify", help="Review dispatched work (FORTIFY phase)")
    fab_fortify.add_argument("--intent-id", dest="intent_id", default=None, help="Filter by intent ID")
    fab_fortify.add_argument("--record-id", dest="record_id", default=None, help="Filter by record ID")
    fab_fortify.add_argument(
        "--verdict", default=None,
        help="Verdict (approve|reject|recycle)",
    )
    fab_fortify.add_argument("--check", action="store_true", help="Poll backends for status updates")

    fab_status = fab_sub.add_parser("status", help="Show active relay cycles")
    fab_status.add_argument("--packet-id", dest="packet_id", default=None, help="Filter by packet ID")
    fab_status.add_argument("--json", action="store_true", help="Output JSON")

    fab_log = fab_sub.add_parser("log", help="Show transition log")
    fab_log.add_argument("--packet-id", dest="packet_id", default=None, help="Filter by packet ID")
    fab_log.add_argument("--json", action="store_true", help="Output JSON")

    fab_heartbeat = fab_sub.add_parser(
        "heartbeat",
        help="Run a heartbeat cycle or manage the LaunchAgent daemon",
    )
    fab_heartbeat.add_argument(
        "--install", action="store_true",
        help="Generate and load the LaunchAgent plist",
    )
    fab_heartbeat.add_argument(
        "--uninstall", action="store_true",
        help="Unload and remove the LaunchAgent plist",
    )
    fab_heartbeat.add_argument(
        "--interval", type=int, default=900,
        help="Heartbeat interval in seconds (default: 900 = 15 minutes)",
    )
    fab_heartbeat.add_argument("--json", action="store_true", help="Output JSON")

    # contrib — Contribution engine and backflow pipeline
    contrib = sub.add_parser(
        "contrib",
        help="Contribution engine — outbound PR tracking and backflow signals",
    )
    contrib_sub = contrib.add_subparsers(dest="subcommand")
    contrib_sub.add_parser("list", help="List all contribution repos and targets")
    contrib_sub.add_parser("status", help="Check upstream PR status for all contrib repos")
    contrib_backflow = contrib_sub.add_parser(
        "backflow", help="Generate backflow signal report",
    )
    contrib_backflow.add_argument(
        "--write", action="store_true", help="Write manifest to atoms dir",
    )

    # git
    git = sub.add_parser(
        "git",
        help="Hierarchical superproject management",
    )
    git.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    git_sub = git.add_subparsers(dest="subcommand")

    git_init = git_sub.add_parser(
        "init-superproject",
        help="Initialize organ superproject",
    )
    git_init.add_argument(
        "--organ",
        required=True,
        help="Organ key (I, II, ..., META, LIMINAL)",
    )
    git_init.add_argument(
        "--dry-run",
        action="store_true",
        help="Report without making changes",
    )

    git_add = git_sub.add_parser(
        "add-submodule",
        help="Add submodule to organ superproject",
    )
    git_add.add_argument("--organ", required=True, help="Organ key")
    git_add.add_argument("--repo", required=True, help="Repository name")
    git_add.add_argument(
        "--url",
        default=None,
        help="Git URL (auto-derived if omitted)",
    )

    git_sync = git_sub.add_parser(
        "sync-organ",
        help="Sync submodule pointers",
    )
    git_sync.add_argument("--organ", required=True, help="Organ key")
    git_sync.add_argument("--message", default=None, help="Commit message")
    git_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Report without committing",
    )

    git_sync_all = git_sub.add_parser(
        "sync-all",
        help="Sync all organ superprojects",
    )
    git_sync_all.add_argument(
        "--dry-run",
        action="store_true",
        help="Report without committing",
    )

    git_status = git_sub.add_parser("status", help="Show submodule drift")
    git_status.add_argument(
        "--organ",
        default=None,
        help="Specific organ (default: all)",
    )

    git_reproduce = git_sub.add_parser(
        "reproduce-workspace",
        help="Clone workspace from superprojects",
    )
    git_reproduce.add_argument(
        "--target",
        required=True,
        help="Target directory",
    )
    git_reproduce.add_argument(
        "--organ",
        default=None,
        help="Single organ to clone",
    )
    git_reproduce.add_argument(
        "--shallow",
        action="store_true",
        help="Shallow clone",
    )
    git_reproduce.add_argument(
        "--manifest",
        default=None,
        help="Path to workspace-manifest.json",
    )

    git_diff = git_sub.add_parser(
        "diff-pinned",
        help="Show detailed diff between pinned and current",
    )
    git_diff.add_argument(
        "--organ",
        default=None,
        help="Specific organ (default: all)",
    )

    git_hooks = git_sub.add_parser(
        "install-hooks",
        help="Install git context sync hooks",
    )
    git_hooks.add_argument(
        "--organ",
        default=None,
        help="Specific organ (default: all)",
    )

    # deadlines
    dl = sub.add_parser(
        "deadlines",
        help="Show upcoming deadlines from rolling-todo",
    )
    dl.add_argument(
        "--days",
        type=int,
        default=30,
        help="Show deadlines within N days (default 30)",
    )
    dl.add_argument(
        "--all",
        action="store_true",
        help="Show all deadlines regardless of date",
    )

    # corpus
    corpus = sub.add_parser("corpus", help="Corpus knowledge graph (IRF-SYS-104)")
    corpus_sub = corpus.add_subparsers(dest="subcommand")

    corpus_scan = corpus_sub.add_parser(
        "scan", help="Scan post-flood corpus and build knowledge graph",
    )
    corpus_scan.add_argument(
        "--corpus-dir", default="post-flood",
        help="Path to post-flood/ directory (default: post-flood)",
    )
    corpus_scan.add_argument(
        "--workspace", default=None,
        help="Path to ~/Workspace/ for seed.yaml scanning",
    )
    corpus_scan.add_argument(
        "--output", "-o", default=None,
        help="Save graph to JSON file",
    )
    corpus_scan.add_argument(
        "--json", action="store_true",
        help="Output full graph as JSON",
    )

    corpus_stats = corpus_sub.add_parser(
        "stats", help="Show corpus knowledge graph statistics",
    )
    corpus_stats.add_argument(
        "--corpus-dir", default="post-flood",
        help="Path to post-flood/ directory",
    )
    corpus_stats.add_argument(
        "--workspace", default=None,
        help="Path to ~/Workspace/",
    )
    corpus_stats.add_argument(
        "--graph-file", default=None,
        help="Load graph from saved JSON instead of scanning",
    )
    corpus_stats.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )

    corpus_gaps = corpus_sub.add_parser(
        "gaps", help="Show concepts without implementation",
    )
    corpus_gaps.add_argument(
        "--corpus-dir", default="post-flood",
        help="Path to post-flood/ directory",
    )
    corpus_gaps.add_argument(
        "--workspace", default=None,
        help="Path to ~/Workspace/",
    )
    corpus_gaps.add_argument(
        "--graph-file", default=None,
        help="Load graph from saved JSON instead of scanning",
    )
    corpus_gaps.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    corpus_gaps.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show implementation details per concept",
    )

    _corpus_common = {
        "--corpus-dir": {"default": "post-flood", "help": "Path to post-flood/ directory"},
        "--workspace": {"default": None, "help": "Path to ~/Workspace/"},
        "--graph-file": {"default": None, "help": "Load graph from saved JSON instead of scanning"},
        "--json": {"action": "store_true", "help": "Output as JSON"},
    }

    corpus_trace = corpus_sub.add_parser(
        "trace", help="Trace a concept through its full provenance chain",
    )
    corpus_trace.add_argument("concept", help="Concept ID to trace (e.g. AMMOI, evolution_law)")
    for flag, kwargs in _corpus_common.items():
        corpus_trace.add_argument(flag, **kwargs)

    corpus_coverage = corpus_sub.add_parser(
        "coverage", help="Show implementation depth and fragility for all concepts",
    )
    for flag, kwargs in _corpus_common.items():
        corpus_coverage.add_argument(flag, **kwargs)
    corpus_coverage.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show robust concepts with organ distribution",
    )

    corpus_repo = corpus_sub.add_parser(
        "repo", help="Show what concepts a repo implements (reverse lookup)",
    )
    corpus_repo.add_argument("repo", help="Repo name (e.g. organvm-engine)")
    for flag, kwargs in _corpus_common.items():
        corpus_repo.add_argument(flag, **kwargs)

    # ci
    ci = sub.add_parser("ci", help="CI health operations")
    ci_sub = ci.add_subparsers(dest="subcommand")
    ci_triage = ci_sub.add_parser(
        "triage",
        help="Categorize CI failures from soak data",
    )
    ci_triage.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    ci_audit = ci_sub.add_parser(
        "audit",
        help="Infrastructure audit (The Descent Protocol)",
    )
    ci_audit.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    ci_audit.add_argument(
        "--organ",
        help="Filter by organ key (e.g., META-ORGANVM)",
    )
    ci_audit.add_argument(
        "--repo",
        help="Filter by repo name",
    )
    ci_mandate = ci_sub.add_parser(
        "mandate",
        help="Verify CI workflows exist on disk",
    )
    ci_mandate.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    ci_scaffold = ci_sub.add_parser(
        "scaffold",
        help="Generate CI workflow YAML (lint/test/typecheck) for a repo",
    )
    ci_scaffold.add_argument(
        "path",
        help="Path to the repository root directory",
    )
    ci_scaffold.add_argument(
        "--name",
        help="Override the repo name (default: directory name)",
    )
    ci_scaffold.add_argument(
        "--lint",
        action="store_true",
        help="Include linting step",
    )
    ci_scaffold.add_argument(
        "--test",
        action="store_true",
        help="Include testing step",
    )
    ci_scaffold.add_argument(
        "--typecheck",
        action="store_true",
        help="Include type-checking step",
    )
    ci_scaffold.add_argument(
        "--all",
        action="store_true",
        help="Include all steps (default)",
    )
    ci_scaffold.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print workflow to stdout instead of writing (default)",
    )
    ci_scaffold.add_argument(
        "--write",
        action="store_true",
        dest="write",
        help="Write the workflow file to .github/workflows/ci.yml",
    )
    ci_scaffold.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    ci_protect = ci_sub.add_parser(
        "protect",
        help="Generate branch protection commands for GRADUATED repos",
    )
    ci_protect.add_argument(
        "--organ",
        help="Filter by organ key (e.g., ORGAN-I)",
    )
    ci_protect.add_argument(
        "--repo",
        help="Filter by repo name",
    )
    ci_protect.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show plan without generating full commands (default)",
    )
    ci_protect.add_argument(
        "--execute",
        action="store_true",
        dest="execute",
        help="Generate full gh api commands",
    )
    ci_protect.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    # omega
    om = sub.add_parser("omega", help="Omega scorecard operations")
    om_sub = om.add_subparsers(dest="subcommand")
    om_sub.add_parser("status", help="Display omega scorecard summary")
    om_sub.add_parser("check", help="Machine-readable omega status (JSON)")
    om_update = om_sub.add_parser(
        "update",
        help="Evaluate and write omega snapshot",
    )
    om_update.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview without writing (default)",
    )
    om_update.add_argument(
        "--write",
        action="store_true",
        help="Actually write snapshot (overrides --dry-run)",
    )

    # pitch
    pitch = sub.add_parser("pitch", help="Pitch deck generation")
    pitch.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    pitch_sub = pitch.add_subparsers(dest="subcommand")

    pitch_gen = pitch_sub.add_parser(
        "generate",
        help="Generate pitch deck for a single repo",
    )
    pitch_gen.add_argument("repo", help="Repository name")
    pitch_gen.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )

    pitch_sync = pitch_sub.add_parser(
        "sync",
        help="Sync pitch decks across workspace",
    )
    pitch_sync.add_argument(
        "--organ",
        default=None,
        help="Filter to specific organ",
    )
    pitch_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )
    pitch_sync.add_argument(
        "--tier",
        default=None,
        help="Filter by tier (flagship, standard, all)",
    )

    # status (top-level)
    sub.add_parser("status", help="One-command system health pulse")

    # context
    ctx = sub.add_parser(
        "context",
        help="System context file management",
    )
    ctx.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    ctx_sub = ctx.add_subparsers(dest="subcommand")
    c_sync = ctx_sub.add_parser(
        "sync",
        help="Sync CLAUDE.md, GEMINI.md, and AGENTS.md",
    )
    c_sync.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report changes without writing (default)",
    )
    c_sync.add_argument(
        "--write",
        action="store_true",
        help="Actually write changes (overrides --dry-run)",
    )
    c_sync.add_argument(
        "--diff",
        action="store_true",
        help="Print unified diffs for generated context sections",
    )
    c_sync.add_argument(
        "--organ",
        default=None,
        help="Filter to specific organ",
    )
    c_surfaces = ctx_sub.add_parser(
        "surfaces",
        help="Discover and validate conversation corpus surface exports",
    )
    c_surfaces.add_argument(
        "--repo",
        default=None,
        help="Filter to a specific repository name",
    )
    c_surfaces.add_argument(
        "--json",
        action="store_true",
        help="Output JSON",
    )

    # handoff
    handoff = sub.add_parser(
        "handoff",
        help="Active handoff discovery and cleanup",
    )
    handoff.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    handoff_sub = handoff.add_subparsers(dest="subcommand")
    handoff_list = handoff_sub.add_parser(
        "list",
        help="List active handoff files across the workspace",
    )
    handoff_list.add_argument(
        "--workspace",
        default=argparse.SUPPRESS,
        help="Workspace root directory",
    )
    handoff_list.add_argument(
        "--stale-after",
        default="48h",
        help="Mark handoffs stale after this age (default: 48h)",
    )
    handoff_list.add_argument("--json", action="store_true", help="Output JSON")

    handoff_clean = handoff_sub.add_parser(
        "clean",
        help="Remove expired handoffs, optionally also older handoffs",
    )
    handoff_clean.add_argument(
        "--workspace",
        default=argparse.SUPPRESS,
        help="Workspace root directory",
    )
    handoff_clean.add_argument(
        "--older-than",
        default=None,
        help="Also remove handoffs older than this duration, e.g. 7d",
    )
    handoff_clean.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview removals without deleting files (default)",
    )
    handoff_clean.add_argument(
        "--write",
        action="store_true",
        help="Actually remove files (default is dry-run)",
    )
    handoff_clean.add_argument("--json", action="store_true", help="Output JSON")

    # organism
    org_cmd = sub.add_parser(
        "organism",
        help="Living data organism — unified system snapshot",
    )
    org_cmd.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    org_cmd.add_argument(
        "--organ",
        default=None,
        help="Zoom to specific organ",
    )
    org_cmd.add_argument(
        "--repo",
        default=None,
        help="Zoom to specific repo",
    )
    org_cmd.add_argument(
        "--json",
        action="store_true",
        help="Output JSON",
    )
    org_cmd.add_argument(
        "--omega",
        action="store_true",
        help="Include omega scorecard",
    )
    org_sub = org_cmd.add_subparsers(dest="subcommand")
    org_snap = org_sub.add_parser(
        "snapshot",
        help="Write system-organism.json snapshot to corpus",
    )
    org_snap.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    org_snap.add_argument(
        "--omega",
        action="store_true",
        help="Include omega scorecard",
    )
    org_snap.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview without writing (default)",
    )
    org_snap.add_argument(
        "--write",
        action="store_true",
        help="Actually write snapshot (overrides --dry-run)",
    )

    # refresh
    ref = sub.add_parser(
        "refresh",
        help="Unified refresh: metrics + variables + propagation + context + organism",
    )
    ref.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    ref.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )
    ref.add_argument(
        "--skip-context",
        action="store_true",
        help="Skip context file sync",
    )
    ref.add_argument(
        "--skip-organism",
        action="store_true",
        help="Skip organism snapshot",
    )
    ref.add_argument(
        "--skip-legacy",
        action="store_true",
        help="Skip legacy regex propagation",
    )
    ref.add_argument(
        "--skip-plans",
        action="store_true",
        help="Skip plan hygiene check",
    )
    ref.add_argument(
        "--skip-sop",
        action="store_true",
        help="Skip SOP inventory check",
    )
    ref.add_argument(
        "--skip-atoms",
        action="store_true",
        help="Skip atoms pipeline + fanout",
    )

    # lint-vars
    lv = sub.add_parser(
        "lint-vars",
        help="Check for unbound metric references in markdown",
    )
    lv.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    lv.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if violations found",
    )

    # session
    sess = sub.add_parser(
        "session",
        help="Session transcript management and export",
    )
    sess_sub = sess.add_subparsers(dest="subcommand")

    sess_sub.add_parser(
        "projects",
        help="List Claude Code project directories",
        description=(
            "List every Claude Code project directory and its session count. "
            "Decodes the encoded cwd from `~/.claude/projects/<slug>/*.jsonl` "
            "and reports decoded path + count."
        ),
    )
    sess_sub.add_parser(
        "agents",
        help="Show session inventory across all agents",
        description=(
            "Per-agent counts and total size across Claude, Codex, Gemini, "
            "and OpenCode session stores."
        ),
    )

    sess_list = sess_sub.add_parser("list", help="List sessions with metadata")
    sess_list.add_argument(
        "--project",
        default=None,
        help="Filter to specific project directory name or path substring",
    )
    sess_list.add_argument(
        "--directory",
        default=None,
        help=(
            "Filter by exact absolute working directory (not a substring). "
            "Most precise filter; safe when project names share a substring."
        ),
    )
    sess_list.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex", "opencode"],
        help="Filter to specific agent (default: all)",
    )
    sess_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max sessions to show (default 20, 0=all)",
    )

    sess_show = sess_sub.add_parser("show", help="Show session details")
    sess_show.add_argument("session_id", help="Session ID (full or prefix)")

    sess_archive = sess_sub.add_parser(
        "archive",
        help="Archive sessions to their project directories",
    )
    sess_archive.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session ID to archive (omit for batch)",
    )
    sess_archive.add_argument(
        "--project",
        default=None,
        help="Filter to specific project path substring",
    )
    sess_archive.add_argument(
        "--since",
        default=None,
        help="Only sessions on or after this date (YYYY-MM-DD or relative: 7d, 24h)",
    )
    sess_archive.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter to specific agent",
    )
    sess_archive.add_argument(
        "--no-raw",
        action="store_true",
        help="Skip copying raw .jsonl (saves space)",
    )
    sess_archive.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )
    sess_archive.add_argument(
        "--force",
        action="store_true",
        help="Re-archive even if already archived (refresh a stale snapshot, "
        "e.g. a resumed session whose work landed after an earlier archive)",
    )

    sess_export = sess_sub.add_parser(
        "export",
        help="Export session as praxis-perpetua review",
    )
    sess_export.add_argument("session_id", help="Session ID (full or prefix)")
    sess_export.add_argument(
        "--slug",
        required=True,
        help="Descriptive slug for the filename (e.g., 'gemini-styx-research')",
    )
    sess_export.add_argument(
        "--output",
        default=None,
        help="Output directory (default: praxis-perpetua/sessions/)",
    )
    sess_export.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing",
    )

    sess_transcript = sess_sub.add_parser(
        "transcript",
        help="Render session transcript (ephemeral view, not committed)",
    )
    sess_transcript.add_argument("session_id", help="Session ID (full or prefix)")
    sess_transcript.add_argument(
        "--unabridged",
        action="store_true",
        help="Full audit trail: thinking blocks, tool I/O, generated code",
    )
    sess_transcript.add_argument(
        "--output",
        default=None,
        help="Write to file instead of stdout",
    )

    sess_prompts = sess_sub.add_parser(
        "prompts",
        help="Extract prompts only — for drift detection and pattern analysis",
    )
    sess_prompts.add_argument("session_id", help="Session ID (full or prefix)")
    sess_prompts.add_argument(
        "--output",
        default=None,
        help="Write to file instead of stdout",
    )

    # plans
    sess_plans = sess_sub.add_parser(
        "plans",
        help="List or audit plan files across the workspace",
    )
    sess_plans.add_argument(
        "--project",
        default=None,
        help="Filter by project path substring",
    )
    sess_plans.add_argument(
        "--since",
        default=None,
        help="Only plans on or after this date (YYYY-MM-DD)",
    )
    sess_plans.add_argument(
        "--audit",
        action="store_true",
        help="Render plan-vs-reality audit scaffold",
    )
    sess_plans.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex", "governance"],
        help="Filter by agent",
    )
    sess_plans.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key (I, II, ..., META)",
    )
    sess_plans.add_argument(
        "--matrix",
        action="store_true",
        help="Show agent × organ count matrix",
    )

    # analyze
    sess_analyze = sess_sub.add_parser(
        "analyze",
        help="Cross-session prompt analysis",
    )
    sess_analyze.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter to specific agent",
    )
    sess_analyze.add_argument(
        "--full",
        action="store_true",
        help="Analyze all sessions (slow)",
    )
    sess_analyze.add_argument(
        "--output",
        default=None,
        help="Write report to file",
    )

    # review
    sess_review = sess_sub.add_parser(
        "review",
        help="Review a session: summary, prompts, related plans",
    )
    sess_review.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session ID (full or prefix)",
    )
    sess_review.add_argument(
        "--latest",
        action="store_true",
        help="Review the most recent session",
    )
    sess_review.add_argument(
        "--project",
        default=None,
        help="Filter to project when using --latest",
    )

    # debrief
    sess_debrief = sess_sub.add_parser(
        "debrief",
        help="Session close-out with tiered to-dos (big/medium/small)",
    )
    sess_debrief.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Session ID (full or prefix)",
    )
    sess_debrief.add_argument(
        "--latest",
        action="store_true",
        help="Debrief the most recent session",
    )
    sess_debrief.add_argument(
        "--project",
        default=None,
        help="Filter to project when using --latest",
    )
    sess_debrief.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # prompts
    prompts = sub.add_parser("prompts", help="Prompt narrative analysis")
    prompts_sub = prompts.add_subparsers(dest="subcommand")

    prompts_narrate = prompts_sub.add_parser(
        "narrate",
        help="Extract, classify, and thread prompts into narrative arcs",
    )
    prompts_narrate.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter to specific agent",
    )
    prompts_narrate.add_argument(
        "--project",
        default=None,
        help="Filter to specific project directory name or path substring",
    )
    prompts_narrate.add_argument(
        "--output",
        default=None,
        help="Output JSONL file path (default: ~/.claude/prompts/annotated-prompts.jsonl)",
    )
    prompts_narrate.add_argument(
        "--summary",
        default=None,
        help="Output summary .md path (default: ~/.claude/prompts/NARRATIVE-SUMMARY.md)",
    )
    prompts_narrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse all sessions, print stats, write nothing",
    )
    prompts_narrate.add_argument(
        "--gap-hours",
        type=float,
        default=24.0,
        help="Hours gap to split episodes (default 24)",
    )

    prompts_clipboard = prompts_sub.add_parser(
        "clipboard",
        help="Extract and classify AI prompts from Paste.app clipboard history",
    )
    prompts_clipboard.add_argument(
        "--db-path",
        default=None,
        help="Path to Paste.app SQLite database (default: standard macOS location)",
    )
    prompts_clipboard.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for export files",
    )
    prompts_clipboard.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and classify but write nothing",
    )
    prompts_clipboard.add_argument(
        "--json-only",
        action="store_true",
        help="Only write JSON export",
    )
    prompts_clipboard.add_argument(
        "--md-only",
        action="store_true",
        help="Only write Markdown export",
    )

    prompts_audit = prompts_sub.add_parser(
        "audit",
        help="Run prompt & pipeline data audit — noise, completion, linking quality",
    )
    prompts_audit.add_argument(
        "--output",
        default=None,
        help="Output file path (default: <atoms-dir>/AUDIT-REPORT.md)",
    )
    prompts_audit.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of writing report",
    )
    prompts_audit.add_argument(
        "--noise-only",
        action="store_true",
        help="Run only the noise analysis",
    )

    prompts_distill = prompts_sub.add_parser(
        "distill",
        help="Distill clipboard prompts into operational patterns and SOP coverage",
    )
    prompts_distill.add_argument(
        "--input",
        default=None,
        help="Input clipboard prompts JSON file (default: <atoms-dir>/clipboard-prompts.json)",
    )
    prompts_distill.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for generated SOP scaffolds (default: .sops/)",
    )
    prompts_distill.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Analyze but write nothing (default)",
    )
    prompts_distill.add_argument(
        "--write",
        action="store_true",
        help="Actually write scaffold files",
    )
    prompts_distill.add_argument(
        "--json",
        action="store_true",
        help="Output coverage report as JSON",
    )
    prompts_distill.add_argument(
        "--scaffold",
        action="store_true",
        help="Generate SOP scaffold files for uncovered patterns",
    )

    # plans
    plans = sub.add_parser("plans", help="Plan file analysis and atomization")
    plans_sub = plans.add_subparsers(dest="subcommand")

    plans_atomize = plans_sub.add_parser(
        "atomize",
        help="Atomize plan files into atomic tasks with rich metadata",
    )
    plans_atomize.add_argument(
        "--plans-dir",
        default=None,
        help="Root directory containing plan .md files (default: ~/.claude/plans)",
    )
    plans_atomize.add_argument(
        "--output",
        default=None,
        help="Output JSONL file path (default: <plans-dir>/atomized-tasks.jsonl)",
    )
    plans_atomize.add_argument(
        "--summary",
        default=None,
        help="Output summary .md path (default: <plans-dir>/ATOMIZED-SUMMARY.md)",
    )
    plans_atomize.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse all files, print stats, write nothing",
    )
    plans_atomize.add_argument(
        "--all",
        action="store_true",
        help="Discover from entire workspace (multi-agent) instead of single --plans-dir",
    )
    plans_atomize.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter source plans by agent (requires --all)",
    )
    plans_atomize.add_argument(
        "--organ",
        default=None,
        help="Filter source plans by organ key (requires --all)",
    )

    plans_index = plans_sub.add_parser(
        "index",
        help="Build and display plan index (machine-readable snapshot)",
    )
    plans_index.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of table",
    )
    plans_index.add_argument(
        "--write",
        action="store_true",
        help="Write plan-index.json to corpus data/plans/",
    )
    plans_index.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter by agent",
    )
    plans_index.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )

    plans_audit = plans_sub.add_parser(
        "audit",
        help="Flag stale plans, duplicates, and orphans",
    )
    plans_audit.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )
    plans_audit.add_argument(
        "--stale-days",
        type=int,
        default=30,
        help="Days threshold for stale detection (default 30)",
    )

    plans_overlaps = plans_sub.add_parser(
        "overlaps",
        help="Show overlapping plan clusters",
    )
    plans_overlaps.add_argument(
        "--severity",
        default=None,
        choices=["conflict", "warning", "info"],
        help="Filter by severity level",
    )
    plans_overlaps.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )

    plans_sweep = plans_sub.add_parser(
        "sweep",
        help="List archival candidates (read-only)",
    )
    plans_sweep.add_argument(
        "--stale-days",
        type=int,
        default=14,
        help="Days threshold for stale detection (default 14)",
    )
    plans_sweep.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter by agent",
    )
    plans_sweep.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )
    plans_sweep.add_argument(
        "--json",
        action="store_true",
        help="Output JSON",
    )

    plans_tidy = plans_sub.add_parser(
        "tidy",
        help="Archive eligible plans (dry-run by default)",
    )
    plans_tidy.add_argument(
        "--stale-days",
        type=int,
        default=14,
        help="Days threshold for stale detection (default 14)",
    )
    plans_tidy.add_argument(
        "--include-review",
        action="store_true",
        help="Include stale plans (review confidence) in archival",
    )
    plans_tidy.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter by agent",
    )
    plans_tidy.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )
    plans_tidy.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview without moving files (default)",
    )
    plans_tidy.add_argument(
        "--write",
        action="store_true",
        help="Actually move files (overrides --dry-run)",
    )

    # sop
    sop = sub.add_parser("sop", help="SOP discovery and inventory tracking")
    sop.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    sop.add_argument(
        "--organ",
        default=None,
        help="Filter to specific organ",
    )
    sop_sub = sop.add_subparsers(dest="subcommand")

    sop_discover = sop_sub.add_parser("discover", help="Find all SOP/METADOC files")
    sop_discover.add_argument("--json", action="store_true", help="Output JSON")

    sop_sub.add_parser("audit", help="Compare discovered SOPs against METADOC inventory")

    sop_check = sop_sub.add_parser(
        "check",
        help="Exit non-zero if untracked SOPs exist",
    )
    sop_check.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on any untracked or missing SOPs",
    )

    sop_resolve = sop_sub.add_parser(
        "resolve",
        help="Show active SOPs for a given context",
    )
    sop_resolve.add_argument("name", nargs="?", default=None, help="SOP name to resolve")
    sop_resolve.add_argument("--repo", default=None, help="Filter to specific repo")
    sop_resolve.add_argument(
        "--phase",
        default=None,
        choices=["genesis", "foundation", "hardening", "graduation", "sustaining", "any"],
        help="Filter to lifecycle phase",
    )

    sop_init = sop_sub.add_parser(
        "init",
        help="Scaffold a .sops/ directory with template",
    )
    sop_init.add_argument(
        "--scope",
        choices=["repo", "organ"],
        default="repo",
        help="Scope of the new SOP (default: repo)",
    )
    sop_init.add_argument("--name", default=None, help="SOP name (default: new-procedure)")

    # content
    content = sub.add_parser("content", help="Content pipeline management")
    content_sub = content.add_subparsers(dest="subcommand")

    content_list = content_sub.add_parser("list", help="List all content posts")
    content_list.add_argument("--status", help="Filter by status (draft/published/archived)")
    content_list.add_argument("--tag", help="Filter by tag")
    content_list.add_argument("--json", action="store_true", help="JSON output")

    content_new = content_sub.add_parser("new", help="Scaffold a new post")
    content_new.add_argument("slug", help="Post slug (e.g. trash-and-church)")
    content_new.add_argument("--title", help="Post title")
    content_new.add_argument("--hook", help="Hook line")
    content_new.add_argument("--session", help="Source session ID")
    content_new.add_argument("--dry-run", action="store_true", help="Preview without creating")

    content_status = content_sub.add_parser("status", help="Weekly cadence health check")
    content_status.add_argument("--json", action="store_true", help="JSON output")

    # testament
    testament = sub.add_parser(
        "testament",
        help="Generative self-portrait — the system renders itself",
    )
    testament_sub = testament.add_subparsers(dest="subcommand")

    testament_status = testament_sub.add_parser("status", help="Testament system status")
    testament_status.add_argument("--json", action="store_true", help="JSON output")

    testament_render = testament_sub.add_parser(
        "render",
        help="Render artifacts from live system data",
    )
    testament_render.add_argument("--organ", default=None, help="Filter to organ")
    testament_render.add_argument("--write", action="store_true", help="Actually produce files")
    testament_render.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for artifacts",
    )
    testament_render.add_argument("--registry", default=None, help="Registry path override")
    testament_render.add_argument(
        "--all-repos",
        action="store_true",
        help="Render SVG identity cards for all repos",
    )

    testament_catalog = testament_sub.add_parser("catalog", help="List produced artifacts")
    testament_catalog.add_argument("--organ", default=None, help="Filter to organ")
    testament_catalog.add_argument("--json", action="store_true", help="JSON output")

    testament_gallery = testament_sub.add_parser(
        "gallery",
        help="Generate static HTML gallery",
    )
    testament_gallery.add_argument("--write", action="store_true", help="Actually generate")
    testament_gallery.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for gallery",
    )

    testament_cascade = testament_sub.add_parser(
        "cascade",
        help="Execute feedback network — renderers feed each other",
    )
    testament_cascade.add_argument(
        "--write",
        action="store_true",
        help="Actually execute (default: manifest only)",
    )
    testament_cascade.add_argument("--json", action="store_true", help="JSON output")
    testament_cascade.add_argument("--registry", default=None, help="Registry path override")

    testament_play = testament_sub.add_parser(
        "play",
        help="Render system as sonic parameters — OSC bridge to alchemical-synthesizer",
    )
    testament_play.add_argument("--json", action="store_true", help="JSON output")
    testament_play.add_argument(
        "--osc",
        action="store_true",
        help="Output OSC messages only (for piping to SC)",
    )
    testament_play.add_argument(
        "--yaml",
        action="store_true",
        help="Output YAML only (for BrahmaModBus.sc)",
    )
    testament_play.add_argument("--registry", default=None, help="Registry path override")

    testament_record = testament_sub.add_parser(
        "record-session",
        help="Detect self-referential changes and emit testament events",
    )
    testament_record.add_argument(
        "--from-commit",
        default="HEAD~1",
        help="Start commit (default: HEAD~1)",
    )
    testament_record.add_argument(
        "--to-commit",
        default="HEAD",
        help="End commit (default: HEAD)",
    )
    testament_record.add_argument(
        "--write",
        action="store_true",
        help="Actually emit events (default: dry-run)",
    )
    testament_record.add_argument(
        "--spine-path",
        default=None,
        help="Custom spine JSONL path",
    )

    # ledger (Testament Protocol — hash-linked event chain)
    ledger = sub.add_parser(
        "ledger",
        help="Testament Protocol — native hash-linked event chain",
    )
    ledger_sub = ledger.add_subparsers(dest="subcommand")

    ledger_genesis = ledger_sub.add_parser("genesis", help="Initialize the chain")
    ledger_genesis.add_argument("--chain-path", default=None, help="Override chain file path")

    ledger_status_p = ledger_sub.add_parser("status", help="Chain status")
    ledger_status_p.add_argument("--json", action="store_true")
    ledger_status_p.add_argument("--chain-path", default=None)

    ledger_verify_p = ledger_sub.add_parser("verify", help="Verify chain integrity")
    ledger_verify_p.add_argument("--chain-path", default=None)
    ledger_verify_p.add_argument("--event", default=None, help="Verify single event")

    ledger_log_p = ledger_sub.add_parser("log", help="Query the chain")
    ledger_log_p.add_argument("--type", default=None, help="Filter by event type")
    ledger_log_p.add_argument("--tier", default=None, help="Filter by tier")
    ledger_log_p.add_argument("--limit", type=int, default=20)
    ledger_log_p.add_argument("--json", action="store_true")
    ledger_log_p.add_argument("--chain-path", default=None)

    ledger_chk = ledger_sub.add_parser("checkpoint", help="Create Merkle checkpoint")
    ledger_chk.add_argument("--write", action="store_true")
    ledger_chk.add_argument("--chain-path", default=None)

    ledger_repair = ledger_sub.add_parser("repair", help="Repair corrupted chain")
    ledger_repair.add_argument("--write", action="store_true", help="Execute repair")
    ledger_repair.add_argument("--chain-path", default=None)

    # ecosystem
    eco = sub.add_parser(
        "ecosystem",
        help="Product ecosystem discovery — per-product business profiles",
    )
    eco.add_argument("--workspace", default=None, help="Workspace root directory")
    eco.add_argument("--organ", default=None, help="Filter to specific organ")
    eco_sub = eco.add_subparsers(dest="subcommand")

    eco_show = eco_sub.add_parser("show", help="Show ecosystem profile for a repo")
    eco_show.add_argument("repo", help="Repository name")
    eco_show.add_argument("--json", action="store_true", help="Output JSON")

    eco_sub.add_parser("list", help="List products with/without ecosystem profiles")

    eco_cov = eco_sub.add_parser("coverage", help="Product x Pillar coverage matrix")
    eco_cov.add_argument("--json", action="store_true", help="Output JSON")

    eco_sub.add_parser("audit", help="Show gaps and suggestions")

    eco_scaffold = eco_sub.add_parser(
        "scaffold",
        help="Generate ecosystem scaffold for a repo",
    )
    eco_scaffold.add_argument("repo", help="Repository name")
    eco_scaffold.add_argument("--dry-run", action="store_true", default=True)
    eco_scaffold.add_argument("--write", action="store_true", help="Write file")

    eco_sync = eco_sub.add_parser(
        "sync",
        help="Scaffold ecosystem.yaml for all missing products",
    )
    eco_sync.add_argument("--dry-run", action="store_true", default=True)
    eco_sync.add_argument("--write", action="store_true", help="Actually write files")

    eco_matrix = eco_sub.add_parser("matrix", help="Cross-product view of one pillar")
    eco_matrix.add_argument("--pillar", required=True, help="Pillar name")
    eco_matrix.add_argument("--json", action="store_true", help="Output JSON")

    eco_actions = eco_sub.add_parser("actions", help="Prioritized next-action list")
    eco_actions.add_argument("--json", action="store_true", help="Output JSON")

    eco_validate = eco_sub.add_parser("validate", help="Validate all ecosystem.yaml files")
    eco_validate.add_argument("--json", action="store_true", help="Output JSON")

    eco_dna = eco_sub.add_parser("dna", help="Show pillar DNA for a repo")
    eco_dna.add_argument("repo", help="Repository name")
    eco_dna.add_argument("--pillar", default=None, help="Show only one pillar")
    eco_dna.add_argument("--json", action="store_true", help="Output JSON")

    eco_scaffold_dna = eco_sub.add_parser(
        "scaffold-dna",
        help="Generate pillar DNA from ecosystem.yaml",
    )
    eco_scaffold_dna.add_argument("repo", help="Repository name")
    eco_scaffold_dna.add_argument("--dry-run", action="store_true", default=True)
    eco_scaffold_dna.add_argument("--write", action="store_true", help="Write files")

    eco_sync_dna = eco_sub.add_parser(
        "sync-dna",
        help="Scaffold pillar DNA for all repos with ecosystem.yaml",
    )
    eco_sync_dna.add_argument("--dry-run", action="store_true", default=True)
    eco_sync_dna.add_argument("--write", action="store_true", help="Actually write files")

    eco_staleness = eco_sub.add_parser(
        "staleness",
        help="Staleness report for pillar DNA artifacts",
    )
    eco_staleness.add_argument("--json", action="store_true", help="Output JSON")

    eco_lifecycle = eco_sub.add_parser("lifecycle", help="Show lifecycle stages for a repo")
    eco_lifecycle.add_argument("repo", help="Repository name")
    eco_lifecycle.add_argument("--json", action="store_true", help="Output JSON")

    # network testament
    net = sub.add_parser(
        "network",
        help="Network testament — external mirror mapping and engagement tracking",
    )
    net.add_argument("--workspace", default=None, help="Workspace root directory")
    net.add_argument("--organ", default=None, help="Filter to specific organ")
    net_sub = net.add_subparsers(dest="subcommand")

    net_scan = net_sub.add_parser("scan", help="Scan repos for potential mirrors")
    net_scan.add_argument("--repo", default=None, help="Filter to specific repo")
    net_scan.add_argument("--dry-run", action="store_true", default=True)
    net_scan.add_argument("--write", action="store_true", help="Update network-map.yaml files")

    net_map = net_sub.add_parser("map", help="Show network map for repo or organ")
    net_map.add_argument("--repo", default=None, help="Filter to specific repo")
    net_map.add_argument("--json", action="store_true", help="Output JSON")

    net_log = net_sub.add_parser("log", help="Record an engagement action")
    net_log.add_argument("repo", help="ORGANVM repo name")
    net_log.add_argument("project", help="External project identifier")
    net_log.add_argument("--lens", required=True, choices=["technical", "parallel", "kinship"])
    net_log.add_argument(
        "--action",
        required=True,
        choices=["presence", "contribution", "dialogue", "invitation"],
    )
    net_log.add_argument("--detail", required=True, help="Description of the action")
    net_log.add_argument("--url", default=None, help="Link to the action")
    net_log.add_argument("--outcome", default=None, help="Response or result")
    net_log.add_argument("--tags", default=None, help="Comma-separated tags")

    net_status = net_sub.add_parser("status", help="Network health summary")
    net_status.add_argument("--json", action="store_true", help="Output JSON")

    net_synth = net_sub.add_parser("synthesize", help="Generate narrative testament")
    net_synth.add_argument(
        "--period",
        default="monthly",
        choices=["weekly", "monthly", "all-time"],
    )
    net_synth.add_argument("--write", action="store_true", help="Write to testament directory")

    net_sub.add_parser("suggest", help="Suggest next engagement actions")

    # portal — BIFRONS star<->contribution portal (engine half)
    portal = sub.add_parser(
        "portal",
        help="BIFRONS star<->contribution portal — resonance, proposals, convergence",
    )
    portal_sub = portal.add_subparsers(dest="subcommand")

    portal_status = portal_sub.add_parser("status", help="Portal store status")
    portal_status.add_argument("--db", default=None, help="Portal DB path")

    portal_import = portal_sub.add_parser(
        "import-stars", help="Compile star dossiers into resonance edges",
    )
    portal_import.add_argument("--db", default=None, help="Portal DB path")
    portal_import.add_argument("--write", action="store_true", help="Persist edges (default)")

    portal_conv = portal_sub.add_parser("convergences", help="Cross-organ convergence points")
    portal_conv.add_argument("--db", default=None, help="Portal DB path")
    portal_conv.add_argument("--min-repos", type=int, default=2, dest="min_repos")
    portal_conv.add_argument("--json", action="store_true", help="Output JSON")

    portal_prop = portal_sub.add_parser("propose", help="Generate a transmutation proposal")
    portal_prop.add_argument("external", help="External repo (owner/name)")
    portal_prop.add_argument("target", help="Target ORGANVM repo")
    portal_prop.add_argument("--db", default=None, help="Portal DB path")

    # trivium — dialectica universalis
    trv = sub.add_parser(
        "trivium",
        help="Trivium — Dialectica Universalis: cross-organ structural isomorphism",
    )
    trv.add_argument("--registry", default=None, help="Path to registry JSON")
    trv_sub = trv.add_subparsers(dest="subcommand")

    trv_dialects = trv_sub.add_parser("dialects", help="List all eight dialects")
    trv_dialects.add_argument("--json", action="store_true", help="Output JSON")

    trv_matrix = trv_sub.add_parser("matrix", help="Show translation evidence matrix")
    trv_matrix.add_argument("--organ", default=None, help="Filter to organ pairs")
    trv_matrix.add_argument("--json", action="store_true", help="Output JSON")

    trv_scan = trv_sub.add_parser("scan", help="Scan correspondences between organs")
    trv_scan.add_argument("organ_a", nargs="?", default=None, help="First organ key")
    trv_scan.add_argument("organ_b", nargs="?", default=None, help="Second organ key")
    trv_scan.add_argument("--all", action="store_true", help="Scan all 28 pairs")
    trv_scan.add_argument("--json", action="store_true", help="Output JSON")

    trv_synth = trv_sub.add_parser("synthesize", help="Generate trivium testament")
    trv_synth.add_argument("--write", action="store_true", help="Write to testament dir")
    trv_synth.add_argument("--output-dir", default=None, help="Output directory")

    trv_status = trv_sub.add_parser("status", help="Trivium subsystem health")
    trv_status.add_argument("--json", action="store_true", help="Output JSON")

    trv_essays = trv_sub.add_parser("essays", help="Generate essay catalog from translations")
    trv_essays.add_argument("--json", action="store_true", help="Output JSON")
    trv_essays.add_argument("--write", action="store_true", help="Write catalog to disk")
    trv_essays.add_argument("--output-dir", default=None, help="Output directory")
    trv_essays.add_argument(
        "--tier",
        default="analogical",
        choices=["formal", "structural", "analogical", "all"],
        help="Minimum tier to include (default: analogical)",
    )

    # audit
    aud = sub.add_parser(
        "audit",
        help="Infrastructure wiring audit — 6-layer verification",
    )
    aud.add_argument("--workspace", default=None, help="Workspace root directory")
    aud_sub = aud.add_subparsers(dest="subcommand")

    aud_full = aud_sub.add_parser("full", help="Run all 6 audit layers")
    aud_full.add_argument("--organ", default=None, help="Filter to specific organ")
    aud_full.add_argument("--json", action="store_true", help="Output JSON")
    aud_full.add_argument("--output", default=None, help="Write report to file")

    aud_layer = aud_sub.add_parser("layer", help="Run a single audit layer")
    aud_layer.add_argument(
        "layer",
        choices=["filesystem", "reconcile", "seeds", "edges", "content", "absorption"],
        help="Layer name",
    )
    aud_layer.add_argument("--organ", default=None, help="Filter to specific organ")
    aud_layer.add_argument("--json", action="store_true", help="Output JSON")

    aud_repo = aud_sub.add_parser("repo", help="Audit a single repo")
    aud_repo.add_argument("repo", help="Repository name")
    aud_repo.add_argument("--json", action="store_true", help="Output JSON")

    aud_organ = aud_sub.add_parser("organ", help="Audit a single organ")
    aud_organ.add_argument("organ_key", help="Organ key (I, II, ..., META)")
    aud_organ.add_argument("--json", action="store_true", help="Output JSON")

    aud_abs = aud_sub.add_parser("absorption", help="Scan deposit locations only")
    aud_abs.add_argument("--json", action="store_true", help="Output JSON")
    aud_abs.add_argument("--verbose", action="store_true", help="Include per-deposit detail")

    # verify
    vfy = sub.add_parser(
        "verify",
        help="Formal verification of the dispatch pipeline",
    )
    vfy.add_argument("--workspace", default=None, help="Workspace root directory")
    vfy_sub = vfy.add_subparsers(dest="subcommand")

    vfy_contracts = vfy_sub.add_parser(
        "contracts",
        help="Check registered dispatch contracts",
    )
    vfy_contracts.add_argument(
        "--event",
        default=None,
        help="Check a specific event type only",
    )

    vfy_temporal = vfy_sub.add_parser(
        "temporal",
        help="Check temporal ordering of dispatch events",
    )
    vfy_temporal.add_argument(
        "--event",
        default=None,
        help="Check a specific event type only",
    )

    vfy_ledger = vfy_sub.add_parser(
        "ledger",
        help="Show dispatch ledger state",
    )
    vfy_ledger.add_argument("--json", action="store_true", help="Output JSON")

    vfy_system = vfy_sub.add_parser(
        "system",
        help="Full system verification (all layers)",
    )
    vfy_system.add_argument("--json", action="store_true", help="Output JSON")

    # study
    study = sub.add_parser(
        "study",
        help="Study Suite — feedback loops, consilience index, combined audit",
    )
    study_sub = study.add_subparsers(dest="subcommand")

    study_feedback = study_sub.add_parser(
        "feedback",
        help="Show the feedback loop inventory (positive and negative)",
    )
    study_feedback.add_argument("--json", action="store_true", help="Output JSON")
    study_feedback.add_argument(
        "--polarity",
        choices=["positive", "negative"],
        default=None,
        help="Filter by loop polarity",
    )

    study_consilience = study_sub.add_parser(
        "consilience",
        help="Compute and display the consilience index for derived principles",
    )
    study_consilience.add_argument("--json", action="store_true", help="Output JSON")

    study_audit = study_sub.add_parser(
        "audit",
        help="Combined governance + feedback + consilience audit report",
    )
    study_audit.add_argument("--json", action="store_true", help="Output JSON")
    study_audit.add_argument(
        "--output",
        default=None,
        help="Write report to file instead of stdout",
    )

    # atoms
    atoms = sub.add_parser("atoms", help="Cross-system atom linking")
    atoms_sub = atoms.add_subparsers(dest="subcommand")

    atoms_link = atoms_sub.add_parser(
        "link",
        help="Link atomized tasks to annotated prompts by content similarity",
    )
    atoms_link.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Minimum Jaccard similarity (default 0.30)",
    )
    atoms_link.add_argument(
        "--by-thread",
        action="store_true",
        help="Aggregate prompts per thread before comparison (higher recall)",
    )
    atoms_link.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of table",
    )
    atoms_link.add_argument(
        "--output",
        default=None,
        help="Write output to file",
    )
    atoms_link.add_argument(
        "--tasks",
        default=None,
        help="Path to atomized-tasks.jsonl (default: ~/.claude/plans/atomized-tasks.jsonl)",
    )
    atoms_link.add_argument(
        "--prompts",
        default=None,
        help="Path to annotated-prompts.jsonl",
    )

    atoms_pipeline = atoms_sub.add_parser(
        "pipeline",
        help="Run the full atomization pipeline (atomize → narrate → link → index)",
    )
    atoms_pipeline.add_argument(
        "--write",
        action="store_true",
        help="Execute pipeline and write files (default is dry-run)",
    )
    atoms_pipeline.add_argument(
        "--skip-narrate",
        action="store_true",
        help="Skip prompt narration step",
    )
    atoms_pipeline.add_argument(
        "--skip-link",
        action="store_true",
        help="Skip cross-system linking step",
    )
    atoms_pipeline.add_argument(
        "--agent",
        default=None,
        choices=["claude", "gemini", "codex"],
        help="Filter by agent",
    )
    atoms_pipeline.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )
    atoms_pipeline.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Minimum Jaccard similarity for linking (default 0.30)",
    )
    atoms_pipeline.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: corpus data/atoms/)",
    )
    atoms_pipeline.add_argument(
        "--reconcile",
        action="store_true",
        default=True,
        help="Run git-based task reconciliation after pipeline (default: on)",
    )
    atoms_pipeline.add_argument(
        "--skip-reconcile",
        action="store_true",
        help="Skip git-based reconciliation step",
    )
    atoms_pipeline.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip research activation step",
    )
    atoms_pipeline.add_argument(
        "--research-dir",
        default=None,
        help="Path to research docs directory (default: praxis-perpetua/research/)",
    )

    atoms_reconcile = atoms_sub.add_parser(
        "reconcile",
        help="Cross-reference tasks against git history to detect completed work",
    )
    atoms_reconcile.add_argument(
        "--write",
        action="store_true",
        help="Rewrite tasks JSONL with updated statuses",
    )
    atoms_reconcile.add_argument(
        "--since",
        default=None,
        help="Only check git log since this date (default: plan date)",
    )
    atoms_reconcile.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )

    atoms_fanout = atoms_sub.add_parser(
        "fanout",
        help="Fan out atom data to per-organ rollup JSON files",
    )
    atoms_fanout.add_argument(
        "--write",
        action="store_true",
        help="Execute fanout (default is dry-run)",
    )
    atoms_fanout.add_argument(
        "--atoms-dir",
        default=None,
        help="Path to centralized atoms directory (default: corpus data/atoms/)",
    )
    atoms_fanout.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )

    atoms_research = atoms_sub.add_parser(
        "research",
        help="Scan research docs for actionable directives",
    )
    atoms_research.add_argument(
        "--write",
        action="store_true",
        help="Mark scanned docs as activated (default is dry-run)",
    )
    atoms_research.add_argument(
        "--research-dir",
        default=None,
        help="Path to research docs directory (default: praxis-perpetua/research/)",
    )
    atoms_research.add_argument(
        "--min-confidence",
        type=float,
        default=0.4,
        help="Minimum extraction confidence 0.0-1.0 (default 0.4)",
    )
    atoms_research.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of table",
    )

    # ontologia — structural registry and entity identity
    ont = sub.add_parser(
        "ontologia",
        help="Structural registry: entity identity, naming, governance",
    )
    ont_sub = ont.add_subparsers(dest="subcommand")

    ont_resolve = ont_sub.add_parser("resolve", help="Resolve an entity by name or UID")
    ont_resolve.add_argument("query", help="Entity name, UID, slug, or alias")
    ont_resolve.add_argument("--json", action="store_true", help="JSON output")

    ont_list = ont_sub.add_parser("list", help="List entities")
    ont_list.add_argument("--type", default=None, help="Filter by entity type")
    ont_list.add_argument("--json", action="store_true", help="JSON output")

    ont_bootstrap = ont_sub.add_parser("bootstrap", help="Bootstrap from registry-v2.json")
    ont_bootstrap.add_argument("--store-dir", default=None, help="Store directory override")

    ont_history = ont_sub.add_parser("history", help="Show entity name history")
    ont_history.add_argument("entity", help="Entity name or UID")

    ont_events = ont_sub.add_parser("events", help="Show recent ontologia events")
    ont_events.add_argument("--limit", type=int, default=20, help="Max events to show")

    ont_sub.add_parser("status", help="Show ontologia store status")

    ont_sense = ont_sub.add_parser("sense", help="Run sensors, show detected changes")
    ont_sense.add_argument("--sensor", default=None, help="Run only this sensor")
    ont_sense.add_argument("--json", action="store_true", help="JSON output")

    ont_tensions = ont_sub.add_parser("tensions", help="Run tension detection")
    ont_tensions.add_argument("--json", action="store_true", help="JSON output")

    ont_policies = ont_sub.add_parser("policies", help="List or evaluate governance policies")
    ont_policies.add_argument("--evaluate", action="store_true", help="Evaluate policies")
    ont_policies.add_argument("--write", action="store_true", help="Write revisions")
    ont_policies.add_argument("--json", action="store_true", help="JSON output")

    ont_snapshot = ont_sub.add_parser("snapshot", help="Create or compare state snapshots")
    ont_snapshot.add_argument("--compare", action="store_true", help="Compare with previous")
    ont_snapshot.add_argument("--json", action="store_true", help="JSON output")

    ont_revisions = ont_sub.add_parser("revisions", help="Show revision log")
    ont_revisions.add_argument("--status", default=None, help="Filter by status")
    ont_revisions.add_argument("--json", action="store_true", help="JSON output")

    ont_health = ont_sub.add_parser("health", help="Composite entity health view")
    ont_health.add_argument("--entity", default=None, help="Specific entity to check")
    ont_health.add_argument("--json", action="store_true", help="JSON output")

    ont_runbooks = ont_sub.add_parser("runbooks", help="Generate or verify operational runbooks")
    ont_runbooks.add_argument("--generate", action="store_true", help="Generate runbooks")
    ont_runbooks.add_argument("--verify", action="store_true", help="Verify runbooks exist")
    ont_runbooks.add_argument("--output", default=None, help="Output directory")
    ont_runbooks.add_argument("--json", action="store_true", help="JSON output")

    ont_relocate = ont_sub.add_parser("relocate", help="Move an entity to a new parent")
    ont_relocate.add_argument("entity", help="Entity UID to relocate")
    ont_relocate.add_argument("new_parent", help="New parent entity UID")
    ont_relocate.add_argument("--json", action="store_true", help="JSON output")

    ont_reclassify = ont_sub.add_parser("reclassify", help="Change an entity's type")
    ont_reclassify.add_argument("entity", help="Entity UID to reclassify")
    ont_reclassify.add_argument("new_type", help="New entity type value")
    ont_reclassify.add_argument("--json", action="store_true", help="JSON output")

    ont_merge = ont_sub.add_parser("merge", help="Merge multiple entities into one")
    ont_merge.add_argument("sources", nargs="+", help="Source entity UIDs to merge")
    ont_merge.add_argument("--name", required=True, help="Display name for the successor entity")
    ont_merge.add_argument("--json", action="store_true", help="JSON output")

    ont_split = ont_sub.add_parser("split", help="Split one entity into multiple descendants")
    ont_split.add_argument("source", help="Source entity UID to split")
    ont_split.add_argument(
        "--descendants",
        nargs="+",
        required=True,
        help="Display names for descendant entities",
    )
    ont_split.add_argument(
        "--deprecate",
        action="store_true",
        help="Deprecate the source entity after split",
    )
    ont_split.add_argument("--json", action="store_true", help="JSON output")

    # index — deep structural indexer
    idx = sub.add_parser(
        "index",
        help="Deep structural indexer — drill to atomic components",
    )
    idx.add_argument("--workspace", default=None, help="Workspace root directory")
    idx_sub = idx.add_subparsers(dest="subcommand")

    idx_scan = idx_sub.add_parser("scan", help="Scan repos for atomic components")
    idx_scan.add_argument("--repo", default=None, help="Single repo to scan")
    idx_scan.add_argument("--organ", default=None, help="Filter to specific organ")
    idx_scan.add_argument("--json", action="store_true", help="Output JSON")
    idx_scan.add_argument(
        "--write",
        action="store_true",
        help="Write deep-index.json to corpus",
    )

    idx_show = idx_sub.add_parser("show", help="Show component tree for a repo")
    idx_show.add_argument("repo", help="Repository name")
    idx_show.add_argument("--json", action="store_true", help="Output JSON")
    idx_show.add_argument("--workspace", default=None, help="Workspace root directory")

    idx_sub.add_parser("stats", help="Show cached scan statistics")

    idx_bridge = idx_sub.add_parser("bridge", help="Register components in ontologia")
    idx_bridge.add_argument("--repo", default=None, help="Single repo to bridge")
    idx_bridge.add_argument("--organ", default=None, help="Filter to specific organ")
    idx_bridge.add_argument("--json", action="store_true", help="Output JSON")

    # pulse — system nervous system and self-awareness
    pulse = sub.add_parser(
        "pulse",
        help="System pulse: mood, density, events, nervous system",
    )
    pulse_sub = pulse.add_subparsers(dest="subcommand")

    pulse_show = pulse_sub.add_parser(
        "show",
        help="Current pulse — mood + density + recent events (default)",
    )
    pulse_show.add_argument("--json", action="store_true", help="Output JSON")

    pulse_density = pulse_sub.add_parser(
        "density",
        help="Interconnection density profile",
    )
    pulse_density.add_argument("--json", action="store_true", help="Output JSON")

    pulse_mood = pulse_sub.add_parser(
        "mood",
        help="System mood with reasoning",
    )
    pulse_mood.add_argument("--json", action="store_true", help="Output JSON")

    pulse_events = pulse_sub.add_parser(
        "events",
        help="Event log",
    )
    pulse_events.add_argument(
        "--type",
        default=None,
        help="Filter by event type",
    )
    pulse_events.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max events (default 20)",
    )
    pulse_events.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only events from last N days",
    )
    pulse_events.add_argument("--json", action="store_true", help="Output JSON")

    pulse_nerve = pulse_sub.add_parser(
        "nerve",
        help="Subscription wiring map from seed.yaml declarations",
    )
    pulse_nerve.add_argument("--json", action="store_true", help="Output JSON")

    pulse_emit = pulse_sub.add_parser(
        "emit",
        help="Manually emit an event",
    )
    pulse_emit.add_argument("event_type", help="Event type to emit")
    pulse_emit.add_argument(
        "--source",
        default="cli",
        help="Event source (default: cli)",
    )
    pulse_emit.add_argument(
        "--payload",
        default=None,
        help="JSON payload string",
    )
    pulse_emit.add_argument("--json", action="store_true", help="Output JSON")

    pulse_briefing = pulse_sub.add_parser(
        "briefing",
        help="Session briefing — recent activity summary",
    )
    pulse_briefing.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Lookback window in hours (default 24)",
    )
    pulse_briefing.add_argument("--json", action="store_true", help="Output JSON")

    pulse_memory = pulse_sub.add_parser(
        "memory",
        help="Cross-agent shared memory store",
    )
    pulse_memory.add_argument(
        "--summary",
        action="store_true",
        help="Show aggregate summary instead of listing insights",
    )
    pulse_memory.add_argument(
        "--category",
        default=None,
        help="Filter by category (decision/finding/pattern/warning/todo)",
    )
    pulse_memory.add_argument(
        "--agent",
        default=None,
        help="Filter by recording agent",
    )
    pulse_memory.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max insights to show (default 20)",
    )
    pulse_memory.add_argument("--json", action="store_true", help="Output JSON")

    pulse_flow = pulse_sub.add_parser(
        "flow",
        help="Dependency flow — active/warm/dormant edge visualization",
    )
    pulse_flow.add_argument(
        "--hours",
        type=int,
        default=168,
        help="Lookback window in hours (default 168 = 7 days)",
    )
    pulse_flow.add_argument("--json", action="store_true", help="Output JSON")

    pulse_ecosystem = pulse_sub.add_parser(
        "ecosystem",
        help="Ecosystem universality — archetype coverage across all organs",
    )
    pulse_ecosystem.add_argument("--organ", help="Filter by organ key")
    pulse_ecosystem.add_argument("--json", action="store_true", help="Output JSON")

    pulse_scan = pulse_sub.add_parser(
        "scan",
        help="Run all sensors, emit events, compute AMMOI",
    )
    pulse_scan.add_argument("--json", action="store_true", help="Output JSON")
    pulse_scan.add_argument(
        "--no-sensors",
        action="store_true",
        help="Skip sensor scan, only compute AMMOI",
    )

    pulse_ammoi = pulse_sub.add_parser(
        "ammoi",
        help="Show AMMOI density snapshot (system/organ/repo scale)",
    )
    pulse_ammoi.add_argument("--organ", help="Show organ-level density")
    pulse_ammoi.add_argument("--repo", help="Show entity-level density")
    pulse_ammoi.add_argument("--json", action="store_true", help="Output JSON")

    pulse_history = pulse_sub.add_parser(
        "history",
        help="Temporal AMMOI density trend",
    )
    pulse_history.add_argument(
        "--days",
        type=int,
        default=30,
        help="Lookback window in days (default 30)",
    )
    pulse_history.add_argument("--json", action="store_true", help="Output JSON")

    pulse_start = pulse_sub.add_parser(
        "start",
        help="Install and start the pulse LaunchAgent (15-min heartbeat)",
    )
    pulse_start.add_argument(
        "--interval",
        type=int,
        default=900,
        help="Seconds between pulses (default 900 = 15 min)",
    )
    pulse_start.add_argument("--json", action="store_true", help="Output JSON")

    pulse_stop = pulse_sub.add_parser(
        "stop",
        help="Stop and uninstall the pulse LaunchAgent",
    )
    pulse_stop.add_argument("--json", action="store_true", help="Output JSON")

    pulse_status = pulse_sub.add_parser(
        "status",
        help="Show pulse daemon status and last heartbeat",
    )
    pulse_status.add_argument("--json", action="store_true", help="Output JSON")

    pulse_tensions = pulse_sub.add_parser(
        "tensions",
        help="Show structural tensions (orphans, naming conflicts, overcoupling)",
    )
    pulse_tensions.add_argument("--json", action="store_true", help="Output JSON")

    pulse_clusters = pulse_sub.add_parser(
        "clusters",
        help="Show detected entity clusters with cohesion scores",
    )
    pulse_clusters.add_argument("--json", action="store_true", help="Output JSON")

    pulse_advisories = pulse_sub.add_parser(
        "advisories",
        help="Show governance advisories (recommendations from policy evaluation)",
    )
    pulse_advisories.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max advisories to show (default 20)",
    )
    pulse_advisories.add_argument(
        "--unacked",
        action="store_true",
        help="Show only unacknowledged advisories",
    )
    pulse_advisories.add_argument(
        "--ack",
        dest="ack_id",
        default=None,
        help="Acknowledge an advisory by ID",
    )
    pulse_advisories.add_argument("--json", action="store_true", help="Output JSON")

    pulse_blast = pulse_sub.add_parser(
        "blast",
        help="Show blast radius for a specific entity",
    )
    pulse_blast.add_argument("entity", help="Entity name or UID")
    pulse_blast.add_argument("--json", action="store_true", help="Output JSON")

    pulse_edges = pulse_sub.add_parser(
        "edges",
        help="Show structural edge counts or sync seed edges",
    )
    pulse_edges.add_argument("--json", action="store_true", help="Output JSON")
    pulse_edges_sub = pulse_edges.add_subparsers(dest="edges_action")
    pulse_edges_sync = pulse_edges_sub.add_parser(
        "sync",
        help="Sync seed.yaml edges into ontologia",
    )
    pulse_edges_sync.add_argument("--json", action="store_true", help="Output JSON")

    pulse_temporal = pulse_sub.add_parser(
        "temporal",
        help="Show temporal profile — velocity, acceleration, and trends",
    )
    pulse_temporal.add_argument("--json", action="store_true", help="Output JSON")
    pulse_temporal.add_argument(
        "--window",
        type=int,
        default=7,
        help="Lookback window for derivatives",
    )
    pulse_temporal.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max history snapshots to read",
    )

    pulse_relations = pulse_sub.add_parser(
        "relations",
        help="Multi-scale relation query — seed + indexer + ontologia edges",
    )
    pulse_relations.add_argument("entity", help="Entity name, component path, or UID")
    pulse_relations.add_argument("--json", action="store_true", help="Output JSON")
    pulse_relations.add_argument("--no-seed", action="store_true", help="Skip seed graph")
    pulse_relations.add_argument("--no-indexer", action="store_true", help="Skip import edges")
    pulse_relations.add_argument("--no-ontologia", action="store_true", help="Skip ontologia")

    pulse_entity_mem = pulse_sub.add_parser(
        "entity-memory",
        help="Aggregate all signals about an entity from every data source",
    )
    pulse_entity_mem.add_argument("entity", help="Entity name, component path, or UID")
    pulse_entity_mem.add_argument("--json", action="store_true", help="Output JSON")
    pulse_entity_mem.add_argument("--limit", type=int, default=50, help="Max signals per source")
    pulse_entity_mem.add_argument("--no-pulse", action="store_true")
    pulse_entity_mem.add_argument("--no-insights", action="store_true")
    pulse_entity_mem.add_argument("--no-ontologia", action="store_true")
    pulse_entity_mem.add_argument("--no-continuity", action="store_true")
    pulse_entity_mem.add_argument("--no-metrics", action="store_true")

    # debt — DEBT header detection and tracking
    debt = sub.add_parser(
        "debt",
        help="Scan for DEBT markers (emergency maintenance protocol)",
    )
    debt_sub = debt.add_subparsers(dest="subcommand")

    debt_scan = debt_sub.add_parser("scan", help="Scan source files for DEBT markers")
    debt_scan.add_argument("--organ", default=None, help="Scan only this organ (e.g. META, I)")
    debt_scan.add_argument("--path", default=None, help="Scan a specific directory instead")
    debt_scan.add_argument("--json", action="store_true", help="Output JSON")

    debt_stats_p = debt_sub.add_parser("stats", help="Show DEBT summary statistics")
    debt_stats_p.add_argument("--organ", default=None, help="Scan only this organ (e.g. META, I)")
    debt_stats_p.add_argument("--path", default=None, help="Scan a specific directory instead")
    debt_stats_p.add_argument("--json", action="store_true", help="Output JSON")

    # irf — Index Rerum Faciendarum
    irf = sub.add_parser(
        "irf",
        help="Index Rerum Faciendarum — query the universal work registry",
    )
    irf_sub = irf.add_subparsers(dest="subcommand")

    irf_list = irf_sub.add_parser("list", help="List IRF items with optional filters")
    irf_list.add_argument("--priority", default=None, help="Filter by priority (P0–P3)")
    irf_list.add_argument("--domain", default=None, help="Filter by domain code (e.g. SYS)")
    irf_list.add_argument(
        "--status",
        default=None,
        help="Filter by status (open, completed, blocked, archived)",
    )
    irf_list.add_argument("--owner", default=None, help="Filter by owner (substring match)")
    irf_list.add_argument("--json", action="store_true", help="Output JSON")

    irf_status = irf_sub.add_parser("status", help="Show all fields for a single IRF item")
    irf_status.add_argument("item_id", help="IRF item ID (e.g. IRF-SYS-001)")

    irf_stats_p = irf_sub.add_parser(
        "stats",
        help="Show summary statistics for the IRF document",
    )
    irf_stats_p.add_argument("--json", action="store_true", help="Output JSON")
    irf_stats_p.add_argument(
        "--write",
        action="store_true",
        help="Regenerate the document's ## Statistics block from the parse (IRF-OPS-091)",
    )

    irf_add = irf_sub.add_parser(
        "add",
        help="Add a new open item row (dry-run by default)",
    )
    irf_add.add_argument("--domain", required=True, help="Domain code (e.g. SYS, OPS)")
    irf_add.add_argument("--action", required=True, help="Item description")
    irf_add.add_argument("--priority", default="P2", help="P0–P4 (default P2)")
    irf_add.add_argument("--owner", default="Agent", help="Owner (default Agent)")
    irf_add.add_argument("--source", default="", help="Session ID / provenance")
    irf_add.add_argument("--blocker", default="None", help="Blocker (default None)")
    irf_add.add_argument("--id", default=None, help="Explicit item ID (default: auto-allocate)")
    irf_add.add_argument("--write", action="store_true", help="Apply the mutation")

    irf_complete = irf_sub.add_parser(
        "complete",
        help="Complete an open item: strike through + append DONE ledger row (dry-run by default)",
    )
    irf_complete.add_argument("item_id", help="IRF item ID to complete")
    irf_complete.add_argument("--note", required=True, help="Completion note for the ledger row")
    irf_complete.add_argument("--session", required=True, help="Session ID for provenance")
    irf_complete.add_argument(
        "--done", default=None, help="Explicit DONE-NNN (default: auto-allocate)",
    )
    irf_complete.add_argument("--write", action="store_true", help="Apply the mutation")

    # exit-interview — presidential handoff protocol (A9: Alchemical Inheritance)
    ei = sub.add_parser(
        "exit-interview",
        help="Exit interview protocol — V1→V2 governance handoff",
    )
    ei_sub = ei.add_subparsers(dest="subcommand")

    ei_discover = ei_sub.add_parser("discover", help="Parse gate contracts, build demand/supply maps")
    ei_discover.add_argument("--gate-dir", default=None, help="Gate contract directory (default: ~/Workspace/a-organvm)")
    ei_discover.add_argument("--json", action="store_true", help="Output full discovery as YAML")

    ei_generate = ei_sub.add_parser("generate", help="Generate V1 testimony (exit interviews)")
    ei_generate.add_argument("--gate", default=None, help="Scope to one gate contract name")
    ei_generate.add_argument("--gate-dir", default=None, help="Gate contract directory")

    ei_counter = ei_sub.add_parser("counter", help="Generate V2 counter-testimony (expectations)")
    ei_counter.add_argument("--gate", default=None, help="Scope to one gate contract name")
    ei_counter.add_argument("--gate-dir", default=None, help="Gate contract directory")

    ei_rectify = ei_sub.add_parser("rectify", help="Three-voice rectification (V1 vs V2 vs reality)")
    ei_rectify.add_argument("--gate", default=None, help="Scope to one gate contract name")
    ei_rectify.add_argument("--gate-dir", default=None, help="Gate contract directory")

    ei_plan = ei_sub.add_parser("plan", help="Generate remediation plan from rectification")
    ei_plan.add_argument("--gate", default=None, help="Scope to one gate contract name")
    ei_plan.add_argument("--gate-dir", default=None, help="Gate contract directory")
    ei_plan.add_argument("--format", choices=["yaml", "plan", "issues"], default="plan", help="Output format")

    ei_full = ei_sub.add_parser("full", help="Run all 5 phases: discover → generate → counter → rectify → plan")
    ei_full.add_argument("--gate-dir", default=None, help="Gate contract directory")
    ei_full.add_argument("--dry-run", action="store_true", default=True, help="Preview without writing (default)")
    ei_full.add_argument("--write", action="store_true", help="Persist output to corpus data directory")

    ei_orphans = ei_sub.add_parser("orphans", help="Show V1 modules not claimed by any gate")
    ei_orphans.add_argument("--gate-dir", default=None, help="Gate contract directory")

    # functions — named functions (liquid model)
    functions = sub.add_parser(
        "functions",
        help="Named functions — the liquid constitutional model",
    )
    functions_sub = functions.add_subparsers(dest="subcommand")

    functions_sub.add_parser("list", help="List all named functions").add_argument(
        "--json",
        action="store_true",
        help="Output JSON",
    )

    fn_resolve = functions_sub.add_parser(
        "resolve",
        help="Resolve any identifier to a canonical function name",
    )
    fn_resolve.add_argument("key", help="Organ key, function name, or display name")
    fn_resolve.add_argument("--json", action="store_true", help="Output JSON")

    # fossil — archaeological reconstruction of system history
    fossil = sub.add_parser(
        "fossil",
        help="Fossil record — archaeological reconstruction of ORGANVM git history",
    )
    fossil_sub = fossil.add_subparsers(dest="subcommand")

    fossil_exc = fossil_sub.add_parser(
        "excavate",
        help="Crawl git history and produce fossil-record.jsonl (dry-run by default)",
    )
    fossil_exc.add_argument(
        "--since",
        default=None,
        help="Only include commits after this date (YYYY-MM-DD)",
    )
    fossil_exc.add_argument(
        "--organ",
        default=None,
        help="Filter to specific organ key (e.g. META, I)",
    )
    fossil_exc.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    fossil_exc.add_argument(
        "--write",
        action="store_true",
        help="Append new records to fossil-record.jsonl (default is dry-run)",
    )

    fossil_chronicle = fossil_sub.add_parser(
        "chronicle",
        help="Generate Jungian-voiced epoch narratives",
    )
    fossil_chronicle.add_argument("--epoch", default=None, help="Generate for specific epoch ID")
    fossil_chronicle.add_argument(
        "--regenerate",
        action="store_true",
        help="Overwrite existing chronicles",
    )
    fossil_chronicle.add_argument("--write", action="store_true", help="Write chronicle files")

    fossil_epochs = fossil_sub.add_parser("epochs", help="List all declared epochs")
    fossil_epochs.add_argument("--json", action="store_true", help="Output JSON")

    fossil_stratum = fossil_sub.add_parser("stratum", help="Query the fossil record")
    fossil_stratum.add_argument(
        "--organ",
        default=None,
        help="Filter by organ key",
    )
    fossil_stratum.add_argument(
        "--archetype",
        default=None,
        help="Filter by Jungian archetype (shadow, anima, animus, self, trickster, mother, father, individuation)",
    )
    fossil_stratum.add_argument("--json", action="store_true", help="Output JSON")

    fossil_intentions = fossil_sub.add_parser(
        "intentions",
        help="Browse and extract unique prompt intentions",
    )
    fossil_intentions.add_argument(
        "--scan", default=None, help="Directory to scan for session files",
    )
    fossil_intentions.add_argument("--write", action="store_true", help="Save extracted intentions")
    fossil_intentions.add_argument("--json", action="store_true", help="Output JSON")

    fossil_drift = fossil_sub.add_parser("drift", help="Analyze intention-reality divergence")
    fossil_drift.add_argument("--json", action="store_true", help="Output JSON")

    fossil_witness = fossil_sub.add_parser(
        "witness",
        help="Real-time capture: install hooks, check status, record commits",
    )
    fossil_witness_sub = fossil_witness.add_subparsers(dest="witness_subcommand")

    fossil_witness_install = fossil_witness_sub.add_parser(
        "install",
        help="Install post-commit hooks across workspace (dry-run by default)",
    )
    fossil_witness_install.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    fossil_witness_install.add_argument(
        "--write",
        action="store_true",
        help="Actually install hooks (default is dry-run)",
    )

    fossil_witness_status_p = fossil_witness_sub.add_parser(
        "status",
        help="Show witness coverage across repos",
    )
    fossil_witness_status_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    fossil_witness_status_p.add_argument("--json", action="store_true", help="Output JSON")

    fossil_witness_record = fossil_witness_sub.add_parser(
        "record",
        help="Record a single witnessed commit (called by hook)",
    )
    fossil_witness_record.add_argument(
        "--repo-path",
        dest="repo_path",
        default=None,
        help="Path to the git repo",
    )
    fossil_witness_record.add_argument(
        "--workspace",
        default=None,
        help="Workspace root directory",
    )
    fossil_witness_record.add_argument(
        "--fossil-path",
        dest="fossil_path",
        default=None,
        help="Path to fossil-record.jsonl",
    )

    # taxonomy — functional classification
    tax = sub.add_parser("taxonomy", help="Functional taxonomy commands")
    tax_sub = tax.add_subparsers(dest="subcommand")

    tax_cls = tax_sub.add_parser("classify", help="Classify repos by heuristic")
    tax_cls.add_argument("--organ", help="Filter by organ key")
    tax_cls.add_argument("--dry-run", action="store_true", help="Show without writing")
    tax_cls.add_argument("--json", action="store_true", dest="as_json")

    tax_aud = tax_sub.add_parser("audit", help="Audit classification drift")
    tax_aud.add_argument("--organ", help="Filter by organ key")
    tax_aud.add_argument("--json", action="store_true", dest="as_json")

    # completion — shell completion script generation
    comp = sub.add_parser("completion", help="Generate shell completion scripts")
    comp.add_argument(
        "shell",
        choices=["bash", "zsh", "fish"],
        help="Shell type to generate completion for",
    )

    # primitive — institutional primitives (SPEC-025)
    prim = sub.add_parser(
        "primitive",
        help="Institutional primitives — invoke, inspect, manage",
    )
    prim_sub = prim.add_subparsers(dest="subcommand")

    prim_sub.add_parser("list", help="List all registered primitives").add_argument(
        "--json", action="store_true", help="Output JSON",
    )

    prim_insp = prim_sub.add_parser("inspect", help="Show primitive metadata")
    prim_insp.add_argument("name", help="Primitive name (e.g. assessor)")
    prim_insp.add_argument("--json", action="store_true", help="Output JSON")

    prim_inv = prim_sub.add_parser("invoke", help="Invoke a primitive directly")
    prim_inv.add_argument("name", help="Primitive name")
    prim_inv.add_argument("--context", default=None, help="JSON context string")
    prim_inv.add_argument(
        "--frame",
        default=None,
        help="Frame type (legal, financial, strategic, operational, relational, reputational)",
    )
    prim_inv.add_argument(
        "--stakes",
        default=None,
        help="Stakes level (routine, significant, critical)",
    )
    prim_inv.add_argument("--json", action="store_true", help="Output JSON")

    # guardian subcommands
    prim_guard = prim_sub.add_parser("guardian", help="Guardian watchlist operations")
    guard_sub = prim_guard.add_subparsers(dest="guardian_subcommand")

    guard_add = guard_sub.add_parser("add-watch", help="Add a watch item")
    guard_add.add_argument("--category", required=True, help="deadline, threshold, registration, benefit")
    guard_add.add_argument("--description", required=True, help="What to watch")
    guard_add.add_argument("--threshold", required=True, help="Trigger value (date or number)")
    guard_add.add_argument("--direction", default="approaching", help="above, below, approaching, expired")
    guard_add.add_argument("--watched-value", dest="watched_value", default="", help="Key in state dict to monitor")
    guard_add.add_argument("--alert-window", dest="alert_window", type=int, default=7, help="Days before deadline to alert")

    guard_sub.add_parser("watchlist", help="Show current watchlist").add_argument(
        "--json", action="store_true", help="Output JSON",
    )
    guard_sub.add_parser("check", help="Run a guardian check cycle")

    # ledger subcommands
    prim_ledger = prim_sub.add_parser("ledger", help="Institutional ledger operations")
    ledger_sub = prim_ledger.add_subparsers(dest="ledger_subcommand")

    led_rec = ledger_sub.add_parser("record", help="Record a ledger entry")
    led_rec.add_argument("--category", required=True, help="income, expense, obligation, receivable, equity, asset")
    led_rec.add_argument("--amount", required=True, help="Dollar amount")
    led_rec.add_argument("--description", default="", help="Entry description")
    led_rec.add_argument("--direction", default="", help="inflow, outflow, neutral")
    led_rec.add_argument("--counterparty", default="", help="Who the entry is with")
    led_rec.add_argument("--recurring", action="store_true", help="Is this recurring?")
    led_rec.add_argument("--frequency", default="one-time", help="monthly, weekly, one-time, etc.")

    ledger_sub.add_parser("snapshot", help="Show economic snapshot").add_argument(
        "--json", action="store_true", help="Output JSON",
    )
    led_ent = ledger_sub.add_parser("entries", help="List ledger entries")
    led_ent.add_argument("--category", default="", help="Filter by category")
    led_ent.add_argument("--json", action="store_true", help="Output JSON")

    # formation — crystallized compositions (INST-COMPOSITION)
    form = sub.add_parser(
        "formation",
        help="Institutional formations — invoke, inspect, list",
    )
    form_sub = form.add_subparsers(dest="subcommand")

    form_sub.add_parser("list", help="List registered formations").add_argument(
        "--json", action="store_true", help="Output JSON",
    )

    form_show = form_sub.add_parser("show", help="Show formation details")
    form_show.add_argument("name", help="Formation name (e.g. aegis)")

    form_inv = form_sub.add_parser("invoke", help="Invoke a formation")
    form_inv.add_argument("name", help="Formation name")
    form_inv.add_argument("--context", default=None, help="JSON context string")
    form_inv.add_argument("--json", action="store_true", help="Output JSON")

    # ── resolve (top-level) ──
    res = sub.add_parser("resolve", help="Resolve a capability to a filesystem path")
    res.add_argument("query", nargs="?", help="Repo name, alias, or @capability")
    res.add_argument("--fallback", default=None, help="Value to return if not found (exit 0)")
    res.add_argument("--all", action="store_true", help="Print all resolved paths")
    res.add_argument("--json", action="store_true", help="Output JSON (with --all)")

    # ── topology ──
    topo = sub.add_parser("topology", help="Topology cache management")
    topo_sub = topo.add_subparsers(dest="subcommand")

    topo_build = topo_sub.add_parser("build", help="Build the topology cache from seed.yaml files")
    topo_build.add_argument("--write", action="store_true", help="Write cache to disk")
    topo_build.add_argument("--verbose", action="store_true", help="List all discovered repos")
    topo_build.add_argument("--workspace", default=None, help="Workspace root override")

    return parser


def main() -> int:
    parser = build_parser()

    # Enable shell completion if argcomplete is installed.
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        ("registry", "show"): cmd_registry_show,
        ("registry", "list"): cmd_registry_list,
        ("registry", "search"): cmd_registry_search,
        ("registry", "deps"): cmd_registry_deps,
        ("registry", "stats"): cmd_registry_stats,
        ("registry", "validate"): cmd_registry_validate,
        ("registry", "update"): cmd_registry_update,
        ("registry", "split"): cmd_registry_split,
        ("registry", "merge"): cmd_registry_merge,
        ("governance", "audit"): cmd_governance_audit,
        ("governance", "check-deps"): cmd_governance_checkdeps,
        ("governance", "graph-history"): cmd_governance_graph_history,
        ("governance", "promote"): cmd_governance_promote,
        ("governance", "authorize"): cmd_governance_authorize,
        ("governance", "impact"): cmd_governance_impact,
        ("governance", "dictums"): cmd_governance_dictums,
        ("governance", "placement"): cmd_governance_placement,
        ("governance", "excavate"): cmd_governance_excavate,
        ("seed", "discover"): cmd_seed_discover,
        ("seed", "validate"): cmd_seed_validate,
        ("seed", "graph"): cmd_seed_graph,
        ("seed", "ownership"): cmd_seed_ownership,
        ("metrics", "calculate"): cmd_metrics_calculate,
        ("metrics", "count-words"): cmd_metrics_count_words,
        ("metrics", "propagate"): cmd_metrics_propagate,
        ("metrics", "refresh"): cmd_metrics_refresh,
        ("dispatch", "validate"): cmd_dispatch_validate,
        ("git", "init-superproject"): cmd_git_init_superproject,
        ("git", "add-submodule"): cmd_git_add_submodule,
        ("git", "sync-organ"): cmd_git_sync_organ,
        ("git", "sync-all"): cmd_git_sync_all,
        ("git", "status"): cmd_git_status,
        ("git", "reproduce-workspace"): cmd_git_reproduce,
        ("git", "diff-pinned"): cmd_git_diff_pinned,
        ("git", "install-hooks"): cmd_git_install_hooks,
        ("corpus", "scan"): cmd_corpus_scan,
        ("corpus", "stats"): cmd_corpus_stats,
        ("corpus", "gaps"): cmd_corpus_gaps,
        ("corpus", "trace"): cmd_corpus_trace,
        ("corpus", "coverage"): cmd_corpus_coverage,
        ("corpus", "repo"): cmd_corpus_repo,
        ("ci", "triage"): cmd_ci_triage,
        ("ci", "audit"): cmd_ci_audit,
        ("ci", "mandate"): cmd_ci_mandate,
        ("ci", "scaffold"): cmd_ci_scaffold,
        ("ci", "protect"): cmd_ci_protect,
        ("pitch", "generate"): cmd_pitch_generate,
        ("pitch", "sync"): cmd_pitch_sync,
        ("context", "sync"): cmd_context_sync,
        ("context", "surfaces"): cmd_context_surfaces,
        ("handoff", "list"): cmd_handoff_list,
        ("handoff", "clean"): cmd_handoff_clean,
        ("omega", "status"): cmd_omega_status,
        ("omega", "check"): cmd_omega_check,
        ("omega", "update"): cmd_omega_update,
        ("taxonomy", "classify"): cmd_taxonomy_classify,
        ("taxonomy", "audit"): cmd_taxonomy_audit,
    }

    # Handle top-level commands (no subcommand)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "topology":
        topo_dispatch = {
            "build": cmd_topology_build,
        }
        sub_cmd = getattr(args, "subcommand", None)
        handler = topo_dispatch.get(sub_cmd) if sub_cmd else None
        if handler:
            return handler(args)
        print("Usage: organvm topology build [--write]", file=sys.stderr)
        return 2
    if args.command == "status":
        return cmd_status(args)
    if args.command == "deadlines":
        return cmd_deadlines(args)
    if args.command == "completion":
        return cmd_completion(args)
    if args.command == "refresh":
        return cmd_refresh(args)
    if args.command == "lint-vars":
        return cmd_lint_vars(args)
    if args.command == "organism":
        if getattr(args, "subcommand", None) == "snapshot":
            return cmd_organism_snapshot(args)
        return cmd_organism(args)
    if args.command == "atoms":
        atoms_dispatch = {
            "link": cmd_atoms_link,
            "pipeline": cmd_atoms_pipeline,
            "reconcile": cmd_atoms_reconcile,
            "fanout": cmd_atoms_fanout,
            "research": cmd_atoms_research,
        }
        handler = atoms_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["atoms", "--help"])
        return 0
    if args.command == "prompts":
        prompts_dispatch = {
            "narrate": cmd_prompts_narrate,
            "clipboard": cmd_prompts_clipboard,
            "audit": cmd_prompts_audit,
            "distill": cmd_prompts_distill,
        }
        handler = prompts_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["prompts", "--help"])
        return 0
    if args.command == "plans":
        plans_dispatch = {
            "atomize": cmd_plans_atomize,
            "index": cmd_plans_index,
            "audit": cmd_plans_audit,
            "overlaps": cmd_plans_overlaps,
            "sweep": cmd_plans_sweep,
            "tidy": cmd_plans_tidy,
        }
        handler = plans_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["plans", "--help"])
        return 0
    if args.command == "audit":
        audit_dispatch = {
            "full": cmd_audit_full,
            "layer": cmd_audit_layer,
            "repo": cmd_audit_repo,
            "organ": cmd_audit_organ,
            "absorption": cmd_audit_absorption,
        }
        handler = audit_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["audit", "--help"])
        return 0
    if args.command == "verify":
        verify_dispatch = {
            "contracts": cmd_verify_contracts,
            "temporal": cmd_verify_temporal,
            "ledger": cmd_verify_ledger,
            "system": cmd_verify_system,
        }
        handler = verify_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["verify", "--help"])
        return 0
    if args.command == "study":
        study_dispatch = {
            "feedback": cmd_study_feedback,
            "consilience": cmd_study_consilience,
            "audit": cmd_study_audit_report,
        }
        handler = study_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["study", "--help"])
        return 0
    if args.command == "content":
        content_dispatch = {
            "list": cmd_content_list,
            "new": cmd_content_new,
            "status": cmd_content_status,
        }
        handler = content_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["content", "--help"])
        return 0
    if args.command == "testament":
        testament_dispatch = {
            "status": cmd_testament_status,
            "render": cmd_testament_render,
            "cascade": cmd_testament_cascade,
            "catalog": cmd_testament_catalog,
            "gallery": cmd_testament_gallery,
            "play": cmd_testament_play,
            "record-session": cmd_testament_record_session,
        }
        handler = testament_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["testament", "--help"])
        return 0
    if args.command == "ledger":
        ledger_dispatch = {
            "genesis": cmd_ledger_genesis,
            "status": cmd_ledger_status,
            "verify": cmd_ledger_verify,
            "log": cmd_ledger_log,
            "checkpoint": cmd_ledger_checkpoint,
            "repair": cmd_ledger_repair,
        }
        handler = ledger_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["ledger", "--help"])
        return 0
    if args.command == "network":
        network_dispatch = {
            "scan": cmd_network_scan,
            "map": cmd_network_map,
            "log": cmd_network_log,
            "status": cmd_network_status,
            "synthesize": cmd_network_synthesize,
            "suggest": cmd_network_suggest,
        }
        handler = network_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["network", "--help"])
        return 0
    if args.command == "portal":
        portal_dispatch = {
            "status": cmd_portal_status,
            "import-stars": cmd_portal_import_stars,
            "convergences": cmd_portal_convergences,
            "propose": cmd_portal_propose,
        }
        handler = portal_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["portal", "--help"])
        return 0
    if args.command == "trivium":
        trivium_dispatch = {
            "dialects": cmd_trivium_dialects,
            "matrix": cmd_trivium_matrix,
            "scan": cmd_trivium_scan,
            "synthesize": cmd_trivium_synthesize,
            "status": cmd_trivium_status,
            "essays": cmd_trivium_essays,
        }
        handler = trivium_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["trivium", "--help"])
        return 0
    if args.command == "ecosystem":
        ecosystem_dispatch = {
            "show": cmd_ecosystem_show,
            "list": cmd_ecosystem_list,
            "coverage": cmd_ecosystem_coverage,
            "audit": cmd_ecosystem_audit,
            "scaffold": cmd_ecosystem_scaffold,
            "sync": cmd_ecosystem_sync,
            "matrix": cmd_ecosystem_matrix,
            "actions": cmd_ecosystem_actions,
            "validate": cmd_ecosystem_validate,
            "dna": cmd_ecosystem_dna,
            "scaffold-dna": cmd_ecosystem_scaffold_dna,
            "sync-dna": cmd_ecosystem_sync_dna,
            "staleness": cmd_ecosystem_staleness,
            "lifecycle": cmd_ecosystem_lifecycle,
        }
        handler = ecosystem_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["ecosystem", "--help"])
        return 0
    if args.command == "sop":
        sop_dispatch = {
            "discover": cmd_sop_discover,
            "audit": cmd_sop_audit,
            "check": cmd_sop_check,
            "resolve": cmd_sop_resolve,
            "init": cmd_sop_init,
        }
        handler = sop_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["sop", "--help"])
        return 0
    if args.command == "session":
        session_dispatch = {
            "projects": cmd_session_projects,
            "agents": cmd_session_agents,
            "list": cmd_session_list,
            "show": cmd_session_show,
            "archive": cmd_session_archive,
            "export": cmd_session_export,
            "transcript": cmd_session_transcript,
            "prompts": cmd_session_prompts,
            "plans": cmd_session_plans,
            "analyze": cmd_session_analyze,
            "review": cmd_session_review,
            "debrief": cmd_session_debrief,
        }
        handler = session_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["session", "--help"])
        return 0
    if args.command == "ontologia":
        ontologia_dispatch = {
            "resolve": cmd_ontologia_resolve,
            "list": cmd_ontologia_list,
            "bootstrap": cmd_ontologia_bootstrap,
            "history": cmd_ontologia_history,
            "events": cmd_ontologia_events,
            "status": cmd_ontologia_status,
            "sense": cmd_ontologia_sense,
            "tensions": cmd_ontologia_tensions,
            "policies": cmd_ontologia_policies,
            "snapshot": cmd_ontologia_snapshot,
            "revisions": cmd_ontologia_revisions,
            "health": cmd_ontologia_health,
            "runbooks": cmd_ontologia_runbooks,
            "relocate": cmd_ontologia_relocate,
            "reclassify": cmd_ontologia_reclassify,
            "merge": cmd_ontologia_merge,
            "split": cmd_ontologia_split,
        }
        handler = ontologia_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        # Default to status when no subcommand given
        if not (getattr(args, "subcommand", "") or ""):
            return cmd_ontologia_status(args)
        parser.parse_args(["ontologia", "--help"])
        return 0
    if args.command == "index":
        index_dispatch = {
            "scan": cmd_index_scan,
            "show": cmd_index_show,
            "stats": cmd_index_stats,
            "bridge": cmd_index_bridge,
        }
        handler = index_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["index", "--help"])
        return 0
    if args.command == "pulse":
        pulse_dispatch = {
            "show": cmd_pulse_show,
            "density": cmd_pulse_density,
            "mood": cmd_pulse_mood,
            "events": cmd_pulse_events,
            "nerve": cmd_pulse_nerve,
            "emit": cmd_pulse_emit,
            "briefing": cmd_pulse_briefing,
            "memory": cmd_pulse_memory,
            "flow": cmd_pulse_flow,
            "ecosystem": cmd_pulse_ecosystem,
            "scan": cmd_pulse_scan,
            "ammoi": cmd_pulse_ammoi,
            "history": cmd_pulse_history,
            "start": cmd_pulse_start,
            "stop": cmd_pulse_stop,
            "status": cmd_pulse_status,
            "tensions": cmd_pulse_tensions,
            "clusters": cmd_pulse_clusters,
            "advisories": cmd_pulse_advisories,
            "blast": cmd_pulse_blast,
            "edges": cmd_pulse_edges,
            "temporal": cmd_pulse_temporal,
            "relations": cmd_pulse_relations,
            "entity-memory": cmd_pulse_entity_memory,
        }
        sub_cmd = getattr(args, "subcommand", "") or ""
        handler = pulse_dispatch.get(sub_cmd)
        if handler:
            return handler(args)
        # Default to "show" when no subcommand given
        if not sub_cmd:
            return cmd_pulse_show(args)
        parser.parse_args(["pulse", "--help"])
        return 0
    if args.command == "debt":
        debt_dispatch = {
            "scan": cmd_debt_scan,
            "stats": cmd_debt_stats,
        }
        handler = debt_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["debt", "--help"])
        return 0
    if args.command == "irf":
        irf_dispatch = {
            "list": cmd_irf_list,
            "status": cmd_irf_status,
            "stats": cmd_irf_stats,
            "add": cmd_irf_add,
            "complete": cmd_irf_complete,
        }
        handler = irf_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["irf", "--help"])
        return 0
    if args.command == "exit-interview":
        ei_dispatch = {
            "discover": cmd_exit_interview_discover,
            "generate": cmd_exit_interview_generate,
            "counter": cmd_exit_interview_counter,
            "rectify": cmd_exit_interview_rectify,
            "plan": cmd_exit_interview_plan,
            "full": cmd_exit_interview_full,
            "orphans": cmd_exit_interview_orphans,
        }
        handler = ei_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["exit-interview", "--help"])
        return 0
    if args.command == "functions":
        functions_dispatch = {
            "list": cmd_functions_list,
            "resolve": cmd_functions_resolve,
        }
        handler = functions_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["functions", "--help"])
        return 0
    if args.command == "fossil":
        from organvm_engine.cli.fossil import (
            cmd_fossil_chronicle,
            cmd_fossil_drift,
            cmd_fossil_epochs,
            cmd_fossil_excavate,
            cmd_fossil_intentions,
            cmd_fossil_stratum,
            cmd_fossil_witness,
        )

        fossil_dispatch = {
            "excavate": cmd_fossil_excavate,
            "chronicle": cmd_fossil_chronicle,
            "intentions": cmd_fossil_intentions,
            "drift": cmd_fossil_drift,
            "epochs": cmd_fossil_epochs,
            "stratum": cmd_fossil_stratum,
            "witness": cmd_fossil_witness,
        }
        handler = fossil_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        parser.parse_args(["fossil", "--help"])
        return 0
    if args.command == "fabrica":
        from organvm_engine.cli.fabrica import (
            cmd_fabrica_catch,
            cmd_fabrica_fortify,
            cmd_fabrica_handoff,
            cmd_fabrica_heartbeat,
            cmd_fabrica_log,
            cmd_fabrica_release,
            cmd_fabrica_status,
        )

        fabrica_dispatch = {
            "release": cmd_fabrica_release,
            "catch": cmd_fabrica_catch,
            "handoff": cmd_fabrica_handoff,
            "fortify": cmd_fabrica_fortify,
            "status": cmd_fabrica_status,
            "log": cmd_fabrica_log,
            "heartbeat": cmd_fabrica_heartbeat,
        }
        handler = fabrica_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        # Default to status when no subcommand given
        if not (getattr(args, "subcommand", "") or ""):
            return cmd_fabrica_status(args)
        parser.parse_args(["fabrica", "--help"])
        return 0

    if args.command == "contrib":
        from organvm_engine.cli.contrib import (
            cmd_contrib_backflow,
            cmd_contrib_list,
            cmd_contrib_status,
        )
        contrib_dispatch = {
            "list": cmd_contrib_list,
            "status": cmd_contrib_status,
            "backflow": cmd_contrib_backflow,
        }
        handler = contrib_dispatch.get(getattr(args, "subcommand", "") or "")
        if handler:
            return handler(args)
        # Default to list when no subcommand given
        if not (getattr(args, "subcommand", "") or ""):
            return cmd_contrib_list(args)
        parser.parse_args(["contrib", "--help"])
        return 0

    if args.command == "primitive":
        sub_cmd = getattr(args, "subcommand", "") or ""
        if sub_cmd == "guardian":
            guard_sub = getattr(args, "guardian_subcommand", "") or ""
            guard_dispatch = {
                "add-watch": cmd_primitive_guardian_add_watch,
                "watchlist": cmd_primitive_guardian_watchlist,
                "check": cmd_primitive_guardian_check,
            }
            handler = guard_dispatch.get(guard_sub)
            if handler:
                return handler(args)
            parser.parse_args(["primitive", "guardian", "--help"])
            return 0
        if sub_cmd == "ledger":
            ledger_sub = getattr(args, "ledger_subcommand", "") or ""
            ledger_dispatch = {
                "record": cmd_primitive_ledger_record,
                "snapshot": cmd_primitive_ledger_snapshot,
                "entries": cmd_primitive_ledger_entries,
            }
            handler = ledger_dispatch.get(ledger_sub)
            if handler:
                return handler(args)
            parser.parse_args(["primitive", "ledger", "--help"])
            return 0
        prim_dispatch = {
            "list": cmd_primitive_list,
            "inspect": cmd_primitive_inspect,
            "invoke": cmd_primitive_invoke,
        }
        handler = prim_dispatch.get(sub_cmd)
        if handler:
            return handler(args)
        parser.parse_args(["primitive", "--help"])
        return 0

    if args.command == "formation":
        form_dispatch = {
            "list": cmd_formation_list,
            "show": cmd_formation_show,
            "invoke": cmd_formation_invoke,
        }
        sub_cmd = getattr(args, "subcommand", "") or ""
        handler = form_dispatch.get(sub_cmd)
        if handler:
            return handler(args)
        parser.parse_args(["formation", "--help"])
        return 0

    subcommand: str | None = getattr(args, "subcommand", None)
    handler = dispatch.get((args.command, subcommand or ""))
    if handler:
        return handler(args)

    parser.parse_args([args.command, "--help"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
