"""Unit tests for the Detailer Plan Builder (application/build_detailer_plan).

Covers Requirements 3.1/3.3 (task_id), 5.3 (>=1 enabled task per scope),
6.1-6.5 (build from analysis, fallback for missing scopes, no invented facts),
8.1/8.4 (scope-limited prompts using the scope preset), 9.4 (forbidden filter),
10.6 (default profile), 10.7 (default order).
"""

import pytest

from prompt_detailer_router.application.build_detailer_plan import (
    PlanBuildInput,
    build_detailer_plan,
)
from prompt_detailer_router.domain.detailer_plan import SCHEMA_VERSION, validate_plan
from prompt_detailer_router.domain.errors import PlanValidationError
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis


def _analysis(scoped) -> PromptAnalysis:
    return PromptAnalysis(global_features={}, scoped_features=scoped, warnings=())


def test_builds_one_task_per_requested_scope() -> None:
    analysis = _analysis({"face": ["dark brown eyes"], "hair": ["short black hair"]})
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face", "hair"), analysis=analysis)
    )
    assert [t.task_id for t in plan.tasks] == ["main.face", "main.hair"]
    assert plan.requested_scopes == ("face", "hair")
    assert plan.schema_version == SCHEMA_VERSION
    assert validate_plan(plan) == ()


def test_task_uses_scope_preset_and_extracted_features() -> None:
    analysis = _analysis({"face": ["dark brown eyes"]})
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face",), analysis=analysis)
    )
    face = plan.tasks[0]
    assert face.extracted_features == ("dark brown eyes",)
    assert "dark brown eyes" in face.prompt_final
    assert "Refine natural skin texture" in face.prompt_final  # face preset local_details
    assert face.enabled is True
    assert face.prompt_final.strip()


def test_default_order_applied_per_scope() -> None:
    analysis = _analysis({"face": ["x"], "hair": ["y"]})
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face", "hair"), analysis=analysis)
    )
    orders = {t.scope: t.order for t in plan.tasks}
    assert orders == {"face": 30, "hair": 20}


def test_missing_scope_features_produce_enabled_fallback_with_warning() -> None:
    analysis = _analysis({})  # no features at all
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("hands",), analysis=analysis)
    )
    task = plan.tasks[0]
    assert task.enabled is True
    assert task.extracted_features == ()
    assert task.prompt_final.strip()  # non-empty, preset-based
    assert any("hands" in w for w in plan.warnings)
    assert validate_plan(plan) == ()


def test_does_not_invent_attributes_beyond_extracted() -> None:
    analysis = _analysis({"face": ["dark brown eyes"]})
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face",), analysis=analysis)
    )
    assert plan.tasks[0].prompt_core == "dark brown eyes"


def test_forbidden_terms_removed_from_prompt_final_with_task_warning() -> None:
    analysis = _analysis({"face": ["beautiful eyes"]})
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face",), analysis=analysis)
    )
    task = plan.tasks[0]
    assert "beautiful" not in task.prompt_final.lower()
    assert any("forbidden" in w.lower() for w in task.warnings)


def test_is_deterministic() -> None:
    analysis = _analysis({"face": ["dark brown eyes"], "hair": ["short black hair"]})
    a = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face", "hair"), analysis=analysis)
    )
    b = build_detailer_plan(
        PlanBuildInput(requested_scopes=("face", "hair"), analysis=analysis)
    )
    assert a == b


def test_empty_subject_id_is_rejected_by_builder() -> None:
    analysis = _analysis({"face": ["x"]})
    with pytest.raises(PlanValidationError):
        build_detailer_plan(
            PlanBuildInput(requested_scopes=("face",), analysis=analysis, subject_id="")
        )


def test_custom_subject_id_used_in_task_id() -> None:
    analysis = _analysis({"face": ["x"]})
    plan = build_detailer_plan(
        PlanBuildInput(
            requested_scopes=("face",), analysis=analysis, subject_id="left_person"
        )
    )
    assert plan.tasks[0].task_id == "left_person.face"
