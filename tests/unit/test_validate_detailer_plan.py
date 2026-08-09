"""Unit tests for the plan validation use case (application/validate_detailer_plan).

Covers Requirement 5: promote domain invariant violations to a user-facing
PlanValidationError; pass silently for a valid plan.
"""

import pytest

from prompt_detailer_router.application.validate_detailer_plan import (
    validate_detailer_plan,
)
from prompt_detailer_router.domain.detailer_plan import (
    SCHEMA_VERSION,
    DetailerPlan,
    DetailerTask,
)
from prompt_detailer_router.domain.errors import PlanValidationError


def _task(scope: str = "face", *, enabled: bool = True, prompt_final: str = "done") -> DetailerTask:
    return DetailerTask(
        task_id=f"main.{scope}",
        subject_id="main",
        scope=scope,
        extracted_features=(),
        prompt_core="",
        prompt_final=prompt_final,
        order=30,
        enabled=enabled,
        warnings=(),
    )


def _plan(tasks, requested=("face",)) -> DetailerPlan:
    return DetailerPlan(
        schema_version=SCHEMA_VERSION,
        requested_scopes=tuple(requested),
        tasks=tuple(tasks),
        warnings=(),
    )


def test_valid_plan_passes_without_raising() -> None:
    validate_detailer_plan(_plan([_task("face")]))  # no exception


def test_invalid_plan_raises_plan_validation_error() -> None:
    plan = _plan([_task("hair")], requested=("face",))
    with pytest.raises(PlanValidationError):
        validate_detailer_plan(plan)


def test_error_message_includes_the_violation_detail() -> None:
    plan = _plan([_task("face", enabled=False, prompt_final="")], requested=("face",))
    with pytest.raises(PlanValidationError) as excinfo:
        validate_detailer_plan(plan)
    assert "face" in str(excinfo.value)
