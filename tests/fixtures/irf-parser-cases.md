# INST — Index Rerum Faciendarum (parser regression fixture)

Synthetic registry exercising every row shape the live document contains,
including the five drop categories enumerated 2026-06-07 (IRF-OPS-091 chain).

## System-Wide

### Governance & Standards

| ID | Priority | Action | Owner | Source | Blocker |
|----|----------|--------|-------|--------|---------|
| IRF-SYS-001 | P0 | Plain canonical active row | Agent | S1 | None |
| IRF-SYS-002 | **P2** | **Bolded-priority row** (IRF-OPS-017 class) | Agent | S1 | None |
| ~~IRF-SYS-003~~ | ~~P1~~ | ~~Struck-through completed-in-place row~~ — **DONE** | Agent | S1 | Completed |
| IRF-SKL-004 | DONE-525 | DONE-ref in the priority cell (completed in place) | Agent | S2 | None |
| IRF-SYS-096 | **P2** | **Row without trailing pipe** (category E)
| IRF-OPS-087 | P1 | Late-file row reachable by status (IRF-OPS-088) | Agent | S3 | None |

### S-2026-06-07-fixture Discovered Items (2026-06-07)

| ID | Priority | Action | Owner | Source | Blocker |
|----|----------|--------|-------|--------|---------|
| IRF-VAC-001a | P0 | Letter-suffixed sub-item (IRF-SYS-182 class) | Agent | S4 | None |
| IRF-VAC-001b | P1 | Second letter-suffixed sub-item | Agent | S4 | None |
| ~~IRF-VAC-002a~~ | ~~P0~~ | ~~Struck letter-suffixed sub-item~~ — **DONE** | Agent | S4 | None |

## Blocked

| ID | What | Reason | Date |
|----|------|--------|------|
| IRF-SYS-155 | 4-cell ledger-shaped row mentioning P4 in a Blocked section (category C) | xattr corruption | 2026-05-16 |

## Completed (ledger)

| ID | What | Session | Date |
|----|------|---------|------|
| DONE-001 | Canonical 4-col completed ledger row | S5 | 2026-06-01 |
| DONE-114a | Letter-suffixed DONE row | S5 | 2026-06-01 |
| DONE-145 | Short 3-cell DONE row (category D) | 2026-06-02 |

## Statistics

**Last updated:** 2026-05-17

| Metric | Value |
|--------|-------|
| Total Items | 999 |
| Open Items | 999 |

### Items by Priority

| Priority | Count |
|----------|-------|
| P0 | 999 |

### Items by Domain

| Domain | Count |
|--------|-------|
| SYS | 999 |
| DONE | 999 |
