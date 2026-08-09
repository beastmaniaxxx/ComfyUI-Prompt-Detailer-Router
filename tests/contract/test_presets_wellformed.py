"""Contract: preset and profile resources are well-formed with required keys.

Covers Requirements 10.1, 10.2, 10.3 at the resource level and 8.4 (per-scope
detailer presets exist). Loader-level rejection paths (ConfigurationError) are
covered by the preset_loader tests / task 6.1.
"""

import json

import pytest

from prompt_detailer_router.infrastructure.resource_paths import resource_file

SEVEN_SCOPES = ("face", "hair", "hands", "body", "upper_body", "clothing", "generic")
UPSCALE_PRESETS = ("photographic", "illustration", "minimal")

DETAILER_REQUIRED = {"version", "scope", "preservation", "local_details", "restrictions"}
UPSCALE_REQUIRED = {"version", "preset_id", "quality_details", "preservation", "restrictions"}
PROFILE_REQUIRED = {"version", "profile_id", "mappings"}


def _read(*parts: str) -> dict:
    text = resource_file(*parts).read_text(encoding="utf-8")
    return json.loads(text)


@pytest.mark.parametrize("scope", SEVEN_SCOPES)
def test_detailer_preset_present_with_required_keys(scope: str) -> None:
    preset = _read("presets", "detailer", f"{scope}.json")
    assert DETAILER_REQUIRED <= preset.keys(), f"{scope}: missing keys"
    assert preset["scope"] == scope, "preset scope must match filename"
    for key in ("preservation", "local_details", "restrictions"):
        assert preset[key].strip(), f"{scope}.{key} must be non-empty"


@pytest.mark.parametrize("preset_id", UPSCALE_PRESETS)
def test_upscale_preset_present_with_required_keys(preset_id: str) -> None:
    preset = _read("presets", "upscale", f"{preset_id}.json")
    assert UPSCALE_REQUIRED <= preset.keys(), f"{preset_id}: missing keys"
    assert preset["preset_id"] == preset_id, "preset_id must match filename"
    for key in ("quality_details", "preservation", "restrictions"):
        assert preset[key].strip(), f"{preset_id}.{key} must be non-empty"


def test_default_profile_maps_all_scopes_to_matching_presets() -> None:
    profile = _read("presets", "detailer_profiles", "default_v1.json")
    assert PROFILE_REQUIRED <= profile.keys()
    assert profile["profile_id"] == "default_v1"
    mappings = profile["mappings"]
    assert set(mappings.keys()) == set(SEVEN_SCOPES), "profile must map all 7 scopes"
    for scope, preset_ref in mappings.items():
        target = _read("presets", "detailer", f"{preset_ref}.json")
        assert target["scope"] == scope, (
            f"profile maps {scope} -> {preset_ref}, but that preset's scope is "
            f"{target['scope']}"
        )
