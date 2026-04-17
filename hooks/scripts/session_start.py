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

from scripts.memory_store import ensure_memory_home, utc_now_iso


def emit_silent_response() -> None:
    sys.stdout.write(json.dumps({
        "continue": True,
        "suppressOutput": True,
    }, ensure_ascii=False))


def main() -> int:
    ensure_memory_home()
    payload = {}
    raw = sys.stdin.read().strip()
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}

    sys.stdout.write(json.dumps({
        "continue": True,
        "suppressOutput": True,
        "metadata": {
            "initialized_at": utc_now_iso(),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        emit_silent_response()
        raise SystemExit(0)
