# Release Notes - v0.1.0

## AI Memory Plugin for Claude Code v0.1.0

`ai-memory-plugin` v0.1.0 is the first public release of a local memory plugin for Claude Code.

The plugin records Bash command outcomes, derives reusable lessons from repeated failures, identifies stable low-risk command habits, and surfaces reminders only when the signal is strong enough to be useful.

## Highlights

- Records Bash command results under `~/.ai-memory`.
- Tracks command success and failure counts.
- Normalizes repeated error signatures such as `command not found`, `ModuleNotFoundError`, and `permission denied`.
- Generates lessons from repeated command failures.
- Identifies habit candidates from repeated low-risk successful commands.
- Uses a high-value-only reminder policy for `PreToolUse`.
- Keeps `SessionStart` and `PostToolUse` silent by default.
- Uses fail-open hook behavior for malformed JSON payloads and unexpected hook errors.
- Provides memory summary and migration utilities.
- Includes secret redaction, path sanitization, and local-first storage.

## Stability notes

This release prioritizes low interference with the Claude Code interaction flow:

- `SessionStart` initializes storage without adding conversation output.
- `PostToolUse` records outcomes silently.
- `PreToolUse` only emits reminders for high-value matches.
- Lesson rebuilding is limited to the most recent `1000` events.
- The plugin does not inject `permissionDecision: allow`.

## Install

Enable the repository as a Claude Code plugin and verify these files are present:

```text
.claude-plugin/plugin.json
hooks/hooks.json
```

## Verify

```bash
python -m unittest discover -s tests -v
```

Current verification status: `29` tests passing.

## Upgrade notes

If you already have local memory data under `~/.ai-memory`, run a backup migration before relying on the new version:

```bash
python scripts/migrate_memory.py --backup
```

## Known limitations

- The current release focuses on Bash command memory.
- Reminder thresholds are currently defined in code.
- There is no dedicated CLI yet for editing or deleting generated lessons.
