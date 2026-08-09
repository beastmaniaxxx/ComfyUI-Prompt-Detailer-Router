"""Unit tests for forbidden-term removal (domain/forbidden_terms).

Covers Requirements 9.2 (scan the finalized combined text), 9.3 (remove and
report count), 9.5 (deterministic, not delegated to an LLM).
"""

from prompt_detailer_router.domain.forbidden_terms import apply_forbidden_terms

TERMS = ("beautiful", "perfect", "symmetrical")
MATCH = "case_insensitive_literal"


def test_removes_terms_case_insensitively_and_counts() -> None:
    result = apply_forbidden_terms(
        "A beautiful and Perfect, SYMMETRICAL face", TERMS, MATCH
    )
    assert result.removed_count == 3
    lowered = result.text.lower()
    assert "beautiful" not in lowered
    assert "perfect" not in lowered
    assert "symmetrical" not in lowered
    assert set(result.removed_terms) == {"beautiful", "perfect", "symmetrical"}


def test_no_forbidden_terms_leaves_text_intact() -> None:
    result = apply_forbidden_terms("A natural face", TERMS, MATCH)
    assert result.removed_count == 0
    assert result.removed_terms == ()
    assert result.text == "A natural face"


def test_output_whitespace_is_normalized_after_removal() -> None:
    result = apply_forbidden_terms("beautiful   face", TERMS, MATCH)
    assert result.text == "face"
    assert "  " not in result.text
    assert result.text == result.text.strip()


def test_word_boundary_prevents_partial_word_mutilation() -> None:
    # "perfect" must not be stripped out of "imperfect".
    result = apply_forbidden_terms("an imperfect result", TERMS, MATCH)
    assert result.removed_count == 0
    assert "imperfect" in result.text


def test_counts_repeated_occurrences() -> None:
    result = apply_forbidden_terms("perfect perfect", TERMS, MATCH)
    assert result.removed_count == 2


def test_is_deterministic() -> None:
    a = apply_forbidden_terms("Beautiful face", TERMS, MATCH)
    b = apply_forbidden_terms("Beautiful face", TERMS, MATCH)
    assert a == b


def test_leading_separator_repaired_after_removal() -> None:
    result = apply_forbidden_terms("beautiful, photorealistic", TERMS, MATCH)
    assert result.text == "photorealistic"


def test_middle_separator_repaired_after_removal() -> None:
    result = apply_forbidden_terms("face, beautiful, hair", TERMS, MATCH)
    assert result.text == "face, hair"


def test_trailing_separator_repaired_after_removal() -> None:
    result = apply_forbidden_terms("photorealistic, beautiful", TERMS, MATCH)
    assert result.text == "photorealistic"


def test_no_dangling_punctuation_remains() -> None:
    result = apply_forbidden_terms("a beautiful, perfect, natural face", TERMS, MATCH)
    assert ",," not in result.text
    assert not result.text.startswith(",")
    assert not result.text.strip().endswith(",")
