"""Pure prompt-text composition helpers.

Deterministic string helpers used by the upscale and detailer prompt builders
(Requirements 7, 8). Pure domain logic: no ComfyUI, Ollama, filesystem, or
``jsonschema`` imports.
"""

from __future__ import annotations

import re
from typing import Sequence

from prompt_detailer_router.utils.collections import ordered_unique

_WHITESPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]|\{\s*\}")
# A run of adjacent separators with no content between them (e.g. ",,", "..",
# ",."); collapse to the last separator in the run.
_ADJACENT_SEPARATORS = re.compile(r"[,;.](?:\s*[,;.])+")
# Leading separators include periods (a dangling ". x"); trailing keeps periods
# since a sentence legitimately ends with one.
_LEADING_SEPARATOR = re.compile(r"^[\s,;.]+")
_TRAILING_SEPARATOR = re.compile(r"[\s,;]+$")


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace runs, remove space before punctuation, and strip."""

    collapsed = _WHITESPACE.sub(" ", text).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", collapsed).strip()


def _collapse_separators(match: "re.Match[str]") -> str:
    return match.group(0).strip()[-1]


def repair_separators(text: str) -> str:
    """Repair dangling punctuation left after removing list/sentence elements.

    Handles separators left where a term was removed: empty brackets, runs of
    adjacent commas/semicolons/periods, and leading separators. Content-bearing
    text (multi-sentence prompts) is untouched because those separators are not
    adjacent. Examples: ``", photorealistic"`` -> ``"photorealistic"``;
    ``"face,, hair"`` -> ``"face, hair"``; ``"face.. hair"`` -> ``"face. hair"``;
    ``"(), face"`` -> ``"face"``.
    """

    text = _EMPTY_BRACKETS.sub("", text)
    text = _ADJACENT_SEPARATORS.sub(_collapse_separators, text)
    text = _LEADING_SEPARATOR.sub("", text)
    text = _TRAILING_SEPARATOR.sub("", text)
    return text


def join_prompt(parts: Sequence[str]) -> str:
    """Join non-empty parts with a single space, then normalize whitespace."""

    kept = [part for part in parts if part and part.strip()]
    return normalize_whitespace(" ".join(kept))


def dedup_features(features: Sequence[str]) -> tuple[str, ...]:
    """Strip features, drop empties, and dedup preserving first-occurrence order."""

    cleaned = [feature.strip() for feature in features]
    cleaned = [feature for feature in cleaned if feature]
    return ordered_unique(cleaned)
