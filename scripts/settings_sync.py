from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.sanitize import command_prefix, normalize_command, normalize_scope_path

PLUGIN_MARKER = "ai-memory-plugin"
PROJECT_SETTINGS_PATH = Path(".claude/settings.json")


def read_project_settings(project_root: Path) -> dict[str, Any]:
    path = project_root / PROJECT_SETTINGS_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_project_settings(project_root: Path, settings: dict[str, Any]) -> None:
    path = project_root / PROJECT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_auto_allow_permission_entry(rule: dict[str, Any]) -> str:
    command = rule.get("command", "").strip()
    return f"Bash({command} *)"


def rule_matches(command: str, cwd: str | None, item: dict[str, Any], all_matching: bool = False) -> bool:
    command_key = command_prefix(command) or normalize_command(command)
    normalized_cwd = normalize_scope_path(cwd)
    if item.get("command") != command_key:
        return False
    if all_matching:
        return item.get("scope") == "project"
    if normalized_cwd:
        return item.get("scope") == "project" and item.get("cwd") == normalized_cwd
    return item.get("scope") == "global"


def sync_project_auto_allow_rules(project_root: Path, rules: list[dict[str, Any]]) -> dict[str, Any]:
    settings = read_project_settings(project_root)
    permissions = settings.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
        settings["permissions"] = permissions

    allow = permissions.get("allow")
    if not isinstance(allow, list):
        allow = []
        permissions["allow"] = allow

    managed = settings.get("aiMemoryPlugin")
    if not isinstance(managed, dict):
        managed = {}
        settings["aiMemoryPlugin"] = managed

    managed_rules = managed.get("managedAutoAllowRules")
    if not isinstance(managed_rules, list):
        managed_rules = []
        managed["managedAutoAllowRules"] = managed_rules

    existing_permissions = {item for item in allow if isinstance(item, str)}
    existing_rule_keys = {
        (item.get("command"), item.get("scope"), item.get("cwd"))
        for item in managed_rules
        if isinstance(item, dict)
    }

    added_permissions: list[str] = []
    added_rules: list[dict[str, Any]] = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        permission_entry = build_auto_allow_permission_entry(rule)
        rule_key = (rule.get("command"), rule.get("scope"), rule.get("cwd"))
        if permission_entry not in existing_permissions:
            allow.append(permission_entry)
            existing_permissions.add(permission_entry)
            added_permissions.append(permission_entry)
        if rule_key not in existing_rule_keys:
            managed_rule = {
                "command": rule.get("command", ""),
                "scope": rule.get("scope", "project"),
                "cwd": rule.get("cwd", ""),
                "approved_count": int(rule.get("approved_count", 0) or 0),
                "source": PLUGIN_MARKER,
            }
            managed_rules.append(managed_rule)
            existing_rule_keys.add(rule_key)
            added_rules.append(managed_rule)

    if added_permissions or added_rules:
        write_project_settings(project_root, settings)

    return {
        "updated": bool(added_permissions or added_rules),
        "added_permissions": added_permissions,
        "added_rules": added_rules,
        "settings_path": str(project_root / PROJECT_SETTINGS_PATH),
    }


def remove_project_auto_allow_rules(project_root: Path, command: str, cwd: str | None = None, all_matching: bool = False) -> dict[str, Any]:
    settings = read_project_settings(project_root)
    permissions = settings.get("permissions")
    managed = settings.get("aiMemoryPlugin")
    if not isinstance(permissions, dict) or not isinstance(managed, dict):
        return {
            "updated": False,
            "removed_permissions": [],
            "removed_rules": [],
            "settings_path": str(project_root / PROJECT_SETTINGS_PATH),
        }

    allow = permissions.get("allow")
    if not isinstance(allow, list):
        allow = []
        permissions["allow"] = allow

    managed_rules = managed.get("managedAutoAllowRules")
    if not isinstance(managed_rules, list):
        managed_rules = []
        managed["managedAutoAllowRules"] = managed_rules

    removed_rules = [item for item in managed_rules if isinstance(item, dict) and rule_matches(command, cwd, item, all_matching=all_matching)]
    kept_rules = [item for item in managed_rules if not (isinstance(item, dict) and rule_matches(command, cwd, item, all_matching=all_matching))]

    removed_permissions = []
    permissions_to_remove = {
        build_auto_allow_permission_entry(item)
        for item in removed_rules
    }
    kept_permissions = []
    for item in allow:
        if isinstance(item, str) and item in permissions_to_remove:
            removed_permissions.append(item)
            continue
        kept_permissions.append(item)

    managed["managedAutoAllowRules"] = kept_rules
    permissions["allow"] = kept_permissions

    updated = bool(removed_rules or removed_permissions)
    if updated:
        write_project_settings(project_root, settings)

    return {
        "updated": updated,
        "removed_permissions": removed_permissions,
        "removed_rules": removed_rules,
        "settings_path": str(project_root / PROJECT_SETTINGS_PATH),
    }
