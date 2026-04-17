from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|passwd|secret|authorization)\s*[:=]\s*(['\"]?)([^\s,'\";]+)"),
    re.compile(r"(?i)(bearer)\s+([A-Za-z0-9._\-]+)"),
    re.compile(r"(?i)(sk-[A-Za-z0-9]+)"),
]

_WHITESPACE_RE = re.compile(r"\s+")
_PATH_RE = re.compile(r"([A-Za-z]:[/\\][^\s\"']+)")
_LINE_NUMBER_RE = re.compile(r"\b(line|column)\s+\d+\b", re.IGNORECASE)
_DYNAMIC_NUMBER_RE = re.compile(r"\b\d+\b")
_WINDOWS_NOT_RECOGNIZED_RE = re.compile(r"'?([^'\s:]+)'?\s+is not recognized as an internal or external command", re.IGNORECASE)
_UNIX_COMMAND_NOT_FOUND_RE = re.compile(r"([^:\s]+):\s+command not found", re.IGNORECASE)
_LEGACY_COMMAND_NOT_FOUND_RE = re.compile(r"^([A-Za-z0-9._\-]+):\s+command not found$", re.IGNORECASE)
_MODULE_NOT_FOUND_RE = re.compile(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", re.IGNORECASE)
_PERMISSION_DENIED_RE = re.compile(r"permission denied", re.IGNORECASE)

_LOW_RISK_COMMAND_PREFIXES = {
    "git status",
    "git diff",
    "git log",
    "pwd",
    "dir",
    "ls",
    "npm test",
    "npm run test",
    "pnpm test",
    "pnpm run test",
    "bun test",
    "bun run test",
    "pytest",
    "python -m pytest",
    "py -m pytest",
    "uv run pytest",
}


def redact_secrets(text: str | None) -> str:
    if not text:
        return ""

    result = text
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(bearer)"):
            result = pattern.sub(lambda m: f"{m.group(1)} ***", result)
        elif pattern.pattern.startswith("(?i)(sk-"):
            result = pattern.sub("***", result)
        else:
            result = pattern.sub(lambda m: f"{m.group(1)}={m.group(2)}***", result)
    return result


def sanitize_path(text: str | None) -> str:
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1).replace("\\", "/")
        parts = [p for p in raw.split("/") if p]
        if len(parts) <= 2:
            return raw
        drive = parts[0]
        tail = "/".join(parts[-2:])
        return f"{drive}/.../{tail}"

    return _PATH_RE.sub(_replace, text)


def sanitize_text(text: str | None) -> str:
    sanitized = redact_secrets(text)
    sanitized = sanitize_path(sanitized)
    return sanitized.strip()


def normalize_command(command: str | None) -> str:
    if not command:
        return ""
    sanitized = sanitize_text(command)
    normalized = _WHITESPACE_RE.sub(" ", sanitized)
    return normalized.strip()


def command_prefix(command: str | None, max_parts: int = 2) -> str:
    normalized = normalize_command(command)
    if not normalized:
        return ""

    parts = normalized.split(" ")
    if len(parts) >= 3 and parts[0] in {"npm", "pnpm", "bun"} and parts[1] == "run":
        return " ".join(parts[:3])
    if len(parts) >= 3 and parts[1] == "-m":
        return " ".join(parts[:3])
    if len(parts) >= 3 and parts[0] == "uv" and parts[1] == "run":
        return " ".join(parts[:3])
    return " ".join(parts[:max_parts])


def normalize_scope_path(path: str | None) -> str:
    if not path:
        return ""
    normalized = (path or "").strip().replace("\\", "/").rstrip("/")
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.lower()


def is_low_risk_command(command: str | None) -> bool:
    prefix = command_prefix(command)
    return prefix in _LOW_RISK_COMMAND_PREFIXES


def normalize_error_signature(text: str | None) -> str:
    if not text:
        return ""

    sanitized = sanitize_text(text)
    lines = [line.strip() for line in sanitized.splitlines() if line.strip()]
    if not lines:
        return ""

    search_space = " | ".join(lines[:3])

    for line in lines[:3]:
        module_match = _MODULE_NOT_FOUND_RE.search(line)
        if module_match:
            return f"module not found: {module_match.group(1).lower()}"

        windows_match = _WINDOWS_NOT_RECOGNIZED_RE.search(line)
        if windows_match:
            return f"command not found: {windows_match.group(1).lower()}"

        unix_match = _UNIX_COMMAND_NOT_FOUND_RE.search(line)
        if unix_match:
            return f"command not found: {unix_match.group(1).lower()}"

        legacy_match = _LEGACY_COMMAND_NOT_FOUND_RE.match(line)
        if legacy_match:
            return f"command not found: {legacy_match.group(1).lower()}"

        if _PERMISSION_DENIED_RE.search(line):
            return "permission denied"

    normalized = _LINE_NUMBER_RE.sub(lambda m: f"{m.group(1)} <num>", search_space)
    normalized = _DYNAMIC_NUMBER_RE.sub("<num>", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip(" |")
    return normalized[:240]


def normalize_tool_result_text(tool_result: Any) -> tuple[str, str, int | None]:
    if tool_result is None:
        return ("", "", None)

    if isinstance(tool_result, str):
        text = sanitize_text(tool_result)
        signature = normalize_error_signature(text)
        return ("" if signature else text, text if signature else "", None)

    if isinstance(tool_result, dict):
        direct_return_code = tool_result.get("return_code")
        if isinstance(direct_return_code, int):
            stdout = sanitize_text(tool_result.get("stdout", ""))
            stderr = sanitize_text(tool_result.get("stderr", ""))
            return (stdout, stderr, direct_return_code)

        content = tool_result.get("content")
        if isinstance(content, dict):
            return_code = content.get("return_code")
            stdout = sanitize_text(content.get("stdout", ""))
            stderr = sanitize_text(content.get("stderr", ""))
            if isinstance(return_code, int):
                return (stdout, stderr, return_code)

        text = sanitize_text(json.dumps(tool_result, ensure_ascii=False))
        signature = extract_error_signature(tool_result)
        return ("" if signature else text, text if signature else "", None)

    return ("", "", None)


def extract_error_signature(tool_result: Any) -> str:
    if tool_result is None:
        return ""

    if isinstance(tool_result, str):
        return normalize_error_signature(tool_result)

    if isinstance(tool_result, dict):
        for key in ("stderr", "error", "message", "output"):
            value = tool_result.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_error_signature(value)

        content = tool_result.get("content")
        if isinstance(content, dict):
            for key in ("stderr", "error", "message"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return normalize_error_signature(value)

    return ""


def compact_error_text(text: str | None, max_lines: int = 3) -> str:
    if not text:
        return ""
    sanitized = sanitize_text(text)
    lines = [line.strip() for line in sanitized.splitlines() if line.strip()]
    return " | ".join(lines[:max_lines])[:500]


def to_jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [to_jsonable(v) for v in value]
        return str(value)


def expand_user_home(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()
