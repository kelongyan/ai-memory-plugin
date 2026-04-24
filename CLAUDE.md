# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python-based Claude Code plugin that gives Claude Code persistent local command memory. Records Bash command outcomes into `~/.ai-memory/`, extracts lessons from repeated failures, identifies stable command habits, and surfaces high-value reminders before repeated mistakes. Pure stdlib — no third-party dependencies.

## Commands

```bash
# Run full test suite (29 tests)
python -m unittest discover -s tests -v

# Exercise a hook with a fixture
python tests/run_fixture.py pre_tool_use.py pre_tool_use.json
python tests/run_fixture.py post_tool_use.py post_tool_use_success.json
python tests/run_fixture.py post_tool_use.py post_tool_use_failure.json

# CLI tools
python scripts/memory_summary.py [--json|--pretty] [--only overview,lessons] [--limit 5]
python scripts/migrate_memory.py [--dry-run|--backup]
```

## Architecture

**Hook pipeline** (configured in `hooks/hooks.json`):

1. **SessionStart** → `hooks/scripts/session_start.py`: Creates `~/.ai-memory/` and default files if missing. Always silent.
2. **PostToolUse (Bash)** → `hooks/scripts/post_tool_use.py`: Normalizes command/output via `sanitize.py`, appends event to `events.jsonl`, updates `stats.json` counters, updates habit candidates in `preferences.json`, rebuilds lessons via `lesson_engine.py` on error detection. Always silent.
3. **PreToolUse (Bash)** → `hooks/scripts/pre_tool_use.py`: Matches lessons/habits, filters to high-value hits only (failure_count >= 3, confidence >= 0.8, project-scoped, or habit success_count >= 5), outputs `systemMessage` in Chinese if hits found.

**Core scripts** (in `scripts/`):

- `sanitize.py` — All text normalization: secret redaction, path truncation, error signature normalization, low-risk command check
- `memory_store.py` — All I/O: read/write events.jsonl, lessons.json, preferences.json, stats.json
- `lesson_engine.py` — Lesson rebuild (from last 1000 events) and relevance matching

**Data model**: Records are tagged `global` (no cwd) or `project` (with normalized lowercase cwd). Project-scoped lessons/habits take priority over global ones.

## Key Patterns

- **Fail-open**: All hook scripts wrap `main()` in try/except → `emit_silent_response()` on any uncaught exception. Hooks never block Claude Code.
- **stdin/stdout contract**: Hooks read JSON from stdin, write single JSON response to stdout. Response always has `"continue": true`. Active reminders add `"systemMessage"`; silent responses add `"suppressOutput": true`.
- **CLAUDE_PLUGIN_ROOT**: Scripts use `os.environ.get("CLAUDE_PLUGIN_ROOT", ...)` to set up sys.path, supporting both plugin-loaded and standalone subprocess execution.
- **Sanitization before storage**: Every command/output passes through `sanitize.py` before persistence. Includes secret redaction, path truncation, and cross-platform error normalization.
- **Test isolation**: Tests use `tempfile.TemporaryDirectory()` with overridden HOME/USERPROFILE and module-level path constants. No pytest — pure `unittest`.

## Coding Conventions

- Python 3.13+, `from __future__ import annotations`, 4-space indentation, type hints
- `snake_case` functions/modules, `UPPER_SNAKE_CASE` constants, `PascalCase` test classes only
- JSON persistence: `indent=2`, `ensure_ascii=False`; JSONL: single-line records
- Small focused functions, no external dependencies
- Imperative commit messages (e.g., `Add lesson deduplication for repeated failures`)