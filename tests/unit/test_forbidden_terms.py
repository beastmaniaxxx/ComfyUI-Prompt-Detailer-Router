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


def test_underscore_delimited_terms_are_removed() -> None:
    for text, term in [
        ("perfect_face", "perfect"),
        ("beautiful_skin", "beautiful"),
        ("symmetrical_eyes", "symmetrical"),
    ]:
        result = apply_forbidden_terms(text, TERMS, MATCH)
        assert result.removed_count == 1
        assert term not in result.text.lower()


def test_underscore_removal_leaves_no_orphan_underscore() -> None:
    result = apply_forbidden_terms("perfect_face", TERMS, MATCH)
    assert result.text == "face"
    result2 = apply_forbidden_terms("very_beautiful_face", TERMS, MATCH)
    assert result2.text == "very_face"


def test_longer_word_still_not_matched_with_underscore_boundary() -> None:
    result = apply_forbidden_terms("an imperfect result", TERMS, MATCH)
    assert result.removed_count == 0
    assert "imperfect" in result.text


def test_intra_token_underscore_is_preserved() -> None:
    # A legitimate underscore token must survive even when another term is removed.
    result = apply_forbidden_terms("upper_body, beautiful detail", TERMS, MATCH)
    assert "upper_body" in result.text
    assert "beautiful" not in result.text.lower()


def test_leading_period_repaired_after_removal() -> None:
    result = apply_forbidden_terms("beautiful. photorealistic", TERMS, MATCH)
    assert result.text == "photorealistic"


def test_double_period_repaired_after_removal() -> None:
    result = apply_forbidden_terms("face. beautiful. hair", TERMS, MATCH)
    assert result.text == "face. hair"


def test_empty_brackets_removed_after_removal() -> None:
    result = apply_forbidden_terms("(beautiful), face", TERMS, MATCH)
    assert result.text == "face"
    assert "()" not in result.text


def test_multi_sentence_text_is_preserved() -> None:
    # No removal: legitimate multi-sentence text keeps its periods intact.
    text = "Keep the shape. Refine the texture. Do not redesign."
    result = apply_forbidden_terms(text, TERMS, MATCH)
    assert result.text == text


def test_no_removal_preserves_adjacent_separators() -> None:
    # When nothing is removed, separator repair must NOT run: an ellipsis or
    # repeated punctuation in unrelated input is preserved verbatim (only
    # whitespace is normalized). Repair is reserved for artifacts left by an
    # actual removal.
    result = apply_forbidden_terms("cinematic... dreamlike", TERMS, MATCH)
    assert result.removed_count == 0
    assert result.text == "cinematic... dreamlike"


def test_no_removal_preserves_empty_brackets() -> None:
    # A user's literal "()" is not an artifact when no term was removed.
    result = apply_forbidden_terms("style () tag", TERMS, MATCH)
    assert result.removed_count == 0
    assert result.text == "style () tag"


def test_repair_is_confined_to_the_removal_site() -> None:
    # A removal elsewhere must not disturb a legitimate ellipsis (or other
    # punctuation) that is not adjacent to the removed term.
    result = apply_forbidden_terms(
        "cinematic... portrait, beautiful eyes", TERMS, MATCH
    )
    assert result.removed_count == 1
    assert result.text == "cinematic... portrait, eyes"


def test_separator_orphaned_by_removal_is_still_repaired() -> None:
    # The comma orphaned by removing the list item is repaired, while the
    # unrelated ellipsis earlier in the string is preserved.
    result = apply_forbidden_terms(
        "cinematic... portrait, beautiful, eyes", TERMS, MATCH
    )
    assert result.text == "cinematic... portrait, eyes"


def test_consecutive_removals_leave_no_residual_separators() -> None:
    # Consecutive forbidden terms leave adjacent removal markers; the repair must
    # run to a fixpoint so no dangling separators or empty brackets survive
    # (Issue #3 / Req 9.3).
    assert apply_forbidden_terms("beautiful, perfect, face", TERMS, MATCH).text == (
        "face"
    )
    assert apply_forbidden_terms(
        "face, beautiful, perfect, hair", TERMS, MATCH
    ).text == "face, hair"
    assert apply_forbidden_terms(
        "(beautiful perfect), face", TERMS, MATCH
    ).text == "face"


def test_bracketed_separator_delimited_consecutive_removals() -> None:
    # Consecutive terms separated by a separator *inside* a bracket must not leave
    # residual separators or empty brackets (PR#4 review / Req 9.3).
    assert apply_forbidden_terms(
        "(beautiful, perfect), face", TERMS, MATCH
    ).text == "face"
    assert apply_forbidden_terms(
        "[beautiful; perfect], face", TERMS, MATCH
    ).text == "face"
    assert apply_forbidden_terms(
        "{beautiful. perfect}, face", TERMS, MATCH
    ).text == "face"


def test_preexisting_empty_brackets_kept_even_with_a_removal() -> None:
    # An empty bracket pair the user wrote is not a removal artifact, so it is
    # preserved even when a term is removed elsewhere in the string.
    assert apply_forbidden_terms(
        "render () beautiful thing", TERMS, MATCH
    ).text == "render () thing"


def test_deeply_nested_brackets_are_linear_not_quadratic() -> None:
    # A term wrapped in thousands of nested brackets must be repaired in bulk
    # (linear), not by re-scanning once per nesting level (PR#4 review: avoid a
    # quadratic fixpoint that stalls ComfyUI on schema-valid but pathological
    # input). A quadratic implementation takes seconds; linear is well under 1s.
    import time

    depth = 20000
    pathological = "(" * depth + "beautiful" + ")" * depth
    start = time.perf_counter()
    result = apply_forbidden_terms(pathological, TERMS, MATCH)
    elapsed = time.perf_counter() - start
    assert result.text == ""
    assert result.removed_count == 1
    assert elapsed < 1.0
