"""Contract: shared forbidden-terms policy resource (forbidden_terms_v1).

Covers Requirement 9.1: a versioned shared policy exists with the required
keys and includes the default banned beautification terms.
"""

import json
from prompt_detailer_router.infrastructure.resource_paths import resource_file

REQUIRED_KEYS = {"version", "terms", "match"}
EXPECTED_TERMS = {"beautiful", "perfect", "symmetrical"}


def _load_policy() -> dict:
    text = resource_file("policies", "forbidden_terms_v1.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def test_policy_has_required_keys() -> None:
    policy = _load_policy()
    assert REQUIRED_KEYS <= policy.keys()


def test_policy_declares_case_insensitive_literal_match() -> None:
    assert _load_policy()["match"] == "case_insensitive_literal"


def test_policy_terms_are_non_empty_string_list() -> None:
    terms = _load_policy()["terms"]
    assert isinstance(terms, list) and terms
    assert all(isinstance(t, str) and t for t in terms)


def test_policy_includes_default_banned_terms() -> None:
    terms = {t.lower() for t in _load_policy()["terms"]}
    assert EXPECTED_TERMS <= terms
