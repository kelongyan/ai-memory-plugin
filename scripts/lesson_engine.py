from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.memory_store import read_events, read_lessons, write_lessons
from scripts.sanitize import command_prefix, normalize_command, normalize_scope_path

LESSON_THRESHOLD = 2
MAX_EVENTS_FOR_REBUILD = 1000


def rebuild_lessons_from_events() -> list[dict[str, Any]]:
    events = read_events(limit=MAX_EVENTS_FOR_REBUILD)
    failure_events = [event for event in events if not event.get("ok") and event.get("error_signature")]

    counts = Counter(
        (
            event.get("command_prefix", ""),
            event.get("error_signature", ""),
            normalize_scope_path(event.get("cwd", "")),
        )
        for event in failure_events
    )

    lessons: list[dict[str, Any]] = []
    for (command_prefix_value, error_signature, normalized_cwd), count in counts.items():
        if not command_prefix_value or not error_signature or count < LESSON_THRESHOLD:
            continue

        scope = "project" if normalized_cwd else "global"
        lessons.append({
            "id": build_lesson_id(command_prefix_value, error_signature, normalized_cwd),
            "scope": scope,
            "cwd": normalized_cwd,
            "match_scope_priority": 2 if scope == "project" else 1,
            "pattern": {
                "command_prefix": command_prefix_value,
                "error_signature": error_signature,
            },
            "advice": default_advice(command_prefix_value, error_signature),
            "confidence": min(0.5 + count * 0.15, 0.95),
            "failure_count": count,
        })

    lessons.sort(
        key=lambda item: (
            item.get("scope") != "project",
            item["pattern"]["command_prefix"],
            item["pattern"]["error_signature"],
            item.get("cwd", ""),
        )
    )
    write_lessons(lessons)
    return lessons


def build_lesson_id(command_prefix_value: str, error_signature: str, cwd: str) -> str:
    parts = [command_prefix_value.strip().replace(" ", "-"), error_signature[:40].replace(" ", "-")]
    if cwd:
        parts.append(cwd.replace("\\", "/").split("/")[-1])
    normalized = "-".join(part.lower() for part in parts if part)
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in normalized)
    return f"lesson-{normalized.strip('-')}"


def default_advice(command_prefix_value: str, error_signature: str) -> str:
    lower = error_signature.lower()
    if "command not found" in lower or "not found" in lower or "is not recognized" in lower:
        return f"`{command_prefix_value}` 之前多次因命令不可用失败。先检查工具是否已安装，或当前 shell/PATH 是否正确。"
    if "permission denied" in lower:
        return f"`{command_prefix_value}` 之前多次因权限问题失败。先检查当前目录权限、凭证或是否需要更安全的替代命令。"
    if "module not found" in lower:
        return f"`{command_prefix_value}` 之前多次因依赖缺失失败。先检查虚拟环境或依赖是否已安装。"
    return f"`{command_prefix_value}` 在当前环境中曾多次触发相同错误，执行前先复查命令参数、依赖与工作目录。"


def find_relevant_lessons(command: str, cwd: str | None = None) -> list[dict[str, Any]]:
    normalized_command = normalize_command(command)
    normalized_cwd = normalize_scope_path(cwd)
    target_prefix = command_prefix(normalized_command)
    lessons = read_lessons()
    matched: list[dict[str, Any]] = []

    for lesson in lessons:
        pattern = lesson.get("pattern", {})
        prefix = normalize_command(pattern.get("command_prefix", ""))
        lesson_cwd = normalize_scope_path(lesson.get("cwd", ""))
        if not prefix:
            continue

        prefix_matches = (
            target_prefix == prefix
            or normalized_command == prefix
            or normalized_command.startswith(f"{prefix} ")
        )
        if not prefix_matches:
            continue

        if lesson_cwd and lesson_cwd != normalized_cwd:
            continue

        matched.append(lesson)

    matched.sort(
        key=lambda item: (
            item.get("scope") == "project",
            item.get("confidence", 0),
            item.get("failure_count", 0),
            len(item.get("pattern", {}).get("command_prefix", "")),
        ),
        reverse=True,
    )
    return matched
