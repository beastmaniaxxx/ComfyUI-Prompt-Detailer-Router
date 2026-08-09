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


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace runs, remove space before punctuation, and strip."""

    collapsed = _WHITESPACE.sub(" ", text).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", collapsed).strip()


def join_prompt(parts: Sequence[str]) -> str:
    """Join non-empty parts with a single space, then normalize whitespace."""

    kept = [part for part in parts if part and part.strip()]
    return normalize_whitespace(" ".join(kept))


def dedup_features(features: Sequence[str]) -> tuple[str, ...]:
    """Strip features, drop empties, and dedup preserving first-occurrence order."""

    cleaned = [feature.strip() for feature in features]
    cleaned = [feature for feature in cleaned if feature]
    return ordered_unique(cleaned)
