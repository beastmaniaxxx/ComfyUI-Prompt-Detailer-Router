"""Foundation smoke test: package skeleton imports without ComfyUI/Ollama.

Verifies Requirement 14.1 at the scaffolding level: core layers can be
imported in a plain Python process (no ComfyUI, no Ollama, no network).
"""

import importlib

import pytest

LAYER_MODULES = [
    "prompt_detailer_router",
    "prompt_detailer_router.domain",
    "prompt_detailer_router.application",
    "prompt_detailer_router.infrastructure",
    "prompt_detailer_router.resources",
    "prompt_detailer_router.utils",
]


@pytest.mark.parametrize("module_name", LAYER_MODULES)
def test_layer_module_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module is not None
