# Changelog

All notable changes to this project will be documented in this file.

This project follows a pragmatic changelog style inspired by [Keep a Changelog](https://keepachangelog.com/) and uses semantic versioning where practical.

## [0.1.0] - 2026-04-17

### Added

- Initial Claude Code plugin metadata and hook configuration.
- `SessionStart`, `PreToolUse`, and `PostToolUse` hook scripts.
- Local memory store under `~/.ai-memory` with:
  - `events.jsonl`
  - `lessons.json`
  - `preferences.json`
  - `stats.json`
- Bash command result recording and command statistics.
- Error signature normalization for repeated failures such as:
  - `command not found`
  - `ModuleNotFoundError`
  - `permission denied`
- Lesson generation from repeated command failures.
- Habit candidate generation for repeated low-risk successful commands.
- High-value-only reminder mode for `PreToolUse`.
- Safe fail-open behavior for hook exceptions and malformed JSON payloads.
- Local memory summary CLI with JSON and pretty output modes.
- Memory migration CLI with dry-run and backup support.
- Chinese GitHub-ready README with examples, troubleshooting, and usage guidance.
- MIT license.

### Changed

- Made `SessionStart` silent by default.
- Made `PostToolUse` silent by default to reduce Claude Code conversation noise.
- Limited lesson rebuilding to the most recent `1000` events for better stability.
- Removed automatic `permissionDecision: allow` from reminder output.

### Security

- Added secret redaction for common token/password/API key patterns.
- Added path sanitization for command output and stored events.
- Added `.gitignore` rules to avoid committing local memory files, logs, virtual environments, and secrets.

### Tested

- Verified with `python -m unittest discover -s tests -v`.
- Current suite: `29` tests passing.
