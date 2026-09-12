"""Unit tests for LLM resource loading (infrastructure/llm_prompt_loader).

Requirements 2.3, 2.6, 10.13, 10.14, 10.15, 10.16: the LLM system prompt, the
repair prompt, and the scope definitions load through the *shared* config-JSON
validation path, and every anomaly surfaces as ConfigurationError instead of a
raw JSONDecodeError / UnicodeDecodeError / KeyError / TypeError.
"""

import json

import pytest

from prompt_detailer_router.domain.errors import ConfigurationError
from prompt_detailer_router.domain.scopes import SUPPORTED_SCOPES
from prompt_detailer_router.infrastructure import llm_prompt_loader

VALID_PROMPT = {"id": "extraction_system_v1", "version": "1.0", "text": "Extract."}
VALID_DEFINITIONS = {
    "id": "scope_definitions_v1",
    "version": "1.0",
    "definitions": {scope: f"{scope} details" for scope in SUPPORTED_SCOPES},
}


class _TextResource:
    """Stands in for a bundled resource file with arbitrary raw contents."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._text


class _BadUtf8Resource:
    def read_text(self, encoding: str = "utf-8") -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def _serve(monkeypatch, resource) -> list[tuple[str, ...]]:
    """Serve ``resource`` for every lookup, recording the requested path parts."""

    seen: list[tuple[str, ...]] = []

    def fake_resource_file(*parts: str):
        seen.append(parts)
        return resource

    monkeypatch.setattr(llm_prompt_loader, "resource_file", fake_resource_file)
    return seen


def _serve_json(monkeypatch, data: object) -> list[tuple[str, ...]]:
    return _serve(monkeypatch, _TextResource(json.dumps(data)))


# --- happy path: the bundled resources load ---

def test_load_bundled_system_prompt() -> None:
    prompt = llm_prompt_loader.load_llm_prompt(
        llm_prompt_loader.DEFAULT_EXTRACTION_PROMPT_ID
    )
    assert prompt.id == "extraction_system_v1"
    assert prompt.version and prompt.text.strip()


def test_load_bundled_repair_prompt() -> None:
    prompt = llm_prompt_loader.load_llm_prompt(
        llm_prompt_loader.DEFAULT_REPAIR_PROMPT_ID
    )
    assert prompt.id == "extraction_repair_v1"
    assert prompt.version and prompt.text.strip()


def test_load_bundled_scope_definitions_covers_seven_scopes() -> None:
    definitions = llm_prompt_loader.load_scope_definitions()
    assert definitions.id == "scope_definitions_v1"
    assert set(definitions.definitions) == set(SUPPORTED_SCOPES)
    assert all(text.strip() for text in definitions.definitions.values())


def test_scope_definitions_default_id_is_the_bundled_one() -> None:
    assert (
        llm_prompt_loader.load_scope_definitions().id
        == llm_prompt_loader.DEFAULT_SCOPE_DEFINITIONS_ID
    )


def test_scope_definitions_mapping_is_immutable() -> None:
    definitions = llm_prompt_loader.load_scope_definitions()
    with pytest.raises(TypeError):
        definitions.definitions["face"] = "changed"  # type: ignore[index]


def test_prompts_resolve_under_the_prompts_directory(monkeypatch) -> None:
    seen = _serve_json(monkeypatch, VALID_PROMPT)
    llm_prompt_loader.load_llm_prompt("extraction_system_v1")
    assert seen == [("prompts", "extraction_system_v1.json")]


# --- 10 anomaly classes, per prompt resource and scope definitions ---

def test_prompt_invalid_json_raises(monkeypatch) -> None:
    _serve(monkeypatch, _TextResource("{ not valid json"))
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


def test_definitions_invalid_json_raises(monkeypatch) -> None:
    _serve(monkeypatch, _TextResource("{ not valid json"))
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


def test_prompt_non_utf8_raises(monkeypatch) -> None:
    _serve(monkeypatch, _BadUtf8Resource())
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


def test_definitions_non_utf8_raises(monkeypatch) -> None:
    _serve(monkeypatch, _BadUtf8Resource())
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


def test_prompt_duplicate_key_raises(monkeypatch) -> None:
    _serve(
        monkeypatch,
        _TextResource(
            '{"id": "extraction_system_v1", "version": "1.0", '
            '"text": "a", "text": "b"}'
        ),
    )
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


def test_definitions_duplicate_key_raises(monkeypatch) -> None:
    _serve(
        monkeypatch,
        _TextResource(
            '{"id": "scope_definitions_v1", "version": "1.0", '
            '"definitions": {}, "definitions": {}}'
        ),
    )
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


def test_definitions_duplicate_scope_key_raises(monkeypatch) -> None:
    # A duplicate *inside* ``definitions`` must not be accepted last-wins either.
    body = json.dumps(VALID_DEFINITIONS["definitions"])[:-1] + ', "face": "again"}'
    _serve(
        monkeypatch,
        _TextResource(
            '{"id": "scope_definitions_v1", "version": "1.0", '
            f'"definitions": {body}}}'
        ),
    )
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


@pytest.mark.parametrize("text", ["null", "5", '"a string"', "[1, 2]"])
def test_prompt_non_object_root_raises(monkeypatch, text: str) -> None:
    _serve(monkeypatch, _TextResource(text))
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


@pytest.mark.parametrize("text", ["null", "5", '"a string"', "[1, 2]"])
def test_definitions_non_object_root_raises(monkeypatch, text: str) -> None:
    _serve(monkeypatch, _TextResource(text))
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


@pytest.mark.parametrize("missing", ["id", "version", "text"])
def test_prompt_missing_required_key_raises(monkeypatch, missing: str) -> None:
    data = {key: value for key, value in VALID_PROMPT.items() if key != missing}
    _serve_json(monkeypatch, data)
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


@pytest.mark.parametrize("missing", ["id", "version", "definitions"])
def test_definitions_missing_required_key_raises(monkeypatch, missing: str) -> None:
    data = {key: value for key, value in VALID_DEFINITIONS.items() if key != missing}
    _serve_json(monkeypatch, data)
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


@pytest.mark.parametrize("key", ["id", "version", "text"])
@pytest.mark.parametrize("value", [1, True, None, [], {}])
def test_prompt_wrong_value_type_raises(monkeypatch, key: str, value: object) -> None:
    _serve_json(monkeypatch, {**VALID_PROMPT, key: value})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


@pytest.mark.parametrize("value", [1, True, None, [], "text"])
def test_definitions_wrong_definitions_type_raises(monkeypatch, value: object) -> None:
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "definitions": value})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


@pytest.mark.parametrize("value", [1, True, None, [], {}])
def test_definitions_wrong_scope_value_type_raises(
    monkeypatch, value: object
) -> None:
    definitions = {**VALID_DEFINITIONS["definitions"], "face": value}
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "definitions": definitions})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
@pytest.mark.parametrize("key", ["id", "version", "text"])
def test_prompt_blank_required_string_raises(
    monkeypatch, key: str, blank: str
) -> None:
    _serve_json(monkeypatch, {**VALID_PROMPT, key: blank})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_definitions_blank_scope_text_raises(monkeypatch, blank: str) -> None:
    definitions = {**VALID_DEFINITIONS["definitions"], "hair": blank}
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "definitions": definitions})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


def test_prompt_unknown_field_raises(monkeypatch) -> None:
    _serve_json(monkeypatch, {**VALID_PROMPT, "txet": "typo"})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


def test_definitions_unknown_field_raises(monkeypatch) -> None:
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "defintions": {}})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


def test_definitions_unknown_scope_key_raises(monkeypatch) -> None:
    definitions = {**VALID_DEFINITIONS["definitions"], "feet": "toes"}
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "definitions": definitions})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


@pytest.mark.parametrize(
    "unsafe",
    ["../secrets", "a/b", "a.b", "", "  ", "extraction_system_v1.json", "a\\b"],
)
def test_unsafe_prompt_id_raises(unsafe: str) -> None:
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt(unsafe)


@pytest.mark.parametrize("unsafe", ["../secrets", "a/b", "a.b", "", "  "])
def test_unsafe_definitions_id_raises(unsafe: str) -> None:
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions(unsafe)


def test_prompt_id_mismatch_raises(monkeypatch) -> None:
    _serve_json(monkeypatch, {**VALID_PROMPT, "id": "some_other_prompt"})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_llm_prompt("extraction_system_v1")


def test_definitions_id_mismatch_raises(monkeypatch) -> None:
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "id": "other_definitions"})
    with pytest.raises(ConfigurationError):
        llm_prompt_loader.load_scope_definitions()


# --- Requirement 10.14: a missing scope is never substituted with an empty one ---

@pytest.mark.parametrize("dropped", SUPPORTED_SCOPES)
def test_definitions_missing_scope_raises(monkeypatch, dropped: str) -> None:
    definitions = {
        scope: text
        for scope, text in VALID_DEFINITIONS["definitions"].items()
        if scope != dropped
    }
    _serve_json(monkeypatch, {**VALID_DEFINITIONS, "definitions": definitions})
    with pytest.raises(ConfigurationError) as excinfo:
        llm_prompt_loader.load_scope_definitions()
    assert dropped in str(excinfo.value)


# --- the loader owns no validation implementation of its own (Requirement 10.15) ---

def test_loader_delegates_to_the_shared_validation_helpers() -> None:
    from prompt_detailer_router.infrastructure import config_json, resource_ids

    assert llm_prompt_loader.read_config_json is config_json.read_config_json
    assert llm_prompt_loader.reject_unknown_keys is config_json.reject_unknown_keys
    assert llm_prompt_loader.require_keys is config_json.require_keys
    assert llm_prompt_loader.require_str_fields is config_json.require_str_fields
    assert llm_prompt_loader.safe_resource_id is resource_ids.safe_resource_id
