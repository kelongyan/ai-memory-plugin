from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
HOOKS = PROJECT_ROOT / "hooks" / "scripts"


def run(script_name: str, fixture_name: str) -> None:
    payload = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(PROJECT_ROOT)
    process = subprocess.run(
        [sys.executable, str(HOOKS / script_name)],
        input=payload,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=True,
    )
    print(process.stdout.strip())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python run_fixture.py <script_name> <fixture_name>")
        raise SystemExit(1)
    run(sys.argv[1], sys.argv[2])
