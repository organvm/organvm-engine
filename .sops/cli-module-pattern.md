---
sop: true
name: cli-module-pattern
scope: repo
phase: any
last_reviewed: 2026-06-19
governed_paths:
  - src/organvm_engine/cli/
  - tests/test_cli.py
triggers:
  - context:new-cli-command
complements: []
overrides: null
---
# CLI Module Pattern

## Purpose

Defines how to add a new command group to the `organvm` CLI. The CLI is a package at `src/organvm_engine/cli/` with one module per command group.

## Procedure

1. **Create module**: `src/organvm_engine/cli/{group}.py`
   - Export `cmd_{group}_{subcommand}` functions taking `argparse.Namespace`, returning `int`
   - Use deferred imports inside functions (not at module level) for fast CLI startup
2. **Wire in `__init__.py`**:
   - Import the `cmd_*` functions at the top
   - Add argparse subparser in `build_parser()`
   - Add dispatch entry in the `if args.command == "{group}":` block
3. **Write tests**: `tests/test_cli_{group}.py` or extend existing test module
4. **Update CLAUDE.md**: Add the command to the CLI reference docstring

## Verification

- `organvm {group} --help` shows subcommands
- `ruff check src/organvm_engine/cli/{group}.py` passes
- `pytest tests/ -k {group} -v` passes
