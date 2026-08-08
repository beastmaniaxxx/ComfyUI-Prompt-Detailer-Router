"""Unit tests for schema loading + validator caching (infrastructure/schema_loader).

Covers Requirements 11.1 and 13.2: load the versioned JSON Schemas and provide
cached Draft 2020-12 validators.
"""

from jsonschema import Draft202012Validator

from prompt_detailer_router.infrastructure import schema_loader


def test_get_plan_validator_returns_draft_2020_12() -> None:
    validator = schema_loader.get_plan_validator()
    assert isinstance(validator, Draft202012Validator)


def test_plan_validator_accepts_valid_plan() -> None:
    valid = {
        "schema_version": 1,
        "requested_scopes": ["face"],
        "tasks": [
            {
                "task_id": "main.face",
                "subject_id": "main",
                "scope": "face",
                "extracted_features": [],
                "prompt_core": "",
                "prompt_final": "done",
                "order": 30,
                "enabled": True,
                "warnings": [],
            }
        ],
        "warnings": [],
    }
    assert list(schema_loader.get_plan_validator().iter_errors(valid)) == []


def test_get_ollama_response_validator_accepts_valid_response() -> None:
    valid = {"global": {"style": ["x"]}, "scoped_features": {"face": ["y"]}}
    assert list(schema_loader.get_ollama_response_validator().iter_errors(valid)) == []


def test_validators_are_cached() -> None:
    assert schema_loader.get_plan_validator() is schema_loader.get_plan_validator()
    assert (
        schema_loader.get_ollama_response_validator()
        is schema_loader.get_ollama_response_validator()
    )
