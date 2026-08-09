"""Forbidden-term removal (deterministic, LLM-independent).

Pure domain logic (Requirements 9.2, 9.3, 9.5). Applies a shared, versioned
forbidden-terms policy to a finalized string. Matching is
``case_insensitive_literal`` with word boundaries so a banned word is removed as
a whole word without mutilating longer words (e.g. "perfect" is not stripped
from "imperfect"). Separator/bracket repair after removal is confined to the
exact spots a term was removed, so punctuation that was already in the input
away from any removal (e.g. an ellipsis in "cinematic... portrait") is preserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from prompt_detailer_router.domain.prompt_text import normalize_whitespace

CASE_INSENSITIVE_LITERAL = "case_insensitive_literal"

# Underscores are common word separators in generation prompts, so a forbidden
# term must be matched when delimited by ``_`` (e.g. "perfect_face"). Using
# alphanumeric look-arounds treats ``_`` as a boundary while still refusing
# matches inside longer words like "imperfect".
_ALNUM_LEFT = r"(?<![A-Za-z0-9])"
_ALNUM_RIGHT = r"(?![A-Za-z0-9])"

# A private sentinel marks each spot where a term was removed, so separator and
# bracket repair (Req 9.3) can be confined to the immediate neighbourhood of a
# removal. It is a control character that never appears in a normal prompt (any
# stray occurrence in the input is stripped up front).
_SENTINEL = "\x00"
_S = re.escape(_SENTINEL)

# Strip underscores left dangling at a token boundary after a term is removed
# (e.g. "_face" -> "face", "very__face" -> "very_face"), without touching
# intra-token underscores such as "upper_body".
_ORPHAN_UNDERSCORE_LEFT = re.compile(r"(?<![A-Za-z0-9])_+")
_ORPHAN_UNDERSCORE_RIGHT = re.compile(r"_+(?![A-Za-z0-9])")

# Repairs applied ONLY around a sentinel (i.e. exactly where a term was removed):
#   - an empty bracket pair that wrapped the removed term: "(sentinel)" -> ""
#   - a separator orphaned on both sides: "a, sentinel, b" -> "a, b"
#   - a separator left dangling at the string start/end by the removal.
_SENT_EMPTY_BRACKETS = re.compile(rf"[(\[{{]\s*{_S}\s*[)\]}}]")
_SENT_BETWEEN_SEPARATORS = re.compile(rf"[,;.]\s*{_S}\s*([,;.])")
_SENT_LEADING_SEPARATOR = re.compile(rf"^\s*{_S}\s*[,;.]")
_SENT_TRAILING_SEPARATOR = re.compile(rf"[,;.]\s*{_S}\s*$")


@dataclass(frozen=True, slots=True)
class ForbiddenScanResult:
    """Result of removing forbidden terms from a text.

    ``text`` is the cleaned, whitespace-normalized output. ``removed_count`` is
    the total number of occurrences removed. ``removed_terms`` lists the distinct
    policy terms that matched, in policy order.
    """

    text: str
    removed_count: int
    removed_terms: tuple[str, ...]


def _repair_removal_sites(working: str) -> str:
    """Clean up separators/brackets left exactly where terms were removed.

    Operates on a string still carrying sentinels at each removal site, so the
    repair cannot reach unrelated punctuation elsewhere in the text. The
    sentinels are dropped at the end, then underscores orphaned by the removal
    are tidied.
    """

    working = _SENT_EMPTY_BRACKETS.sub(_SENTINEL, working)
    working = _SENT_BETWEEN_SEPARATORS.sub(rf"{_SENTINEL}\1", working)
    working = _SENT_LEADING_SEPARATOR.sub(_SENTINEL, working)
    working = _SENT_TRAILING_SEPARATOR.sub(_SENTINEL, working)
    working = working.replace(_SENTINEL, "")
    working = _ORPHAN_UNDERSCORE_LEFT.sub("", working)
    working = _ORPHAN_UNDERSCORE_RIGHT.sub("", working)
    return working


def apply_forbidden_terms(
    text: str, terms: Sequence[str], match: str = CASE_INSENSITIVE_LITERAL
) -> ForbiddenScanResult:
    """Remove forbidden ``terms`` from ``text`` per the ``match`` mode.

    v1 supports the ``case_insensitive_literal`` mode only; other modes raise
    ``ValueError`` rather than silently mismatching.
    """

    if match != CASE_INSENSITIVE_LITERAL:
        raise ValueError(f"Unsupported forbidden-term match mode: {match!r}")

    # The sentinel is an internal marker; never let one from the input survive.
    working = text.replace(_SENTINEL, "")
    removed_terms: list[str] = []
    total = 0
    for term in terms:
        if not term:
            continue
        pattern = re.compile(
            rf"{_ALNUM_LEFT}{re.escape(term)}{_ALNUM_RIGHT}", re.IGNORECASE
        )
        working, count = pattern.subn(_SENTINEL, working)
        if count:
            removed_terms.append(term)
            total += count

    # Repair only where a term was actually removed; unrelated input (including
    # legitimate ellipses or empty brackets) is preserved verbatim.
    if total:
        working = _repair_removal_sites(working)
    cleaned = normalize_whitespace(working)
    return ForbiddenScanResult(
        text=cleaned,
        removed_count=total,
        removed_terms=tuple(removed_terms),
    )
