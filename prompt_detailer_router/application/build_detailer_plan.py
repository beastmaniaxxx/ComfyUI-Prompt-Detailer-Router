"""Detailer Plan Builder use case.

Application layer (Requirements 3.1, 3.3, 5.3, 6.1-6.5, 8.1, 8.4, 9.4, 10.6,
10.7). Builds a DETAILER_PLAN deterministically from normalized requested scopes
and a validated PromptAnalysis: one task per requested scope, a non-empty
preset-based fallback task when a scope has no extracted features, default order
resolution, forbidden-term filtering of the finalized text, and a final
invariant check.

The builder never adopts LLM-provided task_id/prompt_final and never invents
attributes: only extracted features and preset text are used.
"""

from __future__ import annotations

from dataclasses import dataclass

from prompt_detailer_router.domain.detailer_plan import (
    SCHEMA_VERSION,
    DetailerPlan,
    DetailerTask,
    make_task_id,
    validate_plan,
)
from prompt_detailer_router.domain.errors import PlanValidationError
from prompt_detailer_router.domain.forbidden_terms import apply_forbidden_terms
from prompt_detailer_router.domain.order_defaults import default_order_for
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis, features_for_scope
from prompt_detailer_router.domain.prompt_text import dedup_features, join_prompt
from prompt_detailer_router.infrastructure.policy_loader import (
    ForbiddenTermsPolicy,
    load_forbidden_terms_policy,
)
from prompt_detailer_router.infrastructure.preset_loader import (
    DetailerPreset,
    DetailerProfile,
    load_detailer_preset,
    load_detailer_profile,
)
from prompt_detailer_router.infrastructure.prompt_template_loader import (
    DetailerBuilderTemplate,
    load_detailer_builder_template,
)


@dataclass(frozen=True, slots=True)
class PlanBuildInput:
    requested_scopes: tuple[str, ...]
    analysis: PromptAnalysis
    profile_id: str = "default_v1"
    subject_id: str = "main"


def _resolve_order(preset: DetailerPreset, scope: str) -> int:
    return preset.default_order if preset.default_order is not None else default_order_for(scope)


def _build_task(
    scope: str,
    subject_id: str,
    preset: DetailerPreset,
    features: tuple[str, ...],
    policy: ForbiddenTermsPolicy,
    template: DetailerBuilderTemplate,
) -> DetailerTask:
    feature_clause = (
        template.render_feature_clause(", ".join(features)) if features else ""
    )
    prompt_final_raw = join_prompt(
        [feature_clause, preset.preservation, preset.local_details, preset.restrictions]
    )
    scan = apply_forbidden_terms(prompt_final_raw, policy.terms, policy.match)

    task_warnings: list[str] = []
    if scan.removed_count:
        task_warnings.append(
            f"Removed {scan.removed_count} forbidden term(s): "
            + ", ".join(scan.removed_terms)
            + "."
        )

    return DetailerTask(
        task_id=make_task_id(subject_id, scope),
        subject_id=subject_id,
        scope=scope,
        extracted_features=features,
        prompt_core=", ".join(features),
        prompt_final=scan.text,
        order=_resolve_order(preset, scope),
        enabled=True,
        warnings=tuple(task_warnings),
    )


def build_detailer_plan(build_input: PlanBuildInput) -> DetailerPlan:
    profile: DetailerProfile = load_detailer_profile(build_input.profile_id)
    policy = load_forbidden_terms_policy()
    template = load_detailer_builder_template()

    tasks: list[DetailerTask] = []
    plan_warnings: list[str] = []

    for scope in build_input.requested_scopes:
        preset = load_detailer_preset(profile.mappings[scope])
        features = dedup_features(features_for_scope(build_input.analysis, scope))
        if not features:
            plan_warnings.append(
                f"No extracted features for scope '{scope}'; generated a fallback task."
            )
        tasks.append(
            _build_task(
                scope, build_input.subject_id, preset, features, policy, template
            )
        )

    plan = DetailerPlan(
        schema_version=SCHEMA_VERSION,
        requested_scopes=tuple(build_input.requested_scopes),
        tasks=tuple(tasks),
        warnings=tuple(plan_warnings),
    )

    issues = validate_plan(plan)
    if issues:
        raise PlanValidationError(
            "Built plan failed invariants: "
            + "; ".join(issue.message for issue in issues)
        )
    return plan
