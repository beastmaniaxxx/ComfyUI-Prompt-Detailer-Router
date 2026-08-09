"""Architecture guard: the domain layer stays pure.

Enforces the design boundary (Requirement 14.1 / design Boundary Commitments):
domain modules must not import ComfyUI, Ollama, filesystem/preset loaders, or
``jsonschema``. ``jsonschema`` is confined to the infrastructure layer.
"""

from importlib.resources import files

import pytest

FORBIDDEN_IMPORTS = ("jsonschema", "requests", "comfy", "nodes", "folder_paths")


def _domain_module_sources() -> dict[str, str]:
    domain_dir = files("prompt_detailer_router.domain")
    sources: dict[str, str] = {}
    for entry in domain_dir.iterdir():
        name = entry.name
        if name.endswith(".py") and name != "__init__.py":
            sources[name] = entry.read_text(encoding="utf-8")
    return sources


def test_domain_modules_exist() -> None:
    assert set(_domain_module_sources()) >= {
        "scopes.py",
        "order_defaults.py",
        "detailer_plan.py",
        "prompt_analysis.py",
        "forbidden_terms.py",
        "prompt_text.py",
        "errors.py",
    }


@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORTS)
def test_domain_modules_do_not_import_forbidden_dependencies(forbidden: str) -> None:
    for module_name, source in _domain_module_sources().items():
        assert f"import {forbidden}" not in source, (
            f"domain module {module_name} imports forbidden dependency {forbidden}"
        )
