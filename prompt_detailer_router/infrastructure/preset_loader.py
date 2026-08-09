"""Preset and profile loading with required-key validation.

Infrastructure layer (Requirements 10.1-10.6). Reads versioned resource files,
validates required keys, and never falls back to a different preset implicitly:
missing keys, missing mappings, or scope mismatches raise ConfigurationError.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.scopes import SUPPORTED_SCOPES
from prompt_detailer_router.infrastructure.resource_ids import safe_resource_id

DEFAULT_PROFILE_ID = "default_v1"

_UPSCALE_KEYS = ("version", "preset_id", "quality_details", "preservation", "restrictions")
_DETAILER_KEYS = ("version", "scope", "preservation", "local_details", "restrictions")
_PROFILE_KEYS = ("version", "profile_id", "mappings")


@dataclass(frozen=True, slots=True)
class UpscalePreset:
    version: str
    preset_id: str
    quality_details: str
    preservation: str
    restrictions: str


@dataclass(frozen=True, slots=True)
class DetailerPreset:
    version: str
    scope: str
    preservation: str
    local_details: str
    restrictions: str
    default_order: int | None = None


@dataclass(frozen=True, slots=True)
class DetailerProfile:
    version: str
    profile_id: str
    mappings: Mapping[str, str]


def _read_json(*parts: str) -> dict:
    resource = files("prompt_detailer_router.resources").joinpath(*parts)
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(
            f"Resource not found: {'/'.join(parts)}"
        ) from exc
    return loads_config_json(text, "/".join(parts))


def loads_config_json(text: str, what: str) -> dict:
    """Parse config JSON, converting syntax errors to ConfigurationError."""

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Resource is not valid JSON: {what} ({exc})") from exc


def _require_keys(data: dict, keys: tuple[str, ...], what: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ConfigurationError(
            f"{what} is missing required keys: {', '.join(missing)}"
        )


def _require_str_fields(data: dict, keys: tuple[str, ...], what: str) -> None:
    for key in keys:
        if not isinstance(data[key], str):
            raise ConfigurationError(
                f"{what} field '{key}' must be a string, got "
                f"{type(data[key]).__name__}."
            )


def parse_upscale_preset(data: dict) -> UpscalePreset:
    _require_keys(data, _UPSCALE_KEYS, "Upscale preset")
    _require_str_fields(data, _UPSCALE_KEYS, "Upscale preset")
    return UpscalePreset(
        version=data["version"],
        preset_id=data["preset_id"],
        quality_details=data["quality_details"],
        preservation=data["preservation"],
        restrictions=data["restrictions"],
    )


def parse_detailer_preset(data: dict) -> DetailerPreset:
    _require_keys(data, _DETAILER_KEYS, "Detailer preset")
    _require_str_fields(data, _DETAILER_KEYS, "Detailer preset")
    default_order = data.get("default_order")
    if default_order is not None and (
        not isinstance(default_order, int) or isinstance(default_order, bool)
    ):
        raise ConfigurationError(
            "Detailer preset field 'default_order' must be an integer or omitted."
        )
    return DetailerPreset(
        version=data["version"],
        scope=data["scope"],
        preservation=data["preservation"],
        local_details=data["local_details"],
        restrictions=data["restrictions"],
        default_order=default_order,
    )


def parse_detailer_profile(data: dict) -> DetailerProfile:
    _require_keys(data, _PROFILE_KEYS, "Detailer profile")
    _require_str_fields(data, ("version", "profile_id"), "Detailer profile")
    mappings = data["mappings"]
    if not isinstance(mappings, dict):
        raise ConfigurationError("Detailer profile 'mappings' must be an object.")
    for scope, preset_id in mappings.items():
        if not isinstance(scope, str) or not isinstance(preset_id, str):
            raise ConfigurationError(
                "Detailer profile 'mappings' must map string scopes to string "
                "preset ids."
            )
    missing = [scope for scope in SUPPORTED_SCOPES if scope not in mappings]
    if missing:
        raise ConfigurationError(
            "Detailer profile is missing mappings for scopes: "
            + ", ".join(missing)
        )
    return DetailerProfile(
        version=data["version"],
        profile_id=data["profile_id"],
        mappings=MappingProxyType(dict(mappings)),
    )


def verify_profile_targets(profile: DetailerProfile) -> None:
    """Ensure each mapping target exists and its scope matches the mapping key."""

    for scope, preset_id in profile.mappings.items():
        target = load_detailer_preset(preset_id)
        if target.scope != scope:
            raise ConfigurationError(
                f"Profile '{profile.profile_id}' maps scope '{scope}' to preset "
                f"'{preset_id}', but that preset's scope is '{target.scope}'."
            )


def load_upscale_preset(preset_id: str) -> UpscalePreset:
    safe_resource_id(preset_id, "upscale preset")
    return parse_upscale_preset(_read_json("presets", "upscale", f"{preset_id}.json"))


def load_detailer_preset(preset_id: str) -> DetailerPreset:
    safe_resource_id(preset_id, "detailer preset")
    return parse_detailer_preset(_read_json("presets", "detailer", f"{preset_id}.json"))


def load_detailer_profile(profile_id: str = DEFAULT_PROFILE_ID) -> DetailerProfile:
    safe_resource_id(profile_id, "detailer profile")
    profile = parse_detailer_profile(
        _read_json("presets", "detailer_profiles", f"{profile_id}.json")
    )
    verify_profile_targets(profile)
    return profile
