"""Contract: builder prompt-template resource (detailer_builder_v1).

Verifies the fixed builder prompt text lives in a versioned resource (project
rule: no hard-coded prompt strings in Python) with the required keys and the
'{features}' placeholder.
"""

import pytest

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.infrastructure import prompt_template_loader


def test_default_detailer_builder_template_loads() -> None:
    template = prompt_template_loader.load_detailer_builder_template()
    assert template.version
    assert "{features}" in template.feature_clause_template


def test_render_feature_clause_interpolates() -> None:
    template = prompt_template_loader.load_detailer_builder_template()
    rendered = template.render_feature_clause("dark brown eyes, fair skin")
    assert "dark brown eyes, fair skin" in rendered


def test_missing_template_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        prompt_template_loader.load_detailer_builder_template("does_not_exist")


def test_template_missing_placeholder_raises() -> None:
    with pytest.raises(ConfigurationError):
        prompt_template_loader.parse_detailer_builder_template(
            {"version": "1.0", "feature_clause_template": "no placeholder here"}
        )


def test_template_with_extra_placeholder_raises() -> None:
    with pytest.raises(ConfigurationError):
        prompt_template_loader.parse_detailer_builder_template(
            {"version": "1.0", "feature_clause_template": "Keep {features} {oops}."}
        )


def test_template_with_malformed_braces_raises() -> None:
    with pytest.raises(ConfigurationError):
        prompt_template_loader.parse_detailer_builder_template(
            {"version": "1.0", "feature_clause_template": "Keep {features"}
        )
