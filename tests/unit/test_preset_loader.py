"""Unit tests for preset/profile loading (infrastructure/preset_loader).

Covers Requirements 10.1-10.6: load presets/profiles with required-key
validation, default profile, and ConfigurationError for missing keys, missing
mappings, or scope mismatches (no implicit fallback).
"""

import pytest

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.infrastructure import preset_loader

SEVEN = ("face", "hair", "hands", "body", "upper_body", "clothing", "generic")


# --- happy path ---

def test_load_upscale_preset() -> None:
    preset = preset_loader.load_upscale_preset("photographic")
    assert preset.preset_id == "photographic"
    assert preset.quality_details and preset.preservation and preset.restrictions


@pytest.mark.parametrize("scope", SEVEN)
def test_load_detailer_preset_scope_matches(scope: str) -> None:
    preset = preset_loader.load_detailer_preset(scope)
    assert preset.scope == scope
    assert preset.local_details and preset.preservation and preset.restrictions


def test_load_default_profile_maps_all_scopes() -> None:
    profile = preset_loader.load_detailer_profile()
    assert profile.profile_id == "default_v1"
    assert set(profile.mappings) == set(SEVEN)


def test_default_profile_is_used_when_unspecified() -> None:
    assert preset_loader.load_detailer_profile().profile_id == "default_v1"


# --- error paths ---

def test_missing_upscale_preset_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.load_upscale_preset("does_not_exist")


def test_missing_detailer_preset_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.load_detailer_preset("does_not_exist")


def test_missing_profile_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.load_detailer_profile("does_not_exist")


def test_upscale_preset_missing_key_raises() -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.parse_upscale_preset({"preset_id": "x", "version": "1.0"})


def test_detailer_profile_missing_mapping_raises() -> None:
    incomplete = {
        "version": "1.0",
        "profile_id": "p",
        "mappings": {s: s for s in SEVEN[:-1]},  # missing one scope
    }
    with pytest.raises(ConfigurationError):
        preset_loader.parse_detailer_profile(incomplete)


def test_profile_target_scope_mismatch_raises() -> None:
    # A profile that maps "face" -> the "hair" preset must be rejected.
    bad = preset_loader.DetailerProfile(
        version="1.0",
        profile_id="bad",
        mappings={**{s: s for s in SEVEN}, "face": "hair"},
    )
    with pytest.raises(ConfigurationError):
        preset_loader.verify_profile_targets(bad)


def test_profile_target_missing_preset_raises() -> None:
    bad = preset_loader.DetailerProfile(
        version="1.0",
        profile_id="bad",
        mappings={**{s: s for s in SEVEN}, "generic": "nonexistent"},
    )
    with pytest.raises(ConfigurationError):
        preset_loader.verify_profile_targets(bad)


def test_malformed_preset_json_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.loads_config_json("{ not valid json", "presets/detailer/face.json")
