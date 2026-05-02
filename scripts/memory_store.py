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
    "approval_threshold_for_auto_allow": 6,
    "minimum_risk_level": "low",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_preferences() -> dict[str, Any]:
    return {
        "version": 2,
        "created_at": utc_now_iso(),
        "always_allow_candidates": [],
        "auto_allow_rules": [],
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
        "approved_count": max(int(candidate.get("approved_count", 0) or 0), 0),
        "last_seen_at": candidate.get("last_seen_at"),
        "reason": candidate.get("reason") or "repeated low-risk successful command",
        "risk_level": candidate.get("risk_level") or "low",
        "suggested_permission": candidate.get("suggested_permission") or "allow",
        "source": candidate.get("source") or "derived_from_events",
        "enabled": bool(candidate.get("enabled", True)),
    }


def normalize_auto_allow_rule(rule: Any) -> dict[str, Any] | None:
    candidate = normalize_candidate(rule)
    if not candidate:
        return None
    candidate["success_count"] = max(int(rule.get("success_count", candidate.get("success_count", 0)) or 0), 0)
    candidate["approved_count"] = max(int(rule.get("approved_count", candidate.get("approved_count", 0)) or 0), 0)
    candidate["reason"] = rule.get("reason") or "repeated allowed low-risk command"
    candidate["source"] = rule.get("source") or "promoted_from_history"
    candidate["enabled"] = bool(rule.get("enabled", True))
    return candidate


def normalize_never_allow_rule(rule: Any) -> dict[str, Any] | None:
    candidate = normalize_candidate(rule)
    if not candidate:
        return None
    candidate["reason"] = rule.get("reason") or "manually revoked auto allow rule"
    candidate["created_at"] = rule.get("created_at") or utc_now_iso()
    candidate["enabled"] = True
    return candidate


def _candidate_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (item.get("command", ""), item.get("scope", "global"), item.get("cwd", ""))


def _normalize_command_scope(command: str, cwd: str | None = None) -> tuple[str, str, str]:
    command_key = command_prefix(command) or normalize_command(command)
    normalized_cwd = normalize_scope_path(cwd)
    scope = "project" if normalized_cwd else "global"
    return (command_key, scope, normalized_cwd if scope == "project" else "")


def _rule_matches(command: str, cwd: str | None, item: dict[str, Any], all_matching: bool = False) -> bool:
    command_key, scope, normalized_cwd = _normalize_command_scope(command, cwd)
    if item.get("command") != command_key:
        return False
    if all_matching:
        return item.get("scope") == "project"
    if item.get("scope") != scope:
        return False
    if scope == "project":
        return item.get("cwd") == normalized_cwd
    return True


def _is_never_allowed(command_key: str, scope: str, cwd: str, rules: list[dict[str, Any]]) -> bool:
    for rule in rules:
        if rule.get("command") != command_key:
            continue
        if rule.get("scope") != scope:
            continue
        if scope == "project" and rule.get("cwd") != cwd:
            continue
        return True
    return False


