"""Unit tests for the PR Budget declaration check (AGENTS.md §19.4)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL_PATH = _REPO_ROOT / "tools" / "check_pr_declaration.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_pr_declaration", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_pr_declaration"] = module
    spec.loader.exec_module(module)
    return module


checker = _load_module()


def _report(**overrides):
    report = {
        "verdict": "WITHIN_BUDGET",
        "over_lines": False,
        "over_files": False,
        "over_observations": False,
        "reasons": [],
        "advisories": [],
    }
    report.update(overrides)
    return report


def _body(**overrides) -> str:
    fields = {
        "BASE": "develop",
        "REVIEW_LINES": "100 / 1500",
        "REVIEW_FILES": "3 / 30",
        "TEST_LINES": "200",
        "OBSERVATIONS": "A 外部入力検証",
        "VERDICT": "WITHIN_BUDGET",
        "OVER_BUDGET_REASON": "N/A",
    }
    fields.update(overrides)
    lines = "\n".join(f"{key}: {value}" for key, value in fields.items())
    return f"## 概要\n\n本文\n\n## PR Budget\n\n```text\n{lines}\n```\n"


# --- Section / field parsing ------------------------------------------------


def test_missing_block_is_rejected() -> None:
    problems = checker.check(_report(), "## 概要\n\n計測していない本文")
    assert len(problems) == 1
    assert "## PR Budget" in problems[0]


def test_unedited_template_is_rejected() -> None:
    """The template itself contains the heading, so presence alone is not enough."""
    template = (_REPO_ROOT / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    problems = checker.check(_report(), template)
    assert any("必須フィールドが空" in problem for problem in problems)


def test_fully_filled_declaration_passes() -> None:
    assert checker.check(_report(), _body()) == []


def test_each_required_field_is_enforced() -> None:
    for field in checker.REQUIRED_FIELDS:
        problems = checker.check(_report(), _body(**{field: ""}))
        assert any(field in problem for problem in problems), field


def test_parsing_stops_at_the_next_heading() -> None:
    body = _body() + "\n## チェックリスト\n\nBASE: 別の値\n"
    assert checker.parse_declaration(body)["BASE"] == "develop"


def test_fields_outside_the_section_are_ignored() -> None:
    body = "VERDICT: WITHIN_BUDGET\n\n" + "## 概要\n\n本文\n"
    assert checker.parse_declaration(body) == {}


def test_inline_mention_of_the_heading_is_not_the_declaration() -> None:
    """PR #8's body mentions the block in prose before declaring it."""
    body = (
        "## 設計上の判断\n\n"
        "PR本文には `## PR Budget` ブロックを必ず含めます。\n\n" + _body()
    )
    assert checker.parse_declaration(body)["BASE"] == "develop"
    assert checker.check(_report(), body) == []


def test_prose_mention_alone_does_not_satisfy_the_requirement() -> None:
    body = "## 設計上の判断\n\n`## PR Budget` を必ず含めます。\n"
    problems = checker.check(_report(), body)
    assert len(problems) == 1
    assert "## PR Budget" in problems[0]


def test_first_section_without_fields_does_not_mask_the_real_one() -> None:
    body = "## PR Budget\n\n説明だけの節。\n\n" + _body()
    assert checker.parse_declaration(body)["VERDICT"] == "WITHIN_BUDGET"


# --- Estimate marker --------------------------------------------------------


def test_unconfirmed_estimate_marker_is_rejected() -> None:
    body = _body(OBSERVATIONS="A 外部入力検証  (推定 — 実分類を確認して修正すること)")
    problems = checker.check(_report(), body)
    assert any("推定" in problem for problem in problems)


def test_confirmed_observations_pass() -> None:
    assert checker.check(_report(), _body(OBSERVATIONS="A 外部入力検証")) == []


