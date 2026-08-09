"""Contract: Ollama response JSON Schema (ollama_response_v1) -- foundation only.

Covers Requirement 13.1: the schema defines the shape of the validated
extraction result (global + scoped_features required, warnings optional).
Actual LLM calls / prompts / retry are out of this spec's scope (13.3).
"""

import json
from importlib.resources import files

from jsonschema import Draft202012Validator


def _load_schema() -> dict:
    text = (
        files("prompt_detailer_router.resources")
        .joinpath("schemas", "ollama_response_v1.schema.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _valid_response() -> dict:
    return {
        "schema_version": 1,
        "global": {
            "style": ["photorealistic"],
            "lighting": ["soft window light"],
            "camera": ["shallow depth of field"],
        },
        "scoped_features": {
            "face": ["dark brown eyes"],
            "hair": ["short black hair"],
        },
        "warnings": [],
    }


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(_load_schema())


def test_valid_response_passes() -> None:
    validator = Draft202012Validator(_load_schema())
    assert list(validator.iter_errors(_valid_response())) == []


def test_schema_version_required() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    del response["schema_version"]
    assert list(validator.iter_errors(response)), "schema_version is required (13.2)"


def test_schema_version_incompatible_rejected() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    response["schema_version"] = 2
    assert list(validator.iter_errors(response)), "schema_version 2 must be rejected (13.2)"


def test_warnings_optional() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    del response["warnings"]
    assert list(validator.iter_errors(response)) == []


def test_global_required() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    del response["global"]
    assert list(validator.iter_errors(response)), "global is required"


def test_scoped_features_required() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    del response["scoped_features"]
    assert list(validator.iter_errors(response)), "scoped_features is required"


def test_scoped_features_keys_limited_to_supported_scopes() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    response["scoped_features"]["nose"] = ["x"]
    assert list(validator.iter_errors(response)), "unsupported scope key must be rejected"


def test_feature_values_must_be_string_arrays() -> None:
    validator = Draft202012Validator(_load_schema())
    response = _valid_response()
    response["scoped_features"]["face"] = "dark brown eyes"
    assert list(validator.iter_errors(response)), "scoped feature values must be arrays"
