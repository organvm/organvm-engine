"""Tests for session plan discovery and inventory."""

from pathlib import Path

from organvm_engine.session.plans import (
    AGENT_PLAN_DIRS,
    PlanFile,
    _infer_lifecycle_statuses,
    _parse_plan_file,
    _resolve_organ_repo,
    discover_plans,
    render_plan_audit,
    render_plan_inventory,
    render_plan_matrix,
)

# ── PlanFile dataclass ────────────────────────────────────────────


def test_planfile_filename():
    pf = PlanFile(
        path=Path("/tmp/plans/2026-03-06-my-plan.md"),
        project="test", slug="my-plan", date="2026-03-06",
        title="My Plan", size_bytes=1024, has_verification=False,
    )
    assert pf.filename == "2026-03-06-my-plan.md"


def test_planfile_defaults():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="s", date="2026-01-01",
        title="T", size_bytes=0, has_verification=True,
    )
    assert pf.status == "unknown"
    assert pf.has_verification is True
    assert pf.agent == "claude"
    assert pf.organ is None
    assert pf.repo is None
    assert pf.version == 1
    assert pf.location_tier == "project"


def test_planfile_agent_field():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="s", date="2026-01-01",
        title="T", size_bytes=0, has_verification=False, agent="gemini",
    )
    assert pf.agent == "gemini"


def test_planfile_organ_repo():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="s", date="2026-01-01",
        title="T", size_bytes=0, has_verification=False,
        organ="III", repo="my-tool",
    )
    assert pf.organ == "III"
    assert pf.repo == "my-tool"


def test_planfile_version():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="s", date="2026-01-01",
        title="T", size_bytes=0, has_verification=False, version=3,
    )
    assert pf.version == 3


def test_planfile_qualified_id():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="my-plan", date="2026-01-01",
        title="T", size_bytes=0, has_verification=False,
        agent="gemini", organ="II", repo="art-repo",
    )
    assert pf.qualified_id == "gemini:II:art-repo:my-plan"


def test_planfile_qualified_id_missing_fields():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="plan", date="2026-01-01",
        title="T", size_bytes=0, has_verification=False,
    )
    assert pf.qualified_id == "claude:?:?:plan"


def test_planfile_is_agent_subplan():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="plan-agent-a1b2c3d4",
        date="2026-01-01", title="T", size_bytes=0, has_verification=False,
    )
    assert pf.is_agent_subplan is True


def test_planfile_is_not_agent_subplan():
    pf = PlanFile(
        path=Path("/tmp/x.md"), project="p", slug="regular-plan",
        date="2026-01-01", title="T", size_bytes=0, has_verification=False,
    )
    assert pf.is_agent_subplan is False


# ── _parse_plan_file ──────────────────────────────────────────────


def test_parse_dated_plan(tmp_path):
    md = tmp_path / "2026-03-06-living-data-organism.md"
    md.write_text("# Living Data Organism\n\nSome content\n\n## Verification\n- Check 1\n")
    result = _parse_plan_file(md, "test-project")
    assert result is not None
    assert result.date == "2026-03-06"
    assert result.slug == "living-data-organism"
    assert result.title == "Living Data Organism"
    assert result.has_verification is True


def test_parse_dated_plan_with_version(tmp_path):
    md = tmp_path / "2026-03-06-my-plan-v2.md"
    md.write_text("# My Plan v2\n\nRevised.\n")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.date == "2026-03-06"
    assert result.slug == "my-plan"  # -v2 stripped
    assert result.version == 2


def test_parse_undated_plan(tmp_path):
    md = tmp_path / "adhoc-notes.md"
    md.write_text("# Adhoc Notes\n\nSome notes.\n")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.slug == "adhoc-notes"
    assert result.title == "Adhoc Notes"
    assert result.date != "unknown"  # should use mtime


def test_parse_plan_no_title(tmp_path):
    md = tmp_path / "2026-01-01-untitled.md"
    md.write_text("No heading here.\n")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.title == "untitled"  # falls back to slug


