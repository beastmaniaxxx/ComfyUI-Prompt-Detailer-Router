"""Contract: Tier 1 (JSON Schema) and Tier 2 (domain invariants) agree.

Covers Requirements 11.1, 11.2, 11.4 (schema + schema_version compat), 13.1,
13.2 (response schema), 9.1 / 10.1-10.5 (resources load via loaders and reject
misconfiguration), and the design's two-tier validation decision: a built plan
passes BOTH tiers, and a shape-valid-but-invariant-invalid plan is accepted by
the schema yet rejected by domain validation (complementary, not contradictory).
"""

import json

import pytest

from prompt_detailer_router.application.build_detailer_plan import (
    PlanBuildInput,
    build_detailer_plan,
)
from prompt_detailer_router.domain.detailer_plan import validate_plan
from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.prompt_analysis import PromptAnalysis
from prompt_detailer_router.infrastructure import policy_loader, preset_loader
from prompt_detailer_router.infrastructure.json_codec import plan_to_dict
from prompt_detailer_router.infrastructure.schema_loader import get_plan_validator

SEVEN = ("face", "hair", "hands", "body", "upper_body", "clothing", "generic")


def _built_plan(scopes):
    analysis = PromptAnalysis(
        global_features={},
        scoped_features={s: [f"{s} feature"] for s in scopes},
        warnings=(),
    )
    return build_detailer_plan(PlanBuildInput(requested_scopes=tuple(scopes), analysis=analysis))


@pytest.mark.parametrize("scopes", [("face",), ("face", "hair"), SEVEN])
def test_built_plans_pass_both_tiers(scopes) -> None:
    plan = _built_plan(scopes)
    data = plan_to_dict(plan)
    # Tier 1: schema
    assert list(get_plan_validator().iter_errors(data)) == []
    # Tier 2: domain invariants
    assert validate_plan(plan) == ()


def test_shape_valid_but_invariant_invalid_is_schema_ok_domain_rejected() -> None:
    # Task scope 'hair' not present in requested_scopes: schema-valid, invariant-invalid.
    data = {
        "schema_version": 1,
        "requested_scopes": ["face"],
        "tasks": [
            {
                "task_id": "main.hair",
                "subject_id": "main",
                "scope": "hair",
                "extracted_features": [],
                "prompt_core": "",
                "prompt_final": "done",
                "order": 20,
                "enabled": True,
                "warnings": [],
            }
        ],
        "warnings": [],
    }
    assert list(get_plan_validator().iter_errors(data)) == [], "schema should accept shape"
    # Domain must catch what the schema cannot express.
    from prompt_detailer_router.infrastructure.json_codec import _dict_to_plan

    assert validate_plan(_dict_to_plan(data)), "domain must reject the invariant break"


def test_schema_version_compatibility_gate() -> None:
    validator = get_plan_validator()
    good = plan_to_dict(_built_plan(("face",)))
    assert list(validator.iter_errors(good)) == []
    bad = json.loads(json.dumps(good))
    bad["schema_version"] = 2
    assert list(validator.iter_errors(bad)), "schema_version 2 must be rejected (11.4)"


# --- resources load via loaders / reject misconfiguration ---

def test_all_resources_load_via_loaders() -> None:
    for scope in SEVEN:
        assert preset_loader.load_detailer_preset(scope).scope == scope
    for upscale in ("photographic", "illustration", "minimal"):
        assert preset_loader.load_upscale_preset(upscale).preset_id == upscale
    assert set(preset_loader.load_detailer_profile().mappings) == set(SEVEN)
    assert policy_loader.load_forbidden_terms_policy().match == "case_insensitive_literal"


def test_loaders_reject_missing_keys() -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.parse_detailer_preset({"scope": "face"})
    with pytest.raises(ConfigurationError):
        policy_loader.parse_policy({"version": "1.0"})
