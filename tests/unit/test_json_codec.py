"""Unit tests for the DETAILER_PLAN JSON codec (infrastructure/json_codec).

Covers Requirements 11.3 and 12.1-12.5: information-preserving round trip,
Tier 1 shape validation (unknown fields / malformed JSON rejected explicitly),
and Tier 2 business-invariant validation.
"""

import json

import pytest

from prompt_detailer_router.domain.detailer_plan import (
    SCHEMA_VERSION,
    DetailerPlan,
    DetailerTask,
)
from prompt_detailer_router.domain.errors import PlanDecodeError, PlanValidationError
from prompt_detailer_router.infrastructure import json_codec


def _plan() -> DetailerPlan:
    task = DetailerTask(
        task_id="main.face",
        subject_id="main",
        scope="face",
        extracted_features=("dark brown eyes",),
        prompt_core="dark brown eyes",
        prompt_final="Completed face detailer prompt.",
        order=30,
        enabled=True,
        warnings=("note",),
    )
    return DetailerPlan(
        schema_version=SCHEMA_VERSION,
        requested_scopes=("face",),
        tasks=(task,),
        warnings=(),
    )


def _valid_json() -> str:
    return json_codec.encode_plan(_plan())


def test_round_trip_preserves_information() -> None:
    plan = _plan()
    assert json_codec.decode_plan(json_codec.encode_plan(plan)) == plan


def test_encode_is_deterministic() -> None:
    assert json_codec.encode_plan(_plan()) == json_codec.encode_plan(_plan())


def test_encode_produces_all_fields() -> None:
    data = json.loads(_valid_json())
    assert set(data) == {"schema_version", "requested_scopes", "tasks", "warnings"}
    assert set(data["tasks"][0]) == {
        "task_id",
        "subject_id",
        "scope",
        "extracted_features",
        "prompt_core",
        "prompt_final",
        "order",
        "enabled",
        "warnings",
    }


def test_decode_malformed_json_raises_plan_decode_error() -> None:
    with pytest.raises(PlanDecodeError):
        json_codec.decode_plan("{not valid json")


def test_decode_unknown_field_raises_plan_decode_error() -> None:
    data = json.loads(_valid_json())
    data["surprise"] = 1
    with pytest.raises(PlanDecodeError):
        json_codec.decode_plan(json.dumps(data))


def test_decode_wrong_schema_version_raises_plan_decode_error() -> None:
    data = json.loads(_valid_json())
    data["schema_version"] = 2
    with pytest.raises(PlanDecodeError):
        json_codec.decode_plan(json.dumps(data))


def test_decode_business_invalid_raises_plan_validation_error() -> None:
    # Shape-valid but violates an invariant: task scope not in requested_scopes.
    data = json.loads(_valid_json())
    data["tasks"][0]["scope"] = "hair"
    with pytest.raises(PlanValidationError):
        json_codec.decode_plan(json.dumps(data))


def test_decode_enabled_empty_prompt_final_raises_validation_error() -> None:
    data = json.loads(_valid_json())
    data["tasks"][0]["prompt_final"] = ""
    with pytest.raises(PlanValidationError):
        json_codec.decode_plan(json.dumps(data))


def test_decode_malformed_task_id_raises_validation_error() -> None:
    # Shape-valid string but not subject_id + "." + scope (Req 3.1).
    data = json.loads(_valid_json())
    data["tasks"][0]["task_id"] = "garbage"
    with pytest.raises(PlanValidationError):
        json_codec.decode_plan(json.dumps(data))
