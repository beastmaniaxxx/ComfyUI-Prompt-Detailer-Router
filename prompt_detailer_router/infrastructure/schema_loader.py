"""JSON Schema loading and cached Draft 2020-12 validators.

Infrastructure layer (Requirements 11.1, 13.2). This module is one of the few
permitted to import ``jsonschema``. Validators are cached per schema file so the
schema is compiled once per process.
"""

from __future__ import annotations

import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from prompt_detailer_router.infrastructure.resource_paths import resource_file

DETAILER_PLAN_SCHEMA = "detailer_plan_v1.schema.json"
OLLAMA_RESPONSE_SCHEMA = "ollama_response_v1.schema.json"


def load_schema(schema_filename: str) -> dict:
    """Load and parse a bundled JSON Schema file by name."""

    text = resource_file("schemas", schema_filename).read_text(encoding="utf-8")
    return json.loads(text)


@lru_cache(maxsize=None)
def get_validator(schema_filename: str) -> Draft202012Validator:
    """Return a cached Draft 2020-12 validator for the named schema."""

    schema = load_schema(schema_filename)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def get_plan_validator() -> Draft202012Validator:
    """Return the cached validator for the DETAILER_PLAN schema."""

    return get_validator(DETAILER_PLAN_SCHEMA)


def get_ollama_response_validator() -> Draft202012Validator:
    """Return the cached validator for the Ollama response schema."""

    return get_validator(OLLAMA_RESPONSE_SCHEMA)