def test_parse_plan_no_verification(tmp_path):
    md = tmp_path / "2026-01-01-plan.md"
    md.write_text("# Plan\n\nJust content.\n")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.has_verification is False


def test_parse_plan_nonexistent():
    result = _parse_plan_file(Path("/nonexistent/file.md"), "proj")
    assert result is None


def test_parse_plan_empty(tmp_path):
    md = tmp_path / "2026-01-01-empty.md"
    md.write_text("")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.title == "empty"  # falls back to slug
    assert result.size_bytes == 0


def test_parse_plan_with_agent(tmp_path):
    md = tmp_path / "2026-01-01-plan.md"
    md.write_text("# Plan\n")
    result = _parse_plan_file(md, "proj", agent="gemini")
    assert result is not None
    assert result.agent == "gemini"


def test_parse_plan_with_workspace_resolution(tmp_path):
    # Create organ directory structure
    organ_dir = tmp_path / "organvm-iii-ergon" / "my-repo" / ".claude" / "plans"
    organ_dir.mkdir(parents=True)
    md = organ_dir / "2026-01-01-plan.md"
    md.write_text("# Plan\n")
    result = _parse_plan_file(md, str(organ_dir.parent.parent), workspace=tmp_path)
    assert result is not None
    assert result.organ == "III"
    assert result.repo == "my-repo"


def test_parse_plan_version_extraction(tmp_path):
    md = tmp_path / "2026-01-01-plan-v5.md"
    md.write_text("# Plan v5\n")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.version == 5


def test_parse_plan_no_version_defaults_to_1(tmp_path):
    md = tmp_path / "2026-01-01-plan.md"
    md.write_text("# Plan\n")
    result = _parse_plan_file(md, "proj")
    assert result is not None
    assert result.version == 1


# ── _resolve_organ_repo ──────────────────────────────────────────


def test_resolve_organ_repo_organ_level(tmp_path):
    path = tmp_path / "organvm-i-theoria" / ".claude" / "plans" / "plan.md"
    path.parent.mkdir(parents=True)
    organ, repo = _resolve_organ_repo(path, tmp_path)
    assert organ == "I"
    assert repo is None


def test_resolve_organ_repo_repo_level(tmp_path):
    path = tmp_path / "organvm-iii-ergon" / "my-tool" / ".gemini" / "plans" / "plan.md"
    path.parent.mkdir(parents=True)
    organ, repo = _resolve_organ_repo(path, tmp_path)
    assert organ == "III"
    assert repo == "my-tool"


def test_resolve_organ_repo_meta(tmp_path):
    path = tmp_path / "meta-organvm" / "organvm-engine" / ".claude" / "plans" / "plan.md"
    path.parent.mkdir(parents=True)
    organ, repo = _resolve_organ_repo(path, tmp_path)
    assert organ == "META"
    assert repo == "organvm-engine"


def test_resolve_organ_repo_global_path(tmp_path):
    """Path outside workspace returns None, None."""
    path = Path("/some/other/path/plan.md")
    organ, repo = _resolve_organ_repo(path, tmp_path)
    assert organ == "_root"
    assert repo == "_global"


def test_resolve_organ_repo_personal(tmp_path):
    path = tmp_path / "4444J99" / "portfolio" / ".codex" / "plans" / "plan.md"
    path.parent.mkdir(parents=True)
    organ, repo = _resolve_organ_repo(path, tmp_path)
    assert organ == "LIMINAL"
    assert repo == "portfolio"


# ── discover_plans ────────────────────────────────────────────────


def test_discover_plans_project_level(tmp_path):
    """Plans in <workspace>/project/.claude/plans/ are found."""
    plans_dir = tmp_path / "project" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-03-01-alpha.md").write_text("# Alpha\n")
    (plans_dir / "2026-03-02-beta.md").write_text("# Beta\n")

    results = discover_plans(workspace=tmp_path)
    assert len(results) == 2
    # Sorted by date descending
    assert results[0].slug == "beta"
    assert results[1].slug == "alpha"


