"""Unit tests for the shared config-JSON validation helpers.

``require_keys`` / ``require_str_fields`` are the shared validation path every
resource loader delegates to (AGENTS.md 22.2, Requirement 10.15): a new loader
must not carry its own required-key / blank-string implementation.
"""

import pytest

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.infrastructure import config_json


# --- require_keys ---

def test_require_keys_accepts_complete_object() -> None:
    config_json.require_keys({"a": 1, "b": 2}, ("a", "b"), "Thing")


def test_require_keys_reports_every_missing_key() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        config_json.require_keys({"a": 1}, ("a", "b", "c"), "Thing")
    assert str(excinfo.value) == "Thing is missing required keys: b, c"


# --- require_str_fields ---

def test_require_str_fields_accepts_non_blank_strings() -> None:
    config_json.require_str_fields({"a": "x", "b": " y "}, ("a", "b"), "Thing")


@pytest.mark.parametrize("value", [1, 1.5, True, None, [], {}, ["x"]])
def test_require_str_fields_rejects_non_string(value: object) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        config_json.require_str_fields({"a": value}, ("a",), "Thing")
    assert str(excinfo.value) == (
        f"Thing field 'a' must be a string, got {type(value).__name__}."
    )


@pytest.mark.parametrize("blank", ["", "   ", "\t\n", "　"])
def test_require_str_fields_rejects_blank(blank: str) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        config_json.require_str_fields({"a": blank}, ("a",), "Thing")
    assert str(excinfo.value) == (
        "Thing field 'a' must not be empty or whitespace-only."
    )


def test_require_str_fields_checks_keys_in_declared_order() -> None:
    # The first declared offender is reported, so messages stay deterministic.
    with pytest.raises(ConfigurationError) as excinfo:
        config_json.require_str_fields({"a": 1, "b": ""}, ("a", "b"), "Thing")
    assert "field 'a'" in str(excinfo.value)


# --- preset_loader delegates to the shared helpers (no private duplicate) ---

def test_preset_loader_has_no_private_duplicates() -> None:
    from prompt_detailer_router.infrastructure import preset_loader

    assert not hasattr(preset_loader, "_require_str_fields")
    assert not hasattr(preset_loader, "_require_keys")
    assert preset_loader.require_str_fields is config_json.require_str_fields
    assert preset_loader.require_keys is config_json.require_keys
