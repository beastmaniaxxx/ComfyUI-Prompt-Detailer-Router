"""Forbidden-term removal (deterministic, LLM-independent).

Pure domain logic (Requirements 9.2, 9.3, 9.5). Applies a shared, versioned
forbidden-terms policy to a finalized string. Matching is
``case_insensitive_literal`` with word boundaries so a banned word is removed as
a whole word without mutilating longer words (e.g. "perfect" is not stripped
from "imperfect"). Whitespace is normalized after removal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from prompt_detailer_router.domain.prompt_text import (
    normalize_whitespace,
    repair_separators,
)

CASE_INSENSITIVE_LITERAL = "case_insensitive_literal"


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


def apply_forbidden_terms(
    text: str, terms: Sequence[str], match: str = CASE_INSENSITIVE_LITERAL
) -> ForbiddenScanResult:
    """Remove forbidden ``terms`` from ``text`` per the ``match`` mode.

    v1 supports the ``case_insensitive_literal`` mode only; other modes raise
    ``ValueError`` rather than silently mismatching.
    """

    if match != CASE_INSENSITIVE_LITERAL:
        raise ValueError(f"Unsupported forbidden-term match mode: {match!r}")

    working = text
    removed_terms: list[str] = []
    total = 0
    for term in terms:
        if not term:
            continue
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        working, count = pattern.subn("", working)
        if count:
            removed_terms.append(term)
            total += count

    cleaned = normalize_whitespace(repair_separators(normalize_whitespace(working)))
    return ForbiddenScanResult(
        text=cleaned,
        removed_count=total,
        removed_terms=tuple(removed_terms),
    )
