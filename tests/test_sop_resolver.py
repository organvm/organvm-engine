"""Tests for sop.resolver module."""

from pathlib import Path

from organvm_engine.sop.discover import SOPEntry
from organvm_engine.sop.resolver import promotion_to_phase, resolve_all, resolve_sop


def _entry(
    name: str,
    scope: str = "system",
    org: str = "meta-organvm",
    repo: str = "praxis-perpetua",
    overrides: str | None = None,
    complements: list[str] | None = None,
    phase: str = "any",
) -> SOPEntry:
    return SOPEntry(
        path=Path(f"/ws/{org}/{repo}/{name}.md"),
        org=org,
        repo=repo,
        filename=f"{name}.md",
        title=f"SOP: {name}",
        doc_type="SOP",
        canonical=False,
        has_canonical_header=False,
        scope=scope,
        phase=phase,
        triggers=[],
        overrides=overrides,
        complements=complements or [],
        sop_name=name,
    )


class TestResolveSop:
    def test_resolve_by_name(self):
        entries = [_entry("foo"), _entry("bar")]
        result = resolve_sop("foo", entries)
        assert len(result) == 1
        assert result[0].sop_name == "foo"

    def test_resolve_no_match(self):
        entries = [_entry("foo")]
        assert resolve_sop("nonexistent", entries) == []

    def test_resolve_cascade_override(self):
        """T4 (repo) overrides T2 (system) when override is declared."""
        system = _entry("deploy", scope="system")
        repo = _entry("deploy", scope="repo", repo="engine", overrides="deploy")
        result = resolve_sop("deploy", [system, repo])
        # Only the repo-level entry remains (it overrides the system one)
        assert len(result) == 1
        assert result[0].scope == "repo"

    def test_resolve_additive_no_override(self):
        """Without overrides, all tiers are additive."""
        system = _entry("audit", scope="system")
        organ = _entry("audit", scope="organ")
        repo = _entry("audit", scope="repo", repo="engine")
        result = resolve_sop("audit", [system, organ, repo])
        assert len(result) == 3
        # Ordered by specificity: repo first, then organ, then system
        assert result[0].scope == "repo"
        assert result[1].scope == "organ"
        assert result[2].scope == "system"

    def test_unknown_shadow_copy_removed_when_governed_entry_exists(self):
        system = _entry("pitch-deck-rollout", scope="system")
        legacy = _entry("pitch-deck-rollout", scope="unknown", repo="engine")
        result = resolve_sop("pitch-deck-rollout", [system, legacy])
        assert len(result) == 1
        assert result[0].scope == "system"

    def test_exact_duplicate_entries_are_collapsed(self):
        first = _entry("prompting-standards", scope="system")
        duplicate = _entry("prompting-standards", scope="system")
        result = resolve_sop("prompting-standards", [first, duplicate])
        assert len(result) == 1


class TestResolveAll:
    def test_system_always_included(self):
        system = _entry("audit", scope="system")
        result = resolve_all([system])
        assert len(result) == 1

    def test_organ_filtered_by_org(self):
        organ = _entry("sync", scope="organ", org="meta-organvm")
        result = resolve_all([organ], organ="meta-organvm")
        assert len(result) == 1

    def test_organ_excluded_when_mismatch(self):
        organ = _entry("sync", scope="organ", org="organvm-iii-ergon")
        result = resolve_all([organ], organ="meta-organvm")
        assert len(result) == 0

    def test_repo_filtered_by_repo(self):
        repo = _entry("cli-pattern", scope="repo", repo="organvm-engine")
        result = resolve_all([repo], repo="organvm-engine")
        assert len(result) == 1

    def test_repo_excluded_when_mismatch(self):
        repo = _entry("cli-pattern", scope="repo", repo="organvm-engine")
        result = resolve_all([repo], repo="other-repo")
        assert len(result) == 0

    def test_combined_resolution(self):
        system = _entry("audit", scope="system")
        organ = _entry("sync", scope="organ", org="meta-organvm")
        repo = _entry("cli", scope="repo", repo="organvm-engine")
        other = _entry("deploy", scope="repo", repo="other-repo")
        result = resolve_all(
            [system, organ, repo, other],
            repo="organvm-engine",
            organ="meta-organvm",
        )
        names = {e.sop_name for e in result}
        assert "audit" in names
        assert "sync" in names
        assert "cli" in names
        assert "deploy" not in names

    def test_override_in_resolve_all(self):
        system = _entry("deploy", scope="system")
        repo = _entry("deploy", scope="repo", repo="engine", overrides="deploy")
        result = resolve_all([system, repo], repo="engine")
        assert len(result) == 1
        assert result[0].scope == "repo"

    def test_empty_input(self):
        assert resolve_all([]) == []

    def test_unknown_scope_matched_by_repo(self):
        legacy = _entry("old-sop", scope="unknown", repo="engine")
        result = resolve_all([legacy], repo="engine")
        assert len(result) == 1

    def test_unknown_scope_matched_by_organ(self):
        legacy = _entry("old-sop", scope="unknown", org="meta-organvm")
        result = resolve_all([legacy], organ="meta-organvm")
        assert len(result) == 1

    def test_unknown_scope_duplicate_excluded_from_active_directives(self):
        system = _entry("ira-grade-norming", scope="system")
        legacy = _entry("ira-grade-norming", scope="unknown", repo="organvm-engine")
        result = resolve_all(
            [system, legacy],
            repo="organvm-engine",
            organ="meta-organvm",
        )
        assert len(result) == 1
        assert result[0].scope == "system"

    def test_resolve_filters_by_phase(self):
        hardening = _entry("deploy", scope="system", phase="hardening")
        foundation = _entry("test", scope="system", phase="foundation")
        result = resolve_all([hardening, foundation], phase="hardening")
        assert len(result) == 1
        assert result[0].sop_name == "deploy"

    def test_resolve_phase_any_always_included(self):
        hardening = _entry("deploy", scope="system", phase="hardening")
        always = _entry("critique", scope="system", phase="any")
        result = resolve_all([hardening, always], phase="hardening")
        assert len(result) == 2
        names = {e.sop_name for e in result}
        assert "deploy" in names
        assert "critique" in names

    def test_resolve_no_phase_returns_all(self):
        hardening = _entry("deploy", scope="system", phase="hardening")
        foundation = _entry("test", scope="system", phase="foundation")
        always = _entry("critique", scope="system", phase="any")
        result = resolve_all([hardening, foundation, always])
        assert len(result) == 3

    def test_promotion_to_phase_mapping(self):
        assert promotion_to_phase("LOCAL") == "foundation"
        assert promotion_to_phase("CANDIDATE") == "hardening"
        assert promotion_to_phase("PUBLIC_PROCESS") == "graduation"
        assert promotion_to_phase("GRADUATED") == "sustaining"
        assert promotion_to_phase("ARCHIVED") == "sustaining"
        assert promotion_to_phase("UNKNOWN_STATUS") == "any"
