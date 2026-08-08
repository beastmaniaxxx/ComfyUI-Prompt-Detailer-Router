"""Unit tests for prompt-text helpers and ordered dedup.

Supports Requirements 7 and 8 (deterministic prompt composition helpers used
by the builders) via domain/prompt_text and utils/collections.
"""

from prompt_detailer_router.domain import prompt_text
from prompt_detailer_router.utils import collections


def test_ordered_unique_preserves_first_occurrence() -> None:
    assert collections.ordered_unique([3, 1, 3, 2, 1]) == (3, 1, 2)


def test_ordered_unique_is_case_sensitive_for_strings() -> None:
    assert collections.ordered_unique(["a", "A", "a"]) == ("a", "A")


def test_normalize_whitespace_collapses_runs_and_strips() -> None:
    assert prompt_text.normalize_whitespace("  a   b  ") == "a b"


def test_normalize_whitespace_tidies_space_before_punctuation() -> None:
    assert prompt_text.normalize_whitespace("a  ,  b .") == "a, b."


def test_join_prompt_drops_empty_parts() -> None:
    assert prompt_text.join_prompt(["a.", "", "   ", "b."]) == "a. b."


def test_dedup_features_strips_drops_empty_and_dedups() -> None:
    assert prompt_text.dedup_features(
        ["dark eyes", "dark eyes", "", "  pale skin  "]
    ) == ("dark eyes", "pale skin")
