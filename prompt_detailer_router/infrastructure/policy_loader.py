"""Forbidden-terms policy loading.

Infrastructure layer (Requirement 9.1). Loads the shared, versioned policy that
both the upscale and detailer builders apply.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

from prompt_detailer_router.domain.errors import ConfigurationError

DEFAULT_POLICY_ID = "forbidden_terms_v1"
_POLICY_KEYS = ("version", "terms", "match")


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
    if not isinstance(data["terms"], list):
        raise ConfigurationError("Forbidden-terms policy 'terms' must be a list.")
    return ForbiddenTermsPolicy(
        version=data["version"],
        terms=tuple(data["terms"]),
        match=data["match"],
    )


def load_forbidden_terms_policy(policy_id: str = DEFAULT_POLICY_ID) -> ForbiddenTermsPolicy:
    resource = files("prompt_detailer_router.resources").joinpath(
        "policies", f"{policy_id}.json"
    )
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(
            f"Forbidden-terms policy not found: {policy_id}"
        ) from exc
    return parse_policy(json.loads(text))
