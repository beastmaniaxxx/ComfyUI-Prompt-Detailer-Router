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


def test_sequence_fields_are_coerced_to_tuples_and_isolated() -> None:
    features = ["dark brown eyes"]
    warns = ["w"]
    task = DetailerTask(
        task_id="main.face",
        subject_id="main",
        scope="face",
        extracted_features=features,
        prompt_core="",
        prompt_final="done",
        order=30,
        enabled=True,
        warnings=warns,
    )
    assert isinstance(task.extracted_features, tuple)
    assert isinstance(task.warnings, tuple)
    # Mutating the original lists must not affect the constructed task.
    features.append("mutated")
    warns.append("mutated")
    assert task.extracted_features == ("dark brown eyes",)
    assert task.warnings == ("w",)

    scopes = ["face"]
    tasks = [task]
    plan = DetailerPlan(
        schema_version=SCHEMA_VERSION,
        requested_scopes=scopes,
        tasks=tasks,
        warnings=[],
    )
    scopes.append("hair")
    tasks.append(task)
    assert plan.requested_scopes == ("face",)
    assert isinstance(plan.tasks, tuple) and len(plan.tasks) == 1


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
    # A disabled task may have an empty prompt_final. Since (subject_id, scope)
    # must be unique, the disabled task uses a distinct subject_id while the
    # requested scope still has an enabled task.
    enabled = _task("face")  # main.face, enabled, non-empty
    disabled = _task("face", subject_id="other", prompt_final="", enabled=False)
    issues = validate_plan(_plan([enabled, disabled], requested=("face",)))
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


# --- contract completeness: task_id format, (subject,scope) uniqueness,
#     requested_scopes normalization (Req 3.1, 3.3, 4.4) ---

def test_malformed_task_id_is_rejected() -> None:
    bad = DetailerTask(
        task_id="garbage",
        subject_id="main",
        scope="face",
        extracted_features=(),
        prompt_core="",
        prompt_final="done",
        order=30,
        enabled=True,
        warnings=(),
    )
    issues = validate_plan(_plan([bad], requested=("face",)))
    assert any(i.code == "malformed_task_id" for i in issues)


def test_duplicate_subject_scope_is_rejected() -> None:
    # Two distinct task_ids but the same (subject_id, scope) pair.
    a = _task("face")
    b = DetailerTask(
        task_id="main.face",
        subject_id="main",
        scope="face",
        extracted_features=(),
        prompt_core="",
        prompt_final="another",
        order=31,
        enabled=True,
        warnings=(),
    )
    issues = validate_plan(_plan([a, b], requested=("face",)))
    assert any(i.code == "duplicate_subject_scope" for i in issues)


def test_unsupported_or_non_lowercase_requested_scope_is_rejected() -> None:
    plan = _plan([_task("face")], requested=("Face",))
    issues = validate_plan(plan)
    assert any(i.code == "unsupported_requested_scope" for i in issues)


def test_duplicate_requested_scope_is_rejected() -> None:
    plan = _plan([_task("face")], requested=("face", "face"))
    issues = validate_plan(plan)
    assert any(i.code == "duplicate_requested_scope" for i in issues)


def test_empty_subject_id_is_rejected() -> None:
    # task_id=".face" is formally subject_id + "." + scope, but an empty
    # subject_id violates the schema minLength and breaks JSON round-trip.
    bad = DetailerTask(
        task_id=".face",
        subject_id="",
        scope="face",
        extracted_features=(),
        prompt_core="",
        prompt_final="done",
        order=30,
        enabled=True,
        warnings=(),
    )
    issues = validate_plan(_plan([bad], requested=("face",)))
    assert any(i.code == "empty_subject_id" for i in issues)
