"""Verbatim evidence matching for extracted features.

Pure domain logic (Requirements 3.8, 3.9, 3.11, 3.15-3.17, 3.19). A feature is
kept only when it occurs in ``original_prompt`` verbatim -- after NFC
normalization and casefolding -- at a word boundary. This is what stops an LLM
from inventing a feature that then enters ``prompt_final`` as established fact.

Two details matter:

* Boundary means "the adjacent character is not a Unicode alphanumeric", so
  ``man`` is not grounded by ``woman`` and ``blue`` is not grounded by
  ``blueberry``. ``_`` is not alphanumeric, so ``perfect_face`` does ground
  ``face`` (Requirement 3.16). This set deliberately differs from the ASCII-only
  set the core forbidden-term matcher uses; the two have different purposes.
* Casefolding can change a string's length (``ß`` -> ``ss``), so a position in
  normalized space is never mapped back to the original. Matching happens
  entirely in normalized space, and the value carried forward is the stripped
  *original* text (Requirement 3.19).

Matching uses ``str.find`` in a loop and stops at the first bounded occurrence.
No regex is involved, so there is no backtracking; the cost is at worst
O(len(prompt) x len(feature)) per feature with no iteration cap.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class EvidenceFilterResult:
    """Outcome of grounding a feature list against the original prompt.

    ``kept`` and ``dropped`` hold the whitespace-stripped original spellings.
    ``blank_dropped_count`` counts elements that were empty after stripping
    (Requirement 3.11) -- these are neither kept nor dropped, since there is no
    feature text to report.
    """

    kept: tuple[str, ...]
    dropped: tuple[str, ...]
    blank_dropped_count: int


def build_evidence_text(original_prompt: str) -> str:
    """Return the normalized form of ``original_prompt`` used for matching."""

    return _normalize(original_prompt)


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _has_bounded_occurrence(evidence_text: str, needle: str) -> bool:
    """Return whether ``needle`` occurs in ``evidence_text`` at a word boundary."""

    start = 0
    while True:
        index = evidence_text.find(needle, start)
        if index == -1:
            return False
        end = index + len(needle)
        before_is_boundary = index == 0 or not evidence_text[index - 1].isalnum()
        after_is_boundary = (
            end >= len(evidence_text) or not evidence_text[end].isalnum()
        )
        if before_is_boundary and after_is_boundary:
            return True
        start = index + 1


def filter_by_evidence(
    features: Sequence[str], evidence_text: str
) -> EvidenceFilterResult:
    """Keep only the features grounded in ``evidence_text``.

    ``evidence_text`` must come from :func:`build_evidence_text`. Order of
    processing is (1) strip surrounding whitespace, (2) discard what became
    empty, (3) match (Requirement 3.19).
    """

    kept: list[str] = []
    dropped: list[str] = []
    blank_dropped_count = 0

    for feature in features:
        stripped = feature.strip()
        if not stripped:
            blank_dropped_count += 1
            continue
        if _has_bounded_occurrence(evidence_text, _normalize(stripped)):
            kept.append(stripped)
        else:
            dropped.append(stripped)

    return EvidenceFilterResult(
        kept=tuple(kept),
        dropped=tuple(dropped),
        blank_dropped_count=blank_dropped_count,
    )
