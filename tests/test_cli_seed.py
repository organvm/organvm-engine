import argparse
from unittest.mock import patch
from organvm_engine.cli.seed import cmd_seed_validate

def test_cmd_seed_validate_warns_on_zero_edges(capsys, tmp_path, monkeypatch):
    import yaml
    
    # We must put the repos inside an org dir that gets discovered or patch discover_seeds
    repo_dir = tmp_path / "test-org" / "zero-edges-repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "seed.yaml").write_text(yaml.dump({
        "schema_version": "1.0",
        "organ": "Test",
        "repo": "zero-edges-repo",
        "org": "test-org",
        "produces": [],
        "consumes": [],
    }))
    
    repo_dir2 = tmp_path / "test-org" / "has-edges-repo"
    repo_dir2.mkdir(parents=True)
    (repo_dir2 / "seed.yaml").write_text(yaml.dump({
        "schema_version": "1.0",
        "organ": "Test",
        "repo": "has-edges-repo",
        "org": "test-org",
        "produces": [{"type": "something"}],
        "consumes": [],
    }))
    
    monkeypatch.setattr(
        "organvm_engine.seed.discover.ORGAN_ORGS",
        ["test-org"]
    )
    
    args = argparse.Namespace(workspace=str(tmp_path))
    
    rc = cmd_seed_validate(args)
    
    assert rc == 0
    out = capsys.readouterr().out
    
    assert "WARN test-org/zero-edges-repo: zero produces/consumes edges (LEX-IV Metabolism violation)" in out
    assert "PASS test-org/has-edges-repo" in out
