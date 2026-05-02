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

from scripts.memory_store import add_never_allow_rule, remove_auto_allow_rules
from scripts.settings_sync import remove_project_auto_allow_rules


def parse_args(argv: list[str]) -> tuple[str, str | None, bool]:
    command = ""
    cwd: str | None = None
    all_matching = False

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--command":
            if index + 1 >= len(argv):
                raise ValueError("--command requires a value")
            command = argv[index + 1]
            index += 2
            continue
        if arg == "--cwd":
            if index + 1 >= len(argv):
                raise ValueError("--cwd requires a value")
            cwd = argv[index + 1]
            index += 2
            continue
        if arg == "--all-matching":
            all_matching = True
            index += 1
            continue
        raise ValueError(f"unknown argument: {arg}")

    if not command.strip():
        raise ValueError("--command is required")
    return (command, cwd, all_matching)


def main() -> int:
    try:
        command, cwd, all_matching = parse_args(sys.argv[1:])
    except ValueError as exc:
        sys.stderr.write(str(exc))
        return 1

    removed_memory = remove_auto_allow_rules(command, cwd=cwd, all_matching=all_matching)
    never_allow = add_never_allow_rule(command, cwd=cwd)
    removed_settings = remove_project_auto_allow_rules(PLUGIN_ROOT, command, cwd=cwd, all_matching=all_matching)

    sys.stdout.write(json.dumps({
        "ok": True,
        "summary": {
            "command": command,
            "cwd": cwd,
            "all_matching": all_matching,
            "memory": removed_memory,
            "never_allow": never_allow,
            "settings": removed_settings,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
