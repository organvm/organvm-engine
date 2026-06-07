# IRF Parser Remediation + Write-Back Tooling

**Date**: 2026-06-07
**Branch**: `fix/irf-parser-and-writeback` (worktree `organvm-engine-irf-remediation-2026-06-07`)
**Targets**: IRF-OPS-091 (parser/stats undercounting chain: OPS-017 / SYS-182 / OPS-088) + IRF-SYS-251 (write-back tooling: `add` / `complete` / `stats --write`)
**Session**: S-2026-06-07-irf-parser-and-writeback (Claude, dispatched from antigravity handoff brief)

## Evidence baseline (measured against live registry)

Live file: `~/Code/organvm/organvm-corpvs-testamentvm/INST-INDEX-RERUM-FACIENDARUM.md`
(2037 lines at measurement; hardlinked per IRF-SYS-168 — **inode must survive writes**).

Reconciliation script (grep ground truth vs `parse_irf`):
- Ground-truth ID-bearing table rows: **1367**
- Parser items: **1316**
- **Dropped: 51, Phantom: 0**

Drop categories (enumerated, not guessed):
- **A. Letter-suffixed IDs** (~40 rows): `IRF-VAC-001a`…`009h`, `IRF-SYS-070a`, `DONE-114a`, `DONE-145b`. ID regex `^(IRF-(?:[A-Z]+-)+\d+|DONE-\d+)$` requires numeric tail. This is the real face of the "### Discovered Items blind spot" (IRF-SYS-182) — those sections use suffixed sub-item IDs.
- **B. DONE-ref in priority cell**: `| IRF-SKL-004 | DONE-525 | …` — completed-in-place rows rejected by the `^P[0-4]$` priority gate.
- **C. 4-cell ledger rows outside completed sections** (L1943-44): rows route to `_parse_active_row` (needs 6 cells) because section status isn't "completed".
- **D. Short DONE rows** (<4 cells, L1738 `DONE-145`).
- **E. L113 `IRF-SYS-096`** — verify byte-level during build (suspected missing trailing pipe → `_ROW_RE` no-match).

## Phase 1 — Parser fixes (`src/organvm_engine/irf/parser.py`)

1. Widen ID regex to accept letter suffixes: `^(IRF-(?:[A-Z]+-)+\d+[a-z]?|DONE-\d+[a-z]?)$` (single trailing letter, matching observed convention).
2. Row routing becomes a fallback chain: try active-row parse; on failure try completed-row parse **regardless of section status** (status from section still applies to successful active parses). A 4-cell ID-bearing row anywhere becomes a completed/ledger item rather than silently dropping.
3. Priority cell matching `DONE-\d+[a-z]?` → parse as completed-in-place: status="completed", priority="", source gains the DONE ref.
4. Relax `_parse_completed_row` minimum to 3 cells (ID | what | rest).
5. Handle E (trailing-pipe or whatever byte-level cause emerges).
6. **Diagnostics API** (closes the OPS-088 "parse-complete before relying on it" requirement): `parse_irf_diagnostics(path)` returns `(items, skipped)` where `skipped` = ID-bearing lines that produced no item. `irf stats` prints a `⚠ unparsed ID rows: N` warning when N > 0. The drops-to-zero condition becomes machine-checkable forever.

## Phase 2 — Write-back tooling (`organvm irf add` / `complete` / `stats --write`)

Constraints (constitutional + repo conventions):
- **Dry-run by default**; mutations require `--write` (repo-wide destructive-command convention).
- **In-place write** (`open(path, "w")` truncate) — never temp+rename; preserves the IRF-SYS-168 hardlink inode.
- **Additive idiom**: `complete` = strikethrough the active row in place **and** append a 4-col ledger row to `## Completed` — both idioms already coexist in the file; preserve-never-delete.
- **DONE-ID allocation**: follow the file's own `### DONE-ID Allocation Protocol` (read at build time); allocator = max(existing DONE-NNN)+1 to avoid repeating the DONE-593 collision the prior session introduced.
- `add`: append a 6-col row to the open-items table whose rows share the target domain (last matching table); `--section` override; auto-ID `IRF-<DOMAIN>-<next>` unless `--id` given.
- `stats --write`: regenerate the `## Statistics` block between AUTOGEN markers (derive-don't-copy, IRF-OPS-091's prescribed resolution); refuses when diagnostics report unparsed rows (parser must be clean before stats are authoritative).

## Phase 3 — Tests (hermetic; conftest blocks production paths)

- Fixture `tests/fixtures/irf-parser-cases.md` containing every drop category A–E + canonical rows.
- Parser: each category parses; diagnostics reports zero skips on fixture; regression for OPS-088 late-file rows.
- Write-back: `add`/`complete`/`stats --write` round-trip on `tmp_path` copies; **inode-preservation test** (`st_ino` identical before/after); dry-run produces no mutation; `stats --write` refusal when skips > 0.

## Phase 4 — Verify against live registry (read-only + tmp-copy dry-runs)

- `organvm irf stats` total == grep ground truth (1367 at baseline; re-derive at verify time, file is live).
- `organvm irf status IRF-OPS-087`, `IRF-VAC-001a`, `IRF-SYS-182` all resolve.
- Dry-run `add`/`complete` against a tmp copy; diff inspection proves no structural damage.

## Phase 5 — LEARN / write-backs (corpvs, separate commits)

- Commit prior session's held IRF-SYS-163 edit on corpvs main (its rebase blocker is gone); repair duplicate DONE-593 (renumber the later collision).
- Dogfood: `organvm irf complete` on IRF-OPS-091 + IRF-SYS-251 (after verification), `stats --write` to heal the stale Statistics block.
- Engine: update `irf/` module doc + CLAUDE.md capability line if hand-maintained sections allow; seed.yaml if present.
- File new vacuums discovered: `organvm session export` cannot index antigravity-cli brain sessions (this session's export had to be manual); transcript secret-leak rotation review (Google API key echoed in prior transcript + `allow-secret` bypasses).

## Risks

- Parallel Codex branches (`wip/irf-sys-250-251-hall-monitor`, `codex/irf-*`) touch adjacent rows — keep corpvs commits targeted, never wholesale.
- corpvs main is [ahead 4] with SSH auth down — commits land locally; push via HTTPS `gh auth git-credential` fallback, else flag for later push.
- The registry is a protected data file: read-before-write, targeted splices only.
