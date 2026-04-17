# Repository Guidelines

## Project Structure & Module Organization
This repository is a Python-based Claude Code plugin. Core logic lives in `scripts/` (`memory_store.py`, `lesson_engine.py`, `sanitize.py`, migration/report helpers). Hook entrypoints are in `hooks/scripts/`, configured by `hooks/hooks.json`. Tests live in `tests/`, with JSON fixtures under `tests/fixtures/`. Plugin metadata is in `.claude-plugin/plugin.json`, and assistant skill definitions live under `skills/`.

## Build, Test, and Development Commands
Use Python 3.13+.

- `python -m unittest discover -s tests -v` — run the full test suite.
- `python tests/run_fixture.py pre_tool_use.py pre_tool_use.json` — exercise a hook script with a fixture.
- `python scripts/migrate_memory.py` — migrate legacy `~/.ai-memory` data formats.
- `python scripts/memory_summary.py` — print a summary of remembered events and lessons.

Run commands from the repository root: `C:\Users\Administrator\ai-memory-plugin`.

## Coding Style & Naming Conventions
Follow existing Python conventions: 4-space indentation, type hints, `from __future__ import annotations`, and small focused functions. Use `snake_case` for functions/modules, `UPPER_SNAKE_CASE` for module constants, and `PascalCase` only for test classes. Keep JSON output stable and human-readable (`indent=2` when persisted).

## Testing Guidelines
Tests use the standard library `unittest` framework. Add or update tests in `tests/test_memory_plugin.py` when changing sanitization, lesson extraction, hook behavior, or persistence logic. Prefer fixture-driven tests for hook I/O and isolated temporary directories for filesystem behavior. Run the full suite before submitting changes.

## Commit & Pull Request Guidelines
This checkout does not include `.git`, so no local commit history is available. Use concise imperative commit messages such as `Add lesson deduplication for repeated failures`. PRs should summarize behavior changes, mention affected commands/hooks, and note test coverage. Include sample hook output when changing user-facing reminders.

## Security & Configuration Tips
Never commit real contents of `~/.ai-memory` or secrets captured from command output. Preserve the repository’s sanitization behavior when handling paths, tokens, or stderr/stdout text. Keep hook timeouts modest and avoid introducing dependencies outside the Python standard library unless the project already adopts them.
