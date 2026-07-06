"""CLI commands for multi-agent session transcript management.

Usage:
    organvm session list [--project X] [--limit N] [--agent X]
    organvm session projects
    organvm session show <session-id>
    organvm session agents
    organvm session export <session-id> --slug <slug> [--output <dir>]
    organvm session transcript <session-id> [--unabridged] [--output <file>]
    organvm session prompts <session-id> [--output <file>]
    organvm session plans [--project X] [--since YYYY-MM-DD] [audit]
    organvm session analyze [--agent X] [--full] [--output <file>]
    organvm session review <session-id> | --latest [--project <path>]
    organvm session debrief <session-id> | --latest [--project <path>] [--json]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from organvm_engine.session.agents import agent_summary, discover_all_sessions
from organvm_engine.session.parser import (
    SessionExport,
    detect_agent,
    find_session,
    list_projects,
    list_sessions,
    parse_any_session,
    render_any_prompts,
    render_any_transcript,
)
from organvm_engine.session.plans import discover_plans


def cmd_session_projects(args: argparse.Namespace) -> int:
    """List all Claude Code project directories."""
    projects = list_projects()
    if not projects:
        print("No Claude Code projects found.")
        return 0

    print(f"{'Project':<60} {'Sessions':>8}")
    print("-" * 70)
    for p in projects:
        print(f"{p['decoded_path']:<60} {p['session_count']:>8}")

    print(f"\n{len(projects)} projects, {sum(p['session_count'] for p in projects)} total sessions")
    return 0


def cmd_session_agents(args: argparse.Namespace) -> int:
    """Show session inventory across all agents."""
    summary = agent_summary()

    if not summary:
        print("No agent sessions found.")
        return 0

    total_sessions = 0
    total_bytes = 0

    print(f"{'Agent':<10} {'Sessions':>8} {'Size':>10} {'Earliest':>12} {'Latest':>12}")
    print("-" * 56)
    for agent, info in sorted(summary.items()):
        print(
            f"{agent:<10} {info['count']:>8} {info['total_human']:>10} "
            f"{info['earliest'] or '?':>12} {info['latest'] or '?':>12}",
        )
        total_sessions += info["count"]
        total_bytes += info["total_bytes"]

    from organvm_engine.session.agents import _human_size

    print("-" * 56)
    print(f"{'Total':<10} {total_sessions:>8} {_human_size(total_bytes):>10}")
    print()
    print("Storage locations:")
    print("  Claude:   ~/.claude/projects/<encoded-cwd>/*.jsonl")
    print("  Gemini:   ~/.local/share/gemini/tmp/<slug>/chats/session-*.{json,jsonl}")
    print("            (slug ← projects.json reverse map of cwd)")
    print("  Codex:    ~/.local/share/codex/sessions/YYYY/MM/DD/rollout-*.jsonl")
    print("            ~/.local/share/codex/archived_sessions/rollout-*.jsonl")
    print("  OpenCode: ~/.local/share/opencode/opencode.db  (SQLite; `session.directory` column)")
    print()
    print("All local-only. Back up ~/.local/share/{claude,codex,gemini,opencode} for durability.")
    return 0


def _print_multi_agent_sessions(
    sessions, limit: int, *, all_agents: bool = False,
) -> None:
    """Render the shared 'multi-agent listing' table."""
    hdr = (
        f"{'Date':<12} {'Agent':<8} {'Size':>8} "
        f"{'Dur':>6} {'ID (first 8)':<10} {'Project'}"
    )
    print(hdr)
    print("-" * 80)
    for s in sessions:
        date = s.date_str
        dur = f"{s.duration_minutes}m" if s.duration_minutes else "?"
        short_id = s.session_id[:8]
        proj = s.project_dir[:35]
        print(f"{date:<12} {s.agent:<8} {s.size_human:>8} {dur:>6} {short_id:<10} {proj}")

    shown = len(sessions)
    if all_agents:
        suffix = " (use --limit to see more)" if limit and shown == limit else ""
        print(f"\nShowing {shown} sessions across all agents{suffix}")
    else:
        print(f"\nShowing {shown} sessions")


def cmd_session_list(args: argparse.Namespace) -> int:
    """List sessions with summary metadata. Supports multi-agent via --agent."""
    project = getattr(args, "project", None)
    limit = getattr(args, "limit", 20)
    agent = getattr(args, "agent", None)
    directory = getattr(args, "directory", None)

    # An exact --directory filter is the most precise signal — always route
    # through the multi-agent pipeline so all four stores honor it.
    if directory:
        sessions = discover_all_sessions(
            agent=agent,
            project_filter=project,
            directory_filter=directory,
        )
        if not sessions:
            scope = agent or "any agent"
            print(f"No sessions found for directory '{directory}' ({scope}).")
            return 0
        if limit:
            sessions = sessions[:limit]
        _print_multi_agent_sessions(sessions, limit)
        return 0

    if agent and agent != "claude":
        # Multi-agent listing via agents module
        sessions = discover_all_sessions(agent=agent, project_filter=project)
        if not sessions:
            print(f"No {agent} sessions found.")
            return 0
        if limit:
            sessions = sessions[:limit]
        _print_multi_agent_sessions(sessions, limit)
        return 0

    if agent is None:
        # Check if user wants all agents
        all_sessions = discover_all_sessions(project_filter=project)
        if all_sessions and not project:
            # Show multi-agent view
            if limit:
                all_sessions = all_sessions[:limit]
            _print_multi_agent_sessions(all_sessions, limit, all_agents=True)
            return 0

    # Claude-only (legacy path, or --agent claude)
    sessions = list_sessions(project)

    if not sessions:
        print("No sessions found.")
        return 0

    if limit:
        sessions = sessions[:limit]

    hdr = (
        f"{'Date':<12} {'Msgs':>5} {'Dur':>6} "
        f"{'Branch':<15} {'ID (first 8)':<10} {'First message'}"
    )
    print(hdr)
    print("-" * 100)
    for s in sessions:
        date = s.date_str
        dur = f"{s.duration_minutes}m" if s.duration_minutes else "?"
        branch = (s.git_branch or "?")[:15]
        short_id = s.session_id[:8]
        preview = s.first_human_message[:50].replace("\n", " ")
        if len(s.first_human_message) > 50:
            preview += "..."
        print(f"{date:<12} {s.message_count:>5} {dur:>6} {branch:<15} {short_id:<10} {preview}")

    shown = len(sessions)
    suffix = " (use --limit to see more)" if limit and shown == limit else ""
    print(f"\nShowing {shown} sessions{suffix}")
    return 0


def cmd_session_show(args: argparse.Namespace) -> int:
    """Show detailed metadata for a specific session."""
    session_id = args.session_id
    jsonl_path = find_session(session_id)

    if not jsonl_path:
        print(f"Session not found: {session_id}")
        print("Use 'organvm session list' to see available sessions.")
        return 1

    agent = detect_agent(jsonl_path)
    meta = parse_any_session(jsonl_path)
    if not meta:
        print(f"Could not parse session: {jsonl_path}")
        return 1

    print(f"Agent:   {agent}")
    print(f"Session: {meta.session_id}")
    print(f"Slug:    {meta.slug}")
    print(f"CWD:     {meta.cwd}")
    print(f"Branch:  {meta.git_branch}")
    print(f"Project: {meta.project_dir}")
    print(f"File:    {meta.file_path}")
    print()
    print(f"Started: {meta.started}")
    print(f"Ended:   {meta.ended}")
    dur = f"{meta.duration_minutes} minutes" if meta.duration_minutes else "unknown"
    print(f"Duration: {dur}")
    print()
    print(
        f"Messages: {meta.message_count} "
        f"({meta.human_messages} human, {meta.assistant_messages} assistant)",
    )
    print()

    if meta.tools_used:
        print("Tool usage:")
        for name, count in sorted(meta.tools_used.items(), key=lambda x: x[1], reverse=True):
            print(f"  {name:<30} {count:>4}")

    short_id = meta.session_id[:8]
    print()
    print("Render commands:")
    print(f"  organvm session transcript {short_id}")
    print(f"  organvm session transcript {short_id} --unabridged")
    print(f"  organvm session prompts {short_id}")
    print()
    print("First human message:")
    print(f"  {meta.first_human_message[:200]}")
    return 0


def cmd_session_export(args: argparse.Namespace) -> int:
    """Export a session as a praxis-perpetua review + prompts extract.

    Committed artifacts: review scaffold (with referential wires) + prompts extract.
    Transcripts are rendered on-demand via CLI, not persisted.
    Works with any supported agent (Claude, Gemini, Codex).
    """
    session_id = args.session_id
    slug = args.slug
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_praxis_sessions()
    )
    dry_run = getattr(args, "dry_run", False)

    jsonl_path = find_session(session_id)
    if not jsonl_path:
        print(f"Session not found: {session_id}")
        print("Use 'organvm session list' to see available sessions.")
        return 1

    meta = parse_any_session(jsonl_path)
    if not meta:
        print(f"Could not parse session: {jsonl_path}")
        return 1

    base_name = f"{meta.date_str}--{slug}"
    review_path = output_dir / f"{base_name}.md"
    prompts_path = output_dir / f"{base_name}--prompts.md"

    export = SessionExport(meta=meta, slug=slug, output_path=review_path)
    review_content = export.render()
    prompts_content = render_any_prompts(jsonl_path)

    if dry_run:
        print(f"Would write review to:  {review_path}")
        print(f"Would write prompts to: {prompts_path}")
        print(f"Review: {len(review_content)} chars")
        pcount = prompts_content.count("### P")
        print(f"Prompts: {len(prompts_content)} chars, {pcount} extracted")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    if review_path.exists():
        print(f"File already exists: {review_path}")
        print("Use a different --slug or remove the existing file.")
        return 1

    review_path.write_text(review_content, encoding="utf-8")
    prompts_path.write_text(prompts_content, encoding="utf-8")

    prompt_count = prompts_content.count("### P")
    short_id = meta.session_id[:8]
    print(f"Exported session review to: {review_path}")
    print(f"Exported prompts extract to: {prompts_path}")
    print(f"  Session: {meta.session_id}")
    print(f"  Date: {meta.date_str}")
    print(f"  Messages: {meta.message_count}")
    print(f"  Prompts extracted: {prompt_count}")
    dur = f"{meta.duration_minutes} min" if meta.duration_minutes else "unknown"
    print(f"  Duration: {dur}")
    print()
    print("Transcripts are on-demand (not committed):")
    print(f"  organvm session transcript {short_id}")
    print(f"  organvm session transcript {short_id} --unabridged")
    return 0


def cmd_session_transcript(args: argparse.Namespace) -> int:
    """Render session transcript as readable markdown.

    Default: conversation summary (text + tool names).
    --unabridged: full audit trail (thinking, tool I/O, generated code).

    Transcripts are ephemeral views rendered from JSONL — not committed.
    """
    session_id = args.session_id
    output = getattr(args, "output", None)
    unabridged = getattr(args, "unabridged", False)

    jsonl_path = find_session(session_id)
    if not jsonl_path:
        print(f"Session not found: {session_id}")
        print("Use 'organvm session list' to see available sessions.")
        return 1

    content = render_any_transcript(jsonl_path, unabridged=unabridged)

    if not content:
        print(f"Could not parse session: {jsonl_path}")
        return 1

    if output:
        out_path = Path(output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        lines = content.count("\n")
        size_kb = len(content.encode("utf-8")) / 1024
        mode = "unabridged" if unabridged else "summary"
        print(f"Transcript ({mode}) written to: {out_path}")
        print(f"  {lines} lines, {size_kb:.0f} KB")
    else:
        print(content)

    return 0


def cmd_session_prompts(args: argparse.Namespace) -> int:
    """Extract prompts only from a session transcript."""
    session_id = args.session_id
    output = getattr(args, "output", None)

    jsonl_path = find_session(session_id)
    if not jsonl_path:
        print(f"Session not found: {session_id}")
        print("Use 'organvm session list' to see available sessions.")
        return 1

    content = render_any_prompts(jsonl_path)
    if not content:
        print(f"Could not parse session: {jsonl_path}")
        return 1

    if output:
        out_path = Path(output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        prompt_count = content.count("### P")
        size_kb = len(content.encode("utf-8")) / 1024
        print(f"Prompts written to: {out_path}")
        print(f"  {prompt_count} prompts, {size_kb:.0f} KB")
    else:
        print(content)

    return 0


def cmd_session_plans(args: argparse.Namespace) -> int:
    """List or audit plan files across the workspace."""
    from organvm_engine.session.plans import (
        discover_plans,
        render_plan_audit,
        render_plan_inventory,
        render_plan_matrix,
    )

    project = getattr(args, "project", None)
    since = getattr(args, "since", None)
    audit = getattr(args, "audit", False)
    agent = getattr(args, "agent", None)
    organ = getattr(args, "organ", None)
    matrix = getattr(args, "matrix", False)

    plans = discover_plans(
        project_filter=project, since=since,
        agent=agent, organ=organ,
    )

    if matrix:
        print(render_plan_matrix(plans))
    elif audit:
        print(render_plan_audit(plans))
    else:
        print(render_plan_inventory(plans))

    return 0


def cmd_session_analyze(args: argparse.Namespace) -> int:
    """Run cross-session prompt analysis."""
    from organvm_engine.session.analysis import (
        analyze_prompts,
        render_analysis_report,
    )

    agent = getattr(args, "agent", None)
    full = getattr(args, "full", False)
    output = getattr(args, "output", None)
    sample_limit = 0 if full else 200

    print(f"Analyzing prompts (limit={sample_limit or 'all'}, agent={agent or 'all'})...")
    stats = analyze_prompts(agent=agent, sample_limit=sample_limit)
    report = render_analysis_report(stats)

    if output:
        out_path = Path(output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Report written to: {out_path}")
    else:
        print(report)

    return 0


def cmd_session_review(args: argparse.Namespace) -> int:
    """Review a session: summary, prompt list, related plans."""
    session_id = getattr(args, "session_id", None)
    latest = getattr(args, "latest", False)
    project = getattr(args, "project", None)

    if latest:
        sessions = discover_all_sessions(project_filter=project)
        if not sessions:
            print("No sessions found.")
            return 1
        target = sessions[0]
        jsonl_path = target.file_path
    elif session_id:
        jsonl_path = find_session(session_id)
        if not jsonl_path:
            print(f"Session not found: {session_id}")
            return 1
    else:
        print("Provide a session ID or use --latest.")
        return 1

    meta = parse_any_session(jsonl_path)
    if not meta:
        print(f"Could not parse session: {jsonl_path}")
        return 1

    agent = detect_agent(jsonl_path)
    dur = f"{meta.duration_minutes} min" if meta.duration_minutes else "unknown"
    short_id = meta.session_id[:8]

    print(f"Session Review: {short_id} ({meta.date_str}, {dur}, {meta.message_count} messages)")
    print(f"Agent: {agent} | Project: {meta.project_dir}")
    print()

    # Extract and list human prompts
    prompts_content = render_any_prompts(jsonl_path)
    prompt_count = prompts_content.count("### P")
    print(f"Prompts ({meta.human_messages} human messages, {prompt_count} extracted):")

    # Show first few prompt opening lines
    prompt_lines = [
        line for line in prompts_content.splitlines()
        if line.startswith("### P")
    ]
    for line in prompt_lines[:10]:
        print(f"  {line}")
    if len(prompt_lines) > 10:
        print(f"  ... and {len(prompt_lines) - 10} more")
    print()

    # Find related plans. Prefer the real cwd over Claude's encoded project
    # directory name so discovery can use the exact-project fast path.
    project_scope = meta.cwd or meta.project_dir
    plans = discover_plans(project_filter=project_scope) if project_scope else []

    if plans:
        print(f"Plans in this project ({len(plans)} total):")
        for p in plans[:5]:
            marker = " <- same day" if p.date == meta.date_str else ""
            print(f"  {p.date} {p.title}{marker}")
        if len(plans) > 5:
            print(f"  ... and {len(plans) - 5} more")
    else:
        print("No plans found for this project.")
    print()

    # Content signals
    try:
        from organvm_engine.content.signals import detect_content_signals
        from organvm_engine.session.parser import extract_human_texts

        human_texts = extract_human_texts(jsonl_path)
        signals = detect_content_signals(human_texts)
        if signals:
            print(f"Content Signals ({len(signals)} potential moments):")
            for s in signals:
                print(f"  P{s.prompt_index}: {s.signal_type} — {s.description}")
                if s.excerpt:
                    trunc = s.excerpt[:80]
                    ellipsis = "..." if len(s.excerpt) > 80 else ""
                    print(f"    \"{trunc}{ellipsis}\"")
            print()
    except ImportError:
        pass  # content module not installed

    # Check for uncommitted files (Nothing Local Only enforcement)
    try:
        from organvm_engine.git.status import check_uncommitted_files

        status_scope = Path(project_scope).expanduser() if project_scope else None
        uncommitted = (
            check_uncommitted_files(status_scope)
            if status_scope is not None and status_scope.is_dir()
            else []
        )
        if uncommitted:
            print("\nWARNING: Uncommitted files detected (Nothing Local Only covenant violation):")
            for report in uncommitted:
                print(f"  [{report['organ']}/{report['repo']}] {report['uncommitted_count']} files")
                for f in report['files']:
                    print(f"    {f}")
            print()
    except ImportError:
        pass

    print(f"Export: organvm session export {short_id} --slug <your-slug>")
    print(f"Full transcript: organvm session transcript {short_id}")
    return 0


def cmd_session_debrief(args: argparse.Namespace) -> int:
    """Generate a structured session debrief with tiered to-dos."""
    from organvm_engine.session.debrief import (
        build_debrief,
        classify_todos,
        render_debrief,
    )

    session_id = getattr(args, "session_id", None)
    latest = getattr(args, "latest", False)
    project = getattr(args, "project", None)
    as_json = getattr(args, "json", False)

    if latest:
        sessions = discover_all_sessions(project_filter=project)
        if not sessions:
            print("No sessions found.")
            return 1
        jsonl_path = sessions[0].file_path
    elif session_id:
        jsonl_path = find_session(session_id)
        if not jsonl_path:
            print(f"Session not found: {session_id}")
            return 1
    else:
        print("Provide a session ID or use --latest.")
        return 1

    debrief = build_debrief(jsonl_path)
    if not debrief:
        print(f"Could not parse session: {jsonl_path}")
        return 1

    classify_todos(debrief)

    if as_json:
        import json

        print(json.dumps(debrief.to_dict(), indent=2))
    else:
        print(render_debrief(debrief))

    return 0


def cmd_session_archive(args: argparse.Namespace) -> int:
    """Archive sessions to their project directories.

    Routes conversation transcripts from agent storage into the project repos
    they belong to, creating per-session directories with transcript, prompts,
    review scaffold, metadata, and optionally raw JSONL.
    """
    from organvm_engine.session.archive import archive_all, archive_session
    # find_session lives in session.parser and is already imported at module scope.

    session_id = getattr(args, "session_id", None)
    project = getattr(args, "project", None)
    since = getattr(args, "since", None)
    agent = getattr(args, "agent", None)
    dry_run = getattr(args, "dry_run", False)
    no_raw = getattr(args, "no_raw", False)
    force = getattr(args, "force", False)

    if session_id:
        # Archive a single session
        session_path = find_session(session_id)
        if not session_path:
            print(f"Session not found: {session_id}")
            return 1

        result = archive_session(
            session_path,
            dry_run=dry_run,
            include_raw=not no_raw,
            force=force,
        )

        if result.error:
            print(f"Error: {result.error}")
            return 1

        if result.skipped:
            print(f"Skipped: {result.skip_reason}")
            return 0

        prefix = "Would write" if dry_run else "Archived"
        print(f"{prefix}: {result.archive_dir}")
        for f in result.files_written:
            print(f"  {f}")
        return 0

    # Batch archive
    results = archive_all(
        project_filter=project,
        since=since,
        agent=agent,
        dry_run=dry_run,
        include_raw=not no_raw,
        force=force,
    )

    if not results:
        print("No unarchived sessions found.")
        return 0

    archived = [r for r in results if not r.skipped and not r.error]
    skipped = [r for r in results if r.skipped]
    errors = [r for r in results if r.error]

    prefix = "Would archive" if dry_run else "Archived"
    print(f"{prefix} {len(archived)} sessions:")
    for r in archived:
        file_count = len(r.files_written)
        print(f"  {r.archive_dir.parent.name}/{r.archive_dir.name} ({file_count} files)")

    if skipped:
        print(f"\nSkipped {len(skipped)} (already archived or unresolvable)")
    if errors:
        print(f"\nErrors: {len(errors)}")
        for r in errors:
            print(f"  {r.session_id}: {r.error}")

    return 0


def _default_praxis_sessions() -> Path:
    """Default output directory for session exports."""
    from organvm_engine.paths import workspace_root

    return workspace_root() / "meta-organvm" / "praxis-perpetua" / "sessions"
