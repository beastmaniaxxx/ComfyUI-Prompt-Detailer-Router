"""Unit tests for cache-key computation (domain/analyzer_cache_key).

Requirements 11.3-11.5, 11.13: every component listed in 11.3 participates in
the key, the excluded ones (``keep_alive``, UI settings, diagnostics formatting)
do not, and serialization is structured so component boundaries cannot blur.
"""

import dataclasses

import pytest

from prompt_detailer_router.domain.analyzer_cache_key import (
    CacheKeyComponents,
    compute_cache_key,
)

BASE = CacheKeyComponents(
    original_prompt="a woman with blue eyes",
    requested_scopes=("face", "hair"),
    dropped_scopes=("feet",),
    subject_hint="main",
    endpoint_identity="http://127.0.0.1:11434",
    model="llama3",
    seed=0,
    temperature=0.2,
    timeout=120.0,
    failure_mode="safe_fallback",
    resources=(
        ("upscale_preset", "minimal", "1.0"),
        ("detailer_profile", "default_v1", "1.0"),
        ("system_prompt", "extraction_system_v1", "1.0"),
    ),
)

# One changed value per component of Requirement 11.3.
SINGLE_CHANGES = {
    "original_prompt": "a man with blue eyes",
    "requested_scopes": ("face", "hands"),
    "dropped_scopes": (),
    "subject_hint": "left_person",
    "endpoint_identity": "http://127.0.0.1:11435",
    "model": "qwen2.5",
    "seed": 1,
    "temperature": 0.3,
    "timeout": 60.0,
    "failure_mode": "strict",
    "resources": (
        ("upscale_preset", "minimal", "2.0"),
        ("detailer_profile", "default_v1", "1.0"),
        ("system_prompt", "extraction_system_v1", "1.0"),
    ),
}


def test_every_component_is_covered_by_the_single_change_table() -> None:
    fields = {field.name for field in dataclasses.fields(CacheKeyComponents)}
    assert fields == set(SINGLE_CHANGES)


@pytest.mark.parametrize("field", sorted(SINGLE_CHANGES))
def test_changing_one_component_changes_the_key(field: str) -> None:
    changed = dataclasses.replace(BASE, **{field: SINGLE_CHANGES[field]})
    assert compute_cache_key(changed) != compute_cache_key(BASE)


def test_identical_components_produce_the_same_key() -> None:
    assert compute_cache_key(BASE) == compute_cache_key(dataclasses.replace(BASE))


def test_key_is_stable_across_calls() -> None:
    assert compute_cache_key(BASE) == compute_cache_key(BASE)


def test_key_is_a_hex_digest() -> None:
    key = compute_cache_key(BASE)
    assert len(key) == 64
    assert all(char in "0123456789abcdef" for char in key)


# --- excluded components (Requirement 11.5) ---

@pytest.mark.parametrize("excluded", ["keep_alive", "diagnostics", "ui", "display"])
def test_excluded_components_are_not_fields(excluded: str) -> None:
    fields = {field.name for field in dataclasses.fields(CacheKeyComponents)}
    assert not any(excluded in name for name in fields)


# --- structured serialization: no boundary blurring ---

def test_scope_boundaries_are_not_blurred() -> None:
    a = dataclasses.replace(BASE, requested_scopes=("face", "hair"))
    b = dataclasses.replace(BASE, requested_scopes=("facehair",))
    assert compute_cache_key(a) != compute_cache_key(b)


def test_component_boundaries_are_not_blurred() -> None:
    a = dataclasses.replace(BASE, model="llama3", subject_hint="main")
    b = dataclasses.replace(BASE, model="llama3main", subject_hint="")
    assert compute_cache_key(a) != compute_cache_key(b)


def test_resource_triple_boundaries_are_not_blurred() -> None:
    a = dataclasses.replace(BASE, resources=(("preset", "ab", "1.0"),))
    b = dataclasses.replace(BASE, resources=(("preset", "a", "b1.0"),))
    assert compute_cache_key(a) != compute_cache_key(b)


def test_resource_order_is_part_of_the_key_input_but_content_decides() -> None:
    # The same set of resources listed in the sorted order the fingerprint
    # produces yields the same key.
    resources = (("a", "x", "1"), ("b", "y", "2"))
    a = dataclasses.replace(BASE, resources=resources)
    b = dataclasses.replace(BASE, resources=tuple(sorted(resources)))
    assert compute_cache_key(a) == compute_cache_key(b)


def test_adding_a_resource_changes_the_key() -> None:
    extended = BASE.resources + (("forbidden_terms_policy", "forbidden_terms_v1", "1.0"),)
    assert compute_cache_key(
        dataclasses.replace(BASE, resources=extended)
    ) != compute_cache_key(BASE)


def test_non_ascii_prompts_are_handled() -> None:
    a = dataclasses.replace(BASE, original_prompt="青い目の女性")
    b = dataclasses.replace(BASE, original_prompt="赤い目の女性")
    assert compute_cache_key(a) != compute_cache_key(b)


# --- immutability (AGENTS.md 22.4) ---

def test_components_are_immutable() -> None:
    with pytest.raises(Exception):
        BASE.model = "other"  # type: ignore[misc]


def test_sequence_components_are_stored_as_tuples() -> None:
    components = CacheKeyComponents(
        original_prompt="p",
        requested_scopes=["face"],  # type: ignore[arg-type]
        dropped_scopes=["feet"],  # type: ignore[arg-type]
        subject_hint="",
        endpoint_identity="http://127.0.0.1:11434",
        model="m",
        seed=0,
        temperature=0.0,
        timeout=1.0,
        failure_mode="strict",
        resources=[("a", "b", "c")],  # type: ignore[arg-type]
    )
    assert isinstance(components.requested_scopes, tuple)
    assert isinstance(components.dropped_scopes, tuple)
    assert isinstance(components.resources, tuple)
    assert all(isinstance(entry, tuple) for entry in components.resources)
