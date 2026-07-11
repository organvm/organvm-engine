#!/usr/bin/env bash
# BIFRONS — Epic 6 acceptance predicate (the two-way proof).
#
# Definition of Done (charter): executable, idempotent, exit 0 <=> done. This
# drives ONE star's exchange through the WHOLE portal loop and asserts the
# single-exchange_id thread across both faces, plus the human-gate boundary.
#
#   star -> dossier -> [inbound] proposal -> draft internal PR
#                   -> [outbound] candidate -> packet -> submit(gated) -> backflow
#
# Core is deterministic + offline (seeded exchange) so it runs anywhere,
# including engine CI. Set BIFRONS_LIVE=1 (with an authenticated gh) to also run
# the real 419-star alchemia intake as a live augment (non-fatal on infra error).
#
# Usage:  bash done.sh
set -euo pipefail

REPO="acme/widget"
NODE="MDEwOlJlcG9zaXRvcnkxMjM0"
export WORK="$(mktemp -d)"
export BIFRONS_DB="$WORK/portal.db"
PROPOSALS="$WORK/proposals"
BACKFLOW="$WORK/backflow"
trap 'rm -rf "$WORK"' EXIT

say() { printf '\n=== %s ===\n' "$*"; }
die() { printf '\nDONE.SH FAILED: %s\n' "$*" >&2; exit 1; }

command -v organvm >/dev/null 2>&1 || die "organvm CLI not on PATH (pip install -e .)"

# --- 0. Seed the intake (alchemia's real schema if importable, else raw SQL) ---
say "0. seed intake — one exchange + S1 dossier"
python3 - "$REPO" "$NODE" <<'PY'
import json, os, sqlite3, sys
repo, node = sys.argv[1], sys.argv[2]
db = os.environ["BIFRONS_DB"]
from organvm_engine.portal import store
conn = store.connect(db)
store.init_exchange_schema(conn)  # exchange spine + engine tables
conn.execute("""
CREATE TABLE IF NOT EXISTS dossier (
    id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL,
    full_name TEXT NOT NULL, level TEXT NOT NULL, doc_json TEXT NOT NULL,
    exchange_id TEXT DEFAULT '', UNIQUE(node_id, level))
""")
exid = "01EXCHANGEDONESH0000000001"
doc = {
    "external_repo": repo, "snapshot_ref": "abc1234567deadbeefcafe",
    "identity": {"primary_language": "Python", "languages": {"Python": 1.0},
                 "topics": ["cli", "tools"], "description": "A widget library."},
    "state": {"archived": False, "last_push_at": "2026-01-01T00:00:00Z"},
    "contracts": {"decision": "idea-or-interface-only-unless-obligations-accepted",
                  "license": {"spdx": "MIT"}, "contributing": "CONTRIBUTING.md", "cla_or_dco": "dco"},
    "architecture": {"manifests": ["pyproject.toml"], "test_strategy": ["pytest"]},
    "provenance": {"hashes": {"README.md": "deadbeef"}},
}
conn.execute("INSERT OR IGNORE INTO exchange(exchange_id, external_repo_node_id, external_repo,"
             " state, created_at, updated_at, data_json) VALUES(?,?,?,?,?,?,?)",
             (exid, node, repo, "MAPPED", store.now_iso(), store.now_iso(), "{}"))
conn.execute("INSERT OR IGNORE INTO dossier(node_id, full_name, level, doc_json, exchange_id)"
             " VALUES(?,?,?,?,?)", (node, repo, "S1", json.dumps(doc), exid))
conn.commit(); conn.close()
print(f"  seeded exchange {exid} + dossier for {repo}")
PY

# --- 1. Inbound face: proposal -> draft internal PR (no default-branch write) ---
say "1. inbound: propose -> prepare (draft internal PR)"
organvm portal propose "$REPO" organvm-engine
organvm portal prepare "$REPO" --out-dir "$PROPOSALS"
[ -f "$PROPOSALS/01EXCHANGEDONESH0000000001.md" ] || die "draft internal PR artifact missing"

# --- 2. Outbound face: candidate -> packet (nothing sent) ---
say "2. outbound: candidate -> package (prepared, not submitted)"
organvm portal candidate "$REPO" --kind documentation-ambiguity \
  --rationale "README setup step is ambiguous; a one-line fix removes the ambiguity."
organvm portal package "$REPO"

# --- 3. The human gate: default A2 must REFUSE the external write ---
say "3. gate: default submit must refuse (A2 = prepare, never submit)"
GATE_OUT="$(organvm portal submit "$REPO")"
printf '%s\n' "$GATE_OUT"
printf '%s' "$GATE_OUT" | grep -q "allowed: False" || die "A2 default did not refuse the submit"
printf '%s' "$GATE_OUT" | grep -q "requires_human" || die "gate did not flag requires_human"

# --- 4. Approval reaches HUMAN_APPROVED but opens NO PR (no --execute) ---
say "4. gate: --approve --checks-passing reaches HUMAN_APPROVED, opens no PR"
organvm portal submit "$REPO" --approve --checks-passing

