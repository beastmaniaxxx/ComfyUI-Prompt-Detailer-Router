"""Failure classification for Ollama calls: the single source of truth.

Pure domain logic (Requirements 4.1, 4.2, 4.4, 4.7, 4.12). Every failure the
Analyzer can hit collapses into one of eight kinds, and the ``failure_mode``
branch table is driven by that kind alone.

Two rules keep the classification stable:

* Retryability is a property of the *kind*. It never consults ``failure_mode``,
  and callers must not re-derive it from transport exception types.
* An HTTP status is classified by the status alone (Requirement 4.4/4.12), never
  by matching text in the response body. A missing model is simply a 404. Body
  text is carried as a summary for reporting, not as classification input.

The status mapping is total: every value outside 2xx maps to a kind, so no
status can slip through unclassified.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from prompt_detailer_router.domain.errors import PDRUserError

_LABELS = {
    "connection": "(a) connection failure",
    "timeout": "(b) timeout",
    "retryable_http": "(c) retryable HTTP error",
    "non_retryable_http": "(d) non-retryable HTTP error",
    "unusable_body": "(e) unusable response body",
    "json_parse": "(f) JSON parse failure",
    "schema_violation": "(g) schema violation",
    "configuration": "(h) configuration error",
}


class FailureKind(Enum):
    """The eight failure classes of Requirement 4.1, in requirement order."""

    CONNECTION = "connection"
    TIMEOUT = "timeout"
    RETRYABLE_HTTP = "retryable_http"
    NON_RETRYABLE_HTTP = "non_retryable_http"
    UNUSABLE_BODY = "unusable_body"
    JSON_PARSE = "json_parse"
    SCHEMA_VIOLATION = "schema_violation"
    CONFIGURATION = "configuration"

    @property
    def label(self) -> str:
        """Stable display name, e.g. ``"(a) connection failure"``."""

        return _LABELS[self.value]


RETRYABLE_FAILURE_KINDS: frozenset[FailureKind] = frozenset(
    {
        FailureKind.CONNECTION,
        FailureKind.TIMEOUT,
        FailureKind.RETRYABLE_HTTP,
        FailureKind.UNUSABLE_BODY,
        FailureKind.JSON_PARSE,
        FailureKind.SCHEMA_VIOLATION,
    }
)

RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})


def classify_http_status(status: int) -> FailureKind | None:
    """Map an HTTP status to a failure kind, or ``None`` for 2xx.

    Total by construction (Requirement 4.2): 2xx is not a failure, the six
    listed statuses are retryable, and *everything else* -- 3xx, other 4xx,
    other 5xx, and values outside the HTTP range -- is non-retryable.
    """

    if 200 <= status < 300:
        return None
    if status in RETRYABLE_HTTP_STATUSES:
        return FailureKind.RETRYABLE_HTTP
    return FailureKind.NON_RETRYABLE_HTTP


def is_retryable(kind: FailureKind) -> bool:
    """Return whether ``kind`` may be retried (Requirement 4.7)."""

    return kind in RETRYABLE_FAILURE_KINDS


@dataclass(frozen=True, slots=True)
class AnalyzerFailure:
    """What failed, in a form safe to show the user.

    ``detail`` never repeats user input and never contains a local absolute path
    (Requirements 9.3 / 9.4); it is reused verbatim in both ``diagnostics`` and
    the explicit-error message.
    """

    kind: FailureKind
    detail: str
    http_status: int | None = None
    body_summary: str | None = None


class AnalyzerExecutionError(PDRUserError):
    """Raised on the explicit-error path: no outputs are produced.

    ``message`` is pre-assembled in the Requirement 4.10 form by
    ``analyzer_report.render_error_message``.
    """

    def __init__(self, failure: AnalyzerFailure, message: str) -> None:
        super().__init__(message)
        self.failure = failure
        self.message = message
