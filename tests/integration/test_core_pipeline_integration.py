"""Integration: fixture extraction -> plan build -> JSON round trip.

Covers Requirements 6.1-6.3 (build from a validated analysis, fallback for
missing scopes), 7.2 (upscale adds no invented subject facts), 12.3 (codec round
trip preserves information), 14.1 (runs without ComfyUI/Ollama, fixtures only).
The fixtures also validate against the Ollama response schema (13.1).
"""

import json
from pathlib import Path

import pytest

from prompt_detailer_router.application.build_detailer_plan import (
    PlanBuildInput,
    build_detailer_plan,
)
from prompt_detailer_router.application.build_upscale_prompt import build_upscale_prompt
from prompt_detailer_router.domain.detailer_plan import validate_plan
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis
from prompt_detailer_router.infrastructure.json_codec import decode_plan, encode_plan
from prompt_detailer_router.infrastructure.schema_loader import (
    get_ollama_response_validator,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _to_analysis(data: dict) -> PromptAnalysis:
    return PromptAnalysis(
        global_features=data.get("global", {}),
        scoped_features=data.get("scoped_features", {}),
        warnings=data.get("warnings", []),
    )


# Diverse fixtures required by task 6.2: photographic, illustration, face
# close-up, full body, no person, short prompt, and contradictory features.
FIXTURE_CASES = [
    ("analysis_photographic.json", ("face", "hair")),
    ("analysis_photographic.json", ("face", "hair", "hands", "body")),
    ("analysis_illustration.json", ("face", "hair")),
    ("analysis_face_closeup.json", ("face",)),
    ("analysis_full_body.json", ("face", "hair", "hands", "upper_body", "clothing", "body")),
    ("analysis_no_person.json", ("generic",)),
    ("analysis_short.json", ("face",)),
    ("analysis_contradictory.json", ("face", "hair")),
]


@pytest.mark.parametrize("fixture,scopes", FIXTURE_CASES)
def test_fixture_response_conforms_to_schema(fixture: str, scopes) -> None:
    data = _load_fixture(fixture)
    assert list(get_ollama_response_validator().iter_errors(data)) == []


@pytest.mark.parametrize("fixture,scopes", FIXTURE_CASES)
def test_plan_build_then_json_round_trip(fixture: str, scopes) -> None:
    analysis = _to_analysis(_load_fixture(fixture))
    plan = build_detailer_plan(PlanBuildInput(requested_scopes=scopes, analysis=analysis))

    assert validate_plan(plan) == ()
    assert [t.task_id for t in plan.tasks] == [f"main.{s}" for s in scopes]

    # Round trip is information-preserving.
    assert decode_plan(encode_plan(plan)) == plan


@pytest.mark.parametrize("fixture,scopes", FIXTURE_CASES)
def test_media_and_global_terms_do_not_leak_into_detailer_tasks(fixture: str, scopes) -> None:
    # Detailer prompt_core is limited to the scope's own extracted features, so
    # global/medium terms (e.g. "illustration", "photo") must not appear there.
    data = _load_fixture(fixture)
    analysis = _to_analysis(data)
    plan = build_detailer_plan(PlanBuildInput(requested_scopes=scopes, analysis=analysis))
    global_terms = {
        term.lower()
        for values in data.get("global", {}).values()
        for term in values
    }
    for task in plan.tasks:
        scoped = {f.lower() for f in analysis.scoped_features.get(task.scope, ())}
        leaked = {f.lower() for f in task.extracted_features} - scoped
        assert not leaked, f"{fixture}:{task.scope} leaked features {leaked}"
        for gterm in global_terms:
            assert gterm not in task.prompt_core.lower()


def test_short_and_contradictory_inputs_still_round_trip() -> None:
    for fixture, scopes in [
        ("analysis_short.json", ("face", "hair")),
        ("analysis_contradictory.json", ("face", "hair", "hands")),
    ]:
        analysis = _to_analysis(_load_fixture(fixture))
        plan = build_detailer_plan(
            PlanBuildInput(requested_scopes=scopes, analysis=analysis)
        )
        assert validate_plan(plan) == ()
        # Scopes without extracted features fall back to enabled preset-only tasks.
        for task in plan.tasks:
            assert task.enabled and task.prompt_final.strip()
        assert decode_plan(encode_plan(plan)) == plan


def test_missing_scope_features_yield_fallback_task() -> None:
    analysis = _to_analysis(_load_fixture("analysis_no_person.json"))
    plan = build_detailer_plan(
        PlanBuildInput(requested_scopes=("generic",), analysis=analysis)
    )
    task = plan.tasks[0]
    assert task.enabled and task.extracted_features == ()
    assert task.prompt_final.strip()
    assert any("generic" in w for w in plan.warnings)


def test_upscale_prompt_does_not_inject_unstated_subject() -> None:
    analysis = _to_analysis(_load_fixture("analysis_photographic.json"))
    prompt = build_upscale_prompt(analysis, "photographic").upscale_prompt
    assert "photorealistic" in prompt
    # scoped face features must not leak into the global upscale prompt
    assert "dark brown eyes" not in prompt