# --- 5. Seven-organ backflow -> BACKFLOW_COMPLETE ---
say "5. backflow: metabolize outcome through the seven organs"
organvm portal backflow "$REPO" --outcome dormant --write --out-dir "$BACKFLOW"
[ -f "$BACKFLOW/backflow-manifest.yaml" ] || die "backflow manifest missing"

# --- 6. Assertions: the thread + the gate held ---
say "6. assert: one exchange_id threads the whole loop; nothing was sent"
python3 - <<'PY'
import os, sqlite3, sys
db = os.environ["BIFRONS_DB"]
conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
exid = "01EXCHANGEDONESH0000000001"
def one(q, *a): return conn.execute(q, a).fetchone()[0]
fails = []
# terminal state
st = one("SELECT state FROM exchange WHERE exchange_id=?", exid)
if st != "BACKFLOW_COMPLETE": fails.append(f"exchange state {st} != BACKFLOW_COMPLETE")
# nothing sent — the external write never happened
n_up = one("SELECT COUNT(*) FROM upstream_interaction WHERE exchange_id=?", exid)
if n_up != 0: fails.append(f"upstream_interaction={n_up} (expected 0 — nothing sent)")
# both faces + backflow all carry the one exchange_id
for t in ("transmutation_proposal", "contribution_candidate", "backflow_signal"):
    n = one(f"SELECT COUNT(*) FROM {t} WHERE exchange_id=?", exid)  # noqa: S608
    if n < 1: fails.append(f"{t} has no row threaded to exchange {exid}")
# proposal was realized (its own status advanced to pr_open)
pst = one("SELECT status FROM transmutation_proposal WHERE exchange_id=?", exid)
if pst != "pr_open": fails.append(f"proposal status {pst} != pr_open")
# backflow generated at least the community + distribution signals
n_bf = one("SELECT COUNT(*) FROM backflow_signal WHERE exchange_id=?", exid)
if n_bf < 2: fails.append(f"backflow_signal={n_bf} (expected >=2)")
conn.close()
if fails:
    print("  THREAD ASSERTIONS FAILED:"); [print("   -", f) for f in fails]; sys.exit(1)
print(f"  exchange {exid}: BACKFLOW_COMPLETE, 0 sent, {n_bf} backflow signals, thread intact")
PY

# --- 6b. Autopoietic beat: one bounded metabolize writes the observable surface ---
say "6b. metabolize: one autopoietic beat (absorb->map->prepare->surface), never submits"
organvm portal metabolize --no-absorb --budget 5 --state-dir "$WORK/state" --db "$BIFRONS_DB"
[ -f "$WORK/state/state.json" ] || die "metabolize state surface missing"
python3 - <<'PY'
import json, os, sqlite3, sys
d = json.load(open(os.path.join(os.environ["WORK"], "state", "state.json")))
for key in ("generated_at", "exchanges_by_state", "prepared_awaiting_gate", "last_run_seconds"):
    if key not in d:
        print(f"  state surface missing key: {key}"); sys.exit(1)
# The beat must never send: no external-write record exists.
conn = sqlite3.connect(os.environ["BIFRONS_DB"])
n_up = conn.execute("SELECT COUNT(*) FROM upstream_interaction").fetchone()[0]
conn.close()
if n_up != 0:
    print(f"  metabolize sent something (upstream_interaction={n_up})"); sys.exit(1)
print(f"  state surface observable: awaiting_gate={d['prepared_awaiting_gate']}, "
      f"states={d['exchanges_by_state']}, 0 sent")
PY

# --- 7. Optional live augment: real 419-star intake (non-fatal on infra) ---
if [ "${BIFRONS_LIVE:-0}" = "1" ]; then
  say "7. live augment: real alchemia star intake (BIFRONS_LIVE=1)"
  if command -v alchemia >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if alchemia stars sync; then
      N1="$(python3 -c "import os,sqlite3;print(sqlite3.connect(os.environ['BIFRONS_DB']).execute('SELECT COUNT(*) FROM external_repo').fetchone()[0])")"
      alchemia stars sync    # idempotency: re-run should add no new external_repo rows
      N2="$(python3 -c "import os,sqlite3;print(sqlite3.connect(os.environ['BIFRONS_DB']).execute('SELECT COUNT(*) FROM external_repo').fetchone()[0])")"
      [ "$N1" = "$N2" ] || die "star sync not idempotent ($N1 -> $N2)"
      echo "  live: $N2 real stars synced, idempotent re-run confirmed"
      organvm portal import-stars || true
    else
      echo "  live: alchemia stars sync failed (network/gh) — skipping augment (non-fatal)"
    fi
  else
    echo "  live: alchemia or gh unavailable — skipping augment (non-fatal)"
  fi
else
  say "7. live augment skipped (set BIFRONS_LIVE=1 with an authenticated gh to run it)"
fi

printf '\nBIFRONS Epic-6 two-way proof passed — one exchange_id threaded star->backflow, gate held.\n'
