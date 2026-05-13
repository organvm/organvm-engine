"""Tests for the metrics module."""

import json
from pathlib import Path

from organvm_engine.metrics.calculator import (
    _count_file_words,
    _strip_frontmatter,
    compute_metrics,
    count_code_files,
    count_code_files_per_repo,
    count_words,
    format_word_count,
    propagate_repo_metrics,
)
from organvm_engine.metrics.propagator import (
    build_patterns,
    compute_landing,
    compute_vitals,
    copy_json_targets,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_canonical(registry):
    """Build a canonical system-metrics.json dict from a registry fixture."""
    computed = compute_metrics(registry)
    return {
        "schema_version": "1.0",
        "generated": "2026-02-24T12:00:00+00:00",
        "computed": computed,
        "manual": {
            "code_files": 100,
            "test_files": 20,
            "repos_with_tests": 5,
            "total_words_numeric": 404000,
            "total_words_short": "404K+",
        },
    }


class TestCalculator:
    def test_compute_totals(self, registry):
        m = compute_metrics(registry)
        assert m["total_repos"] == 6
        assert m["active_repos"] == 6
        assert m["total_organs"] == 4

    def test_per_organ_counts(self, registry):
        m = compute_metrics(registry)
        assert m["per_organ"]["ORGAN-I"]["repos"] == 2
        assert m["per_organ"]["ORGAN-II"]["repos"] == 1

    def test_ci_count(self, registry):
        m = compute_metrics(registry)
        # Only recursive-engine has ci_workflow in fixture
        assert m["ci_workflows"] == 1

    def test_dependency_count(self, registry):
        m = compute_metrics(registry)
        # recursive-engine has 0 deps, ontological has 1, metasystem has 1, product has 0
        assert m["dependency_edges"] == 2


class TestComputeVitals:
    def test_vitals_structure(self, registry):
        canonical = _make_canonical(registry)
        vitals = compute_vitals(canonical)
        assert "repos" in vitals
        assert "substance" in vitals
        assert "logos" in vitals
        assert "timestamp" in vitals

    def test_vitals_repos(self, registry):
        canonical = _make_canonical(registry)
        vitals = compute_vitals(canonical)
        assert vitals["repos"]["total"] == 6
        assert vitals["repos"]["active"] == 6
        assert vitals["repos"]["orgs"] == 4

    def test_vitals_substance_from_manual(self, registry):
        canonical = _make_canonical(registry)
        vitals = compute_vitals(canonical)
        assert vitals["substance"]["code_files"] == 100
        assert vitals["substance"]["test_files"] == 20

    def test_vitals_substance_from_computed(self, registry):
        """After migration, code_files/test_files live in computed, not manual."""
        canonical = _make_canonical(registry)
        # Simulate post-migration state: fields in computed, removed from manual
        canonical["computed"]["code_files"] = 250
        canonical["computed"]["test_files"] = 45
        canonical["computed"]["repos_with_tests"] = 12
        canonical["manual"].pop("code_files", None)
        canonical["manual"].pop("test_files", None)
        canonical["manual"].pop("repos_with_tests", None)
        vitals = compute_vitals(canonical)
        assert vitals["substance"]["code_files"] == 250
        assert vitals["substance"]["test_files"] == 45
        assert vitals["substance"]["automated_tests"] == 12

    def test_vitals_ci_coverage(self, registry):
        canonical = _make_canonical(registry)
        vitals = compute_vitals(canonical)
        # 1 CI workflow / 6 repos = 17%
        assert vitals["substance"]["ci_passing"] == 1
        assert vitals["substance"]["ci_coverage_pct"] == 17

    def test_vitals_logos(self, registry):
        canonical = _make_canonical(registry)
        vitals = compute_vitals(canonical)
        assert vitals["logos"]["words"] == 404000

    def test_vitals_zero_repos(self):
        canonical = {
            "computed": {
                "total_repos": 0,
                "active_repos": 0,
                "ci_workflows": 0,
                "total_organs": 0,
            },
            "manual": {},
        }
        vitals = compute_vitals(canonical)
        assert vitals["substance"]["ci_coverage_pct"] == 0


class TestComputeLanding:
    def test_landing_structure(self, registry):
        canonical = _make_canonical(registry)
        landing = compute_landing(canonical, registry, Path("/tmp/landing.json"))
        assert "title" in landing
        assert "tagline" in landing
        assert "metrics" in landing
        assert "organs" in landing
        assert "sprint_history" in landing
        assert "generated" in landing

    def test_landing_metrics(self, registry):
        canonical = _make_canonical(registry)
        landing = compute_landing(canonical, registry, Path("/tmp/landing.json"))
        assert landing["metrics"]["total_repos"] == 6
        assert landing["metrics"]["active_repos"] == 6
        assert landing["metrics"]["ci_workflows"] == 1

    def test_landing_organs_list(self, registry):
        canonical = _make_canonical(registry)
        landing = compute_landing(canonical, registry, Path("/tmp/landing.json"))
        organ_keys = [o["key"] for o in landing["organs"]]
        assert "ORGAN-I" in organ_keys
        assert "META-ORGANVM" in organ_keys

    def test_landing_organ_repo_count(self, registry):
        canonical = _make_canonical(registry)
        landing = compute_landing(canonical, registry, Path("/tmp/landing.json"))
        organ_i = next(o for o in landing["organs"] if o["key"] == "ORGAN-I")
        assert organ_i["repo_count"] == 2
        assert organ_i["name"] == "Theory"
        assert organ_i["greek"] == "Theoria"

    def test_landing_sprint_history_empty_when_no_existing(self, registry):
        canonical = _make_canonical(registry)
        landing = compute_landing(canonical, registry, Path("/tmp/nonexistent/landing.json"))
        assert landing["sprint_history"] == []

    def test_landing_sprint_history_preserved(self, registry, tmp_path):
        canonical = _make_canonical(registry)
        # Create a fake existing system-metrics.json with sprint_history
        existing = {
            "sprint_history": [{"name": "TEST", "date": "2026-01-01"}],
        }
        sm_path = tmp_path / "system-metrics.json"
        sm_path.write_text(json.dumps(existing))
        landing_path = tmp_path / "landing.json"
        landing = compute_landing(canonical, registry, landing_path)
        assert len(landing["sprint_history"]) == 1
        assert landing["sprint_history"][0]["name"] == "TEST"


class TestCopyJsonTargets:
    def test_vitals_transform(self, registry, tmp_path):
        canonical = _make_canonical(registry)
        dest = tmp_path / "vitals.json"
        manifest = {
            "json_copies": [{"dest": str(dest), "transform": "vitals"}],
        }
        count = copy_json_targets(manifest, canonical, dry_run=False)
        assert count == 1
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert data["repos"]["total"] == 6

    def test_landing_transform(self, registry, tmp_path):
        canonical = _make_canonical(registry)
        dest = tmp_path / "landing.json"
        manifest = {
            "json_copies": [{"dest": str(dest), "transform": "landing"}],
        }
        count = copy_json_targets(manifest, canonical, dry_run=False, registry=registry)
        assert count == 1
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert data["metrics"]["total_repos"] == 6
        assert len(data["organs"]) == 4  # 4 organs in fixture

    def test_landing_skipped_without_registry(self, registry, tmp_path):
        canonical = _make_canonical(registry)
        dest = tmp_path / "landing.json"
        manifest = {
            "json_copies": [{"dest": str(dest), "transform": "landing"}],
        }
        count = copy_json_targets(manifest, canonical, dry_run=False, registry=None)
        assert count == 0  # skipped because no registry
        assert not dest.exists()

    def test_portfolio_transform(self, registry, tmp_path):
        canonical = _make_canonical(registry)
        dest = tmp_path / "system-metrics.json"
        manifest = {
            "json_copies": [{"dest": str(dest), "transform": "portfolio"}],
        }
        count = copy_json_targets(manifest, canonical, dry_run=False)
        assert count == 1
        data = json.loads(dest.read_text())
        assert data["registry"]["total_repos"] == 6


class TestStripFrontmatter:
    def test_strips_yaml_frontmatter(self):
        text = "---\ntitle: Test\ndate: 2026-01-01\n---\nHello world"
        assert _strip_frontmatter(text) == "\nHello world"

    def test_no_frontmatter(self):
        text = "Hello world"
        assert _strip_frontmatter(text) == "Hello world"

    def test_incomplete_frontmatter(self):
        text = "---\ntitle: Test\nHello world"
        assert _strip_frontmatter(text) == "---\ntitle: Test\nHello world"


class TestCountFileWords:
    def test_plain_text(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("hello world foo bar baz")
        assert _count_file_words(f) == 5

    def test_with_frontmatter(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntitle: Test\n---\nhello world foo")
        assert _count_file_words(f) == 3

    def test_strips_html_tags(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("<div>hello</div> <p>world</p>")
        assert _count_file_words(f) == 2

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert _count_file_words(f) == 0


class TestFormatWordCount:
    def test_exact_thousands(self):
        tw, tw_num, tw_short = format_word_count(842000)
        assert tw == "~842,000+"
        assert tw_num == 842000
        assert tw_short == "842K+"

    def test_rounds_to_nearest_thousand(self):
        tw, tw_num, tw_short = format_word_count(809812)
        assert tw == "~810,000+"
        assert tw_num == 809812  # numeric stays precise
        assert tw_short == "810K+"

    def test_rounds_down(self):
        tw, tw_num, tw_short = format_word_count(809400)
        assert tw == "~809,000+"
        assert tw_num == 809400
        assert tw_short == "809K+"

    def test_small_below_threshold(self):
        tw, tw_num, tw_short = format_word_count(300)
        assert tw == "~300+"
        assert tw_num == 300
        assert tw_short == "0K+"

    def test_small_above_threshold(self):
        tw, tw_num, tw_short = format_word_count(1500)
        assert tw == "~2,000+"
        assert tw_num == 1500
        assert tw_short == "2K+"

    def test_zero(self):
        tw, tw_num, tw_short = format_word_count(0)
        assert tw == "~0+"
        assert tw_num == 0
        assert tw_short == "0K+"


class TestCountWords:
    def _make_workspace(self, tmp_path):
        """Build a minimal workspace structure for word counting."""
        ws = tmp_path / "workspace"

        # Create an organ dir with two repos
        organ = ws / "organvm-i-theoria"
        (organ / "repo-a").mkdir(parents=True)
        (organ / "repo-a" / "README.md").write_text("one two three four five")
        (organ / "repo-b").mkdir(parents=True)
        (organ / "repo-b" / "README.md").write_text("alpha beta gamma")

        # Essays
        essays = ws / "organvm-v-logos" / "public-process" / "_posts"
        essays.mkdir(parents=True)
        (essays / "2026-01-01-test.md").write_text("---\ntitle: Test\n---\nword1 word2 word3 word4")

        # Corpus docs
        corpus = ws / "meta-organvm" / "organvm-corpvs-testamentvm" / "docs"
        corpus.mkdir(parents=True)
        (corpus / "test.md").write_text("a b c d e f g h i j")

        # Org profile
        profile = ws / "organvm-i-theoria" / ".github" / "profile"
        profile.mkdir(parents=True)
        (profile / "README.md").write_text("profile words here")

        return ws

    def test_counts_readmes(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        wc = count_words(ws)
        assert wc["readmes"] == 8  # 5 + 3

    def test_counts_essays_without_frontmatter(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        wc = count_words(ws)
        assert wc["essays"] == 4

    def test_counts_corpus(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        wc = count_words(ws)
        assert wc["corpus"] == 10

    def test_counts_org_profiles(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        wc = count_words(ws)
        assert wc["org_profiles"] == 3

    def test_total_is_sum(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        wc = count_words(ws)
        assert wc["total"] == wc["readmes"] + wc["essays"] + wc["corpus"] + wc["org_profiles"]

    def test_empty_workspace(self, tmp_path):
        ws = tmp_path / "empty"
        ws.mkdir()
        wc = count_words(ws)
        assert wc["total"] == 0


class TestCountCodeFiles:
    def _make_workspace(self, tmp_path):
        """Build a minimal workspace with code files."""
        ws = tmp_path / "workspace"
        organ = ws / "organvm-i-theoria"

        # repo-a: 2 python files + 1 test + tests/ dir
        repo_a = organ / "repo-a"
        (repo_a / "src").mkdir(parents=True)
        (repo_a / "src" / "main.py").write_text("print('hello')")
        (repo_a / "src" / "utils.py").write_text("def helper(): pass")
        (repo_a / "tests").mkdir()
        (repo_a / "tests" / "test_main.py").write_text("def test_it(): pass")

        # repo-b: 1 ts file, no tests dir
        repo_b = organ / "repo-b"
        repo_b.mkdir(parents=True)
        (repo_b / "index.ts").write_text("export const x = 1")

        # repo-c: files in node_modules should be skipped
        repo_c = organ / "repo-c"
        (repo_c / "node_modules" / "pkg").mkdir(parents=True)
        (repo_c / "node_modules" / "pkg" / "index.js").write_text("module.exports = {}")
        (repo_c / "src").mkdir(parents=True)
        (repo_c / "src" / "app.tsx").write_text("export default function App() {}")

        return ws

    def test_counts_code_files(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        cf = count_code_files(ws)
        # 2 .py + 1 test .py + 1 .ts + 1 .tsx = 5 (node_modules skipped)
        assert cf["code_files"] == 5

    def test_counts_test_files(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        cf = count_code_files(ws)
        assert cf["test_files"] == 1  # only test_main.py

    def test_counts_repos_with_tests(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        cf = count_code_files(ws)
        assert cf["repos_with_tests"] == 1  # only repo-a has tests/

    def test_skips_venv(self, tmp_path):
        ws = tmp_path / "workspace"
        organ = ws / "organvm-i-theoria" / "repo-a"
        (organ / ".venv" / "lib").mkdir(parents=True)
        (organ / ".venv" / "lib" / "site.py").write_text("x = 1")
        (organ / "src").mkdir(parents=True)
        (organ / "src" / "app.py").write_text("x = 1")
        cf = count_code_files(ws)
        assert cf["code_files"] == 1  # only src/app.py

    def test_empty_workspace(self, tmp_path):
        ws = tmp_path / "empty"
        ws.mkdir()
        cf = count_code_files(ws)
        assert cf["code_files"] == 0
        assert cf["test_files"] == 0
        assert cf["repos_with_tests"] == 0


class TestComputeMetricsWithWorkspace:
    def test_includes_word_counts(self, registry, tmp_path):
        # Repo names match the registry-minimal fixture (ORGAN-I has recursive-engine)
        ws = tmp_path / "workspace"
        organ = ws / "organvm-i-theoria"
        (organ / "recursive-engine").mkdir(parents=True)
        (organ / "recursive-engine" / "README.md").write_text("hello world")

        m = compute_metrics(registry, workspace=ws)
        assert "word_counts" in m
        assert m["word_counts"]["readmes"] == 2
        assert "total_words_numeric" in m
        assert "total_words_short" in m
        assert "total_words" in m

    def test_includes_code_file_counts(self, registry, tmp_path):
        ws = tmp_path / "workspace"
        organ = ws / "organvm-i-theoria"
        (organ / "recursive-engine" / "src").mkdir(parents=True)
        (organ / "recursive-engine" / "src" / "main.py").write_text("x = 1")
        (organ / "recursive-engine" / "tests").mkdir()
        (organ / "recursive-engine" / "tests" / "test_main.py").write_text("pass")
        (organ / "recursive-engine" / "README.md").write_text("hello")

        m = compute_metrics(registry, workspace=ws)
        assert "code_files" in m
        assert m["code_files"] == 2  # main.py + test_main.py
        assert m["test_files"] == 1
        assert m["repos_with_tests"] == 1

    def test_no_workspace_no_words(self, registry):
        m = compute_metrics(registry)
        assert "word_counts" not in m
        assert "code_files" not in m


class TestRegistryDrivenMultiRoot:
    """Regression coverage for IRF-OPS-028: split-topology workspace.

    The post-2026-04-20 decomposition left some organs grouped under one root
    and others under a different root (or flat). The registry-driven walker
    must find every repo regardless of which root it lives under.
    """

    def test_finds_repos_across_two_roots(self, registry, tmp_path):
        # Root A holds ORGAN-I grouped under organ dir; Root B holds META-ORGANVM grouped.
        root_a = tmp_path / "code-root"
        root_b = tmp_path / "workspace-root"
        (root_a / "organvm-i-theoria" / "recursive-engine").mkdir(parents=True)
        (root_a / "organvm-i-theoria" / "recursive-engine" / "README.md").write_text(
            "one two three four five",
        )
        (root_b / "meta-organvm" / "organvm-engine").mkdir(parents=True)
        (root_b / "meta-organvm" / "organvm-engine" / "README.md").write_text(
            "alpha beta gamma",
        )

        m = compute_metrics(registry, candidates=[root_a, root_b])
        # 5 words from recursive-engine + 3 from organvm-engine = 8
        assert m["word_counts"]["readmes"] == 8

    def test_finds_flat_namespace_repos(self, registry, tmp_path):
        # Repos sit at <root>/<repo-name> without an organ-grouping parent —
        # this is the post-decomposition flat layout used by ORGAN-III/V/VII.
        root = tmp_path / "flat-root"
        (root / "recursive-engine").mkdir(parents=True)
        (root / "recursive-engine" / "README.md").write_text("a b c")
        (root / "metasystem-master").mkdir(parents=True)
        (root / "metasystem-master" / "README.md").write_text("d e")
        (root / "product-app").mkdir(parents=True)
        (root / "product-app" / "README.md").write_text("f g h i")

        m = compute_metrics(registry, candidates=[root])
        assert m["word_counts"]["readmes"] == 9  # 3 + 2 + 4

    def test_organ_grouped_wins_over_flat_when_both_exist(self, registry, tmp_path):
        # When the same repo name exists both grouped and flat under one root,
        # the organ-grouped probe should match first (more specific).
        root = tmp_path / "root"
        (root / "organvm-i-theoria" / "recursive-engine").mkdir(parents=True)
        (root / "organvm-i-theoria" / "recursive-engine" / "README.md").write_text("grouped one")
        (root / "recursive-engine").mkdir(parents=True)
        (root / "recursive-engine" / "README.md").write_text(
            "flat one two three four five six seven",
        )

        m = compute_metrics(registry, candidates=[root])
        # Should pick organ-grouped (2 words), not flat (8 words)
        assert m["word_counts"]["readmes"] == 2

    def test_archived_repos_are_skipped(self, registry, tmp_path):
        # Inject an ARCHIVED entry; the walker must skip it even if a README exists.
        import copy
        reg = copy.deepcopy(registry)
        reg["organs"]["ORGAN-I"]["repositories"].append({
            "name": "archived-repo",
            "org": "organvm-i-theoria",
            "implementation_status": "ARCHIVED",
        })
        root = tmp_path / "root"
        (root / "organvm-i-theoria" / "recursive-engine").mkdir(parents=True)
        (root / "organvm-i-theoria" / "recursive-engine" / "README.md").write_text("live")
        (root / "organvm-i-theoria" / "archived-repo").mkdir(parents=True)
        (root / "organvm-i-theoria" / "archived-repo" / "README.md").write_text(
            "should not be counted at all",
        )

        m = compute_metrics(reg, candidates=[root])
        assert m["word_counts"]["readmes"] == 1  # only 'live' from recursive-engine

    def test_code_files_counted_via_registry(self, registry, tmp_path):
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        # recursive-engine under root_a
        (root_a / "organvm-i-theoria" / "recursive-engine" / "src").mkdir(parents=True)
        (root_a / "organvm-i-theoria" / "recursive-engine" / "src" / "main.py").write_text("x=1")
        (root_a / "organvm-i-theoria" / "recursive-engine" / "tests").mkdir()
        (root_a / "organvm-i-theoria" / "recursive-engine" / "tests" / "test_x.py").write_text("p")
        # organvm-engine under root_b
        (root_b / "meta-organvm" / "organvm-engine").mkdir(parents=True)
        (root_b / "meta-organvm" / "organvm-engine" / "app.ts").write_text("export {}")

        m = compute_metrics(registry, candidates=[root_a, root_b])
        assert m["code_files"] == 3  # main.py + test_x.py + app.ts
        assert m["test_files"] == 1
        assert m["repos_with_tests"] == 1


class TestBuildPatternsComputedFirst:
    def test_uses_computed_word_count(self):
        metrics = {
            "computed": {
                "total_repos": 100,
                "active_repos": 90,
                "archived_repos": 5,
                "published_essays": 42,
                "ci_workflows": 80,
                "dependency_edges": 40,
                "sprints_completed": 10,
                "total_words_numeric": 842000,
                "total_words_short": "842K+",
            },
            "manual": {
                "total_words_numeric": 404000,
                "total_words_short": "404K+",
            },
        }
        patterns = build_patterns(metrics)
        # Find a total_words pattern and check the replacement uses 842K
        word_patterns = [(n, p, r) for n, p, r in patterns if n == "total_words"]
        assert any("842" in r for _, _, r in word_patterns)
        assert not any("404" in r for _, _, r in word_patterns)

    def test_falls_back_to_manual(self):
        metrics = {
            "computed": {
                "total_repos": 100,
                "active_repos": 90,
                "archived_repos": 5,
                "published_essays": 42,
                "ci_workflows": 80,
                "dependency_edges": 40,
                "sprints_completed": 10,
            },
            "manual": {
                "total_words_numeric": 404000,
                "total_words_short": "404K+",
            },
        }
        patterns = build_patterns(metrics)
        word_patterns = [(n, p, r) for n, p, r in patterns if n == "total_words"]
        assert any("404" in r for _, _, r in word_patterns)


class TestComputeVitalsComputedFirst:
    def test_uses_computed_words(self, registry):
        canonical = _make_canonical(registry)
        canonical["computed"]["total_words_numeric"] = 842000
        canonical["computed"]["word_counts"] = {
            "readmes": 273000,
            "essays": 137000,
            "corpus": 426000,
            "org_profiles": 6000,
            "total": 842000,
        }
        vitals = compute_vitals(canonical)
        assert vitals["logos"]["words"] == 842000
        assert vitals["logos"]["word_breakdown"]["readmes"] == 273000

    def test_falls_back_to_manual_words(self, registry):
        canonical = _make_canonical(registry)
        vitals = compute_vitals(canonical)
        assert vitals["logos"]["words"] == 404000
        assert "word_breakdown" not in vitals["logos"]


class TestCountCodeFilesPerRepo:
    def _make_workspace(self, tmp_path):
        """Build a workspace with multiple repos across organs."""
        ws = tmp_path / "workspace"
        organ = ws / "organvm-i-theoria"

        # repo-a: 2 source + 1 test
        repo_a = organ / "repo-a"
        (repo_a / "src").mkdir(parents=True)
        (repo_a / "src" / "main.py").write_text("x = 1")
        (repo_a / "src" / "utils.py").write_text("y = 2")
        (repo_a / "tests").mkdir()
        (repo_a / "tests" / "test_main.py").write_text("pass")

        # repo-b: 1 ts file, no tests
        repo_b = organ / "repo-b"
        repo_b.mkdir(parents=True)
        (repo_b / "index.ts").write_text("export const x = 1")

        return ws

    def test_per_repo_keys(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        per_repo = count_code_files_per_repo(ws)
        assert "organvm-i-theoria/repo-a" in per_repo
        assert "organvm-i-theoria/repo-b" in per_repo

    def test_per_repo_counts(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        per_repo = count_code_files_per_repo(ws)
        assert per_repo["organvm-i-theoria/repo-a"]["code_files"] == 3  # main + utils + test
        assert per_repo["organvm-i-theoria/repo-a"]["test_files"] == 1
        assert per_repo["organvm-i-theoria/repo-b"]["code_files"] == 1
        assert per_repo["organvm-i-theoria/repo-b"]["test_files"] == 0

    def test_skips_vendored_dirs(self, tmp_path):
        ws = tmp_path / "workspace"
        organ = ws / "organvm-i-theoria" / "repo-c"
        (organ / "node_modules" / "pkg").mkdir(parents=True)
        (organ / "node_modules" / "pkg" / "index.js").write_text("x")
        (organ / "src").mkdir(parents=True)
        (organ / "src" / "app.py").write_text("y")
        per_repo = count_code_files_per_repo(ws)
        assert per_repo["organvm-i-theoria/repo-c"]["code_files"] == 1

    def test_empty_workspace(self, tmp_path):
        ws = tmp_path / "empty"
        ws.mkdir()
        per_repo = count_code_files_per_repo(ws)
        assert per_repo == {}


class TestPropagateRepoMetrics:
    def test_writes_metrics_to_registry_entries(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "recursive-engine", "org": "organvm-i-theoria"},
                        {"name": "ontological-framework", "org": "organvm-i-theoria"},
                    ],
                },
            },
        }
        per_repo = {
            "organvm-i-theoria/recursive-engine": {"code_files": 42, "test_files": 10},
            "organvm-i-theoria/ontological-framework": {"code_files": 15, "test_files": 3},
        }
        updated = propagate_repo_metrics(registry, per_repo)
        assert updated == 2
        repos = registry["organs"]["ORGAN-I"]["repositories"]
        assert repos[0]["metrics"]["code_files"] == 42
        assert repos[0]["metrics"]["test_files"] == 10
        assert repos[1]["metrics"]["code_files"] == 15
        assert repos[1]["metrics"]["test_files"] == 3

    def test_preserves_existing_metrics_keys(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {
                            "name": "recursive-engine",
                            "org": "organvm-i-theoria",
                            "metrics": {"custom_key": "preserved"},
                        },
                    ],
                },
            },
        }
        per_repo = {
            "organvm-i-theoria/recursive-engine": {"code_files": 42, "test_files": 10},
        }
        propagate_repo_metrics(registry, per_repo)
        m = registry["organs"]["ORGAN-I"]["repositories"][0]["metrics"]
        assert m["custom_key"] == "preserved"
        assert m["code_files"] == 42

    def test_skips_repos_not_on_disk(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "missing-repo", "org": "organvm-i-theoria"},
                    ],
                },
            },
        }
        per_repo = {}  # no repos found on disk
        updated = propagate_repo_metrics(registry, per_repo)
        assert updated == 0
        assert "metrics" not in registry["organs"]["ORGAN-I"]["repositories"][0]

    def test_returns_count_of_updated_entries(self):
        registry = {
            "organs": {
                "ORGAN-I": {
                    "repositories": [
                        {"name": "found", "org": "organvm-i-theoria"},
                        {"name": "missing", "org": "organvm-i-theoria"},
                    ],
                },
            },
        }
        per_repo = {
            "organvm-i-theoria/found": {"code_files": 5, "test_files": 1},
        }
        updated = propagate_repo_metrics(registry, per_repo)
        assert updated == 1

    def test_integration_with_fixture_registry(self, registry):
        """Verify propagation works against the standard minimal registry fixture."""
        per_repo = {
            "organvm-i-theoria/recursive-engine": {"code_files": 100, "test_files": 25},
            "organvm-i-theoria/ontological-framework": {"code_files": 50, "test_files": 8},
            "organvm-ii-poiesis/metasystem-master": {"code_files": 30, "test_files": 5},
            "organvm-iii-ergon/product-app": {"code_files": 80, "test_files": 12},
            "meta-organvm/organvm-engine": {"code_files": 200, "test_files": 60},
            "meta-organvm/organvm-corpvs-testamentvm": {"code_files": 10, "test_files": 0},
        }
        updated = propagate_repo_metrics(registry, per_repo)
        assert updated == 6

        # Check a specific entry
        organ_i = registry["organs"]["ORGAN-I"]["repositories"]
        engine = next(r for r in organ_i if r["name"] == "recursive-engine")
        assert engine["metrics"]["code_files"] == 100
        assert engine["metrics"]["test_files"] == 25

        meta = registry["organs"]["META-ORGANVM"]["repositories"]
        oe = next(r for r in meta if r["name"] == "organvm-engine")
        assert oe["metrics"]["code_files"] == 200
        assert oe["metrics"]["test_files"] == 60
