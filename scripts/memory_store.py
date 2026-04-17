from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.sanitize import (
    command_prefix,
    expand_user_home,
    extract_error_signature,
    is_low_risk_command,
    normalize_command,
    normalize_scope_path,
    normalize_tool_result_text,
    to_jsonable,
)

MEMORY_HOME = expand_user_home("~/.ai-memory")
EVENTS_FILE = MEMORY_HOME / "events.jsonl"
LESSONS_FILE = MEMORY_HOME / "lessons.json"
PREFERENCES_FILE = MEMORY_HOME / "preferences.json"
STATS_FILE = MEMORY_HOME / "stats.json"


DEFAULT_CANDIDATE_THRESHOLDS = {
    "success_threshold_for_candidate": 3,
    "minimum_risk_level": "low",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_preferences() -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": utc_now_iso(),
        "always_allow_candidates": [],
        "never_allow": [],
        "tool_preferences": {
            "claude-code": {
                "shell": "PowerShell"
            }
        },
        "candidate_thresholds": DEFAULT_CANDIDATE_THRESHOLDS.copy(),
    }


def normalize_candidate(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None

    command = command_prefix(candidate.get("command", "")) or normalize_command(candidate.get("command", ""))
    if not command:
        return None

    scope = candidate.get("scope")
    cwd = normalize_scope_path(candidate.get("cwd", ""))
    if scope not in {"global", "project"}:
        scope = "project" if cwd else "global"
    if scope == "global":
        cwd = ""

    return {
        "command": command,
        "scope": scope,
        "cwd": cwd,
        "success_count": max(int(candidate.get("success_count", 0) or 0), 0),
        "last_seen_at": candidate.get("last_seen_at"),
        "reason": candidate.get("reason") or "repeated low-risk successful command",
        "risk_level": candidate.get("risk_level") or "low",
        "suggested_permission": candidate.get("suggested_permission") or "allow",
    }


def normalize_preferences(data: Any) -> dict[str, Any]:
    defaults = default_preferences()
    if not isinstance(data, dict):
        return defaults

    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for raw_candidate in data.get("always_allow_candidates", []):
        candidate = normalize_candidate(raw_candidate)
        if not candidate:
            continue
        key = (candidate["command"], candidate["scope"], candidate["cwd"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append(candidate)

    candidates.sort(key=lambda item: (item.get("scope") != "project", item.get("command", ""), item.get("cwd", "")))

    normalized = {
        "version": data.get("version", defaults["version"]),
        "created_at": data.get("created_at") or defaults["created_at"],
        "always_allow_candidates": candidates,
        "never_allow": data.get("never_allow") if isinstance(data.get("never_allow"), list) else [],
        "tool_preferences": data.get("tool_preferences") if isinstance(data.get("tool_preferences"), dict) else defaults["tool_preferences"],
        "candidate_thresholds": defaults["candidate_thresholds"].copy(),
    }

    if isinstance(data.get("candidate_thresholds"), dict):
        normalized["candidate_thresholds"].update(data["candidate_thresholds"])

    return normalized


def ensure_memory_home() -> Path:
    MEMORY_HOME.mkdir(parents=True, exist_ok=True)

    defaults: dict[Path, Any] = {
        PREFERENCES_FILE: default_preferences(),
        LESSONS_FILE: [],
        STATS_FILE: {
            "version": 1,
            "commands": {},
            "error_signatures": {}
        },
    }

    for path, default in defaults.items():
        if not path.exists():
            write_json(path, default)

    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("", encoding="utf-8")

    return MEMORY_HOME


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(to_jsonable(record), ensure_ascii=False) + "\n")


def rewrite_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(to_jsonable(record), ensure_ascii=False) for record in records)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def append_event(record: dict[str, Any]) -> None:
    ensure_memory_home()
    append_jsonl(EVENTS_FILE, normalize_event_record(record))


def read_events(limit: int | None = None) -> list[dict[str, Any]]:
    ensure_memory_home()
    if not EVENTS_FILE.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if limit is not None:
        return records[-limit:]
    return records


def write_events(events: list[dict[str, Any]]) -> None:
    ensure_memory_home()
    rewrite_jsonl(EVENTS_FILE, events)


def read_lessons() -> list[dict[str, Any]]:
    ensure_memory_home()
    data = read_json(LESSONS_FILE, [])
    return data if isinstance(data, list) else []


def write_lessons(lessons: list[dict[str, Any]]) -> None:
    ensure_memory_home()
    write_json(LESSONS_FILE, lessons)


def read_preferences() -> dict[str, Any]:
    ensure_memory_home()
    data = read_json(PREFERENCES_FILE, default_preferences())
    normalized = normalize_preferences(data)
    return normalized


def write_preferences(preferences: dict[str, Any]) -> None:
    ensure_memory_home()
    write_json(PREFERENCES_FILE, normalize_preferences(preferences))


def read_stats() -> dict[str, Any]:
    ensure_memory_home()
    data = read_json(STATS_FILE, {"version": 1, "commands": {}, "error_signatures": {}})
    if not isinstance(data, dict):
        return {"version": 1, "commands": {}, "error_signatures": {}}
    data.setdefault("commands", {})
    data.setdefault("error_signatures", {})
    return data


def write_stats(stats: dict[str, Any]) -> None:
    ensure_memory_home()
    write_json(STATS_FILE, stats)


def normalize_event_record(event: dict[str, Any]) -> dict[str, Any]:
    normalized_command = normalize_command(event.get("command", "") or event.get("tool_input", {}).get("command", "") or event.get("tool_input", {}).get("cmd", ""))
    normalized_cwd = normalize_scope_path(event.get("cwd", ""))
    ok = bool(event.get("ok", False))
    stdout_text = event.get("stdout", "")
    stderr_text = event.get("stderr", "")
    return_code = event.get("return_code")

    if "tool_result" in event:
        parsed_stdout, parsed_stderr, parsed_return_code = normalize_tool_result_text(event.get("tool_result"))
        stdout_text = parsed_stdout
        stderr_text = parsed_stderr
        if parsed_return_code is not None:
            return_code = parsed_return_code
        if parsed_return_code is not None:
            ok = parsed_return_code == 0
        elif not event.get("ok"):
            ok = False
        else:
            ok = not bool(extract_error_signature(event.get("tool_result")))

    normalized_stdout = stdout_text[:1000] if isinstance(stdout_text, str) else ""
    normalized_stderr = stderr_text[:1000] if isinstance(stderr_text, str) else ""
    error_signature = extract_error_signature({"stderr": normalized_stderr}) if normalized_stderr else ""
    if not error_signature and event.get("error_signature"):
        error_signature = extract_error_signature({"stderr": str(event.get("error_signature", ""))})

    if error_signature:
        ok = False

    return {
        "ts": event.get("ts") or utc_now_iso(),
        "tool": event.get("tool") or event.get("tool_name") or "Bash",
        "hook_event": event.get("hook_event") or event.get("hook_event_name") or "PostToolUse",
        "cwd": normalized_cwd,
        "session_id": event.get("session_id", ""),
        "command": normalized_command,
        "command_prefix": command_prefix(normalized_command),
        "ok": ok,
        "return_code": return_code if isinstance(return_code, int) else None,
        "stdout": normalized_stdout,
        "stderr": normalized_stderr,
        "error_signature": error_signature,
    }


def update_command_stats(command_key: str, ok: bool, ts: str) -> None:
    stats = read_stats()
    commands = stats.setdefault("commands", {})
    entry = commands.setdefault(command_key, {
        "success": 0,
        "failure": 0,
        "last_seen_at": None,
    })
    if ok:
        entry["success"] += 1
    else:
        entry["failure"] += 1
    entry["last_seen_at"] = ts
    write_stats(stats)


def update_error_signature_stats(signature: str, ts: str) -> None:
    if not signature:
        return
    stats = read_stats()
    signatures = stats.setdefault("error_signatures", {})
    entry = signatures.setdefault(signature, {
        "count": 0,
        "last_seen_at": None,
    })
    entry["count"] += 1
    entry["last_seen_at"] = ts
    write_stats(stats)


def _candidate_from_key(command_key: str, scope: str, cwd: str, success_count: int, last_seen_at: str | None) -> dict[str, Any]:
    return {
        "command": command_key,
        "scope": scope,
        "cwd": cwd if scope == "project" else "",
        "success_count": success_count,
        "last_seen_at": last_seen_at,
        "reason": "repeated low-risk successful command",
        "risk_level": "low",
        "suggested_permission": "allow",
    }


def collect_allow_candidates_from_events(events: list[dict[str, Any]], preferences: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    preferences = normalize_preferences(preferences or read_preferences())
    threshold = preferences["candidate_thresholds"].get("success_threshold_for_candidate", 3)

    global_counts: Counter[str] = Counter()
    global_last_seen: dict[str, str] = {}
    project_counts: Counter[tuple[str, str]] = Counter()
    project_last_seen: dict[tuple[str, str], str] = {}

    for raw_event in events:
        event = normalize_event_record(raw_event)
        if not event.get("ok"):
            continue
        command_key = event.get("command_prefix") or event.get("command")
        if not command_key or not is_low_risk_command(command_key):
            continue

        ts = event.get("ts")
        global_counts[command_key] += 1
        if isinstance(ts, str):
            global_last_seen[command_key] = ts

        cwd = normalize_scope_path(event.get("cwd", ""))
        if cwd:
            key = (command_key, cwd)
            project_counts[key] += 1
            if isinstance(ts, str):
                project_last_seen[key] = ts

    candidates: list[dict[str, Any]] = []
    for (command_key, cwd), success_count in project_counts.items():
        if success_count < threshold:
            continue
        candidates.append(_candidate_from_key(command_key, "project", cwd, success_count, project_last_seen.get((command_key, cwd))))

    for command_key, success_count in global_counts.items():
        if success_count < threshold:
            continue
        candidates.append(_candidate_from_key(command_key, "global", "", success_count, global_last_seen.get(command_key)))

    candidates.sort(key=lambda item: (item.get("scope") != "project", item.get("command", ""), item.get("cwd", "")))
    return candidates


def rebuild_preferences_from_events(events: list[dict[str, Any]], base_preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    preferences = normalize_preferences(base_preferences or read_preferences())
    preferences["always_allow_candidates"] = collect_allow_candidates_from_events(events, preferences)
    return preferences


def update_allow_candidate(command_key: str, cwd: str, ts: str) -> list[dict[str, Any]]:
    if not is_low_risk_command(command_key):
        return []

    preferences = rebuild_preferences_from_events(read_events(), read_preferences())
    write_preferences(preferences)
    candidates = []
    normalized_cwd = normalize_scope_path(cwd)
    for candidate in preferences.get("always_allow_candidates", []):
        if candidate.get("command") != command_key:
            continue
        if candidate.get("scope") == "project" and candidate.get("cwd") == normalized_cwd:
            candidates.append(candidate)
        elif candidate.get("scope") == "global":
            candidates.append(candidate)
    return candidates


def rebuild_stats_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    stats = {"version": 1, "commands": {}, "error_signatures": {}}

    for raw_event in events:
        event = normalize_event_record(raw_event)
        command_key = event.get("command_prefix") or event.get("command")
        ts = event.get("ts")
        if command_key:
            command_entry = stats["commands"].setdefault(command_key, {
                "success": 0,
                "failure": 0,
                "last_seen_at": None,
            })
            if event.get("ok"):
                command_entry["success"] += 1
            else:
                command_entry["failure"] += 1
            command_entry["last_seen_at"] = ts

        signature = event.get("error_signature")
        if signature:
            signature_entry = stats["error_signatures"].setdefault(signature, {
                "count": 0,
                "last_seen_at": None,
            })
            signature_entry["count"] += 1
            signature_entry["last_seen_at"] = ts

    return stats


def find_allow_candidates(command: str, cwd: str | None = None) -> list[dict[str, Any]]:
    command_key = command_prefix(command) or normalize_command(command)
    normalized_cwd = normalize_scope_path(cwd)
    if not command_key:
        return []

    candidates: list[dict[str, Any]] = []
    for candidate in read_preferences().get("always_allow_candidates", []):
        if candidate.get("command") != command_key:
            continue
        if candidate.get("scope") == "project" and candidate.get("cwd") == normalized_cwd:
            candidates.append(candidate)
        elif candidate.get("scope") == "global":
            candidates.append(candidate)

    candidates.sort(key=lambda item: (item.get("scope") != "project", -int(item.get("success_count", 0) or 0)))
    return candidates


def build_memory_summary() -> dict[str, Any]:
    ensure_memory_home()
    lessons = read_lessons()
    stats = read_stats()
    preferences = read_preferences()
    events = read_events()

    command_items = sorted(
        stats.get("commands", {}).items(),
        key=lambda item: (
            -(item[1].get("failure", 0) + item[1].get("success", 0)),
            item[0],
        ),
    )
    error_items = sorted(
        stats.get("error_signatures", {}).items(),
        key=lambda item: (-item[1].get("count", 0), item[0]),
    )

    return {
        "memory_home": str(MEMORY_HOME),
        "overview": {
            "events": len(events),
            "lessons": len(lessons),
            "allow_candidates": len(preferences.get("always_allow_candidates", [])),
            "commands_tracked": len(stats.get("commands", {})),
            "error_signatures_tracked": len(stats.get("error_signatures", {})),
        },
        "top_commands": [
            {
                "command": command,
                "success": detail.get("success", 0),
                "failure": detail.get("failure", 0),
                "last_seen_at": detail.get("last_seen_at"),
            }
            for command, detail in command_items[:5]
        ],
        "top_error_signatures": [
            {
                "error_signature": signature,
                "count": detail.get("count", 0),
                "last_seen_at": detail.get("last_seen_at"),
            }
            for signature, detail in error_items[:5]
        ],
        "lessons": [
            {
                "scope": lesson.get("scope", "global"),
                "cwd": lesson.get("cwd", ""),
                "command_prefix": lesson.get("pattern", {}).get("command_prefix", ""),
                "error_signature": lesson.get("pattern", {}).get("error_signature", ""),
                "failure_count": lesson.get("failure_count", 0),
                "advice": lesson.get("advice", ""),
            }
            for lesson in lessons[:5]
        ],
        "habits": {
            "project_candidates": [
                candidate
                for candidate in preferences.get("always_allow_candidates", [])
                if candidate.get("scope") == "project"
            ][:5],
            "global_candidates": [
                candidate
                for candidate in preferences.get("always_allow_candidates", [])
                if candidate.get("scope") == "global"
            ][:5],
        },
    }


def create_memory_backup() -> dict[str, str]:
    ensure_memory_home()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = MEMORY_HOME / f"backups/{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied: dict[str, str] = {}
    for path in (EVENTS_FILE, LESSONS_FILE, PREFERENCES_FILE, STATS_FILE):
        if not path.exists():
            continue
        destination = backup_dir / path.name
        shutil.copy2(path, destination)
        copied[path.name] = str(destination)
    return copied


def migrate_memory_store(dry_run: bool = False, backup: bool = False) -> dict[str, Any]:
    ensure_memory_home()

    original_events = read_events()
    original_stats = read_stats()
    original_preferences = read_preferences()
    original_lessons = read_lessons()

    events = [normalize_event_record(event) for event in original_events]
    stats = rebuild_stats_from_events(events)
    preferences = rebuild_preferences_from_events(events, original_preferences)

    summary = {
        "events": len(events),
        "lessons": 0,
        "candidates": len(preferences.get("always_allow_candidates", [])),
        "dry_run": dry_run,
        "backup_created": False,
        "backup_files": {},
    }

    if backup and not dry_run:
        backup_files = create_memory_backup()
        summary["backup_created"] = bool(backup_files)
        summary["backup_files"] = backup_files

    write_events(events)
    write_stats(stats)
    write_preferences(preferences)

    from scripts.lesson_engine import rebuild_lessons_from_events

    lessons = rebuild_lessons_from_events()
    summary["lessons"] = len(lessons)

    if dry_run:
        write_events(original_events)
        write_stats(original_stats)
        write_preferences(original_preferences)
        write_lessons(original_lessons)

    return summary