def test_discover_plans_nested_projects(tmp_path):
    """Plans in deeply nested project paths are found."""
    plans_dir = tmp_path / "org" / "repo" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-01-01-deep.md").write_text("# Deep Plan\n")

    results = discover_plans(workspace=tmp_path)
    assert len(results) == 1
    assert results[0].slug == "deep"


def test_discover_plans_project_filter(tmp_path):
    p1 = tmp_path / "projectA" / ".claude" / "plans"
    p1.mkdir(parents=True)
    (p1 / "2026-01-01-a.md").write_text("# A\n")

    p2 = tmp_path / "projectB" / ".claude" / "plans"
    p2.mkdir(parents=True)
    (p2 / "2026-01-01-b.md").write_text("# B\n")

    results = discover_plans(workspace=tmp_path, project_filter="projectA")
    assert len(results) == 1
    assert results[0].slug == "a"


def test_discover_plans_since_filter(tmp_path):
    plans_dir = tmp_path / "proj" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2025-01-01-old.md").write_text("# Old\n")
    (plans_dir / "2026-03-01-new.md").write_text("# New\n")

    results = discover_plans(workspace=tmp_path, since="2026-01-01")
    assert len(results) == 1
    assert results[0].slug == "new"


def test_discover_plans_deduplicates(tmp_path):
    """Same plan file found via multiple paths is deduplicated."""
    plans_dir = tmp_path / "proj" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-01-01-plan.md").write_text("# Plan\n")

    results = discover_plans(workspace=tmp_path)
    # No duplicates even if the same directory is traversed multiple ways
    paths = [str(r.path.resolve()) for r in results]
    assert len(paths) == len(set(paths))


def test_discover_plans_empty_workspace(tmp_path):
    results = discover_plans(workspace=tmp_path)
    assert results == []


def test_discover_plans_nonexistent_workspace():
    results = discover_plans(workspace=Path("/nonexistent/workspace"))
    assert results == []


# ── Multi-agent discovery ────────────────────────────────────────


def test_discover_gemini_plans(tmp_path):
    """Gemini plans in .gemini/plans/ are discovered."""
    plans_dir = tmp_path / "project" / ".gemini" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-03-01-gemini-plan.md").write_text("# Gemini Plan\n")

    results = discover_plans(workspace=tmp_path)
    assert len(results) == 1
    assert results[0].agent == "gemini"
    assert results[0].slug == "gemini-plan"


def test_discover_codex_plans(tmp_path):
    """Codex plans in .codex/plans/ are discovered."""
    plans_dir = tmp_path / "project" / ".codex" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-03-01-codex-plan.md").write_text("# Codex Plan\n")

    results = discover_plans(workspace=tmp_path)
    assert len(results) == 1
    assert results[0].agent == "codex"


def test_discover_all_agents(tmp_path):
    """All three agents discovered together."""
    for agent_name, agent_dir in AGENT_PLAN_DIRS.items():
        d = tmp_path / "project" / agent_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / f"2026-03-01-{agent_name}.md").write_text(f"# {agent_name}\n")

    results = discover_plans(workspace=tmp_path)
    assert len(results) == 3
    agents = {r.agent for r in results}
    assert agents == {"claude", "gemini", "codex"}


def test_discover_agent_filter(tmp_path):
    """--agent filter restricts to one agent."""
    for agent_name, agent_dir in AGENT_PLAN_DIRS.items():
        d = tmp_path / "project" / agent_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / f"2026-03-01-{agent_name}.md").write_text(f"# {agent_name}\n")

    results = discover_plans(workspace=tmp_path, agent="gemini")
    assert len(results) == 1
    assert results[0].agent == "gemini"


