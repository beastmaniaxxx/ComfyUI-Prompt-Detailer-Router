"""Scope normalization and supported-scope validation.

Pure domain logic: no ComfyUI, Ollama, filesystem, or ``jsonschema`` imports.

Normalization order (Requirement 1): split on commas, trim whitespace,
lowercase, drop empties, order-preserving dedup, then match against the
supported set. Unsupported scopes are dropped with a warning and never fail the
pipeline (Requirement 2).
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_SCOPES: tuple[str, ...] = (
    "face",
    "hair",
    "hands",
    "body",
    "upper_body",
    "clothing",
    "generic",
)

_SUPPORTED_SET = frozenset(SUPPORTED_SCOPES)


@dataclass(frozen=True, slots=True)
class ScopeNormalizationResult:
    """Outcome of normalizing a raw comma-separated scope string.

    ``requested_scopes`` is normalized, supported, deduplicated, and preserves
    the input's first-occurrence order. ``dropped_scopes`` lists unsupported
    scopes that were removed. ``warnings`` explains drops and empty input.
    """

    requested_scopes: tuple[str, ...]
    dropped_scopes: tuple[str, ...]
    warnings: tuple[str, ...]


def is_supported_scope(scope: str) -> bool:
    """Return whether ``scope`` (already normalized) is a supported scope."""

    return scope in _SUPPORTED_SET


def normalize_scopes(raw: str) -> ScopeNormalizationResult:
    """Normalize a raw comma-separated scope string.

    Deterministic: the same input always yields an equal result.
    """

    tokens = [part.strip().lower() for part in raw.split(",")]
    tokens = [token for token in tokens if token]

    supported: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        if token in _SUPPORTED_SET:
            supported.append(token)
        else:
            dropped.append(token)

    warnings: list[str] = []
    if dropped:
        warnings.append(
            "Unsupported scopes were dropped: " + ", ".join(dropped) + "."
        )
    if not supported:
        warnings.append("No supported scopes were provided.")

    return ScopeNormalizationResult(
        requested_scopes=tuple(supported),
        dropped_scopes=tuple(dropped),
        warnings=tuple(warnings),
    )
