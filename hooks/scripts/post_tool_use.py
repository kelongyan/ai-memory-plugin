from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[2]))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.lesson_engine import rebuild_lessons_from_events
from scripts.memory_store import (
    append_event,
    ensure_memory_home,
    update_allow_candidate,
    update_command_stats,
    update_error_signature_stats,
    utc_now_iso,
)
from scripts.sanitize import command_prefix, extract_error_signature, normalize_command, normalize_tool_result_text


def silent_response() -> dict:
    return {
        "continue": True,
        "suppressOutput": True,
    }


def emit_silent_response() -> None:
    sys.stdout.write(json.dumps(silent_response(), ensure_ascii=False))


def parse_result(tool_result: Any) -> tuple[bool, str, str, int | None]:
    stdout_text, stderr_text, return_code = normalize_tool_result_text(tool_result)
    if return_code is not None:
        return (return_code == 0, stdout_text, stderr_text, return_code)

    signature = extract_error_signature({"stderr": stderr_text}) if stderr_text else extract_error_signature(tool_result)
    ok = not bool(signature)
    return (ok, stdout_text if ok else "", stderr_text if not ok else "", None)


def main() -> int:
    ensure_memory_home()
    raw = sys.stdin.read().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    tool_input = payload.get("tool_input") or {}
    command = normalize_command(tool_input.get("command") or tool_input.get("cmd") or "")
    if not command:
        emit_silent_response()
        return 0

    tool_result = payload.get("tool_result")
    ok, stdout_text, stderr_text, return_code = parse_result(tool_result)
    ts = utc_now_iso()
    error_signature = extract_error_signature({"stderr": stderr_text}) if stderr_text else ""

    event = {
        "ts": ts,
        "tool": payload.get("tool_name", "Bash"),
        "hook_event": payload.get("hook_event_name", "PostToolUse"),
        "cwd": payload.get("cwd", ""),
        "session_id": payload.get("session_id", ""),
        "command": command,
        "command_prefix": command_prefix(command),
        "ok": ok,
        "return_code": return_code,
        "stdout": stdout_text[:1000],
        "stderr": stderr_text[:1000],
        "error_signature": error_signature,
    }

    append_event(event)
    prefix = event["command_prefix"] or command
    update_command_stats(prefix, ok, ts)
    candidate_matches = []
    if ok:
        candidate_matches = update_allow_candidate(prefix, event.get("cwd", ""), ts)
    if error_signature:
        update_error_signature_stats(error_signature, ts)
        rebuild_lessons_from_events()

    emit_silent_response()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        emit_silent_response()
        raise SystemExit(0)