def test_discover_organ_filter(tmp_path):
    """--organ filter restricts to one organ."""
    d1 = tmp_path / "organvm-i-theoria" / "repo" / ".claude" / "plans"
    d1.mkdir(parents=True)
    (d1 / "2026-03-01-theoria.md").write_text("# Theoria\n")

    d2 = tmp_path / "organvm-iii-ergon" / "repo" / ".claude" / "plans"
    d2.mkdir(parents=True)
    (d2 / "2026-03-01-ergon.md").write_text("# Ergon\n")

    results = discover_plans(workspace=tmp_path, organ="III")
    assert len(results) == 1
    assert results[0].organ == "III"


def test_discover_governance_plans(tmp_path):
    """Governance plans in praxis-perpetua are discovered."""
    gov_dir = tmp_path / "meta-organvm" / "praxis-perpetua" / "sessions" / "2026-03-01" / "plans"
    gov_dir.mkdir(parents=True)
    (gov_dir / "2026-03-01-gov.md").write_text("# Governance Plan\n")

    results = discover_plans(workspace=tmp_path, include_governance=True)
    gov_plans = [r for r in results if r.agent == "governance"]
    assert len(gov_plans) == 1
    assert gov_plans[0].location_tier == "governance"
    assert gov_plans[0].organ == "META"
    assert gov_plans[0].repo == "praxis-perpetua"


def test_discover_governance_excluded_by_default(tmp_path):
    """Governance plans not included without include_governance=True."""
    gov_dir = tmp_path / "meta-organvm" / "praxis-perpetua" / "sessions" / "2026-03-01" / "plans"
    gov_dir.mkdir(parents=True)
    (gov_dir / "2026-03-01-gov.md").write_text("# Governance Plan\n")

    results = discover_plans(workspace=tmp_path)
    gov_plans = [r for r in results if r.agent == "governance"]
    assert len(gov_plans) == 0


def test_discover_backward_compat(tmp_path):
    """Default discover_plans still finds Claude plans."""
    plans_dir = tmp_path / "project" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-03-01-plan.md").write_text("# Plan\n")

    results = discover_plans(workspace=tmp_path)
    assert len(results) == 1
    assert results[0].agent == "claude"


# ── Lifecycle status ─────────────────────────────────────────────


def test_lifecycle_archived():
    plans = [
        PlanFile(
            path=Path("/ws/proj/.claude/plans/archive/2026/plan.md"),
            project="proj", slug="plan", date="2026-01-01",
            title="T", size_bytes=100, has_verification=False,
        ),
    ]
    _infer_lifecycle_statuses(plans)
    assert plans[0].status == "archived"


def test_lifecycle_superseded():
    plans = [
        PlanFile(
            path=Path("/ws/v1.md"), project="p", slug="plan",
            date="2026-01-01", title="T", size_bytes=100,
            has_verification=False, version=1,
        ),
        PlanFile(
            path=Path("/ws/v2.md"), project="p", slug="plan",
            date="2026-01-02", title="T v2", size_bytes=100,
            has_verification=False, version=2,
        ),
    ]
    _infer_lifecycle_statuses(plans)
    assert plans[0].status == "superseded"
    assert plans[1].status == "active"


def test_lifecycle_active():
    plans = [
        PlanFile(
            path=Path("/ws/plan.md"), project="p", slug="plan",
            date="2026-01-01", title="T", size_bytes=100,
            has_verification=False, version=1,
        ),
    ]
    _infer_lifecycle_statuses(plans)
    assert plans[0].status == "active"


def test_lifecycle_version_chain():
    plans = [
        PlanFile(
            path=Path("/ws/v1.md"), project="p", slug="plan",
            date="2026-01-01", title="T", size_bytes=100,
            has_verification=False, version=1,
        ),
        PlanFile(
            path=Path("/ws/v2.md"), project="p", slug="plan",
            date="2026-01-02", title="T v2", size_bytes=100,
            has_verification=False, version=2,
        ),
        PlanFile(
            path=Path("/ws/v3.md"), project="p", slug="plan",
            date="2026-01-03", title="T v3", size_bytes=100,
            has_verification=False, version=3,
        ),
    ]
    _infer_lifecycle_statuses(plans)
    assert plans[0].status == "superseded"
    assert plans[1].status == "superseded"
    assert plans[2].status == "active"


