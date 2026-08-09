"""Unit tests for scope normalization (domain/scopes).

Covers Requirements 1.1-1.5 (normalization, order-preserving dedup,
determinism) and 2.1-2.3 (unsupported scopes dropped with a warning, never
failing the pipeline).
"""

from prompt_detailer_router.domain import scopes


def test_supported_scopes_are_the_seven_v1_scopes() -> None:
    assert scopes.SUPPORTED_SCOPES == (
        "face",
        "hair",
        "hands",
        "body",
        "upper_body",
        "clothing",
        "generic",
    )


def test_split_trim_lowercase_and_drop_empty() -> None:
    result = scopes.normalize_scopes("Face, hair,  ,HANDS")
    assert result.requested_scopes == ("face", "hair", "hands")


def test_order_preserving_dedup() -> None:
    result = scopes.normalize_scopes("Face, hair, face,  hands")
    assert result.requested_scopes == ("face", "hair", "hands")
    assert result.dropped_scopes == ()
    assert result.warnings == ()


def test_unsupported_scope_dropped_with_warning() -> None:
    result = scopes.normalize_scopes("face, nose, hair")
    assert result.requested_scopes == ("face", "hair")
    assert result.dropped_scopes == ("nose",)
    assert result.warnings, "dropping an unsupported scope must produce a warning"
    assert any("nose" in w for w in result.warnings)


def test_unsupported_only_input_yields_empty_with_warning() -> None:
    result = scopes.normalize_scopes("nose, ears")
    assert result.requested_scopes == ()
    assert set(result.dropped_scopes) == {"nose", "ears"}
    assert result.warnings


def test_empty_input_yields_empty_with_warning() -> None:
    result = scopes.normalize_scopes("   ")
    assert result.requested_scopes == ()
    assert result.dropped_scopes == ()
    assert result.warnings, "empty input must produce a warning"


def test_normalization_is_deterministic() -> None:
    a = scopes.normalize_scopes("hair, face, hair")
    b = scopes.normalize_scopes("hair, face, hair")
    assert a == b


def test_is_supported_scope() -> None:
    assert scopes.is_supported_scope("face") is True
    assert scopes.is_supported_scope("nose") is False


def test_result_is_immutable() -> None:
    import dataclasses

    result = scopes.normalize_scopes("face")
    with__frozen = dataclasses.fields(result)
    assert with__frozen  # has fields
    try:
        result.requested_scopes = ("hair",)  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ScopeNormalizationResult must be frozen")
