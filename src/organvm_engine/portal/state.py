"""BIFRONS portal state surface — make the metabolize beat observable.

The metabolize effector writes a ``PortalHealthSnapshot`` here each cycle:
``state.json`` (always current) plus an append-only ``metabolize.jsonl`` history.
This is what makes the organ *felt* — organ-health probes the ``state.json`` mtime
to prove the beat fired, and the beat generator reads it back (past tense).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from organvm_engine.portal.models import PortalHealthSnapshot


def state_dir() -> Path:
    """Where the portal surfaces its state (override ``$BIFRONS_STATE_DIR``)."""
    env = os.environ.get("BIFRONS_STATE_DIR")
    if env:
        return Path(env).expanduser()
    return Path("~/.organvm/bifrons").expanduser()


def write_state(
    snapshot: PortalHealthSnapshot, *, directory: Path | str | None = None,
) -> Path:
    """Write the latest snapshot + append it to the history. Returns the state path."""
    target = Path(directory).expanduser() if directory else state_dir()
    target.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot.to_dict(), indent=2)
    state_path = target / "state.json"
    state_path.write_text(payload + "\n")
    with (target / "metabolize.jsonl").open("a") as handle:
        handle.write(json.dumps(snapshot.to_dict()) + "\n")
    return state_path


def read_state(*, directory: Path | str | None = None) -> dict:
    """Read the latest state surface (empty dict if none yet). The past-tense read."""
    target = Path(directory).expanduser() if directory else state_dir()
    state_path = target / "state.json"
    try:
        return json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
