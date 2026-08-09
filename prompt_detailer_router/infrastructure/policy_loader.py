"""Forbidden-terms policy loading.

Infrastructure layer (Requirement 9.1). Loads the shared, versioned policy that
both the upscale and detailer builders apply.
"""

from __future__ import annotations

from dataclasses import dataclass

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.forbidden_terms import CASE_INSENSITIVE_LITERAL
from prompt_detailer_router.infrastructure.config_json import parse_config_json
from prompt_detailer_router.infrastructure.resource_ids import safe_resource_id
from prompt_detailer_router.infrastructure.resource_paths import resource_file

DEFAULT_POLICY_ID = "forbidden_terms_v1"
_POLICY_KEYS = ("version", "terms", "match")
_SUPPORTED_MATCH_MODES = (CASE_INSENSITIVE_LITERAL,)


@dataclass(frozen=True, slots=True)
class ForbiddenTermsPolicy:
    version: str
    terms: tuple[str, ...]
    match: str


def parse_policy(data: dict) -> ForbiddenTermsPolicy:
    missing = [key for key in _POLICY_KEYS if key not in data]
    if missing:
        raise ConfigurationError(
            "Forbidden-terms policy is missing required keys: " + ", ".join(missing)
        )
    if not isinstance(data["version"], str):
        raise ConfigurationError("Forbidden-terms policy 'version' must be a string.")
    if not isinstance(data["terms"], list) or not all(
        isinstance(term, str) for term in data["terms"]
    ):
        raise ConfigurationError(
            "Forbidden-terms policy 'terms' must be a list of strings."
        )
    match = data["match"]
    if not isinstance(match, str) or match not in _SUPPORTED_MATCH_MODES:
        raise ConfigurationError(
            f"Forbidden-terms policy 'match' must be one of {_SUPPORTED_MATCH_MODES}."
        )
    return ForbiddenTermsPolicy(
        version=data["version"],
        terms=tuple(data["terms"]),
        match=match,
    )


def load_forbidden_terms_policy(policy_id: str = DEFAULT_POLICY_ID) -> ForbiddenTermsPolicy:
    safe_resource_id(policy_id, "forbidden-terms policy")
    resource = resource_file("policies", f"{policy_id}.json")
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(
            f"Forbidden-terms policy not found: {policy_id}"
        ) from exc
    return parse_policy(parse_config_json(text, f"policies/{policy_id}.json"))
