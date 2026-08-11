"""Unit tests for failure classification (domain/analyzer_failures).

Requirements 4.1, 4.2, 4.4, 4.7, 4.12: eight failure kinds, a total HTTP status
mapping with no undefined value outside 2xx, and a retryable set derived from
the kind alone (never from ``failure_mode`` or from response body text).
"""

import pytest

from prompt_detailer_router.domain import analyzer_failures as af
from prompt_detailer_router.domain.analyzer_failures import FailureKind
from prompt_detailer_router.domain.errors import PDRUserError


# --- the eight kinds (Requirement 4.1) ---

def test_exactly_eight_failure_kinds() -> None:
    assert len(FailureKind) == 8


def test_every_kind_has_a_stable_label() -> None:
    labels = [kind.label for kind in FailureKind]
    assert len(set(labels)) == 8
    assert all(label.strip() for label in labels)
    # The labels carry the (a)-(h) letters the requirements use.
    assert [label[:3] for label in labels] == [
        "(a)", "(b)", "(c)", "(d)", "(e)", "(f)", "(g)", "(h)"
    ]


# --- retryability is a property of the kind (Requirement 4.7) ---

def test_retryable_set_is_exactly_six_kinds() -> None:
    assert af.RETRYABLE_FAILURE_KINDS == frozenset(
        {
            FailureKind.CONNECTION,
            FailureKind.TIMEOUT,
            FailureKind.RETRYABLE_HTTP,
            FailureKind.UNUSABLE_BODY,
            FailureKind.JSON_PARSE,
            FailureKind.SCHEMA_VIOLATION,
        }
    )
    assert len(af.RETRYABLE_FAILURE_KINDS) == 6


def test_non_retryable_kinds_are_exactly_two() -> None:
    non_retryable = set(FailureKind) - af.RETRYABLE_FAILURE_KINDS
    assert non_retryable == {
        FailureKind.NON_RETRYABLE_HTTP,
        FailureKind.CONFIGURATION,
    }


@pytest.mark.parametrize("kind", list(FailureKind))
def test_is_retryable_agrees_with_the_declared_set(kind: FailureKind) -> None:
    assert af.is_retryable(kind) is (kind in af.RETRYABLE_FAILURE_KINDS)


# --- the HTTP status table is total (Requirement 4.2) ---

@pytest.mark.parametrize("status", [200, 201, 202, 204, 226, 299])
def test_2xx_is_not_a_failure(status: int) -> None:
    assert af.classify_http_status(status) is None


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_listed_statuses_are_retryable(status: int) -> None:
    assert af.classify_http_status(status) is FailureKind.RETRYABLE_HTTP


def test_retryable_status_set_matches_the_requirement_table() -> None:
    assert af.RETRYABLE_HTTP_STATUSES == frozenset({408, 429, 500, 502, 503, 504})


@pytest.mark.parametrize("status", [300, 301, 302, 303, 307, 308, 399])
def test_3xx_is_non_retryable(status: int) -> None:
    assert af.classify_http_status(status) is FailureKind.NON_RETRYABLE_HTTP


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409, 418, 499])
def test_other_4xx_is_non_retryable(status: int) -> None:
    assert af.classify_http_status(status) is FailureKind.NON_RETRYABLE_HTTP


@pytest.mark.parametrize("status", [501, 505, 506, 510, 599])
def test_other_5xx_is_non_retryable(status: int) -> None:
    assert af.classify_http_status(status) is FailureKind.NON_RETRYABLE_HTTP


@pytest.mark.parametrize("status", [-1, 0, 1, 100, 101, 199, 600, 700, 999, 10000])
def test_out_of_range_statuses_are_non_retryable(status: int) -> None:
    # No status outside 2xx may be left undefined (Requirement 4.2, last row).
    assert af.classify_http_status(status) is FailureKind.NON_RETRYABLE_HTTP


def test_classification_is_total_over_a_wide_range() -> None:
    for status in range(-10, 1000):
        result = af.classify_http_status(status)
        if 200 <= status < 300:
            assert result is None
        else:
            assert result in (
                FailureKind.RETRYABLE_HTTP,
                FailureKind.NON_RETRYABLE_HTTP,
            )


# --- model-not-found is status 404, never body text (Requirement 4.4) ---

def test_model_not_found_is_classified_as_404_without_body_inspection() -> None:
    assert af.classify_http_status(404) is FailureKind.NON_RETRYABLE_HTTP
    assert not af.is_retryable(af.classify_http_status(404))


def test_classify_http_status_takes_no_body_argument() -> None:
    import inspect

    parameters = list(inspect.signature(af.classify_http_status).parameters)
    assert parameters == ["status"]


# --- the failure value object and the explicit-error exception ---

def test_failure_carries_kind_and_safe_detail() -> None:
    failure = af.AnalyzerFailure(
        kind=FailureKind.TIMEOUT, detail="The request exceeded the timeout."
    )
    assert failure.kind is FailureKind.TIMEOUT
    assert failure.http_status is None
    assert failure.body_summary is None


def test_failure_is_immutable() -> None:
    failure = af.AnalyzerFailure(kind=FailureKind.CONNECTION, detail="d")
    with pytest.raises(Exception):
        failure.detail = "changed"  # type: ignore[misc]


def test_failure_records_status_and_body_summary() -> None:
    failure = af.AnalyzerFailure(
        kind=FailureKind.NON_RETRYABLE_HTTP,
        detail="Ollama rejected the request.",
        http_status=404,
        body_summary="model 'x' not found",
    )
    assert (failure.http_status, failure.body_summary) == (404, "model 'x' not found")


def test_execution_error_is_a_user_error_carrying_the_failure() -> None:
    failure = af.AnalyzerFailure(kind=FailureKind.CONFIGURATION, detail="bad url")
    error = af.AnalyzerExecutionError(failure, "Analyzer failed: bad url")
    assert isinstance(error, PDRUserError)
    assert error.failure is failure
    assert str(error) == "Analyzer failed: bad url"