# ── render_plan_inventory ─────────────────────────────────────────


def test_render_inventory_empty():
    output = render_plan_inventory([])
    assert "No plan files" in output


def test_render_inventory_basic():
    plans = [
        PlanFile(
            path=Path("/tmp/2026-03-06-plan.md"),
            project="my-project", slug="plan", date="2026-03-06",
            title="My Plan", size_bytes=2048, has_verification=True,
        ),
        PlanFile(
            path=Path("/tmp/2026-03-05-other.md"),
            project="my-project", slug="other", date="2026-03-05",
            title="Other Plan", size_bytes=512, has_verification=False,
        ),
    ]
    output = render_plan_inventory(plans)
    assert "2026-03-06" in output
    assert "My Plan" in output
    assert "2 plans" in output
    assert "1 projects" in output
    assert "Verification sections: 1/2" in output


def test_render_inventory_size_formatting():
    plans = [
        PlanFile(
            path=Path("/tmp/p.md"), project="p", slug="s", date="2026-01-01",
            title="T", size_bytes=100, has_verification=False,
        ),
    ]
    output = render_plan_inventory(plans)
    assert "100B" in output


def test_render_inventory_multi_agent():
    """Multi-agent inventory shows Agent column."""
    plans = [
        PlanFile(
            path=Path("/tmp/c.md"), project="p", slug="c", date="2026-01-01",
            title="Claude Plan", size_bytes=100, has_verification=False, agent="claude",
        ),
        PlanFile(
            path=Path("/tmp/g.md"), project="p", slug="g", date="2026-01-01",
            title="Gemini Plan", size_bytes=100, has_verification=False, agent="gemini",
        ),
    ]
    output = render_plan_inventory(plans)
    assert "Agent" in output
    assert "claude" in output
    assert "gemini" in output
    assert "By agent:" in output


def test_render_inventory_single_agent_no_agent_column():
    """Single-agent (claude only) doesn't show Agent column."""
    plans = [
        PlanFile(
            path=Path("/tmp/c.md"), project="p", slug="c", date="2026-01-01",
            title="Plan", size_bytes=100, has_verification=False, agent="claude",
        ),
    ]
    output = render_plan_inventory(plans)
    assert "Agent" not in output


# ── render_plan_audit ─────────────────────────────────────────────


def test_render_audit_empty():
    output = render_plan_audit([])
    assert "No plan files" in output


def test_render_audit_structure():
    plans = [
        PlanFile(
            path=Path("/tmp/2026-03-06-plan.md"),
            project="proj-a", slug="plan", date="2026-03-06",
            title="Plan Title", size_bytes=1024, has_verification=True,
        ),
    ]
    output = render_plan_audit(plans)
    assert "# Plan Audit Report" in output
    assert "## proj-a" in output
    assert "### 2026-03-06" in output
    assert "Plan Title" in output
    assert "**Verification:** Yes" in output
    assert "**Status:** unknown" in output
    assert "Reality:" in output


def test_render_audit_groups_by_project():
    plans = [
        PlanFile(
            path=Path("/tmp/a.md"), project="alpha", slug="a", date="2026-01-01",
            title="A", size_bytes=100, has_verification=False,
        ),
        PlanFile(
            path=Path("/tmp/b.md"), project="beta", slug="b", date="2026-01-02",
            title="B", size_bytes=100, has_verification=False,
        ),
    ]
    output = render_plan_audit(plans)
    assert "## alpha" in output
    assert "## beta" in output


# ── render_plan_matrix ────────────────────────────────────────────


def test_render_matrix_empty():
    output = render_plan_matrix([])
    assert "No plan files" in output


