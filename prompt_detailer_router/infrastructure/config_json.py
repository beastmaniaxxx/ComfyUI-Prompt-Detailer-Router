"""Shared config-JSON parsing for resource loaders.

Converts JSON syntax errors, duplicate keys, and non-object roots into
ConfigurationError so user-edited preset/profile/policy/template files surface
as user-facing configuration errors (never a raw exception, never a silently
last-wins duplicate key).
"""

from __future__ import annotations

import json

from prompt_detailer_router.domain.errors import ConfigurationError


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(f"Duplicate key '{key}' in configuration JSON.")
        result[key] = value
    return result


def parse_config_json(text: str, what: str) -> dict:
    """Parse a config resource into a JSON object.

    Raises ConfigurationError for invalid JSON, duplicate keys, or a non-object
    root.
    """

    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except ConfigurationError as exc:
        # Duplicate-key detection raises inside the hook; add the resource label.
        raise ConfigurationError(f"{exc} (resource: {what})") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Resource is not valid JSON: {what} ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Resource must be a JSON object: {what} (got {type(data).__name__})."
        )
    return data
