"""Unit tests for the DetailerTask/DetailerPlan domain model and validation.

Covers Requirements 3.1-3.4 (task_id), 4.1-4.5 (immutable model, required
fields, schema_version), and 5.1-5.5 (plan integrity invariants).
"""

import dataclasses

import pytest

from prompt_detailer_router.domain.detailer_plan import (
    SCHEMA_VERSION,
    DetailerPlan,
    DetailerTask,
    PlanValidationIssue,
    make_task_id,
    validate_plan,
)


def _task(
    scope: str = "face",
    *,
    subject_id: str = "main",
    prompt_final: str = "Completed prompt.",
    enabled: bool = True,
    order: int = 30,
) -> DetailerTask:
    return DetailerTask(
        task_id=make_task_id(subject_id, scope),
        subject_id=subject_id,
        scope=scope,
        extracted_features=(),
        prompt_core="",
        prompt_final=prompt_final,
        order=order,
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


# --- task_id (Req 3) ---

def test_make_task_id_is_subject_dot_scope() -> None:
    assert make_task_id("main", "face") == "main.face"
    assert make_task_id("left_person", "hair") == "left_person.hair"


def test_schema_version_is_one() -> None:
    assert SCHEMA_VERSION == 1


# --- immutability & fields (Req 4) ---

def test_task_and_plan_are_frozen() -> None:
    task = _task()
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.prompt_final = "x"  # type: ignore[misc]
    plan = _plan([task])
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.schema_version = 2  # type: ignore[misc]


def test_task_has_all_required_fields() -> None:
    names = {f.name for f in dataclasses.fields(DetailerTask)}
    assert names == {
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


def test_plan_has_all_required_fields() -> None:
    names = {f.name for f in dataclasses.fields(DetailerPlan)}
    assert names == {"schema_version", "requested_scopes", "tasks", "warnings"}


# --- validation (Req 5) ---

def test_valid_plan_has_no_issues() -> None:
    assert validate_plan(_plan([_task("face")])) == ()


def test_scope_not_in_requested_is_rejected() -> None:
    plan = _plan([_task("hair")], requested=("face",))
    issues = validate_plan(plan)
    assert any(i.code == "scope_not_requested" for i in issues)


def test_duplicate_task_id_is_rejected() -> None:
    plan = _plan([_task("face"), _task("face")], requested=("face",))
    issues = validate_plan(plan)
    assert any(i.code == "duplicate_task_id" for i in issues)


def test_enabled_task_with_empty_prompt_final_is_rejected() -> None:
    plan = _plan([_task("face", prompt_final="   ")], requested=("face",))
    issues = validate_plan(plan)
    assert any(i.code == "empty_prompt_final" for i in issues)


def test_disabled_task_with_empty_prompt_final_is_allowed() -> None:
    # A disabled task may have an empty prompt_final, but the requested scope
    # still needs at least one enabled task, so add an enabled sibling.
    disabled = _task("face", prompt_final="", enabled=False)
    enabled = DetailerTask(
        task_id="main.face.alt",
        subject_id="main",
        scope="face",
        extracted_features=(),
        prompt_core="",
        prompt_final="Completed prompt.",
        order=31,
        enabled=True,
        warnings=(),
    )
    issues = validate_plan(_plan([disabled, enabled], requested=("face",)))
    assert not any(i.code == "empty_prompt_final" for i in issues)


def test_requested_scope_without_enabled_task_is_rejected() -> None:
    plan = _plan([_task("face", enabled=False, prompt_final="")], requested=("face",))
    issues = validate_plan(plan)
    assert any(i.code == "missing_enabled_task" for i in issues)


def test_issue_is_structured() -> None:
    plan = _plan([_task("hair")], requested=("face",))
    issues = validate_plan(plan)
    assert issues and all(isinstance(i, PlanValidationIssue) for i in issues)
    assert all(i.message for i in issues)