def normalize_preferences(data: Any) -> dict[str, Any]:
    defaults = default_preferences()
    if not isinstance(data, dict):
        return defaults

    candidates: list[dict[str, Any]] = []
    seen_candidate_keys: set[tuple[str, str, str]] = set()
    for raw_candidate in data.get("always_allow_candidates", []):
        candidate = normalize_candidate(raw_candidate)
        if not candidate:
            continue
        key = _candidate_key(candidate)
        if key in seen_candidate_keys:
            continue
        seen_candidate_keys.add(key)
        candidates.append(candidate)

    auto_allow_rules: list[dict[str, Any]] = []
    seen_rule_keys: set[tuple[str, str, str]] = set()
    for raw_rule in data.get("auto_allow_rules", []):
        rule = normalize_auto_allow_rule(raw_rule)
        if not rule:
            continue
        key = _candidate_key(rule)
        if key in seen_rule_keys:
            continue
        seen_rule_keys.add(key)
        auto_allow_rules.append(rule)

    never_allow_rules: list[dict[str, Any]] = []
    seen_never_allow_keys: set[tuple[str, str, str]] = set()
    for raw_rule in data.get("never_allow", []):
        rule = normalize_never_allow_rule(raw_rule)
        if not rule:
            continue
        key = _candidate_key(rule)
        if key in seen_never_allow_keys:
            continue
        seen_never_allow_keys.add(key)
        never_allow_rules.append(rule)

    candidates.sort(key=lambda item: (item.get("scope") != "project", item.get("command", ""), item.get("cwd", "")))
    auto_allow_rules.sort(key=lambda item: (item.get("scope") != "project", item.get("command", ""), item.get("cwd", "")))
    never_allow_rules.sort(key=lambda item: (item.get("scope") != "project", item.get("command", ""), item.get("cwd", "")))

    normalized = {
        "version": max(int(data.get("version", defaults["version"]) or defaults["version"]), defaults["version"]),
        "created_at": data.get("created_at") or defaults["created_at"],
        "always_allow_candidates": candidates,
        "auto_allow_rules": auto_allow_rules,
        "never_allow": never_allow_rules,
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


def _candidate_from_key(command_key: str, scope: str, cwd: str, success_count: int, approved_count: int, last_seen_at: str | None) -> dict[str, Any]:
    return {
        "command": command_key,
        "scope": scope,
        "cwd": cwd if scope == "project" else "",
        "success_count": success_count,
        "approved_count": approved_count,
        "last_seen_at": last_seen_at,
        "reason": "repeated low-risk successful command",
        "risk_level": "low",
        "suggested_permission": "allow",
        "source": "derived_from_events",
        "enabled": True,
    }


def _auto_allow_rule_from_key(command_key: str, cwd: str, approved_count: int, success_count: int, last_seen_at: str | None) -> dict[str, Any]:
    return {
        "command": command_key,
        "scope": "project",
        "cwd": cwd,
        "success_count": success_count,
        "approved_count": approved_count,
        "last_seen_at": last_seen_at,
        "reason": "repeated allowed low-risk command",
        "risk_level": "low",
        "suggested_permission": "allow",
        "source": "promoted_from_history",
        "enabled": True,
    }


def collect_allow_candidates_from_events(events: list[dict[str, Any]], preferences: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    preferences = normalize_preferences(preferences or read_preferences())
    threshold = preferences["candidate_thresholds"].get("success_threshold_for_candidate", 3)
    never_allow_rules = preferences.get("never_allow", [])

    global_success_counts: Counter[str] = Counter()
    global_approval_counts: Counter[str] = Counter()
    global_last_seen: dict[str, str] = {}
    project_success_counts: Counter[tuple[str, str]] = Counter()
    project_approval_counts: Counter[tuple[str, str]] = Counter()
    project_last_seen: dict[tuple[str, str], str] = {}

    for raw_event in events:
        event = normalize_event_record(raw_event)
        command_key = event.get("command_prefix") or event.get("command")
        if not command_key or not is_low_risk_command(command_key):
            continue

        if _is_never_allowed(command_key, "global", "", never_allow_rules):
            continue

        ts = event.get("ts")
        global_approval_counts[command_key] += 1
        if event.get("ok"):
            global_success_counts[command_key] += 1
        if isinstance(ts, str):
            global_last_seen[command_key] = ts

        cwd = normalize_scope_path(event.get("cwd", ""))
        if cwd:
            if _is_never_allowed(command_key, "project", cwd, never_allow_rules):
                continue
            key = (command_key, cwd)
            project_approval_counts[key] += 1
            if event.get("ok"):
                project_success_counts[key] += 1
            if isinstance(ts, str):
                project_last_seen[key] = ts

    candidates: list[dict[str, Any]] = []
    for (command_key, cwd), success_count in project_success_counts.items():
        if success_count < threshold:
            continue
        candidates.append(_candidate_from_key(
            command_key,
            "project",
            cwd,
            success_count,
            project_approval_counts.get((command_key, cwd), success_count),
            project_last_seen.get((command_key, cwd)),
        ))

    for command_key, success_count in global_success_counts.items():
        if success_count < threshold:
            continue
        candidates.append(_candidate_from_key(
            command_key,
            "global",
            "",
            success_count,
            global_approval_counts.get(command_key, success_count),
            global_last_seen.get(command_key),
        ))

    candidates.sort(key=lambda item: (item.get("scope") != "project", item.get("command", ""), item.get("cwd", "")))
    return candidates


def collect_auto_allow_rules_from_events(events: list[dict[str, Any]], preferences: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    preferences = normalize_preferences(preferences or read_preferences())
    threshold = preferences["candidate_thresholds"].get("approval_threshold_for_auto_allow", 6)
    never_allow_rules = preferences.get("never_allow", [])

    project_approval_counts: Counter[tuple[str, str]] = Counter()
    project_success_counts: Counter[tuple[str, str]] = Counter()
    project_last_seen: dict[tuple[str, str], str] = {}

    for raw_event in events:
        event = normalize_event_record(raw_event)
        command_key = event.get("command_prefix") or event.get("command")
        cwd = normalize_scope_path(event.get("cwd", ""))
        if not command_key or not cwd or not is_low_risk_command(command_key):
            continue
        if _is_never_allowed(command_key, "project", cwd, never_allow_rules):
            continue

        key = (command_key, cwd)
        project_approval_counts[key] += 1
        if event.get("ok"):
            project_success_counts[key] += 1
        ts = event.get("ts")
        if isinstance(ts, str):
            project_last_seen[key] = ts

    rules: list[dict[str, Any]] = []
    for (command_key, cwd), approved_count in project_approval_counts.items():
        if approved_count < threshold:
            continue
        rules.append(_auto_allow_rule_from_key(
            command_key,
            cwd,
            approved_count,
            project_success_counts.get((command_key, cwd), 0),
            project_last_seen.get((command_key, cwd)),
        ))

    rules.sort(key=lambda item: (item.get("command", ""), item.get("cwd", "")))
    return rules


def rebuild_preferences_from_events(events: list[dict[str, Any]], base_preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    preferences = normalize_preferences(base_preferences or read_preferences())
    preferences["always_allow_candidates"] = collect_allow_candidates_from_events(events, preferences)
    preferences["auto_allow_rules"] = collect_auto_allow_rules_from_events(events, preferences)
    return preferences


def _matching_candidates(items: list[dict[str, Any]], command_key: str, normalized_cwd: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in items:
        if item.get("command") != command_key:
            continue
        if item.get("scope") == "project" and item.get("cwd") == normalized_cwd:
            matches.append(item)
        elif item.get("scope") == "global":
            matches.append(item)
    return matches


def update_allow_candidates_and_auto_rules(command_key: str, cwd: str, ts: str) -> dict[str, Any]:
    if not is_low_risk_command(command_key):
        return {
            "candidates": [],
            "auto_allow_rules": [],
            "promoted_rules": [],
            "preferences": read_preferences(),
            "last_seen_at": ts,
        }

    previous_preferences = read_preferences()
    previous_rules = _matching_candidates(previous_preferences.get("auto_allow_rules", []), command_key, normalize_scope_path(cwd))
    previous_rule_keys = {_candidate_key(item) for item in previous_rules}

    preferences = rebuild_preferences_from_events(read_events(), previous_preferences)
    write_preferences(preferences)

    normalized_cwd = normalize_scope_path(cwd)
    candidates = _matching_candidates(preferences.get("always_allow_candidates", []), command_key, normalized_cwd)
    auto_allow_rules = _matching_candidates(preferences.get("auto_allow_rules", []), command_key, normalized_cwd)
    promoted_rules = [rule for rule in auto_allow_rules if _candidate_key(rule) not in previous_rule_keys]

    return {
        "candidates": candidates,
        "auto_allow_rules": auto_allow_rules,
        "promoted_rules": promoted_rules,
        "preferences": preferences,
        "last_seen_at": ts,
    }


def add_never_allow_rule(command: str, cwd: str | None = None, reason: str = "manually revoked auto allow rule") -> dict[str, Any]:
    preferences = read_preferences()
    rules = list(preferences.get("never_allow", []))
    normalized_rule = normalize_never_allow_rule({
        "command": command,
        "cwd": cwd or "",
        "reason": reason,
        "created_at": utc_now_iso(),
    })
    if not normalized_rule:
        return {"added": False, "rule": None}

    rule_key = _candidate_key(normalized_rule)
    for existing in rules:
        if _candidate_key(existing) == rule_key:
            return {"added": False, "rule": existing}

    rules.append(normalized_rule)
    preferences["never_allow"] = rules
    write_preferences(preferences)
    return {"added": True, "rule": normalized_rule}


def remove_auto_allow_rules(command: str, cwd: str | None = None, all_matching: bool = False) -> dict[str, Any]:
    preferences = read_preferences()
    current_rules = preferences.get("auto_allow_rules", [])
    removed_rules = [rule for rule in current_rules if _rule_matches(command, cwd, rule, all_matching=all_matching)]
    kept_rules = [rule for rule in current_rules if not _rule_matches(command, cwd, rule, all_matching=all_matching)]
    preferences["auto_allow_rules"] = kept_rules
    write_preferences(preferences)
    return {
        "removed": len(removed_rules),
        "removed_rules": removed_rules,
    }


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

    candidates = _matching_candidates(read_preferences().get("always_allow_candidates", []), command_key, normalized_cwd)
    candidates.sort(key=lambda item: (item.get("scope") != "project", -int(item.get("success_count", 0) or 0)))
    return candidates


def find_auto_allow_rules(command: str, cwd: str | None = None) -> list[dict[str, Any]]:
    command_key = command_prefix(command) or normalize_command(command)
    normalized_cwd = normalize_scope_path(cwd)
    if not command_key:
        return []

    rules = _matching_candidates(read_preferences().get("auto_allow_rules", []), command_key, normalized_cwd)
    rules = [rule for rule in rules if rule.get("enabled", True)]
    rules.sort(key=lambda item: (item.get("scope") != "project", -int(item.get("approved_count", 0) or 0)))
    return rules


def find_auto_allow_match(command: str, cwd: str | None = None) -> dict[str, Any] | None:
    rules = find_auto_allow_rules(command, cwd)
    return rules[0] if rules else None


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
            "auto_allow_rules": len(preferences.get("auto_allow_rules", [])),
            "never_allow_rules": len(preferences.get("never_allow", [])),
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
            "auto_allow_project_rules": [
                rule
                for rule in preferences.get("auto_allow_rules", [])
                if rule.get("scope") == "project"
            ][:5],
            "never_allow_rules": preferences.get("never_allow", [])[:5],
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
    preferences["never_allow"] = original_preferences.get("never_allow", [])

    summary = {
        "events": len(events),
        "lessons": 0,
        "candidates": len(preferences.get("always_allow_candidates", [])),
        "auto_allow_rules": len(preferences.get("auto_allow_rules", [])),
        "never_allow_rules": len(preferences.get("never_allow", [])),
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
