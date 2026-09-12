"""The resource-loader injection bundle: the one seam for swapping resources.

Infrastructure layer (Requirements 12.12, 12.21). ``ResourceLoaders`` bundles
every loader whose result influences Analyzer output, plus the two version
constants. ``analyze_prompt`` takes it as an argument, so a test replaces a
resource -- a different version, a broken file -- by swapping one field, and
never by monkeypatching core's ``resource_paths`` / ``schema_loader`` internals.

**How far an injection reaches.** The fields do not all have the same effect on
output, because core's builders are not changed by this spec (design "Adjacent
expectations"):

===========================================  ==========================  ===================================
resource                                     consumer                    injection reaches
===========================================  ==========================  ===================================
``load_response_schema``                     Analyzer                    the ``format`` projection *and*
                                                                         response validation
``load_llm_prompt`` / ``load_scope_definitions``  Analyzer               the request payload
preset / profile / detailer preset /         core builders, which        descriptor collection (cache key,
policy / builder template                    re-read them from an id     ``diagnostics``) and load-time
                                             internally                  validation only -- *not* output text
===========================================  ==========================  ===================================

So a test may assert that an injected response schema drives both the payload
projection and validation, but must not assert that an injected preset's wording
appears in ``upscale_prompt`` or ``prompt_final``. Reaching that would require
core's builders to accept resources instead of ids, i.e. an upstream API change,
which v1 does not take. The limit does not block Requirement 12.12 (which needs
the cache key to change -- descriptors suffice) or 12.21 (which needs
classification (h) with zero requests -- load-time validation suffices).

``load_response_schema`` is a single field on purpose: the ``format`` projection
and the response validator are both derived from that one read, so they cannot
end up looking at different schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from prompt_detailer_router.domain.detailer_plan import SCHEMA_VERSION
from prompt_detailer_router.domain.versions import PROMPT_BUILDER_VERSION
from prompt_detailer_router.infrastructure.config_json import read_config_json
from prompt_detailer_router.infrastructure.llm_prompt_loader import (
    DEFAULT_EXTRACTION_PROMPT_ID,
    DEFAULT_REPAIR_PROMPT_ID,
    DEFAULT_SCOPE_DEFINITIONS_ID,
    LlmPromptResource,
    ScopeDefinitions,
    load_llm_prompt,
    load_scope_definitions,
)
from prompt_detailer_router.infrastructure.policy_loader import (
    ForbiddenTermsPolicy,
    load_forbidden_terms_policy,
)
from prompt_detailer_router.infrastructure.preset_loader import (
    DetailerPreset,
    DetailerProfile,
    UpscalePreset,
    load_detailer_preset,
    load_detailer_profile,
    load_upscale_preset,
)
from prompt_detailer_router.infrastructure.prompt_template_loader import (
    DetailerBuilderTemplate,
    load_detailer_builder_template,
)
from prompt_detailer_router.infrastructure.resource_paths import resource_file
from prompt_detailer_router.infrastructure.schema_loader import OLLAMA_RESPONSE_SCHEMA

__all__ = [
    "DEFAULT_EXTRACTION_PROMPT_ID",
    "DEFAULT_REPAIR_PROMPT_ID",
    "DEFAULT_RESOURCE_LOADERS",
    "DEFAULT_SCOPE_DEFINITIONS_ID",
    "ResourceLoaders",
    "load_response_schema",
]


def load_response_schema() -> dict:
    """Read the bundled Ollama response schema as a config resource.

    Goes through :func:`read_config_json` rather than core's
    ``schema_loader.load_schema`` because this is the Analyzer's only supply
    point for the schema: a hand-edited schema file must surface as a
    ConfigurationError -- classification (h) -- and not as a raw JSONDecodeError
    (Requirement 10.16). Core's cached validator path is untouched.
    """

    return read_config_json(
        resource_file("schemas", OLLAMA_RESPONSE_SCHEMA),
        f"schemas/{OLLAMA_RESPONSE_SCHEMA}",
    )


@dataclass(frozen=True, slots=True)
class ResourceLoaders:
    """Every resource read that influences Analyzer output, in one injectable bundle."""

    load_upscale_preset: Callable[[str], UpscalePreset]
    load_detailer_profile: Callable[[str], DetailerProfile]
    load_detailer_preset: Callable[[str], DetailerPreset]
    load_forbidden_terms_policy: Callable[[], ForbiddenTermsPolicy]
    load_detailer_builder_template: Callable[[], DetailerBuilderTemplate]
    load_llm_prompt: Callable[[str], LlmPromptResource]
    load_scope_definitions: Callable[[str], ScopeDefinitions]
    load_response_schema: Callable[[], dict]
    prompt_builder_version: int
    plan_schema_version: int


DEFAULT_RESOURCE_LOADERS = ResourceLoaders(
    load_upscale_preset=load_upscale_preset,
    load_detailer_profile=load_detailer_profile,
    load_detailer_preset=load_detailer_preset,
    load_forbidden_terms_policy=load_forbidden_terms_policy,
    load_detailer_builder_template=load_detailer_builder_template,
    load_llm_prompt=load_llm_prompt,
    load_scope_definitions=load_scope_definitions,
    load_response_schema=load_response_schema,
    prompt_builder_version=PROMPT_BUILDER_VERSION,
    plan_schema_version=SCHEMA_VERSION,
)
