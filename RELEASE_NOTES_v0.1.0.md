# v0.1.0 · First Public Release

AI Memory Plugin is a local memory layer for Claude Code. It records Bash command outcomes, extracts reusable lessons from repeated failures, and recognizes stable low-risk command habits — while staying quiet unless a reminder is likely to be useful.

This first release focuses on one goal: make Claude Code feel more consistent across sessions without turning the plugin into another source of noise.

## What is included

- Local command memory stored under `~/.ai-memory`
- Bash command success/failure tracking
- Repeated failure detection and lesson generation
- Low-risk command habit detection
- High-value-only reminders before command execution
- Silent-by-default `SessionStart` and `PostToolUse` hooks
- Fail-open behavior for malformed hook payloads and runtime errors
- Secret redaction and path sanitization for stored command output
- Memory summary and migration utilities
- Chinese README, changelog, MIT license, and test coverage

## Why it matters

Claude Code is powerful, but repeated sessions often lack continuity. This plugin adds a small, local, auditable memory layer so repeated mistakes and stable project habits can be reused instead of rediscovered.

## Stability and safety

This release is intentionally conservative:

- No automatic permission override
- No remote memory sync
- No upload of `~/.ai-memory`
- No routine conversation output from background hooks
- Lesson rebuilding is limited to the latest `1000` events

## Quick verification

```bash
python -m unittest discover -s tests -v
```

Current status: `29` tests passing.

## Notes

The current release focuses on Bash command memory. Future versions may add configurable thresholds, richer lesson management, and broader tool coverage.
