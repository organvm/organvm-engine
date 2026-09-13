"""Run the real offline acceptance script so lifecycle changes cannot strand it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_done_sh_accepts_local_preparation(tmp_path):
    """The whole loop accepts prepared proposals while keeping submission gated."""
    root = Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Bind both entry points to this test interpreter and checkout, even when
    # another installed organvm executable is earlier on the caller's PATH.
    cli = bin_dir / "organvm"
    cli.write_text(
        f"#!{sys.executable}\n"
        "from organvm_engine.cli import main\n"
        "raise SystemExit(main())\n",
    )
    cli.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    env = {
        **os.environ,
        "BIFRONS_LIVE": "0",
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "PYTHONPATH": str(root / "src"),
    }
    result = subprocess.run(
        ["bash", str(root / "done.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no GitHub PR opened" in result.stdout
    assert "BACKFLOW_COMPLETE, 0 sent" in result.stdout
    assert "gate held" in result.stdout
