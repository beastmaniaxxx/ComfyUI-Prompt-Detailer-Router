"""Validated prompt-extraction result model.

Pure domain value object (Requirements 6.1, 13.3). ``PromptAnalysis``
represents an already-validated extraction result and is agnostic to its
source (Ollama, a fixture, or the From-JSON extraction path). Transport,
prompts, and retry are owned by the ollama-prompt-analyzer spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping


def _freeze_features(mapping: Mapping[str, Iterable[str]]) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType(
        {key: tuple(values) for key, values in mapping.items()}
    )


@dataclass(frozen=True, slots=True)
class PromptAnalysis:
    """Extracted, validated facts grouped globally and per scope.

    ``global_features`` holds category keyed feature lists (style, lighting,
    camera, ...). ``scoped_features`` maps a normalized scope to its extracted
    features. All backing mappings and value lists are made immutable on
    construction.
    """

    global_features: Mapping[str, tuple[str, ...]]
    scoped_features: Mapping[str, tuple[str, ...]]
    warnings: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        object.__setattr__(self, "global_features", _freeze_features(self.global_features))
        object.__setattr__(self, "scoped_features", _freeze_features(self.scoped_features))
        object.__setattr__(self, "warnings", tuple(self.warnings))


def features_for_scope(analysis: PromptAnalysis, scope: str) -> tuple[str, ...]:
    """Return extracted features for ``scope`` (empty tuple if absent)."""

    return analysis.scoped_features.get(scope, ())
