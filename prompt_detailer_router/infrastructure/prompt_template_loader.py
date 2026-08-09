"""Builder prompt-template loading.

Infrastructure layer. Loads the version-managed prompt templates used by the
deterministic Python builders (not LLM system prompts, which are owned by the
ollama-prompt-analyzer spec). Keeping these fixed strings in a versioned
resource — instead of hard-coding them in Python — satisfies the project rule
that prompt text lives in resources so changes are version-tracked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

from prompt_detailer_router.domain.errors import ConfigurationError

DEFAULT_DETAILER_BUILDER_ID = "detailer_builder_v1"
_TEMPLATE_KEYS = ("version", "feature_clause_template")


@dataclass(frozen=True, slots=True)
class DetailerBuilderTemplate:
    version: str
    feature_clause_template: str

    def render_feature_clause(self, features: str) -> str:
        return self.feature_clause_template.format(features=features)


def parse_detailer_builder_template(data: dict) -> DetailerBuilderTemplate:
    missing = [key for key in _TEMPLATE_KEYS if key not in data]
    if missing:
        raise ConfigurationError(
            "Detailer builder template is missing required keys: " + ", ".join(missing)
        )
    template = data["feature_clause_template"]
    if "{features}" not in template:
        raise ConfigurationError(
            "feature_clause_template must contain the '{features}' placeholder."
        )
    return DetailerBuilderTemplate(
        version=data["version"], feature_clause_template=template
    )


def load_detailer_builder_template(
    template_id: str = DEFAULT_DETAILER_BUILDER_ID,
) -> DetailerBuilderTemplate:
    resource = files("prompt_detailer_router.resources").joinpath(
        "prompts", f"{template_id}.json"
    )
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(
            f"Detailer builder template not found: {template_id}"
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Detailer builder template is not valid JSON: {template_id} ({exc})"
        ) from exc
    return parse_detailer_builder_template(data)
