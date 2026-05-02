# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository is a Claude Code hook plugin that records Bash command outcomes into a local memory store under `~/.ai-memory`, derives repeated failure lessons and stable low-risk command habits, and surfaces only high-value reminders before future Bash executions.

The runtime is split across three layers:
- Claude Code hook entrypoints in `hooks/scripts/`
- memory persistence and normalization logic in `scripts/`
- regression coverage in `tests/`

## Common commands

### Run tests

```powershell
python -m unittest discover -s tests -v
```

### Run a single test file

```powershell
python -m unittest tests.test_memory_plugin -v
```

### Run a single test case

```powershell
python -m unittest tests.test_memory_plugin.MemoryPluginTests.test_post_tool_use_updates_stats -v
```

### Replay hook fixtures

```powershell
python tests/run_fixture.py pre_tool_use.py pre_tool_use.json
python tests/run_fixture.py post_tool_use.py post_tool_use_success.json
python tests/run_fixture.py post_tool_use.py post_tool_use_failure.json
```

### Inspect stored memory summary

```powershell
python scripts/memory_summary.py
python scripts/memory_summary.py --pretty
python scripts/memory_summary.py --pretty --only overview,lessons
python scripts/memory_summary.py --json --limit 5
```

### Migrate memory data

```powershell
python scripts/migrate_memory.py
python scripts/migrate_memory.py --dry-run
python scripts/migrate_memory.py --backup
```

## Architecture

### Hook flow

Claude Code loads the plugin through `.claude-plugin/plugin.json`, which points at `hooks/hooks.json`. That hook config wires three Python entrypoints:
- `hooks/scripts/session_start.py` initializes the memory store and returns silent metadata.
- `hooks/scripts/pre_tool_use.py` reads existing lessons and allow-candidate habits before a `Bash` call, then emits a reminder only for high-value matches.
- `hooks/scripts/post_tool_use.py` runs after a `Bash` call, normalizes the result, appends an event, updates aggregate stats, rebuilds lessons on failures, and refreshes allow-candidate habits on successful low-risk commands.

The design is intentionally fail-open and mostly silent: normal execution should not inject chat noise unless a command matches a strong prior signal.

### Memory model

`scripts/memory_store.py` is the persistence backbone. It owns:
- creation of `~/.ai-memory`
- JSON/JSONL read-write helpers
- canonical event normalization
- aggregate command and error-signature stats
- rebuilding preference candidates for repeated low-risk commands
- summary and migration helpers used by CLI scripts and tests

The on-disk store is centered on four files:
- `events.jsonl`: normalized raw Bash execution history
- `lessons.json`: derived repeated-failure patterns
- `preferences.json`: tool preferences plus allow-candidate habits
- `stats.json`: aggregate command/error counters

### Normalization and matching pipeline

`scripts/sanitize.py` is the shared normalization boundary. It redacts secrets, shortens paths, canonicalizes commands, extracts command prefixes, recognizes low-risk commands, and collapses noisy stderr into stable error signatures such as `command not found: jest` or `module not found: dotenv`.

That normalized data feeds `scripts/lesson_engine.py`, which groups repeated failures by:
- command prefix
- normalized error signature
- normalized cwd

Project-scoped lessons are preferred over global ones, and confidence rises with repeated failures. `pre_tool_use.py` uses `find_relevant_lessons()` plus allow-candidate lookup from `memory_store.py` to decide whether a reminder is worth showing.

### Reminder policy

The plugin does not remind on every match. Current thresholds are encoded in hook logic:
- failure reminders are shown for project-scoped lessons, or when failure count is at least 3, or confidence is at least 0.8
- habit reminders are shown only when a low-risk command has at least 5 successful matches

If you change thresholds or matching behavior, update both hook scripts and tests together.

### Testing strategy

`tests/test_memory_plugin.py` is an end-to-end style unit suite covering the important flows:
- initialization of the memory home
- sanitization and signature normalization
- lesson rebuilding from repeated failures
- stats and allow-candidate updates from post-hook execution
- migration rebuilding legacy data
- summary script output

Tests isolate `HOME` and `USERPROFILE` into a temporary directory, so behavior that depends on `~/.ai-memory` should usually be verified there instead of against the real user environment.

`tests/run_fixture.py` is the quickest way to replay hook payloads from `tests/fixtures/` when debugging hook I/O.

## Important implementation notes

- Hook entrypoints rely on `CLAUDE_PLUGIN_ROOT` and manually prepend the repo root to `sys.path`; preserve that behavior when moving files.
- The plugin currently targets `Bash` hook events only, even though the README and user environment may be Windows-first.
- Low-risk command classification is hardcoded in `scripts/sanitize.py`; adding a new habit candidate requires updating that allowlist.
- Lesson rebuilding is capped to the most recent 1000 events in `scripts/lesson_engine.py` for stability.
- The skill definition in `skills/ai-memory-assistant/SKILL.md` is part of the product surface for interpreting stored memory; keep it aligned with any schema or summary changes.
