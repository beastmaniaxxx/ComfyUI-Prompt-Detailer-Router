"""Unit tests for warning / diagnostics assembly (domain/analyzer_report).

Requirements 3.12, 4.8-4.11, 8.1-8.5, 9.1-9.7, 11.2: ten warning slots emitted
in a fixed order and only when they occurred, twenty-one diagnostics items
always emitted in a fixed order with ``unavailable`` for anything not yet
determined, and an error message that follows the same item order.
"""

import pytest

from prompt_detailer_router.domain.analyzer_failures import (
    AnalyzerFailure,
    FailureKind,
)
from prompt_detailer_router.domain.analyzer_report import (
    UNAVAILABLE,
    AnalyzerReport,
    DiagnosticsItem,
    WarningSlot,
)


# --- warning slots (Requirement 8.1, design warning table) ---

def test_there_are_ten_warning_slots() -> None:
    assert len(WarningSlot) == 10


def test_no_events_yields_an_empty_warning(  ) -> None:
    assert AnalyzerReport().render_warning() == ""


def test_a_single_event_is_rendered_as_its_message() -> None:
    report = AnalyzerReport()
    report.add_warning(WarningSlot.EMPTY_PROMPT, "No extraction was performed.")
    assert report.render_warning() == "No extraction was performed."


def test_warnings_are_ordered_by_slot_not_by_insertion() -> None:
    report = AnalyzerReport()
    report.add_warning(WarningSlot.FALLBACK_USED, "fallback")
    report.add_warning(WarningSlot.UNSUPPORTED_SCOPES_DROPPED, "dropped scopes")
    report.add_warning(WarningSlot.RETRY_PERFORMED, "retried")
    assert report.render_warning().splitlines() == [
        "dropped scopes",
        "retried",
        "fallback",
    ]


def test_slot_order_matches_the_declaration_order() -> None:
    report = AnalyzerReport()
    for slot in reversed(list(WarningSlot)):
        report.add_warning(slot, slot.name)
    assert report.render_warning().splitlines() == [slot.name for slot in WarningSlot]


def test_multiple_messages_in_one_slot_keep_insertion_order() -> None:
    # e.g. forbidden terms removed from the upscale prompt, then from each task.
    report = AnalyzerReport()
    report.add_warning(WarningSlot.FORBIDDEN_TERMS_REMOVED, "upscale: removed 1 term")
    report.add_warning(WarningSlot.FORBIDDEN_TERMS_REMOVED, "main.face: removed 2 terms")
    assert report.render_warning().splitlines() == [
        "upscale: removed 1 term",
        "main.face: removed 2 terms",
    ]


def test_same_events_render_identically(  ) -> None:
    def build() -> str:
        report = AnalyzerReport()
        report.add_warning(WarningSlot.EVIDENCE_DROPPED, "2 features dropped")
        report.add_warning(WarningSlot.LLM_WARNING, "x")
        return report.render_warning()

    assert build() == build()


def test_blank_warning_messages_are_ignored() -> None:
    report = AnalyzerReport()
    report.add_warning(WarningSlot.EMPTY_PROMPT, "   ")
    assert report.render_warning() == ""


# --- LLM-sourced warnings are identifiable (Requirement 3.12) ---

def test_llm_warnings_are_prefixed_and_land_in_their_slot() -> None:
    report = AnalyzerReport()
    report.add_warning(WarningSlot.RETRY_PERFORMED, "retried once")
    report.add_llm_warnings(["ambiguous subject", "contradictory colors"])
    lines = report.render_warning().splitlines()
    assert lines == [
        "LLM: ambiguous subject",
        "LLM: contradictory colors",
        "retried once",
    ]


