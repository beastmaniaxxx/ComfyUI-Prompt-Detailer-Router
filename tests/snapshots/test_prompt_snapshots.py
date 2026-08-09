"""Snapshot tests for finalized prompts.

Covers Requirements 8.4 (per-scope detailer prompts for all 7 scopes) and 14.6
(snapshot diff detection for upscale + detailer prompts and warnings). A
scope-isolation assertion demonstrates that a preset change would surface only
in that scope's prompt (reference acceptance: "face preset change affects the
face snapshot only").

Regenerate snapshots intentionally with: PDR_UPDATE_SNAPSHOTS=1 pytest
"""

import os
from pathlib import Path

import pytest

from prompt_detailer_router.application.build_detailer_plan import (
    PlanBuildInput,
    build_detailer_plan,
)
from prompt_detailer_router.application.build_upscale_prompt import build_upscale_prompt
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis

SEVEN = ("face", "hair", "hands", "body", "upper_body", "clothing", "generic")
SNAPSHOT_DIR = Path(__file__).resolve().parent
_UPDATE = os.environ.get("PDR_UPDATE_SNAPSHOTS") == "1"


def _assert_snapshot(name: str, actual: str) -> None:
    path = SNAPSHOT_DIR / name
    if _UPDATE:
        path.write_text(actual, encoding="utf-8")
    expected = path.read_text(encoding="utf-8")  # missing snapshot -> failure
    assert actual == expected, f"snapshot mismatch for {name}"


def _canonical_analysis() -> PromptAnalysis:
    return PromptAnalysis(
        global_features={
            "style": ["photorealistic"],
            "lighting": ["soft window light"],
            "material": ["gray wool fabric"],
        },
        scoped_features={
            "face": ["dark brown eyes", "fair skin"],
            "hair": ["short black hair"],
            "hands": ["slender fingers"],
            "body": ["seated posture"],
            "upper_body": ["fitted blazer"],
            "clothing": ["gray wool suit"],
            "generic": ["ceramic mug"],
        },
        warnings=(),
    )


def _plan():
    return build_detailer_plan(
        PlanBuildInput(requested_scopes=SEVEN, analysis=_canonical_analysis())
    )


def test_upscale_prompt_snapshot() -> None:
    result = build_upscale_prompt(_canonical_analysis(), "photographic")
    _assert_snapshot("upscale_photographic.txt", result.upscale_prompt)


@pytest.mark.parametrize("scope", SEVEN)
def test_detailer_prompt_snapshot(scope: str) -> None:
    plan = _plan()
    task = next(t for t in plan.tasks if t.scope == scope)
    _assert_snapshot(f"detailer_{scope}.txt", task.prompt_final)


def test_plan_warnings_snapshot() -> None:
    plan = _plan()
    _assert_snapshot("plan_warnings.txt", "\n".join(plan.warnings))


def test_scope_isolation_between_presets() -> None:
    # Each scope's prompt reflects only its own preset's local_details, so a
    # preset change would surface only in that scope's snapshot.
    plan = _plan()
    by_scope = {t.scope: t.prompt_final for t in plan.tasks}
    assert "subtle pores" in by_scope["face"]
    assert "subtle pores" not in by_scope["hair"]
    assert "strand grouping" in by_scope["hair"]
    assert "strand grouping" not in by_scope["face"]
