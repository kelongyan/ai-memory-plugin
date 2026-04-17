---
name: ai-memory-assistant
description: This skill should be used when the user asks to "查看我的习惯", "回顾最近失败的命令", "总结 ai-memory 记录", "为什么这个命令总失败", "分析 ~/.ai-memory", or wants Claude Code to interpret remembered command history, lessons, and recurring failures stored under ~/.ai-memory.
version: 0.1.0
---

# AI Memory Assistant

## Purpose

Read the user's shared memory files under `~/.ai-memory/` and explain the patterns in natural language.

Focus on:
- recurring Bash command failures
- repeated error signatures
- reusable lessons already extracted by the plugin
- stable command habits reflected in preferences or stats
- differences between global allow candidates and project-specific allow candidates

## Workflow

1. Read the relevant files in `~/.ai-memory/`:
   - `lessons.json`
   - `stats.json`
   - `events.jsonl` when recent raw events matter
   - `preferences.json` when user asks about habits or preferences
2. Prefer summarized files (`lessons.json`, `stats.json`) before reading raw events.
3. When the user asks about habits, inspect `preferences.json` and distinguish:
   - global allow candidates
   - project allow candidates (`scope=project`, with cwd)
   - whether a suggestion is broadly stable or cwd-specific
4. Explain findings in concise Chinese, but keep commands, paths, and raw error strings in original form.
5. Distinguish between:
   - confirmed repeated patterns
   - one-off failures
   - suggestions that still need user confirmation
6. If the user asks how to improve the memory rules, propose changes conceptually unless they explicitly ask for implementation.

## Output guidance

When summarizing memory, structure the response as:

- **Observed patterns**
- **Likely causes**
- **Reusable advice**
- **What is still uncertain**

## Guardrails

- Do not claim a pattern is stable unless the data shows repeated events.
- Do not suggest automatically changing Claude Code permissions unless the user explicitly asks.
- Treat `events.jsonl` as raw evidence and `lessons.json` as derived guidance.
