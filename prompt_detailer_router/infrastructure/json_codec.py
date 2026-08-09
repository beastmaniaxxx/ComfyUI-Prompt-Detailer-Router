"""DETAILER_PLAN JSON serialization and two-tier decode.

Infrastructure layer (Requirements 11.3, 12.1-12.5). Encoding preserves all
fields with a stable key order. Decoding runs Tier 1 shape validation (against
the JSON Schema, rejecting unknown fields) then constructs the domain model and
runs Tier 2 business-invariant validation. Malformed/invalid input raises an
explicit error and is never silently corrected or dropped.
"""

from __future__ import annotations

import json

from prompt_detailer_router.domain.detailer_plan import (
    DetailerPlan,
    DetailerTask,
    validate_plan,
)
from prompt_detailer_router.domain.errors import PlanDecodeError, PlanValidationError
from prompt_detailer_router.infrastructure.schema_loader import get_plan_validator

_TASK_KEYS = (
    "task_id",
    "subject_id",
    "scope",
    "extracted_features",
    "prompt_core",
    "prompt_final",
    "order",
    "enabled",
    "warnings",
)


def _task_to_dict(task: DetailerTask) -> dict:
    return {
        "task_id": task.task_id,
        "subject_id": task.subject_id,
        "scope": task.scope,
        "extracted_features": list(task.extracted_features),
        "prompt_core": task.prompt_core,
        "prompt_final": task.prompt_final,
        "order": task.order,
        "enabled": task.enabled,
        "warnings": list(task.warnings),
    }


def plan_to_dict(plan: DetailerPlan) -> dict:
    """Convert a plan to a plain dict with stable key order."""

    return {
        "schema_version": plan.schema_version,
        "requested_scopes": list(plan.requested_scopes),
        "tasks": [_task_to_dict(task) for task in plan.tasks],
        "warnings": list(plan.warnings),
    }


def encode_plan(plan: DetailerPlan) -> str:
    """Serialize a plan to a JSON string, preserving all fields deterministically.

    Validates both Tier 2 business invariants and Tier 1 shape/version before
    serialization so ``encode_plan`` never emits schema-non-compliant JSON,
    keeping the ``encode`` -> ``decode`` round trip contract intact even for a
    plan built in memory by another caller (e.g. schema_version != 1 or a
    boolean ``order``).
    """

    issues = validate_plan(plan)
    if issues:
        details = "; ".join(issue.message for issue in issues)
        raise PlanValidationError(f"Cannot encode invalid plan: {details}")

    data = plan_to_dict(plan)
    schema_errors = sorted(
        get_plan_validator().iter_errors(data), key=lambda e: str(list(e.path))
    )
    if schema_errors:
        details = "; ".join(_format_schema_error(error) for error in schema_errors)
        raise PlanValidationError(f"Cannot encode schema-invalid plan: {details}")
    return json.dumps(data, ensure_ascii=False, indent=2)


def _dict_to_task(data: dict) -> DetailerTask:
    return DetailerTask(
        task_id=data["task_id"],
        subject_id=data["subject_id"],
        scope=data["scope"],
        extracted_features=tuple(data["extracted_features"]),
        prompt_core=data["prompt_core"],
        prompt_final=data["prompt_final"],
        order=data["order"],
        enabled=data["enabled"],
        warnings=tuple(data["warnings"]),
    )


def _dict_to_plan(data: dict) -> DetailerPlan:
    return DetailerPlan(
        schema_version=data["schema_version"],
        requested_scopes=tuple(data["requested_scopes"]),
        tasks=tuple(_dict_to_task(task) for task in data["tasks"]),
        warnings=tuple(data["warnings"]),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """object_pairs_hook that rejects duplicate keys instead of silently keeping
    the last value (Req 12.4/12.5: never silently drop input)."""

    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise PlanDecodeError(f"Duplicate key in plan JSON: '{key}'.")
        result[key] = value
    return result


def _format_schema_error(error) -> str:
    location = "/".join(str(part) for part in error.path) or "(root)"
    return f"{location}: {error.message}"


def decode_plan(raw_json: str) -> DetailerPlan:
    """Decode a plan JSON string into a validated DetailerPlan.

    Raises PlanDecodeError for malformed JSON, duplicate keys, or Tier 1 schema
    violations (including unknown fields), and PlanValidationError for Tier 2
    invariant violations.
    """

    try:
        data = json.loads(raw_json, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise PlanDecodeError(f"Invalid JSON: {exc}") from exc

    validator = get_plan_validator()
    errors = sorted(validator.iter_errors(data), key=lambda e: str(list(e.path)))
    if errors:
        details = "; ".join(_format_schema_error(error) for error in errors)
        raise PlanDecodeError(f"Plan JSON failed schema validation: {details}")

    plan = _dict_to_plan(data)

    issues = validate_plan(plan)
    if issues:
        details = "; ".join(issue.message for issue in issues)
        raise PlanValidationError(f"Plan violates invariants: {details}")

    return plan
