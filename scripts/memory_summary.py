from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[1]))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.memory_store import build_memory_summary

_ALLOWED_SECTIONS = {"overview", "commands", "errors", "lessons", "habits"}


def parse_output_mode(argv: list[str]) -> str:
    if "--pretty" in argv:
        return "pretty"
    if "--json" in argv:
        return "json"
    return "json"


def parse_limit(argv: list[str]) -> int | None:
    if "--limit" not in argv:
        return None
    index = argv.index("--limit")
    if index + 1 >= len(argv):
        raise ValueError("--limit requires a positive integer")
    try:
        limit = int(argv[index + 1])
    except ValueError as exc:
        raise ValueError("--limit requires a positive integer") from exc
    if limit < 1:
        raise ValueError("--limit requires a positive integer")
    return limit


def parse_only(argv: list[str]) -> set[str] | None:
    if "--only" not in argv:
        return None
    index = argv.index("--only")
    if index + 1 >= len(argv):
        raise ValueError("--only requires one of: habits, lessons, errors, commands, overview")
    sections = {part.strip().lower() for part in argv[index + 1].split(",") if part.strip()}
    unknown = sections - _ALLOWED_SECTIONS
    if not sections or unknown:
        allowed = ", ".join(sorted(_ALLOWED_SECTIONS))
        raise ValueError(f"--only requires one or more of: {allowed}")
    return sections


def apply_limit(summary: dict, limit: int | None) -> dict:
    if limit is None:
        return summary
    limited = dict(summary)
    limited["top_commands"] = summary.get("top_commands", [])[:limit]
    limited["top_error_signatures"] = summary.get("top_error_signatures", [])[:limit]
    limited["lessons"] = summary.get("lessons", [])[:limit]
    habits = summary.get("habits", {})
    limited["habits"] = {
        "project_candidates": habits.get("project_candidates", [])[:limit],
        "global_candidates": habits.get("global_candidates", [])[:limit],
    }
    return limited


def filter_summary(summary: dict, sections: set[str] | None) -> dict:
    if sections is None:
        return summary
    filtered = {"memory_home": summary.get("memory_home", "")}
    if "overview" in sections:
        filtered["overview"] = summary.get("overview", {})
    if "commands" in sections:
        filtered["top_commands"] = summary.get("top_commands", [])
    if "errors" in sections:
        filtered["top_error_signatures"] = summary.get("top_error_signatures", [])
    if "lessons" in sections:
        filtered["lessons"] = summary.get("lessons", [])
    if "habits" in sections:
        filtered["habits"] = summary.get("habits", {})
    return filtered


def render_pretty(summary: dict) -> str:
    overview = summary.get("overview")
    lines = ["ai-memory summary"]

    if overview is not None:
        lines.extend([
            "",
            "Overview",
            f"- memory_home: {summary.get('memory_home', '')}",
            f"- events: {overview.get('events', 0)}",
            f"- lessons: {overview.get('lessons', 0)}",
            f"- allow_candidates: {overview.get('allow_candidates', 0)}",
            f"- commands_tracked: {overview.get('commands_tracked', 0)}",
            f"- error_signatures_tracked: {overview.get('error_signatures_tracked', 0)}",
        ])

    top_commands = summary.get("top_commands")
    if top_commands is not None:
        lines.append("")
        lines.append("Top commands")
        if top_commands:
            for item in top_commands:
                lines.append(
                    f"- {item.get('command', '')}: success={item.get('success', 0)}, failure={item.get('failure', 0)}, last_seen_at={item.get('last_seen_at') or '-'}"
                )
        else:
            lines.append("- none")

    top_errors = summary.get("top_error_signatures")
    if top_errors is not None:
        lines.append("")
        lines.append("Top error signatures")
        if top_errors:
            for item in top_errors:
                lines.append(
                    f"- {item.get('error_signature', '')}: count={item.get('count', 0)}, last_seen_at={item.get('last_seen_at') or '-'}"
                )
        else:
            lines.append("- none")

    lessons = summary.get("lessons")
    if lessons is not None:
        lines.append("")
        lines.append("Lessons")
        if lessons:
            for item in lessons:
                scope = item.get("scope", "global")
                cwd = item.get("cwd") or "-"
                lines.append(
                    f"- [{scope}] {item.get('command_prefix', '')} -> {item.get('error_signature', '')} (failures={item.get('failure_count', 0)}, cwd={cwd})"
                )
                lines.append(f"  advice: {item.get('advice', '')}")
        else:
            lines.append("- none")

    habits = summary.get("habits")
    if habits is not None:
        lines.append("")
        lines.append("Project habits")
        project_candidates = habits.get("project_candidates", [])
        if project_candidates:
            for item in project_candidates:
                lines.append(
                    f"- {item.get('command', '')} @ {item.get('cwd', '-')}: success_count={item.get('success_count', 0)}, suggested_permission={item.get('suggested_permission', '-')}"
                )
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Global habits")
        global_candidates = habits.get("global_candidates", [])
        if global_candidates:
            for item in global_candidates:
                lines.append(
                    f"- {item.get('command', '')}: success_count={item.get('success_count', 0)}, suggested_permission={item.get('suggested_permission', '-')}"
                )
        else:
            lines.append("- none")

    return "\n".join(lines)


def main() -> int:
    try:
        output_mode = parse_output_mode(sys.argv[1:])
        limit = parse_limit(sys.argv[1:])
        sections = parse_only(sys.argv[1:])
    except ValueError as exc:
        sys.stderr.write(str(exc))
        return 1

    summary = build_memory_summary()
    summary = apply_limit(summary, limit)
    summary = filter_summary(summary, sections)
    if output_mode == "pretty":
        sys.stdout.write(render_pretty(summary))
    else:
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