def test_render_matrix_basic():
    plans = [
        PlanFile(
            path=Path("/tmp/a.md"), project="p", slug="a", date="2026-01-01",
            title="A", size_bytes=100, has_verification=False,
            agent="claude", organ="I",
        ),
        PlanFile(
            path=Path("/tmp/b.md"), project="p", slug="b", date="2026-01-01",
            title="B", size_bytes=100, has_verification=False,
            agent="gemini", organ="I",
        ),
        PlanFile(
            path=Path("/tmp/c.md"), project="p", slug="c", date="2026-01-01",
            title="C", size_bytes=100, has_verification=False,
            agent="claude", organ="III",
        ),
    ]
    output = render_plan_matrix(plans)
    assert "Agent" in output
    assert "claude" in output
    assert "gemini" in output
    assert "Total" in output


def test_render_matrix_unknown_organ():
    plans = [
        PlanFile(
            path=Path("/tmp/a.md"), project="p", slug="a", date="2026-01-01",
            title="A", size_bytes=100, has_verification=False,
            agent="claude", organ=None,
        ),
    ]
    output = render_plan_matrix(plans)
    assert "?" in output


# ── Integration: discover + render ────────────────────────────────


def test_discover_and_render(tmp_path):
    """Full pipeline: discover plans in tmp workspace and render inventory."""
    plans_dir = tmp_path / "my-project" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "2026-03-01-sprint-plan.md").write_text(
        "# Sprint Plan\n\nContent here.\n\n## Verification\n- All tests pass\n",
    )
    (plans_dir / "2026-03-02-bugfix-plan.md").write_text(
        "# Bugfix Plan\n\nFix the bug.\n",
    )

    plans = discover_plans(workspace=tmp_path)
    assert len(plans) == 2

    inventory = render_plan_inventory(plans)
    assert "Sprint Plan" in inventory
    assert "Bugfix Plan" in inventory
    assert "2 plans" in inventory

    audit = render_plan_audit(plans)
    assert "# Plan Audit Report" in audit
    assert "Sprint Plan" in audit


def test_discover_multi_agent_render(tmp_path):
    """Multi-agent discovery + render shows agent info."""
    claude_dir = tmp_path / "proj" / ".claude" / "plans"
    claude_dir.mkdir(parents=True)
    (claude_dir / "2026-03-01-claude.md").write_text("# Claude\n")

    gemini_dir = tmp_path / "proj" / ".gemini" / "plans"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "2026-03-01-gemini.md").write_text("# Gemini\n")

    plans = discover_plans(workspace=tmp_path)
    assert len(plans) == 2

    inventory = render_plan_inventory(plans)
    assert "Agent" in inventory
    assert "By agent:" in inventory

    matrix = render_plan_matrix(plans)
    assert "claude" in matrix
    assert "gemini" in matrix


# ── Atomizer integration ─────────────────────────────────────────


def test_atomizer_agent_field(tmp_path):
    """AtomicTask includes agent field when parsed with agent info."""
    from organvm_engine.plans.atomizer import PlanParser

    lines = ["# Test Plan", "", "- [x] Task one", "- [ ] Task two"]
    filepath = tmp_path / "plan.md"
    filepath.write_text("\n".join(lines))

    parser = PlanParser(lines, filepath, tmp_path, agent="gemini", organ="II", repo="art")
    tasks = parser.parse()
    assert len(tasks) >= 2
    assert tasks[0].agent == "gemini"

    d = tasks[0].to_dict()
    assert d["agent"] == "gemini"
    assert d["project"]["organ"] == "II"
    assert d["project"]["repo"] == "art"


def test_atomize_all_convenience(tmp_path):
    """atomize_all uses unified discovery."""
    from organvm_engine.plans.atomizer import atomize_plans

    plans_dir = tmp_path / "proj" / ".claude" / "plans"
    plans_dir.mkdir(parents=True)
    md = plans_dir / "2026-03-01-plan.md"
    md.write_text("# Plan\n\n- [x] Done\n- [ ] Pending\n")

    from organvm_engine.session.plans import PlanFile

    pf = PlanFile(
        path=md, project="proj", slug="plan", date="2026-03-01",
        title="Plan", size_bytes=md.stat().st_size, has_verification=False,
        agent="claude", organ="META", repo="proj",
    )

    result = atomize_plans(tmp_path, plan_files_override=[pf])
    assert result.plans_parsed == 1
    assert len(result.tasks) >= 2
    assert result.tasks[0]["agent"] == "claude"
    assert result.tasks[0]["project"]["organ"] == "META"


