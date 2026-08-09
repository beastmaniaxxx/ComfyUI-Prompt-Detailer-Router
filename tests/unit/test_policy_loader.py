"""Unit tests for forbidden-terms policy loading (infrastructure/policy_loader).

Covers Requirement 9.1: load the versioned shared policy with required keys.
"""

import pytest

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.infrastructure import policy_loader


def test_load_default_policy() -> None:
    policy = policy_loader.load_forbidden_terms_policy()
    assert policy.match == "case_insensitive_literal"
    assert isinstance(policy.terms, tuple)
    lowered = {t.lower() for t in policy.terms}
    assert {"beautiful", "perfect", "symmetrical"} <= lowered
    assert policy.version


def test_missing_policy_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        policy_loader.load_forbidden_terms_policy("does_not_exist")


def test_policy_missing_key_raises() -> None:
    with pytest.raises(ConfigurationError):
        policy_loader.parse_policy({"version": "1.0", "terms": ["x"]})  # no match


def test_policy_non_string_term_raises() -> None:
    with pytest.raises(ConfigurationError):
        policy_loader.parse_policy(
            {"version": "1.0", "terms": [1], "match": "case_insensitive_literal"}
        )


def test_policy_unknown_match_mode_raises() -> None:
    with pytest.raises(ConfigurationError):
        policy_loader.parse_policy(
            {"version": "1.0", "terms": ["x"], "match": "regex"}
        )


def test_policy_unknown_key_raises() -> None:
    with pytest.raises(ConfigurationError):
        policy_loader.parse_policy(
            {
                "version": "1.0",
                "terms": ["x"],
                "match": "case_insensitive_literal",
                "extra": 1,
            }
        )


class _BadUtf8Resource:
    def read_text(self, encoding: str = "utf-8") -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def test_non_utf8_policy_raises_configuration_error(monkeypatch) -> None:
    monkeypatch.setattr(
        policy_loader, "resource_file", lambda *parts: _BadUtf8Resource()
    )
    with pytest.raises(ConfigurationError):
        policy_loader.load_forbidden_terms_policy()
