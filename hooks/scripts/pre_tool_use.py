from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[2]))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.lesson_engine import find_relevant_lessons
from scripts.memory_store import ensure_memory_home, find_allow_candidates
from scripts.sanitize import normalize_command

HIGH_VALUE_FAILURE_COUNT = 3
HIGH_VALUE_CONFIDENCE = 0.8
HIGH_VALUE_HABIT_SUCCESS_COUNT = 5


def silent_response() -> dict:
    return {
        "continue": True,
        "suppressOutput": True,
    }


def emit_silent_response() -> None:
    sys.stdout.write(json.dumps(silent_response(), ensure_ascii=False))


def high_value_lessons(lessons: list[dict]) -> list[dict]:
    selected = []
    for lesson in lessons:
        failure_count = int(lesson.get("failure_count", 0) or 0)
        confidence = float(lesson.get("confidence", 0) or 0)
        is_project_scoped = lesson.get("scope") == "project"
        if failure_count >= HIGH_VALUE_FAILURE_COUNT or confidence >= HIGH_VALUE_CONFIDENCE or is_project_scoped:
            selected.append(lesson)
    return selected[:1]


def high_value_candidates(candidates: list[dict]) -> list[dict]:
    selected = []
    for candidate in candidates:
        success_count = int(candidate.get("success_count", 0) or 0)
        if success_count >= HIGH_VALUE_HABIT_SUCCESS_COUNT:
            selected.append(candidate)
    return selected[:1]


def build_failure_message(command: str, lessons: list[dict]) -> str:
    top = lessons[0]
    advice = top.get("advice", "")
    failure_count = top.get("failure_count", 0)
    scope = top.get("scope", "global")
    return (
        "ai-memory 提醒：该命令与历史失败模式相似。\n"
        f"- command: `{command}`\n"
        f"- scope: {scope}\n"
        f"- repeated_failures: {failure_count}\n"
        f"- advice: {advice}"
    )


def build_habit_message(command: str, candidates: list[dict]) -> str:
    top = candidates[0]
    scope = top.get("scope", "global")
    cwd = top.get("cwd") or "-"
    success_count = top.get("success_count", 0)
    suggested_permission = top.get("suggested_permission", "allow")
    lines = [
        "ai-memory 提醒：该命令命中历史成功习惯。",
        f"- command: `{command}`",
        f"- scope: {scope}",
        f"- success_count: {success_count}",
        f"- suggested_permission: {suggested_permission}",
    ]
    if scope == "project":
        lines.append(f"- cwd: {cwd}")
    lines.append("- note: 仅供参考，不会自动修改权限设置。")
    return "\n".join(lines)


def main() -> int:
    ensure_memory_home()
    raw = sys.stdin.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    tool_input = payload.get("tool_input") or {}
    command = normalize_command(tool_input.get("command") or tool_input.get("cmd") or "")
    cwd = payload.get("cwd") or ""

    if not command:
        emit_silent_response()
        return 0

    lessons = find_relevant_lessons(command=command, cwd=cwd)
    candidates = find_allow_candidates(command=command, cwd=cwd)
    lessons = high_value_lessons(lessons)
    candidates = high_value_candidates(candidates)
    if not lessons and not candidates:
        emit_silent_response()
        return 0

    messages: list[str] = []
    if lessons:
        messages.append(build_failure_message(command, lessons))
    if candidates:
        messages.append(build_habit_message(command, candidates))

    sys.stdout.write(json.dumps({
        "continue": True,
        "suppressOutput": False,
        "systemMessage": "\n\n".join(messages)
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        emit_silent_response()
        raise SystemExit(0)
