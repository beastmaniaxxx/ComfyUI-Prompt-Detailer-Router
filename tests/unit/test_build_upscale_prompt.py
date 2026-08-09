"""Unit tests for the Upscale Prompt Builder (application/build_upscale_prompt).

Covers Requirements 7.1 (compose from extracted globals + preset), 7.2 (no
invented subject attributes), 7.3 (determinism), 9.4 (forbidden-term filtering).
"""

from prompt_detailer_router.application.build_upscale_prompt import build_upscale_prompt
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis


def _analysis(**global_features) -> PromptAnalysis:
    return PromptAnalysis(
        global_features=global_features or {"style": ["photorealistic"]},
        scoped_features={},
        warnings=(),
    )


def test_includes_extracted_globals_and_preset_text() -> None:
    analysis = _analysis(
        style=["photorealistic"],
        lighting=["soft window light"],
        material=["gray wool fabric"],
    )
    result = build_upscale_prompt(analysis, "photographic")
    prompt = result.upscale_prompt
    assert "photorealistic" in prompt
    assert "soft window light" in prompt
    assert "gray wool fabric" in prompt
    # preset quality_details / preservation text present
    assert "Refine" in prompt
    assert "Keep the original composition" in prompt


def test_does_not_invent_subject_attributes() -> None:
    analysis = _analysis(style=["photorealistic"])
    prompt = build_upscale_prompt(analysis, "photographic").upscale_prompt
    # nothing that was not in the analysis or preset should appear
    assert "blue eyes" not in prompt
    assert "smiling" not in prompt


def test_is_deterministic() -> None:
    analysis = _analysis(style=["photorealistic"], lighting=["soft light"])
    a = build_upscale_prompt(analysis, "photographic")
    b = build_upscale_prompt(analysis, "photographic")
    assert a == b


def test_forbidden_terms_removed_with_warning() -> None:
    analysis = _analysis(style=["beautiful photorealistic style"])
    result = build_upscale_prompt(analysis, "photographic")
    assert "beautiful" not in result.upscale_prompt.lower()
    assert "photorealistic" in result.upscale_prompt
    assert result.warnings, "removing a forbidden term should surface a warning"


def test_empty_globals_still_produces_preset_based_prompt() -> None:
    analysis = PromptAnalysis(global_features={}, scoped_features={}, warnings=())
    prompt = build_upscale_prompt(analysis, "minimal").upscale_prompt
    assert prompt.strip()
    assert "Refine" in prompt


def test_photographic_preset_is_subject_agnostic() -> None:
    # For a non-person image the photographic preset must not force body/fabric
    # attributes into the prompt (Req 7.2).
    analysis = PromptAnalysis(
        global_features={"style": ["product photo"], "environment": ["white background"]},
        scoped_features={},
        warnings=(),
    )
    prompt = build_upscale_prompt(analysis, "photographic").upscale_prompt.lower()
    for term in ("skin", "pores", "hair strand", "fabric"):
        assert term not in prompt
