"""Unit tests for verbatim evidence matching (domain/evidence).

Requirements 3.8, 3.9, 3.11, 3.15-3.17, 3.19: a feature survives only if it
occurs in the original prompt verbatim (after NFC + casefold) at a word
boundary, where "boundary" means the adjacent character is not a Unicode
alphanumeric. Processing order is strip -> drop blanks -> match, and the value
carried forward is the *stripped original*, not the normalized one.
"""

import pytest

from prompt_detailer_router.domain.evidence import (
    build_evidence_text,
    filter_by_evidence,
)


def _keep(prompt: str, *features: str) -> tuple[str, ...]:
    return filter_by_evidence(features, build_evidence_text(prompt)).kept


def _drop(prompt: str, *features: str) -> tuple[str, ...]:
    return filter_by_evidence(features, build_evidence_text(prompt)).dropped


# --- plain verbatim matching ---

def test_feature_present_verbatim_is_kept() -> None:
    assert _keep("a woman with blue eyes", "blue eyes") == ("blue eyes",)


def test_feature_absent_from_the_prompt_is_dropped() -> None:
    assert _drop("a woman with blue eyes", "green eyes") == ("green eyes",)


def test_paraphrased_feature_is_dropped() -> None:
    # Requirement 3.15 accepts that a reworded feature is discarded.
    assert _drop("short black hair", "hair that is black") == ("hair that is black",)


def test_inflected_feature_is_dropped() -> None:
    assert _drop("a red glove", "gloves") == ("gloves",)


def test_matching_is_case_insensitive() -> None:
    assert _keep("A Woman with BLUE EYES", "blue eyes") == ("blue eyes",)
    assert _keep("a woman with blue eyes", "BLUE Eyes") == ("BLUE Eyes",)


def test_matching_is_nfc_insensitive() -> None:
    # "é" as U+00E9 vs "e" + U+0301 must be treated as the same text.
    assert _keep("a café interior", "café") == ("café",)
    assert _keep("a café interior", "café") == ("café",)


def test_casefold_handles_sharp_s() -> None:
    # casefold("ß") == "ss": the normalized lengths differ, which is why
    # positions are never mapped back to the original string.
    assert _keep("a STRASSE at night", "Straße") == ("Straße",)


# --- word boundaries (Requirements 3.8, 3.16) ---

def test_match_starting_inside_a_word_is_dropped() -> None:
    # "man" inside "woman": the character before the match is alphanumeric.
    assert _drop("a woman in a red coat", "man") == ("man",)


def test_match_ending_inside_a_word_is_dropped() -> None:
    # "blue" inside "blueberry": the character after the match is alphanumeric.
    assert _drop("a blueberry portrait", "blue") == ("blue",)


def test_match_surrounded_by_word_characters_is_dropped() -> None:
    assert _drop("unremarkable", "remark") == ("remark",)


def test_underscore_counts_as_a_boundary() -> None:
    # "_" is not alnum in Unicode, so "perfect_face" grounds "face"
    # (Requirement 3.16).
    assert _keep("perfect_face rendering", "face") == ("face",)


def test_punctuation_counts_as_a_boundary() -> None:
    assert _keep("portrait, blue eyes, soft light", "blue eyes") == ("blue eyes",)
    assert _keep("(masterpiece) blue eyes", "masterpiece") == ("masterpiece",)


def test_string_edges_count_as_boundaries() -> None:
    assert _keep("blue eyes", "blue eyes") == ("blue eyes",)
    assert _keep("blue", "blue") == ("blue",)


def test_a_later_bounded_occurrence_still_grounds_the_feature() -> None:
    # The first occurrence is inside a word; a later one is properly bounded.
    assert _keep("blueberry and blue sky", "blue") == ("blue",)


def test_digits_are_word_characters_on_both_sides() -> None:
    assert _drop("model3face shot", "face") == ("face",)
    assert _drop("face3d render", "face") == ("face",)


def test_non_ascii_alphanumerics_are_word_characters() -> None:
    # Unicode alnum, not the ASCII-only set the core forbidden-term matcher uses
    # (Requirement 3.16).
    assert _drop("ブルーあか", "あ") == ("あ",)


# --- processing order: strip -> drop blanks -> match (Requirements 3.11, 3.19) ---

def test_surrounding_whitespace_is_stripped_before_matching() -> None:
    result = filter_by_evidence(["  blue eyes  "], build_evidence_text("blue eyes"))
    assert result.kept == ("blue eyes",)
    assert result.dropped == ()


def test_blank_features_are_counted_not_dropped_as_unmatched() -> None:
    result = filter_by_evidence(
        ["", "   ", "\t\n", "blue eyes"], build_evidence_text("blue eyes")
    )
    assert result.kept == ("blue eyes",)
    assert result.dropped == ()
    assert result.blank_dropped_count == 3


def test_blank_count_is_zero_when_no_blank_elements() -> None:
    result = filter_by_evidence(["blue eyes"], build_evidence_text("blue eyes"))
    assert result.blank_dropped_count == 0


def test_kept_value_is_the_stripped_original_not_the_normalized_form() -> None:
    result = filter_by_evidence(["  BLUE Eyes "], build_evidence_text("blue eyes"))
    assert result.kept == ("BLUE Eyes",)


def test_dropped_value_is_also_the_stripped_original() -> None:
    result = filter_by_evidence(["  GREEN eyes "], build_evidence_text("blue eyes"))
    assert result.dropped == ("GREEN eyes",)


# --- result shape ---

def test_order_is_preserved_across_kept_and_dropped() -> None:
    result = filter_by_evidence(
        ["blue eyes", "green eyes", "soft light", "harsh light"],
        build_evidence_text("blue eyes under soft light"),
    )
    assert result.kept == ("blue eyes", "soft light")
    assert result.dropped == ("green eyes", "harsh light")


def test_duplicate_features_are_not_deduplicated_here() -> None:
    # Deduplication belongs to the core builders, not to evidence matching.
    result = filter_by_evidence(
        ["blue eyes", "blue eyes"], build_evidence_text("blue eyes")
    )
    assert result.kept == ("blue eyes", "blue eyes")


def test_empty_feature_sequence_yields_empty_result() -> None:
    result = filter_by_evidence([], build_evidence_text("anything"))
    assert (result.kept, result.dropped, result.blank_dropped_count) == ((), (), 0)


def test_empty_prompt_grounds_nothing() -> None:
    result = filter_by_evidence(["blue eyes"], build_evidence_text(""))
    assert result.kept == ()
    assert result.dropped == ("blue eyes",)


def test_result_is_immutable() -> None:
    result = filter_by_evidence(["blue eyes"], build_evidence_text("blue eyes"))
    with pytest.raises(Exception):
        result.kept = ()  # type: ignore[misc]


# --- build_evidence_text ---

def test_build_evidence_text_applies_nfc_and_casefold() -> None:
    assert build_evidence_text("Café STRASSE") == "café strasse"
    assert build_evidence_text("Straße") == "strasse"


def test_no_regex_is_used_for_matching() -> None:
    # Regex-special characters in a feature are matched literally, which also
    # shows no pattern compilation happens (AGENTS.md 22.3: no ReDoS surface).
    assert _keep("a (masterpiece) [detailed] photo", "(masterpiece)") == (
        "(masterpiece)",
    )
    assert _drop("a masterpiece photo", "m.sterpiece") == ("m.sterpiece",)
