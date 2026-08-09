"""Unit tests for resource-id sanitization (path-traversal protection).

Resource ids can originate from node STRING inputs, so loaders must reject ids
that could escape the resources directory.
"""

import pytest

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.infrastructure import (
    policy_loader,
    preset_loader,
    prompt_template_loader,
)
from prompt_detailer_router.infrastructure.resource_ids import safe_resource_id

UNSAFE_IDS = ["/tmp/pdr-secret", "../secret", "a/b", "a.b", "..", "", "a\\b", "with space"]


@pytest.mark.parametrize("name", UNSAFE_IDS)
def test_unsafe_ids_rejected(name: str) -> None:
    with pytest.raises(ConfigurationError):
        safe_resource_id(name, "test")


@pytest.mark.parametrize("name", ["photographic", "default_v1", "forbidden_terms_v1", "face"])
def test_safe_ids_accepted(name: str) -> None:
    assert safe_resource_id(name, "test") == name


@pytest.mark.parametrize("bad", ["/tmp/x", "../face", "face/../face"])
def test_loaders_reject_traversal(bad: str) -> None:
    with pytest.raises(ConfigurationError):
        preset_loader.load_upscale_preset(bad)
    with pytest.raises(ConfigurationError):
        preset_loader.load_detailer_preset(bad)
    with pytest.raises(ConfigurationError):
        preset_loader.load_detailer_profile(bad)
    with pytest.raises(ConfigurationError):
        policy_loader.load_forbidden_terms_policy(bad)
    with pytest.raises(ConfigurationError):
        prompt_template_loader.load_detailer_builder_template(bad)
