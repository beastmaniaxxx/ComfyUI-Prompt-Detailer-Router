"""Unit tests for the error hierarchy (domain/errors).

Covers Requirement 14.3: user-facing errors are distinguished from internal
errors, with explicit types for configuration, JSON decode, and plan validation
failures.
"""

from prompt_detailer_router.domain import errors


def test_user_errors_derive_from_user_base_and_pdr_base() -> None:
    for cls in (
        errors.ConfigurationError,
        errors.PlanDecodeError,
        errors.PlanValidationError,
    ):
        assert issubclass(cls, errors.PDRUserError)
        assert issubclass(cls, errors.PDRError)


def test_internal_error_is_not_a_user_error() -> None:
    assert issubclass(errors.PDRInternalError, errors.PDRError)
    assert not issubclass(errors.PDRInternalError, errors.PDRUserError)


def test_user_base_is_pdr_error() -> None:
    assert issubclass(errors.PDRUserError, errors.PDRError)


def test_errors_are_raisable_and_carry_message() -> None:
    import pytest

    with pytest.raises(errors.ConfigurationError, match="missing key"):
        raise errors.ConfigurationError("missing key")
