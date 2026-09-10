"""Validated audience profiles used by author and independent reviewers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AudienceProfileError(RuntimeError):
    pass


def load_registry(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AudienceProfileError(f"Cannot read audience registry: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise AudienceProfileError("Unsupported audience registry schema.")
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise AudienceProfileError("Audience registry must contain profiles.")
    return value


def validate_profile(profile_id: str, profile: object) -> dict[str, Any]:
    if not isinstance(profile_id, str) or not profile_id:
        raise AudienceProfileError("audience_profile must be a non-empty profile id.")
    if not isinstance(profile, dict):
        raise AudienceProfileError(f"Audience profile {profile_id!r} must be an object.")
    required_strings = {"label", "preferred_level", "calibration_rule"}
    required_lists = {"assumed_knowledge", "teach_explicitly", "avoid_by_default"}
    missing = (required_strings | required_lists) - set(profile)
    if missing:
        raise AudienceProfileError(
            f"Audience profile {profile_id!r} is missing: " + ", ".join(sorted(missing))
        )
    if any(not isinstance(profile[key], str) or not profile[key].strip() for key in required_strings):
        raise AudienceProfileError(f"Audience profile {profile_id!r} has an invalid string field.")
    for key in required_lists:
        value = profile[key]
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise AudienceProfileError(
                f"Audience profile {profile_id!r} field {key!r} must be a non-empty string array."
            )
    return {"profile_id": profile_id, **profile}


def load_audience_profile(config: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    profile_id = config.get("audience_profile")
    if not isinstance(profile_id, str) or not profile_id:
        raise AudienceProfileError("Lesson configuration must explicitly name audience_profile.")
    registry = load_registry(registry_path)
    profiles = registry["profiles"]
    if profile_id not in profiles:
        raise AudienceProfileError(f"Unknown audience profile: {profile_id}")
    return validate_profile(profile_id, profiles[profile_id])
