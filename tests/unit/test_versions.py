"""Unit tests for the shared PROMPT_BUILDER_VERSION constant.

The constant is the reproducibility basis for the deterministic builders,
supplied to a downstream Analyzer cache key. It must be importable from a shared
location and re-exported by both builders.
"""

from prompt_detailer_router.application import build_detailer_plan, build_upscale_prompt
from prompt_detailer_router.domain.versions import PROMPT_BUILDER_VERSION


def test_version_is_an_int() -> None:
    assert isinstance(PROMPT_BUILDER_VERSION, int)


def test_both_builders_reexport_the_same_version() -> None:
    assert build_upscale_prompt.PROMPT_BUILDER_VERSION == PROMPT_BUILDER_VERSION
    assert build_detailer_plan.PROMPT_BUILDER_VERSION == PROMPT_BUILDER_VERSION
