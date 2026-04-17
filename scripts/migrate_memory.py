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

from scripts.memory_store import migrate_memory_store


def parse_flags(argv: list[str]) -> tuple[bool, bool]:
    return ("--dry-run" in argv, "--backup" in argv)


def main() -> int:
    dry_run, backup = parse_flags(sys.argv[1:])
    summary = migrate_memory_store(dry_run=dry_run, backup=backup)
    sys.stdout.write(json.dumps({
        "ok": True,
        "summary": summary,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