def test_every_line_of_a_multiline_llm_warning_is_attributed() -> None:
    """Schema warnings may contain newlines (Requirement 3.12).

    Prefixing only the first line leaves the rest indistinguishable from another
    slot's event once ``render_warning`` joins everything with newlines.
    """
    report = AnalyzerReport()
    report.add_llm_warnings(["ambiguous\nfallback used"])
    assert report.render_warning().splitlines() == [
        "LLM: ambiguous",
        "LLM: fallback used",
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_all_newline_forms_are_attributed(newline: str) -> None:
    report = AnalyzerReport()
    report.add_llm_warnings([f"first{newline}second"])
    assert report.render_warning().splitlines() == ["LLM: first", "LLM: second"]


def test_blank_lines_inside_a_multiline_llm_warning_are_dropped() -> None:
    report = AnalyzerReport()
    report.add_llm_warnings(["first\n\n   \nsecond"])
    assert report.render_warning().splitlines() == ["LLM: first", "LLM: second"]


def test_multiline_llm_warning_keeps_slot_ordering() -> None:
    report = AnalyzerReport()
    report.add_warning(WarningSlot.RETRY_PERFORMED, "retried once")
    report.add_llm_warnings(["ambiguous\nfallback used"])
    assert report.render_warning().splitlines() == [
        "LLM: ambiguous",
        "LLM: fallback used",
        "retried once",
    ]


def test_blank_llm_warnings_are_ignored() -> None:
    report = AnalyzerReport()
    report.add_llm_warnings(["", "   "])
    assert report.render_warning() == ""


def test_empty_llm_warning_sequence_adds_nothing() -> None:
    report = AnalyzerReport()
    report.add_llm_warnings([])
    assert report.render_warning() == ""


# --- diagnostics items (Requirements 9.1, 9.2, 9.6) ---

def test_there_are_twenty_one_diagnostics_items() -> None:
    assert len(DiagnosticsItem) == 21


def test_all_items_are_always_rendered_in_declaration_order() -> None:
    rendered = AnalyzerReport().render_diagnostics().splitlines()
    assert len(rendered) == 21
    assert [line.split(":", 1)[0] for line in rendered] == [
        item.label for item in DiagnosticsItem
    ]


def test_unset_items_render_as_unavailable() -> None:
    rendered = AnalyzerReport().render_diagnostics().splitlines()
    assert all(line.endswith(UNAVAILABLE) for line in rendered)
    assert UNAVAILABLE == "unavailable"


def test_set_items_render_their_value() -> None:
    report = AnalyzerReport()
    report.set_item(DiagnosticsItem.FAILURE_MODE, "safe_fallback")
    report.set_item(DiagnosticsItem.MODEL, "llama3")
    rendered = report.render_diagnostics()
    assert "failure_mode: safe_fallback" in rendered
    assert "model: llama3" in rendered


def test_item_set_is_identical_regardless_of_what_happened() -> None:
    quiet = AnalyzerReport()
    busy = AnalyzerReport()
    busy.set_item(DiagnosticsItem.FAILURE, FailureKind.TIMEOUT.label)
    busy.set_item(DiagnosticsItem.RETRY, "performed (1)")

    def labels(report: AnalyzerReport) -> list[str]:
        return [line.split(":", 1)[0] for line in report.render_diagnostics().splitlines()]

    assert labels(quiet) == labels(busy)


def test_setting_an_item_twice_keeps_the_last_value() -> None:
    report = AnalyzerReport()
    report.set_item(DiagnosticsItem.CACHE, "miss")
    report.set_item(DiagnosticsItem.CACHE, "reused")
    assert "cache: reused" in report.render_diagnostics()


def test_response_derived_item_is_present_for_the_cache_contract() -> None:
    # Requirement 11.7 / 11.12: this item is response-derived and must be
    # reconstructable on a cache hit, so it has its own slot.
    assert DiagnosticsItem.BLANK_FEATURES_DROPPED in list(DiagnosticsItem)


@pytest.mark.parametrize(
    "item",
    [
        DiagnosticsItem.UPSCALE_PRESET,
        DiagnosticsItem.DETAILER_PRESET_PROFILE,
        DiagnosticsItem.DETAILER_PRESETS,
        DiagnosticsItem.DETAILER_BUILDER_TEMPLATE,
        DiagnosticsItem.FORBIDDEN_TERMS_POLICY,
        DiagnosticsItem.SYSTEM_PROMPT,
        DiagnosticsItem.REPAIR_PROMPT,
        DiagnosticsItem.SCOPE_DEFINITIONS,
        DiagnosticsItem.PROMPT_BUILDER_VERSION,
        DiagnosticsItem.RESPONSE_SCHEMA_VERSION,
        DiagnosticsItem.PLAN_SCHEMA_VERSION,
    ],
)
def test_every_resource_item_of_requirement_9_2_exists(item: DiagnosticsItem) -> None:
    assert item in list(DiagnosticsItem)


# --- error message (Requirements 4.10, 9.7) ---

def _failure() -> AnalyzerFailure:
    return AnalyzerFailure(
        kind=FailureKind.TIMEOUT,
        detail="Ollama did not respond within the timeout.",
        http_status=None,
    )


def test_error_message_states_the_failure_kind_mode_and_cause() -> None:
    message = AnalyzerReport().render_error_message(_failure(), "strict")
    assert FailureKind.TIMEOUT.label in message
    assert "strict" in message
    assert "Ollama did not respond within the timeout." in message


def test_error_message_lists_items_in_the_diagnostics_order() -> None:
    report = AnalyzerReport()
    report.set_item(DiagnosticsItem.MODEL, "llama3")
    message = report.render_error_message(_failure(), "strict")
    labels = [
        line.split(":", 1)[0]
        for line in message.splitlines()
        if line.split(":", 1)[0] in {item.label for item in DiagnosticsItem}
    ]
    assert labels == [item.label for item in DiagnosticsItem]


def test_error_message_marks_undetermined_items_as_unavailable() -> None:
    report = AnalyzerReport()
    report.set_item(DiagnosticsItem.MODEL, "llama3")
    message = report.render_error_message(_failure(), "strict")
    assert "model: llama3" in message
    # Nothing else was determined yet: no zeros, no defaults, no guesses.
    assert f"response_time: {UNAVAILABLE}" in message
    assert f"upscale_preset: {UNAVAILABLE}" in message


def test_error_message_does_not_include_warnings() -> None:
    report = AnalyzerReport()
    report.add_warning(WarningSlot.EMPTY_PROMPT, "no extraction performed")
    message = report.render_error_message(_failure(), "strict")
    assert "no extraction performed" not in message


def test_error_message_includes_the_http_body_summary_when_present() -> None:
    failure = AnalyzerFailure(
        kind=FailureKind.NON_RETRYABLE_HTTP,
        detail="Ollama rejected the request.",
        http_status=404,
        body_summary="model not found",
    )
    message = AnalyzerReport().render_error_message(failure, "retry_once")
    assert "404" in message
    assert "model not found" in message


def test_error_message_is_deterministic() -> None:
    report = AnalyzerReport()
    report.set_item(DiagnosticsItem.MODEL, "llama3")
    first = report.render_error_message(_failure(), "strict")
    second = report.render_error_message(_failure(), "strict")
    assert first == second


# --- non-disclosure (Requirements 9.3, 9.4) ---

def test_report_never_receives_the_prompt_or_hint() -> None:
    # The report has no access to user input: it can only render what the use
    # case sets, so a prompt cannot leak through this module.
    import inspect

    source = inspect.getsource(AnalyzerReport)
    assert "original_prompt" not in source
    assert "subject_hint" not in source


def test_rendering_contains_only_what_was_set() -> None:
    report = AnalyzerReport()
    report.set_item(DiagnosticsItem.ENDPOINT, "http://127.0.0.1:11434")
    rendered = report.render_diagnostics()
    assert "http://127.0.0.1:11434" in rendered
    assert "/api/chat" not in rendered
    assert "C:\\" not in rendered and "/home/" not in rendered
