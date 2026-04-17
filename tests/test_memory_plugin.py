from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lesson_engine import find_relevant_lessons
from scripts.memory_store import (
    build_memory_summary,
    ensure_memory_home,
    migrate_memory_store,
    read_events,
    read_lessons,
    read_preferences,
    read_stats,
    write_events,
    write_json,
    write_lessons,
)
from scripts.sanitize import (
    command_prefix,
    compact_error_text,
    extract_error_signature,
    is_low_risk_command,
    normalize_command,
    normalize_error_signature,
    normalize_scope_path,
    redact_secrets,
    sanitize_path,
)


class MemoryPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_home = tempfile.TemporaryDirectory()
        self.original_home = os.environ.get("HOME")
        self.original_userprofile = os.environ.get("USERPROFILE")
        os.environ["HOME"] = self.temp_home.name
        os.environ["USERPROFILE"] = self.temp_home.name

        from scripts import memory_store
        memory_store.MEMORY_HOME = Path(self.temp_home.name) / ".ai-memory"
        memory_store.EVENTS_FILE = memory_store.MEMORY_HOME / "events.jsonl"
        memory_store.LESSONS_FILE = memory_store.MEMORY_HOME / "lessons.json"
        memory_store.PREFERENCES_FILE = memory_store.MEMORY_HOME / "preferences.json"
        memory_store.STATS_FILE = memory_store.MEMORY_HOME / "stats.json"
        self.memory_home = memory_store.MEMORY_HOME
        self.events_file = memory_store.EVENTS_FILE
        self.lessons_file = memory_store.LESSONS_FILE
        self.preferences_file = memory_store.PREFERENCES_FILE
        self.stats_file = memory_store.STATS_FILE

        ensure_memory_home()

    def tearDown(self) -> None:
        if self.original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.original_home

        if self.original_userprofile is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = self.original_userprofile

        self.temp_home.cleanup()

    def test_ensure_memory_home_creates_expected_files(self) -> None:
        self.assertTrue(self.memory_home.exists())
        self.assertTrue(self.events_file.exists())
        self.assertTrue(self.lessons_file.exists())
        self.assertTrue(self.preferences_file.exists())
        self.assertTrue(self.stats_file.exists())
        preferences = read_preferences()
        self.assertEqual(preferences["candidate_thresholds"]["success_threshold_for_candidate"], 3)

    def test_sanitize_helpers(self) -> None:
        self.assertEqual(normalize_command("  npm   test  "), "npm test")
        self.assertEqual(command_prefix("npm test -- --watch"), "npm test")
        self.assertEqual(command_prefix("npm run test -- --watch"), "npm run test")
        self.assertIn("***", redact_secrets("Authorization=Bearer secret-token"))
        self.assertIn("...", sanitize_path("C:/Users/Administrator/very/secret/file.txt"))
        self.assertEqual(compact_error_text("\nerror here\nnext line\n"), "error here | next line")
        self.assertTrue(is_low_risk_command("git status"))
        self.assertFalse(is_low_risk_command("npm install"))
        self.assertEqual(normalize_scope_path("C:/Work/Demo/"), "c:/work/demo")

    def test_normalize_error_signature_collapses_equivalent_errors(self) -> None:
        first = "'jest' is not recognized as an internal or external command, operable program or batch file."
        second = "/bin/sh: jest: command not found"
        self.assertEqual(normalize_error_signature(first), "command not found: jest")
        self.assertEqual(normalize_error_signature(second), "command not found: jest")
        self.assertEqual(
            normalize_error_signature("ModuleNotFoundError: No module named 'dotenv'"),
            "module not found: dotenv",
        )
        self.assertEqual(extract_error_signature({"stderr": "Permission denied: /root/app"}), "permission denied")

    def test_rebuild_lessons_from_repeated_failures(self) -> None:
        payload = {
            "session_id": "session-1",
            "hook_event_name": "PostToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "tool_result": {"return_code": 1, "stdout": "", "stderr": "jest: command not found"},
        }
        self.run_hook("post_tool_use.py", payload)
        self.run_hook("post_tool_use.py", payload)

        lessons = read_lessons()
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["pattern"]["command_prefix"], "npm test")
        self.assertEqual(lessons[0]["pattern"]["error_signature"], "command not found: jest")

        matched = find_relevant_lessons("npm test", "C:/work/demo")
        self.assertEqual(len(matched), 1)

    def test_post_tool_use_updates_stats(self) -> None:
        payload = {
            "session_id": "session-1",
            "hook_event_name": "PostToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_result": {"return_code": 0, "stdout": "On branch main", "stderr": ""},
        }
        self.run_hook("post_tool_use.py", payload)
        stats = read_stats()
        self.assertEqual(stats["commands"]["git status"]["success"], 1)
        events = read_events()
        self.assertEqual(events[0]["ok"], True)

    def test_successful_low_risk_command_becomes_allow_candidate(self) -> None:
        payload = {
            "session_id": "session-1",
            "hook_event_name": "PostToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_result": {"return_code": 0, "stdout": "On branch main", "stderr": ""},
        }
        self.run_hook("post_tool_use.py", payload)
        self.run_hook("post_tool_use.py", payload)
        output = self.run_hook("post_tool_use.py", payload)

        preferences = read_preferences()
        self.assertEqual(len(preferences["always_allow_candidates"]), 2)
        project_candidate = preferences["always_allow_candidates"][0]
        global_candidate = preferences["always_allow_candidates"][1]
        self.assertEqual(project_candidate["command"], "git status")
        self.assertEqual(project_candidate["scope"], "project")
        self.assertEqual(project_candidate["cwd"], "c:/work/demo")
        self.assertEqual(project_candidate["success_count"], 3)
        self.assertEqual(project_candidate["suggested_permission"], "allow")
        self.assertEqual(global_candidate["scope"], "global")
        self.assertEqual(global_candidate["success_count"], 3)
        parsed = json.loads(output)
        self.assertTrue(parsed["suppressOutput"])

    def test_migrate_memory_store_normalizes_legacy_history(self) -> None:
        legacy_events = [
            {
                "ts": "2026-04-17T00:00:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "npm test -- --watch",
                "command_prefix": "npm test",
                "ok": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "jest: command not found",
                "error_signature": "jest: command not found",
            },
            {
                "ts": "2026-04-17T00:01:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "npm test",
                "command_prefix": "npm test",
                "ok": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "'jest' is not recognized as an internal or external command, operable program or batch file.",
                "error_signature": "'jest' is not recognized as an internal or external command, operable program or batch file.",
            },
        ]
        write_events(legacy_events)
        write_json(self.preferences_file, {"version": 1, "created_at": "2026-04-17T00:00:00+00:00"})

        summary = migrate_memory_store()

        self.assertEqual(summary["events"], 2)
        events = read_events()
        self.assertEqual(events[0]["cwd"], "c:/work/demo")
        self.assertEqual(events[0]["error_signature"], "command not found: jest")
        self.assertEqual(events[1]["error_signature"], "command not found: jest")

        stats = read_stats()
        self.assertEqual(stats["commands"]["npm test"]["failure"], 2)
        self.assertEqual(stats["error_signatures"]["command not found: jest"]["count"], 2)

        lessons = read_lessons()
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["pattern"]["error_signature"], "command not found: jest")

        preferences = read_preferences()
        self.assertIn("candidate_thresholds", preferences)
        self.assertEqual(preferences["always_allow_candidates"], [])

    def test_migrate_memory_store_rebuilds_project_and_global_candidates(self) -> None:
        successful_events = [
            {
                "ts": "2026-04-17T00:00:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "git status",
                "ok": True,
                "return_code": 0,
                "stdout": "On branch main",
                "stderr": "",
            },
            {
                "ts": "2026-04-17T00:01:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "git status",
                "ok": True,
                "return_code": 0,
                "stdout": "On branch main",
                "stderr": "",
            },
            {
                "ts": "2026-04-17T00:02:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "git status",
                "ok": True,
                "return_code": 0,
                "stdout": "On branch main",
                "stderr": "",
            },
            {
                "ts": "2026-04-17T00:03:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Other",
                "session_id": "session-1",
                "command": "git status",
                "ok": True,
                "return_code": 0,
                "stdout": "On branch main",
                "stderr": "",
            },
        ]
        write_events(successful_events)

        migrate_memory_store()
        preferences = read_preferences()
        candidates = preferences["always_allow_candidates"]

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["scope"], "project")
        self.assertEqual(candidates[0]["cwd"], "c:/work/demo")
        self.assertEqual(candidates[0]["success_count"], 3)
        self.assertEqual(candidates[1]["scope"], "global")
        self.assertEqual(candidates[1]["success_count"], 4)

    def test_memory_summary_contains_lessons_and_habits(self) -> None:
        write_lessons([
            {
                "id": "lesson-project",
                "scope": "project",
                "cwd": "c:/work/demo",
                "match_scope_priority": 2,
                "pattern": {"command_prefix": "npm test", "error_signature": "command not found: jest"},
                "advice": "project advice",
                "confidence": 0.8,
                "failure_count": 3,
            }
        ])
        write_json(self.stats_file, {
            "version": 1,
            "commands": {
                "git status": {"success": 4, "failure": 0, "last_seen_at": "2026-04-17T00:03:00+00:00"},
                "npm test": {"success": 0, "failure": 3, "last_seen_at": "2026-04-17T00:02:00+00:00"},
            },
            "error_signatures": {
                "command not found: jest": {"count": 3, "last_seen_at": "2026-04-17T00:02:00+00:00"},
            },
        })
        write_json(self.preferences_file, {
            "version": 1,
            "created_at": "2026-04-17T00:00:00+00:00",
            "always_allow_candidates": [
                {
                    "command": "git status",
                    "scope": "project",
                    "cwd": "c:/work/demo",
                    "success_count": 3,
                    "last_seen_at": "2026-04-17T00:02:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                },
                {
                    "command": "git status",
                    "scope": "global",
                    "cwd": "",
                    "success_count": 4,
                    "last_seen_at": "2026-04-17T00:03:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                },
            ],
        })
        write_events([
            {
                "ts": "2026-04-17T00:03:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "c:/work/demo",
                "session_id": "session-1",
                "command": "git status",
                "command_prefix": "git status",
                "ok": True,
                "return_code": 0,
                "stdout": "On branch main",
                "stderr": "",
                "error_signature": "",
            }
        ])

        summary = build_memory_summary()

        self.assertEqual(summary["overview"]["events"], 1)
        self.assertEqual(summary["overview"]["lessons"], 1)
        self.assertEqual(summary["overview"]["allow_candidates"], 2)
        self.assertEqual(summary["top_commands"][0]["command"], "git status")
        self.assertEqual(summary["top_error_signatures"][0]["error_signature"], "command not found: jest")
        self.assertEqual(summary["lessons"][0]["command_prefix"], "npm test")
        self.assertEqual(summary["habits"]["project_candidates"][0]["scope"], "project")
        self.assertEqual(summary["habits"]["global_candidates"][0]["scope"], "global")

    def test_memory_summary_script_outputs_json(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--json"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertIn("overview", parsed)
        self.assertIn("habits", parsed)

    def test_memory_summary_script_defaults_to_json(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertIn("overview", parsed)
        self.assertIn("habits", parsed)

    def test_memory_summary_script_outputs_pretty_text(self) -> None:
        write_json(self.stats_file, {
            "version": 1,
            "commands": {
                "git status": {"success": 2, "failure": 0, "last_seen_at": "2026-04-17T00:03:00+00:00"},
            },
            "error_signatures": {},
        })
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--pretty"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        self.assertIn("ai-memory summary", process.stdout)
        self.assertIn("Top commands", process.stdout)
        self.assertIn("git status", process.stdout)

    def test_memory_summary_script_supports_limit_in_json_mode(self) -> None:
        write_json(self.stats_file, {
            "version": 1,
            "commands": {
                "git status": {"success": 4, "failure": 0, "last_seen_at": "2026-04-17T00:03:00+00:00"},
                "npm test": {"success": 0, "failure": 3, "last_seen_at": "2026-04-17T00:02:00+00:00"},
            },
            "error_signatures": {
                "command not found: jest": {"count": 3, "last_seen_at": "2026-04-17T00:02:00+00:00"},
                "permission denied": {"count": 1, "last_seen_at": "2026-04-17T00:04:00+00:00"},
            },
        })
        write_lessons([
            {
                "id": "lesson-a",
                "scope": "project",
                "cwd": "c:/work/demo",
                "match_scope_priority": 2,
                "pattern": {"command_prefix": "npm test", "error_signature": "command not found: jest"},
                "advice": "a",
                "confidence": 0.8,
                "failure_count": 3,
            },
            {
                "id": "lesson-b",
                "scope": "global",
                "cwd": "",
                "match_scope_priority": 1,
                "pattern": {"command_prefix": "npm install", "error_signature": "permission denied"},
                "advice": "b",
                "confidence": 0.6,
                "failure_count": 2,
            },
        ])
        write_json(self.preferences_file, {
            "version": 1,
            "created_at": "2026-04-17T00:00:00+00:00",
            "always_allow_candidates": [
                {
                    "command": "git status",
                    "scope": "project",
                    "cwd": "c:/work/demo",
                    "success_count": 3,
                    "last_seen_at": "2026-04-17T00:02:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                },
                {
                    "command": "git diff",
                    "scope": "global",
                    "cwd": "",
                    "success_count": 4,
                    "last_seen_at": "2026-04-17T00:03:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                },
            ],
        })
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--json", "--limit", "1"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertEqual(len(parsed["top_commands"]), 1)
        self.assertEqual(len(parsed["top_error_signatures"]), 1)
        self.assertEqual(len(parsed["lessons"]), 1)
        self.assertEqual(len(parsed["habits"]["project_candidates"]), 1)
        self.assertEqual(len(parsed["habits"]["global_candidates"]), 1)

    def test_memory_summary_script_supports_only_filter(self) -> None:
        write_json(self.stats_file, {
            "version": 1,
            "commands": {
                "git status": {"success": 2, "failure": 0, "last_seen_at": "2026-04-17T00:03:00+00:00"},
            },
            "error_signatures": {},
        })
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--json", "--only", "commands"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertIn("top_commands", parsed)
        self.assertNotIn("overview", parsed)
        self.assertNotIn("habits", parsed)

    def test_memory_summary_script_supports_only_filter_in_pretty_mode(self) -> None:
        write_json(self.stats_file, {
            "version": 1,
            "commands": {
                "git status": {"success": 2, "failure": 0, "last_seen_at": "2026-04-17T00:03:00+00:00"},
            },
            "error_signatures": {},
        })
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--pretty", "--only", "commands"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        self.assertIn("Top commands", process.stdout)
        self.assertIn("git status", process.stdout)
        self.assertNotIn("Overview", process.stdout)
        self.assertNotIn("Global habits", process.stdout)

    def test_memory_summary_script_rejects_invalid_limit(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--json", "--limit", "0"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
        )

        self.assertNotEqual(process.returncode, 0)
        self.assertIn("--limit requires a positive integer", process.stderr)

    def test_memory_summary_script_rejects_invalid_only(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "memory_summary.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--json", "--only", "unknown"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
        )

        self.assertNotEqual(process.returncode, 0)
        self.assertIn("--only requires", process.stderr)

    def test_migrate_memory_script_outputs_summary(self) -> None:
        legacy_events = [
            {
                "ts": "2026-04-17T00:00:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "npm test",
                "ok": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "jest: command not found",
            },
            {
                "ts": "2026-04-17T00:01:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "npm test",
                "ok": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "'jest' is not recognized as an internal or external command, operable program or batch file.",
            },
        ]
        write_events(legacy_events)

        script_path = PROJECT_ROOT / "scripts" / "migrate_memory.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertEqual(parsed["ok"], True)
        self.assertEqual(parsed["summary"]["events"], 2)
        self.assertEqual(parsed["summary"]["lessons"], 1)
        self.assertEqual(parsed["summary"]["dry_run"], False)
        self.assertEqual(parsed["summary"]["backup_created"], False)

    def test_migrate_memory_script_supports_dry_run(self) -> None:
        legacy_events = [
            {
                "ts": "2026-04-17T00:00:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "npm test",
                "ok": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "jest: command not found",
                "error_signature": "jest: command not found",
            }
        ]
        write_events(legacy_events)

        script_path = PROJECT_ROOT / "scripts" / "migrate_memory.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--dry-run"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertEqual(parsed["summary"]["dry_run"], True)
        events = read_events()
        self.assertEqual(events[0]["error_signature"], "jest: command not found")

    def test_migrate_memory_script_supports_backup(self) -> None:
        legacy_events = [
            {
                "ts": "2026-04-17T00:00:00+00:00",
                "tool": "Bash",
                "hook_event": "PostToolUse",
                "cwd": "C:/Work/Demo",
                "session_id": "session-1",
                "command": "npm test",
                "ok": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "jest: command not found",
            }
        ]
        write_events(legacy_events)

        script_path = PROJECT_ROOT / "scripts" / "migrate_memory.py"
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path), "--backup"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )

        parsed = json.loads(process.stdout)
        self.assertEqual(parsed["summary"]["backup_created"], True)
        self.assertIn("events.jsonl", parsed["summary"]["backup_files"])

    def test_pre_tool_use_surfaces_habit_candidate_message(self) -> None:
        write_json(self.preferences_file, {
            "version": 1,
            "created_at": "2026-04-17T00:00:00+00:00",
            "always_allow_candidates": [
                {
                    "command": "git status",
                    "scope": "project",
                    "cwd": "c:/work/demo",
                    "success_count": 3,
                    "last_seen_at": "2026-04-17T00:02:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                }
            ],
        })

        output = self.run_hook("pre_tool_use.py", {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        })
        parsed = json.loads(output)
        self.assertTrue(parsed["suppressOutput"])

    def test_pre_tool_use_surfaces_failure_and_habit_messages_together(self) -> None:
        write_lessons([
            {
                "id": "lesson-project",
                "scope": "project",
                "cwd": "c:/work/demo",
                "match_scope_priority": 2,
                "pattern": {"command_prefix": "npm test", "error_signature": "command not found: jest"},
                "advice": "project advice",
                "confidence": 0.8,
                "failure_count": 3,
            }
        ])
        write_json(self.preferences_file, {
            "version": 1,
            "created_at": "2026-04-17T00:00:00+00:00",
            "always_allow_candidates": [
                {
                    "command": "npm test",
                    "scope": "project",
                    "cwd": "c:/work/demo",
                    "success_count": 3,
                    "last_seen_at": "2026-04-17T00:02:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                }
            ],
        })

        output = self.run_hook("pre_tool_use.py", {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
        })
        parsed = json.loads(output)
        self.assertIn("历史失败模式", parsed["systemMessage"])
        self.assertNotIn("历史成功习惯", parsed["systemMessage"])

    def test_pre_tool_use_prefers_project_lesson_over_global(self) -> None:
        write_lessons([
            {
                "id": "lesson-global",
                "scope": "global",
                "cwd": "",
                "match_scope_priority": 1,
                "pattern": {"command_prefix": "npm test", "error_signature": "command not found: jest"},
                "advice": "global advice",
                "confidence": 0.95,
                "failure_count": 10,
            },
            {
                "id": "lesson-project",
                "scope": "project",
                "cwd": "c:/work/demo",
                "match_scope_priority": 2,
                "pattern": {"command_prefix": "npm test", "error_signature": "command not found: jest"},
                "advice": "project advice",
                "confidence": 0.6,
                "failure_count": 2,
            },
        ])

        matched = find_relevant_lessons("npm test -- --watch", "C:/work/demo")
        self.assertEqual(matched[0]["scope"], "project")
        self.assertEqual(matched[0]["advice"], "project advice")

        output = self.run_hook("pre_tool_use.py", {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test -- --watch"},
        })
        parsed = json.loads(output)
        self.assertIn("scope: project", parsed["systemMessage"])

    def test_pre_tool_use_surfaces_matching_lesson(self) -> None:
        payload = {
            "session_id": "session-1",
            "hook_event_name": "PostToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "tool_result": {
                "return_code": 1,
                "stdout": "",
                "stderr": "'jest' is not recognized as an internal or external command, operable program or batch file.",
            },
        }
        self.run_hook("post_tool_use.py", payload)
        self.run_hook("post_tool_use.py", payload)

        output = self.run_hook("pre_tool_use.py", {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
        })
        parsed = json.loads(output)
        self.assertIn("ai-memory 提醒", parsed["systemMessage"])
        self.assertIn("scope: project", parsed["systemMessage"])

    def test_pre_tool_use_surfaces_only_high_value_habit(self) -> None:
        write_json(self.preferences_file, {
            "version": 1,
            "created_at": "2026-04-17T00:00:00+00:00",
            "always_allow_candidates": [
                {
                    "command": "git status",
                    "scope": "project",
                    "cwd": "c:/work/demo",
                    "success_count": 5,
                    "last_seen_at": "2026-04-17T00:02:00+00:00",
                    "reason": "repeated low-risk successful command",
                    "risk_level": "low",
                    "suggested_permission": "allow",
                }
            ],
        })

        output = self.run_hook("pre_tool_use.py", {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        })
        parsed = json.loads(output)
        self.assertIn("命中历史成功习惯", parsed["systemMessage"])
        self.assertIn("success_count: 5", parsed["systemMessage"])

    def test_pre_tool_use_keeps_low_value_failure_silent(self) -> None:
        write_lessons([
            {
                "id": "lesson-global",
                "scope": "global",
                "cwd": "",
                "match_scope_priority": 1,
                "pattern": {"command_prefix": "npm test", "error_signature": "command not found: jest"},
                "advice": "global advice",
                "confidence": 0.65,
                "failure_count": 2,
            }
        ])

        output = self.run_hook("pre_tool_use.py", {
            "session_id": "session-1",
            "hook_event_name": "PreToolUse",
            "cwd": "C:/other/project",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
        })
        parsed = json.loads(output)
        self.assertTrue(parsed["suppressOutput"])

    def test_session_start_is_silent(self) -> None:
        output = self.run_hook("session_start.py", {
            "session_id": "session-1",
            "hook_event_name": "SessionStart",
            "cwd": "C:/work/demo",
        })
        parsed = json.loads(output)
        self.assertTrue(parsed["continue"])
        self.assertTrue(parsed["suppressOutput"])

    def test_hooks_fail_open_on_invalid_json(self) -> None:
        for script_name in ("session_start.py", "pre_tool_use.py", "post_tool_use.py"):
            script_path = PROJECT_ROOT / "hooks" / "scripts" / script_name
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
            env["HOME"] = self.temp_home.name
            env["USERPROFILE"] = self.temp_home.name
            process = subprocess.run(
                [sys.executable, str(script_path)],
                input="{invalid json",
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=True,
            )
            parsed = json.loads(process.stdout.strip())
            self.assertTrue(parsed["continue"])

    def test_post_tool_use_is_silent(self) -> None:
        payload = {
            "session_id": "session-1",
            "hook_event_name": "PostToolUse",
            "cwd": "C:/work/demo",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_result": {"return_code": 0, "stdout": "On branch main", "stderr": ""},
        }
        output = self.run_hook("post_tool_use.py", payload)
        parsed = json.loads(output)
        self.assertTrue(parsed["suppressOutput"])

    def run_hook(self, script_name: str, payload: dict) -> str:
        script_path = PROJECT_ROOT / "hooks" / "scripts" / script_name
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
        env["HOME"] = self.temp_home.name
        env["USERPROFILE"] = self.temp_home.name
        process = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=True,
        )
        return process.stdout.strip()


if __name__ == "__main__":
    unittest.main()
