"""LLM prompt and scope-definition resource loading.

Infrastructure layer (Requirements 2.3, 2.6, 10.13-10.16). Loads the versioned
resources the Analyzer sends to Ollama: the extraction system prompt, the repair
prompt used when a reply was unusable, and the per-scope target-information
definitions.

Validation runs entirely through the shared config-JSON helpers
(``read_config_json`` / ``require_keys`` / ``reject_unknown_keys`` /
``require_str_fields`` / ``safe_resource_id``) that presets, profiles, policies
and templates already use. This module deliberately owns no validation
implementation of its own (Requirement 10.15): a prompt-specific copy is exactly
how one loader ends up missing a check the others have.

These resources live next to the core-owned ``detailer_builder_v1.json`` in
``resources/prompts/``. The ``extraction_*`` / ``scope_definitions_*`` naming
keeps the two sets apart, and the required-key check rejects a core template if
one is ever requested through here.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.scopes import SUPPORTED_SCOPES
from prompt_detailer_router.infrastructure.config_json import (
    read_config_json,
    reject_unknown_keys,
    require_keys,
    require_str_fields,
)
from prompt_detailer_router.infrastructure.resource_ids import safe_resource_id
from prompt_detailer_router.infrastructure.resource_paths import resource_file

DEFAULT_EXTRACTION_PROMPT_ID = "extraction_system_v1"
DEFAULT_REPAIR_PROMPT_ID = "extraction_repair_v1"
DEFAULT_SCOPE_DEFINITIONS_ID = "scope_definitions_v1"

_PROMPT_KEYS = ("id", "version", "text")
_DEFINITIONS_KEYS = ("id", "version", "definitions")


@dataclass(frozen=True, slots=True)
class LlmPromptResource:
    """A versioned instruction text sent to the LLM."""

    id: str
    version: str
    text: str


@dataclass(frozen=True, slots=True)
class ScopeDefinitions:
    """Per-scope target-information definitions sent with an extraction request.

    ``definitions`` covers every supported scope and is immutable, so a caller
    cannot silently blank out a scope after loading.
    """

    id: str
    version: str
    definitions: Mapping[str, str]


def parse_llm_prompt(data: dict) -> LlmPromptResource:
    require_keys(data, _PROMPT_KEYS, "LLM prompt resource")
    reject_unknown_keys(data, _PROMPT_KEYS, "LLM prompt resource")
    require_str_fields(data, _PROMPT_KEYS, "LLM prompt resource")
    return LlmPromptResource(
        id=data["id"], version=data["version"], text=data["text"]
    )


def parse_scope_definitions(data: dict) -> ScopeDefinitions:
    require_keys(data, _DEFINITIONS_KEYS, "Scope definitions")
    reject_unknown_keys(data, _DEFINITIONS_KEYS, "Scope definitions")
    require_str_fields(data, ("id", "version"), "Scope definitions")
    definitions = data["definitions"]
    if not isinstance(definitions, dict):
        raise ConfigurationError(
            "Scope definitions 'definitions' must be an object, got "
            f"{type(definitions).__name__}."
        )
    # A scope without a definition must not be substituted with an empty one
    # (Requirement 10.14): the LLM would then classify that scope with no
    # guidance at all. Unknown scope keys are rejected as unknown fields so a
    # typo cannot sit unreachable in the file.
    require_keys(definitions, SUPPORTED_SCOPES, "Scope definitions 'definitions'")
    reject_unknown_keys(
        definitions, SUPPORTED_SCOPES, "Scope definitions 'definitions'"
    )
    require_str_fields(
        definitions, SUPPORTED_SCOPES, "Scope definitions 'definitions'"
    )
    return ScopeDefinitions(
        id=data["id"],
        version=data["version"],
        definitions=MappingProxyType(dict(definitions)),
    )


def _read(resource_id: str) -> dict:
    resource = resource_file("prompts", f"{resource_id}.json")
    return read_config_json(resource, f"prompts/{resource_id}.json")


def load_llm_prompt(prompt_id: str) -> LlmPromptResource:
    """Load the versioned LLM prompt named ``prompt_id``."""

    safe_resource_id(prompt_id, "LLM prompt")
    prompt = parse_llm_prompt(_read(prompt_id))
    if prompt.id != prompt_id:
        raise ConfigurationError(
            f"LLM prompt file '{prompt_id}.json' declares id '{prompt.id}'; "
            "the file name and id must match."
        )
    return prompt


def load_scope_definitions(
    definitions_id: str = DEFAULT_SCOPE_DEFINITIONS_ID,
) -> ScopeDefinitions:
    """Load the versioned per-scope target-information definitions."""

    safe_resource_id(definitions_id, "scope definitions")
    definitions = parse_scope_definitions(_read(definitions_id))
    if definitions.id != definitions_id:
        raise ConfigurationError(
            f"Scope definitions file '{definitions_id}.json' declares id "
            f"'{definitions.id}'; the file name and id must match."
        )
    return definitions
