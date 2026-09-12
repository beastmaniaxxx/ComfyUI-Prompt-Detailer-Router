"""Assembly of ``warning``, ``diagnostics``, and the explicit-error message.

Pure domain logic (Requirements 3.12, 4.8-4.11, 8.1-8.5, 9.1-9.7, 11.2).

The two outputs have deliberately different contracts, which is why they use
separate enums:

* ``warning`` lists only what actually happened, in a fixed slot order. Same
  input and same response therefore give the same text (Requirement 8.4).
* ``diagnostics`` always lists all 21 items in a fixed order. Items that are not
  determined render as ``unavailable`` -- never as 0, an empty string, or a
  guess (Requirement 9.7). Its values include per-run facts such as elapsed
  time, so it is outside the four-output identity contract (Requirement 11.2)
  and only its item set and order are stable (Requirement 9.6).

Slots order the lines; they never replace the wording. Each warning line is a
sentence the caller writes so a user can tell what happened and what to do
(Requirement 8.3).

This module holds no user input. It renders exactly what the use case sets,
which is where the non-disclosure rules of Requirements 9.3 / 9.4 are enforced:
the endpoint is passed in as scheme/host/port only, and no local path is ever
handed to it.
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from prompt_detailer_router.domain.analyzer_failures import AnalyzerFailure

UNAVAILABLE = "unavailable"
_LLM_WARNING_PREFIX = "LLM: "


class WarningSlot(Enum):
    """Warning categories in output order (design "warning の並び順")."""

    UNSUPPORTED_SCOPES_DROPPED = "unsupported_scopes_dropped"
    NO_REQUESTED_SCOPES = "no_requested_scopes"
    EMPTY_PROMPT = "empty_prompt"
    EVIDENCE_DROPPED = "evidence_dropped"
    OUT_OF_SCOPE_FEATURES_IGNORED = "out_of_scope_features_ignored"
    LLM_WARNING = "llm_warning"
    RETRY_PERFORMED = "retry_performed"
    FALLBACK_USED = "fallback_used"
    FALLBACK_TASKS_GENERATED = "fallback_tasks_generated"
    FORBIDDEN_TERMS_REMOVED = "forbidden_terms_removed"


class DiagnosticsItem(Enum):
    """Diagnostics entries in output order (design "diagnostics の並び順")."""

    FAILURE_MODE = "failure_mode"
    ENDPOINT = "endpoint"
    MODEL = "model"
    FAILURE = "failure"
    HTTP_BODY_SUMMARY = "http_body_summary"
    RETRY = "retry"
    RESPONSE_TIME = "response_time"
    FALLBACK = "fallback"
    CACHE = "cache"
    BLANK_FEATURES_DROPPED = "blank_features_dropped"
    UPSCALE_PRESET = "upscale_preset"
    DETAILER_PRESET_PROFILE = "detailer_preset_profile"
    DETAILER_PRESETS = "detailer_presets"
    DETAILER_BUILDER_TEMPLATE = "detailer_builder_template"
    FORBIDDEN_TERMS_POLICY = "forbidden_terms_policy"
    SYSTEM_PROMPT = "system_prompt"
    REPAIR_PROMPT = "repair_prompt"
    SCOPE_DEFINITIONS = "scope_definitions"
    PROMPT_BUILDER_VERSION = "prompt_builder_version"
    RESPONSE_SCHEMA_VERSION = "response_schema_version"
    PLAN_SCHEMA_VERSION = "plan_schema_version"

    @property
    def label(self) -> str:
        """The name this item is printed under."""

        return self.value


def _http_summary(failure: AnalyzerFailure) -> str | None:
    """Render the HTTP status / body summary an error message can state."""

    if failure.http_status is None and not failure.body_summary:
        return None
    if failure.http_status is None:
        return failure.body_summary
    if not failure.body_summary:
        return f"HTTP {failure.http_status}"
    return f"HTTP {failure.http_status}: {failure.body_summary}"


class AnalyzerReport:
    """Collects report events during a run and renders the three outputs."""

    def __init__(self) -> None:
        self._warnings: dict[WarningSlot, list[str]] = {}
        self._items: dict[DiagnosticsItem, str] = {}

    def add_warning(self, slot: WarningSlot, message: str) -> None:
        """Record a warning line. Blank messages are ignored."""

        if not message.strip():
            return
        self._warnings.setdefault(slot, []).append(message)

    def add_llm_warnings(self, warnings: Sequence[str]) -> None:
        """Record warnings that came from the LLM, marked as such (Requirement 3.12).

        A warning from the response Schema may contain newlines, and
        ``render_warning`` joins every recorded line with newlines. Prefixing
        only the first line would leave the remainder indistinguishable from
        another slot's event, so each line is attributed individually.
        """

        for warning in warnings:
            for line in warning.splitlines():
                if not line.strip():
                    continue
                self.add_warning(WarningSlot.LLM_WARNING, _LLM_WARNING_PREFIX + line)

    def set_item(self, item: DiagnosticsItem, value: str) -> None:
        """Record a diagnostics value, replacing any earlier value for the item."""

        self._items[item] = value

    def render_warning(self) -> str:
        """Render the recorded warnings, or ``""`` when nothing happened."""

        lines: list[str] = []
        for slot in WarningSlot:
            lines.extend(self._warnings.get(slot, ()))
        return "\n".join(lines)

    def render_diagnostics(self) -> str:
        """Render all 21 items in order, with ``unavailable`` for unset ones."""

        return "\n".join(self._render_items())

    def render_error_message(
        self, failure: AnalyzerFailure, failure_mode: str
    ) -> str:
        """Render the explicit-error message (Requirements 4.10, 9.7).

        Carries the failure kind and the safe cause, then the same item list as
        ``diagnostics`` -- values for what is determined, ``unavailable`` for
        what is not. The failure itself determines three of those items
        (``failure_mode``, ``failure``, and the HTTP body summary), so they are
        filled in here rather than being reported as unavailable. Nothing is
        recorded on the report: rendering an error message twice yields the same
        text. ``warning`` and ``diagnostics`` are not emitted on this path.
        """

        determined = {
            DiagnosticsItem.FAILURE_MODE: failure_mode,
            DiagnosticsItem.FAILURE: failure.kind.label,
        }
        http_summary = _http_summary(failure)
        if http_summary is not None:
            determined[DiagnosticsItem.HTTP_BODY_SUMMARY] = http_summary

        lines = [
            f"Analyzer failed: {failure.kind.label}.",
            f"cause: {failure.detail}",
        ]
        lines.extend(self._render_items(determined))
        return "\n".join(lines)

    def _render_items(
        self, determined: dict[DiagnosticsItem, str] | None = None
    ) -> list[str]:
        values = dict(self._items)
        if determined:
            values.update(determined)
        return [
            f"{item.label}: {values.get(item, UNAVAILABLE)}"
            for item in DiagnosticsItem
        ]
