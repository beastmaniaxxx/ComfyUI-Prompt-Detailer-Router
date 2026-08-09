"""Contract: DETAILER_PLAN JSON Schema (detailer_plan_v1).

Covers Requirements 11.1, 11.2: the schema defines the required structure and
rejects unknown fields (additionalProperties:false) and incompatible
schema_version values.
"""

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from prompt_detailer_router.infrastructure.resource_paths import resource_file

SEVEN_SCOPES = ("face", "hair", "hands", "body", "upper_body", "clothing", "generic")


def _load_schema() -> dict:
    text = resource_file("schemas", "detailer_plan_v1.schema.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def _valid_plan() -> dict:
    return {
        "schema_version": 1,
        "requested_scopes": ["face", "hair"],
        "tasks": [
            {
                "task_id": "main.face",
                "subject_id": "main",
                "scope": "face",
                "extracted_features": ["dark brown eyes"],
                "prompt_core": "dark brown eyes",
                "prompt_final": "Completed face detailer prompt.",
                "order": 30,
                "enabled": True,
                "warnings": [],
            }
        ],
        "warnings": [],
    }


def test_schema_is_valid_draft_2020_12() -> None:
    schema = _load_schema()
    Draft202012Validator.check_schema(schema)


def test_valid_plan_passes() -> None:
    validator = Draft202012Validator(_load_schema())
    assert list(validator.iter_errors(_valid_plan())) == []


def test_schema_version_is_pinned_to_one() -> None:
    validator = Draft202012Validator(_load_schema())
    plan = _valid_plan()
    plan["schema_version"] = 2
    assert list(validator.iter_errors(plan)), "schema_version=2 must be rejected"


def test_unknown_field_rejected_at_root() -> None:
    validator = Draft202012Validator(_load_schema())
    plan = _valid_plan()
    plan["unexpected"] = "x"
    assert list(validator.iter_errors(plan)), "unknown root field must be rejected"


def test_unknown_field_rejected_in_task() -> None:
    validator = Draft202012Validator(_load_schema())
    plan = _valid_plan()
    plan["tasks"][0]["unexpected"] = "x"
    assert list(validator.iter_errors(plan)), "unknown task field must be rejected"


@pytest.mark.parametrize(
    "missing", ["schema_version", "requested_scopes", "tasks", "warnings"]
)
def test_missing_required_root_field_rejected(missing: str) -> None:
    validator = Draft202012Validator(_load_schema())
    plan = _valid_plan()
    del plan[missing]
    assert list(validator.iter_errors(plan)), f"missing {missing} must be rejected"


@pytest.mark.parametrize(
    "missing",
    [
        "task_id",
        "subject_id",
        "scope",
        "extracted_features",
        "prompt_core",
        "prompt_final",
        "order",
        "enabled",
        "warnings",
    ],
)
def test_missing_required_task_field_rejected(missing: str) -> None:
    validator = Draft202012Validator(_load_schema())
    plan = _valid_plan()
    del plan["tasks"][0][missing]
    assert list(validator.iter_errors(plan)), f"missing task.{missing} must be rejected"


def test_requested_scopes_reject_out_of_enum_and_duplicates() -> None:
    validator = Draft202012Validator(_load_schema())
    bad_enum = _valid_plan()
    bad_enum["requested_scopes"] = ["nose"]
    assert list(validator.iter_errors(bad_enum)), "non-enum scope must be rejected"

    dup = _valid_plan()
    dup["requested_scopes"] = ["face", "face"]
    assert list(validator.iter_errors(dup)), "duplicate scopes must be rejected"


def test_task_field_types_enforced() -> None:
    validator = Draft202012Validator(_load_schema())
    bad = _valid_plan()
    bad["tasks"][0]["order"] = "30"
    assert list(validator.iter_errors(bad)), "order must be integer"
    bad2 = _valid_plan()
    bad2["tasks"][0]["scope"] = "nose"
    assert list(validator.iter_errors(bad2)), "task scope must be in the 7-scope enum"
