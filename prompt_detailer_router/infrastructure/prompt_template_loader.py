"""Builder prompt-template loading.

Infrastructure layer. Loads the version-managed prompt templates used by the
deterministic Python builders (not LLM system prompts, which are owned by the
ollama-prompt-analyzer spec). Keeping these fixed strings in a versioned
resource — instead of hard-coding them in Python — satisfies the project rule
that prompt text lives in resources so changes are version-tracked.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.infrastructure.config_json import parse_config_json
from prompt_detailer_router.infrastructure.resource_ids import safe_resource_id
from prompt_detailer_router.infrastructure.resource_paths import resource_file

DEFAULT_DETAILER_BUILDER_ID = "detailer_builder_v1"
_TEMPLATE_KEYS = ("version", "feature_clause_template")


@dataclass(frozen=True, slots=True)
class DetailerBuilderTemplate:
    version: str
    feature_clause_template: str

    def render_feature_clause(self, features: str) -> str:
        return self.feature_clause_template.format(features=features)


def _validate_template_fields(template: str) -> None:
    """Reject templates whose format fields are not exactly ``{features}``.

    Also rejects malformed braces so ``str.format`` cannot raise KeyError /
    ValueError later during plan building; failures surface as ConfigurationError.
    """

    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise ConfigurationError(
            f"feature_clause_template has malformed format braces ({exc})."
        ) from exc
    fields = [field for _, field, _, _ in parsed if field is not None]
    unexpected = sorted({field for field in fields if field != "features"})
    if unexpected:
        raise ConfigurationError(
            "feature_clause_template may only use the '{features}' placeholder; "
            f"found: {', '.join(unexpected)}."
        )
    # Reject format specs and conversions (e.g. "{features:{oops}}" or
    # "{features!r}") since they can trigger nested/format errors at render time.
    for _, field, spec, conversion in parsed:
        if field is None:
            continue
        if spec:
            raise ConfigurationError(
                "feature_clause_template must not use a format spec on "
                f"'{{{field}}}'."
            )
        if conversion is not None:
            raise ConfigurationError(
                "feature_clause_template must not use a conversion on "
                f"'{{{field}}}'."
            )
    if "features" not in fields:
        raise ConfigurationError(
            "feature_clause_template must contain the '{features}' placeholder."
        )


def parse_detailer_builder_template(data: dict) -> DetailerBuilderTemplate:
    missing = [key for key in _TEMPLATE_KEYS if key not in data]
    if missing:
        raise ConfigurationError(
            "Detailer builder template is missing required keys: " + ", ".join(missing)
        )
    if not isinstance(data["version"], str) or not isinstance(
        data["feature_clause_template"], str
    ):
        raise ConfigurationError(
            "Detailer builder template 'version' and 'feature_clause_template' "
            "must be strings."
        )
    template = data["feature_clause_template"]
    _validate_template_fields(template)
    return DetailerBuilderTemplate(
        version=data["version"], feature_clause_template=template
    )


def load_detailer_builder_template(
    template_id: str = DEFAULT_DETAILER_BUILDER_ID,
) -> DetailerBuilderTemplate:
    safe_resource_id(template_id, "detailer builder template")
    resource = resource_file("prompts", f"{template_id}.json")
    try:
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(
            f"Detailer builder template not found: {template_id}"
        ) from exc
    return parse_detailer_builder_template(
        parse_config_json(text, f"prompts/{template_id}.json")
    )
