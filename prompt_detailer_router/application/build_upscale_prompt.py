"""Upscale Prompt Builder use case.

Application layer (Requirements 7.1-7.3, 9.4). Composes an ``upscale_prompt``
from the extracted global features plus the selected upscale preset, then
applies the shared forbidden-terms policy. Deterministic: the same analysis and
preset version always yield the same prompt. No subject attribute is invented;
only features present in the analysis are used.
"""

from __future__ import annotations

from dataclasses import dataclass

from prompt_detailer_router.domain.forbidden_terms import apply_forbidden_terms
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis
from prompt_detailer_router.domain.prompt_text import dedup_features, join_prompt
from prompt_detailer_router.infrastructure.policy_loader import load_forbidden_terms_policy
from prompt_detailer_router.infrastructure.preset_loader import load_upscale_preset

# Deterministic category order for assembling the global descriptor.
UPSCALE_GLOBAL_ORDER = (
    "medium",
    "style",
    "lighting",
    "camera",
    "material",
    "texture",
    "environment",
    "subject",
)


@dataclass(frozen=True, slots=True)
class UpscaleBuildResult:
    upscale_prompt: str
    warnings: tuple[str, ...]


def _global_descriptor(analysis: PromptAnalysis) -> str:
    features: list[str] = []
    for category in UPSCALE_GLOBAL_ORDER:
        features.extend(analysis.global_features.get(category, ()))
    unique = dedup_features(features)
    return (", ".join(unique) + ".") if unique else ""


def build_upscale_prompt(
    analysis: PromptAnalysis, upscale_preset_id: str
) -> UpscaleBuildResult:
    preset = load_upscale_preset(upscale_preset_id)
    policy = load_forbidden_terms_policy()

    combined = join_prompt(
        [
            _global_descriptor(analysis),
            preset.quality_details,
            preset.preservation,
            preset.restrictions,
        ]
    )
    scan = apply_forbidden_terms(combined, policy.terms, policy.match)

    warnings: list[str] = []
    if scan.removed_count:
        warnings.append(
            f"Removed {scan.removed_count} forbidden term(s) from upscale_prompt: "
            + ", ".join(scan.removed_terms)
            + "."
        )

    return UpscaleBuildResult(upscale_prompt=scan.text, warnings=tuple(warnings))
