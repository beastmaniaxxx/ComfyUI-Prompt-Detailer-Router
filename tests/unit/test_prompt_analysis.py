"""Unit tests for the PromptAnalysis domain model (domain/prompt_analysis).

Covers Requirement 6.1 (validated extraction result feeding the builders) and
13.3 (a source-agnostic domain type; no transport concerns).
"""

import dataclasses

import pytest

from prompt_detailer_router.domain.prompt_analysis import (
    PromptAnalysis,
    features_for_scope,
)


def _analysis() -> PromptAnalysis:
    return PromptAnalysis(
        global_features={"style": ["photorealistic"], "lighting": ["soft light"]},
        scoped_features={"face": ["dark brown eyes"], "hair": ["short black hair"]},
        warnings=["example warning"],
    )


def test_features_for_scope_returns_tuple() -> None:
    analysis = _analysis()
    assert features_for_scope(analysis, "face") == ("dark brown eyes",)


def test_features_for_missing_scope_is_empty() -> None:
    assert features_for_scope(_analysis(), "hands") == ()


def test_values_are_coerced_to_tuples() -> None:
    analysis = _analysis()
    assert isinstance(analysis.scoped_features["face"], tuple)
    assert isinstance(analysis.global_features["style"], tuple)
    assert isinstance(analysis.warnings, tuple)


def test_model_is_frozen() -> None:
    analysis = _analysis()
    with pytest.raises(dataclasses.FrozenInstanceError):
        analysis.warnings = ()  # type: ignore[misc]


def test_backing_mappings_are_not_externally_mutable() -> None:
    analysis = _analysis()
    with pytest.raises(TypeError):
        analysis.scoped_features["face"] = ("x",)  # type: ignore[index]