def test_atomize_plans_original_behavior(tmp_path):
    """atomize_plans without override still works."""
    from organvm_engine.plans.atomizer import atomize_plans

    md = tmp_path / "2026-01-01-plan.md"
    md.write_text("# Plan\n\n- [ ] Task\n")

    result = atomize_plans(tmp_path)
    assert result.plans_parsed == 1
    assert len(result.tasks) >= 1


# ── Summary integration ──────────────────────────────────────────


def test_summary_by_agent():
    """Summary includes 'By Agent' section when multi-agent tasks present."""
    from organvm_engine.plans.summary import generate_summary

    tasks = [
        {
            "id": "a", "title": "T", "agent": "claude",
            "source": {"file": "f", "plan_title": "P", "plan_date": None,
                       "plan_status": None, "line_start": 1, "line_end": 1,
                       "is_agent_subplan": False, "parent_plan": None},
            "project": {"slug": "s", "archived": False, "organ": "I", "repo": "r"},
            "hierarchy": {}, "status": "pending", "task_type": "generic",
            "actionable": True, "files_touched": [], "dependencies": {},
            "complexity": {}, "tags": [], "raw_text": "",
        },
        {
            "id": "b", "title": "T2", "agent": "gemini",
            "source": {"file": "f2", "plan_title": "P2", "plan_date": None,
                       "plan_status": None, "line_start": 1, "line_end": 1,
                       "is_agent_subplan": False, "parent_plan": None},
            "project": {"slug": "s", "archived": False, "organ": "II", "repo": "r"},
            "hierarchy": {}, "status": "pending", "task_type": "generic",
            "actionable": True, "files_touched": [], "dependencies": {},
            "complexity": {}, "tags": [], "raw_text": "",
        },
    ]
    output = generate_summary(tasks, 2)
    assert "By Agent" in output
    assert "claude" in output
    assert "gemini" in output


def test_summary_by_organ():
    """Summary includes 'By Organ' section when organ data present."""
    from organvm_engine.plans.summary import generate_summary

    tasks = [
        {
            "id": "a", "title": "T", "agent": "claude",
            "source": {"file": "f", "plan_title": "P", "plan_date": None,
                       "plan_status": None, "line_start": 1, "line_end": 1,
                       "is_agent_subplan": False, "parent_plan": None},
            "project": {"slug": "s", "archived": False, "organ": "III", "repo": "r"},
            "hierarchy": {}, "status": "pending", "task_type": "generic",
            "actionable": True, "files_touched": [], "dependencies": {},
            "complexity": {}, "tags": [], "raw_text": "",
        },
    ]
    output = generate_summary(tasks, 1)
    assert "By Organ" in output
    assert "III" in output


def test_summary_no_organ_section_when_all_unknown():
    """No 'By Organ' section when all organs are unknown."""
    from organvm_engine.plans.summary import generate_summary

    tasks = [
        {
            "id": "a", "title": "T", "agent": "claude",
            "source": {"file": "f", "plan_title": "P", "plan_date": None,
                       "plan_status": None, "line_start": 1, "line_end": 1,
                       "is_agent_subplan": False, "parent_plan": None},
            "project": {"slug": "s", "archived": False, "organ": None, "repo": None},
            "hierarchy": {}, "status": "pending", "task_type": "generic",
            "actionable": True, "files_touched": [], "dependencies": {},
            "complexity": {}, "tags": [], "raw_text": "",
        },
    ]
    output = generate_summary(tasks, 1)
    assert "By Organ" not in output
