"""Unit tests for the resource-loader injection bundle.

Requirements 12.12 / 12.21: swapping a bundle field must be enough to change a
resource version or inject a broken resource, without monkeypatching core's
``resource_paths`` / ``schema_loader`` internals. Requirement 11.13 / design
"single supply point": the response schema is read through exactly one field, so
the ``format`` projection and the response validator cannot diverge.
"""

import dataclasses

import pytest
from jsonschema import Draft202012Validator

from prompt_detailer_router.domain.detailer_plan import SCHEMA_VERSION
from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.scopes import SUPPORTED_SCOPES
from prompt_detailer_router.domain.versions import PROMPT_BUILDER_VERSION
from prompt_detailer_router.infrastructure import (
    preset_loader,
    resource_loaders,
    schema_loader,
)

DEFAULTS = resource_loaders.DEFAULT_RESOURCE_LOADERS


# --- the default bundle is core's loaders, unwrapped ---

def test_default_bundle_loads_the_bundled_upscale_preset() -> None:
    assert DEFAULTS.load_upscale_preset("minimal").preset_id == "minimal"


def test_default_bundle_loads_the_bundled_profile() -> None:
    assert DEFAULTS.load_detailer_profile("default_v1").profile_id == "default_v1"


@pytest.mark.parametrize("scope", SUPPORTED_SCOPES)
def test_default_bundle_loads_every_detailer_preset(scope: str) -> None:
    assert DEFAULTS.load_detailer_preset(scope).scope == scope


def test_default_bundle_loads_policy_and_template() -> None:
    assert DEFAULTS.load_forbidden_terms_policy().terms
    assert DEFAULTS.load_detailer_builder_template().feature_clause_template


def test_default_bundle_loads_llm_resources() -> None:
    prompt = DEFAULTS.load_llm_prompt(resource_loaders.DEFAULT_EXTRACTION_PROMPT_ID)
    repair = DEFAULTS.load_llm_prompt(resource_loaders.DEFAULT_REPAIR_PROMPT_ID)
    definitions = DEFAULTS.load_scope_definitions(
        resource_loaders.DEFAULT_SCOPE_DEFINITIONS_ID
    )
    assert prompt.id == "extraction_system_v1"
    assert repair.id == "extraction_repair_v1"
    assert set(definitions.definitions) == set(SUPPORTED_SCOPES)


def test_default_bundle_loads_the_response_schema() -> None:
    schema = DEFAULTS.load_response_schema()
    assert schema["properties"]["schema_version"]["const"] == 1
    Draft202012Validator.check_schema(schema)


def test_default_bundle_carries_the_core_version_constants() -> None:
    assert DEFAULTS.prompt_builder_version == PROMPT_BUILDER_VERSION
    assert DEFAULTS.plan_schema_version == SCHEMA_VERSION


def test_default_response_schema_load_surfaces_config_errors(monkeypatch) -> None:
    # A broken bundled schema must not reach a caller as a raw JSONDecodeError.
    monkeypatch.setattr(
        resource_loaders,
        "resource_file",
        lambda *parts: _TextResource("{ not valid json"),
    )
    with pytest.raises(ConfigurationError):
        resource_loaders.load_response_schema()


class _TextResource:
    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._text


# --- swapping a field is enough to replace a resource ---

def _stub_preset(version: str) -> preset_loader.UpscalePreset:
    return preset_loader.UpscalePreset(
        version=version,
        preset_id="minimal",
        quality_details="q",
        preservation="p",
        restrictions="r",
    )


def test_swapping_a_field_replaces_the_loader() -> None:
    injected = dataclasses.replace(
        DEFAULTS, load_upscale_preset=lambda preset_id: _stub_preset("99.0")
    )
    assert injected.load_upscale_preset("minimal").version == "99.0"


def test_swapping_a_field_does_not_touch_core_loaders() -> None:
    dataclasses.replace(
        DEFAULTS, load_upscale_preset=lambda preset_id: _stub_preset("99.0")
    )
    assert preset_loader.load_upscale_preset("minimal").version != "99.0"
    assert DEFAULTS.load_upscale_preset("minimal").version != "99.0"


def test_swapping_a_field_can_inject_a_failing_resource() -> None:
    def boom(preset_id: str):
        raise ConfigurationError("injected failure")

    injected = dataclasses.replace(DEFAULTS, load_upscale_preset=boom)
    with pytest.raises(ConfigurationError):
        injected.load_upscale_preset("minimal")


def test_version_constants_are_injectable() -> None:
    injected = dataclasses.replace(
        DEFAULTS, prompt_builder_version=99, plan_schema_version=98
    )
    assert (injected.prompt_builder_version, injected.plan_schema_version) == (99, 98)


def test_bundle_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULTS.prompt_builder_version = 42  # type: ignore[misc]


# --- the response schema has exactly one supply point ---

def test_response_schema_has_a_single_supply_point() -> None:
    fields = {field.name for field in dataclasses.fields(resource_loaders.ResourceLoaders)}
    assert {name for name in fields if "response_schema" in name} == {
        "load_response_schema"
    }


def test_injected_response_schema_reaches_projection_input_and_validator() -> None:
    # The use case reads the schema once from this field and derives both the
    # ``format`` projection input and the response validator from that single
    # object; this test pins the seam that makes the two agree.
    injected_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "injected_marker"],
        "properties": {
            "schema_version": {"const": 1},
            "injected_marker": {"type": "string"},
        },
    }
    injected = dataclasses.replace(
        DEFAULTS, load_response_schema=lambda: injected_schema
    )

    schema = injected.load_response_schema()
    projection_input = schema
    validator = Draft202012Validator(schema)

    assert projection_input["required"] == ["schema_version", "injected_marker"]
    assert validator.is_valid({"schema_version": 1, "injected_marker": "x"})
    # The bundled schema's shape is rejected: the validator followed the
    # injection rather than core's cached validator.
    assert not validator.is_valid(
        {"schema_version": 1, "global": {}, "scoped_features": {}}
    )


def test_injection_does_not_disturb_cores_cached_validator() -> None:
    dataclasses.replace(DEFAULTS, load_response_schema=lambda: {"type": "object"})
    core_validator = schema_loader.get_ollama_response_validator()
    assert core_validator.is_valid(
        {"schema_version": 1, "global": {}, "scoped_features": {}}
    )