# --- Observation counting ---------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-", []),
        ("", []),
        ("A 外部入力検証", ["A"]),
        ("A 外部入力検証, C ドメイン不変条件", ["A", "C"]),
        ("A 外部入力検証、C ドメイン不変条件", ["A", "C"]),
        ("A 外部入力検証, A 重複", ["A"]),
        # F テスト is excluded from the count (AGENTS.md §19.2).
        ("A 外部入力検証, C ドメイン不変条件, F テスト", ["A", "C"]),
    ],
)
def test_declared_observation_classes(value: str, expected: list[str]) -> None:
    assert checker.declared_observation_classes(value) == expected


def test_three_declared_classes_force_over_budget() -> None:
    body = _body(
        OBSERVATIONS="A 外部入力検証, C ドメイン不変条件, D preset越境",
        VERDICT="WITHIN_BUDGET",
    )
    problems = checker.check(_report(), body)
    assert any("VERDICT" in problem for problem in problems)


def test_three_declared_classes_pass_when_declared_and_justified() -> None:
    body = _body(
        OBSERVATIONS="A 外部入力検証, C ドメイン不変条件, D preset越境",
        VERDICT="OVER_BUDGET",
        OVER_BUDGET_REASON="§19.3 により Schema と loader は分離不可",
    )
    assert checker.check(_report(), body) == []


def test_declaration_overrides_the_estimated_class_mix() -> None:
    """The estimate is a draft; the author's confirmed classes decide (§19.4)."""
    body = _body(OBSERVATIONS="A 外部入力検証", VERDICT="WITHIN_BUDGET")
    assert checker.check(_report(over_observations=True), body) == []


def test_measured_line_overrun_cannot_be_overridden() -> None:
    body = _body(OBSERVATIONS="A 外部入力検証", VERDICT="WITHIN_BUDGET")
    problems = checker.check(_report(over_lines=True), body)
    assert any("VERDICT" in problem for problem in problems)


def test_measured_file_overrun_cannot_be_overridden() -> None:
    body = _body(OBSERVATIONS="A 外部入力検証", VERDICT="WITHIN_BUDGET")
    problems = checker.check(_report(over_files=True), body)
    assert any("VERDICT" in problem for problem in problems)


# --- Over-budget reason -----------------------------------------------------


@pytest.mark.parametrize("reason", ["", "N/A", "なし", "   "])
def test_over_budget_without_reason_is_rejected(reason: str) -> None:
    body = _body(VERDICT="OVER_BUDGET", OVER_BUDGET_REASON=reason)
    problems = checker.check(_report(over_lines=True), body)
    assert any("OVER_BUDGET_REASON" in problem for problem in problems)


def test_over_budget_with_reason_passes() -> None:
    body = _body(
        VERDICT="OVER_BUDGET",
        OVER_BUDGET_REASON="§19.3 により Schema と loader を分離できない",
    )
    assert checker.check(_report(over_lines=True), body) == []


def test_stale_numbers_do_not_fail_the_check() -> None:
    """Only the verdict must stay current -- see the module docstring."""
    body = _body(REVIEW_LINES="1 / 1500", REVIEW_FILES="1 / 30")
    assert checker.check(_report(), body) == []


# --- CLI --------------------------------------------------------------------


def test_main_reads_body_from_file(tmp_path: Path) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text(
        '{"verdict": "WITHIN_BUDGET", "over_lines": false, "over_files": false,'
        ' "over_observations": false, "reasons": [], "advisories": []}',
        encoding="utf-8",
    )
    body = tmp_path / "body.md"
    body.write_text(_body(), encoding="utf-8")
    assert checker.main([str(budget), str(body)]) == 0


def test_main_fails_on_missing_declaration(tmp_path: Path) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text(
        '{"verdict": "WITHIN_BUDGET", "over_lines": false, "over_files": false,'
        ' "over_observations": false, "reasons": [], "advisories": []}',
        encoding="utf-8",
    )
    body = tmp_path / "body.md"
    body.write_text("計測していない本文", encoding="utf-8")
    assert checker.main([str(budget), str(body)]) == 1


def test_main_reports_bad_input(tmp_path: Path) -> None:
    assert checker.main([str(tmp_path / "missing.json")]) == 2
    assert checker.main([]) == 2
