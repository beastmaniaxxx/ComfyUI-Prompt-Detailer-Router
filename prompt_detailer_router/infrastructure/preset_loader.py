"""Preset and profile loading with required-key validation.

Infrastructure layer (Requirements 10.1-10.6). Reads versioned resource files,
validates required keys, and never falls back to a different preset implicitly:
missing keys, missing mappings, or scope mismatches raise ConfigurationError.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.scopes import SUPPORTED_SCOPES
from prompt_detailer_router.infrastructure.config_json import (
    parse_config_json,
    read_config_json,
    reject_unknown_keys,
)
from prompt_detailer_router.infrastructure.resource_ids import safe_resource_id
from prompt_detailer_router.infrastructure.resource_paths import resource_file

DEFAULT_PROFILE_ID = "default_v1"

_UPSCALE_KEYS = ("version", "preset_id", "quality_details", "preservation", "restrictions")
_DETAILER_KEYS = ("version", "scope", "preservation", "local_details", "restrictions")
_DETAILER_OPTIONAL_KEYS = ("default_order",)
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
    return read_config_json(resource_file(*parts), "/".join(parts))


def loads_config_json(text: str, what: str) -> dict:
    """Parse config JSON into an object, converting errors to ConfigurationError.

    Thin wrapper over the shared :func:`parse_config_json` (kept for callers and
    tests that reference this module).
    """

    return parse_config_json(text, what)


def _require_keys(data: dict, keys: tuple[str, ...], what: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ConfigurationError(
            f"{what} is missing required keys: {', '.join(missing)}"
        )


def _require_str_fields(data: dict, keys: tuple[str, ...], what: str) -> None:
    for key in keys:
        value = data[key]
        if not isinstance(value, str):
            raise ConfigurationError(
                f"{what} field '{key}' must be a string, got "
                f"{type(value).__name__}."
            )
        # A blank required string would yield an empty/degenerate prompt at build
        # time (e.g. an empty upscale_prompt); reject it at load instead.
        if not value.strip():
            raise ConfigurationError(
                f"{what} field '{key}' must not be empty or whitespace-only."
            )


def parse_upscale_preset(data: dict) -> UpscalePreset:
    _require_keys(data, _UPSCALE_KEYS, "Upscale preset")
    reject_unknown_keys(data, _UPSCALE_KEYS, "Upscale preset")
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
    reject_unknown_keys(
        data, _DETAILER_KEYS + _DETAILER_OPTIONAL_KEYS, "Detailer preset"
    )
    _require_str_fields(data, _DETAILER_KEYS, "Detailer preset")
    if data["scope"] not in SUPPORTED_SCOPES:
        raise ConfigurationError(
            f"Detailer preset 'scope' must be one of {SUPPORTED_SCOPES}, "
            f"got '{data['scope']}'."
        )
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
    reject_unknown_keys(data, _PROFILE_KEYS, "Detailer profile")
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
    # The mapping keys must be exactly the supported scopes: an unknown key like
    # "feet" would load successfully but never be reachable (normalize_scopes
    # drops it), silently hiding a typo or an unfinished scope addition.
    unknown = sorted(scope for scope in mappings if scope not in SUPPORTED_SCOPES)
    if unknown:
        raise ConfigurationError(
            "Detailer profile has mappings for unsupported scopes: "
            + ", ".join(unknown)
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
    preset = parse_upscale_preset(_read_json("presets", "upscale", f"{preset_id}.json"))
    if preset.preset_id != preset_id:
        raise ConfigurationError(
            f"Upscale preset file '{preset_id}.json' declares preset_id "
            f"'{preset.preset_id}'; the file name and preset_id must match."
        )
    return preset


def load_detailer_preset(preset_id: str) -> DetailerPreset:
    safe_resource_id(preset_id, "detailer preset")
    preset = parse_detailer_preset(
        _read_json("presets", "detailer", f"{preset_id}.json")
    )
    if preset.scope != preset_id:
        raise ConfigurationError(
            f"Detailer preset file '{preset_id}.json' declares scope "
            f"'{preset.scope}'; the file name and scope must match."
        )
    return preset


def load_detailer_profile(profile_id: str = DEFAULT_PROFILE_ID) -> DetailerProfile:
    safe_resource_id(profile_id, "detailer profile")
    profile = parse_detailer_profile(
        _read_json("presets", "detailer_profiles", f"{profile_id}.json")
    )
    if profile.profile_id != profile_id:
        raise ConfigurationError(
            f"Detailer profile file '{profile_id}.json' declares profile_id "
            f"'{profile.profile_id}'; the file name and profile_id must match."
        )
    verify_profile_targets(profile)
    return profile
