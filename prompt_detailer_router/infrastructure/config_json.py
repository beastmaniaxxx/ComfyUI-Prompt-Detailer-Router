"""Shared config-JSON parsing for resource loaders.

Converts JSON syntax errors, duplicate keys, and non-object roots into
ConfigurationError so user-edited preset/profile/policy/template files surface
as user-facing configuration errors (never a raw exception, never a silently
last-wins duplicate key).
"""

from __future__ import annotations

import json
from typing import Iterable, Mapping

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


def reject_unknown_keys(
    data: Mapping[str, object], allowed: Iterable[str], what: str
) -> None:
    """Reject config objects carrying keys outside ``allowed``.

    A typo like ``"default_oder"`` must not be silently ignored (which would let
    a user-intended value fall back to a default). Unknown fields surface as a
    ConfigurationError naming the offending keys.
    """

    permitted = set(allowed)
    unknown = sorted(key for key in data if key not in permitted)
    if unknown:
        raise ConfigurationError(f"{what} has unknown fields: {', '.join(unknown)}.")


def require_keys(data: Mapping[str, object], keys: Iterable[str], what: str) -> None:
    """Reject config objects missing any of ``keys``.

    Every missing key is reported at once so a user editing a resource file does
    not have to rediscover them one round-trip at a time.
    """

    missing = [key for key in keys if key not in data]
    if missing:
        raise ConfigurationError(
            f"{what} is missing required keys: {', '.join(missing)}"
        )


def require_str_fields(
    data: Mapping[str, object], keys: Iterable[str], what: str
) -> None:
    """Require ``keys`` to hold non-blank strings.

    Callers must have checked key presence first (see :func:`require_keys`).
    A blank required string would yield an empty/degenerate prompt at build time
    (e.g. an empty ``upscale_prompt``); reject it at load instead.
    """

    for key in keys:
        value = data[key]
        if not isinstance(value, str):
            raise ConfigurationError(
                f"{what} field '{key}' must be a string, got "
                f"{type(value).__name__}."
            )
        if not value.strip():
            raise ConfigurationError(
                f"{what} field '{key}' must not be empty or whitespace-only."
            )


def read_config_json(resource, what: str) -> dict:
    """Read a resource as UTF-8 text and parse it as a config JSON object.

    Converts both filesystem read errors and non-UTF-8 decode errors into
    ConfigurationError so a user-edited resource saved in the wrong encoding
    surfaces as a configuration error instead of a raw UnicodeDecodeError.
    """

    try:
        text = resource.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(
            f"Resource is not valid UTF-8: {what} ({exc})"
        ) from exc
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(f"Resource not found: {what}") from exc
    return parse_config_json(text, what)
