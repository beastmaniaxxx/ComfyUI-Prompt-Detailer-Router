"""Unit tests for the PR size budget tool (AGENTS.md §19.2 / §19.4).

The tool lives in ``tools/`` rather than in the distributed package, so it is
imported by path instead of through ``prompt_detailer_router``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOL_PATH = Path(__file__).resolve().parents[2] / "tools" / "pr_budget.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pr_budget", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_budget"] = module
    spec.loader.exec_module(module)
    return module


pr_budget = _load_module()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("prompt_detailer_router/domain/scopes.py", "REVIEW"),
        ("prompt_detailer_router/resources/presets/detailer/face.json", "REVIEW"),
        ("prompt_detailer_router/resources/schemas/detailer_plan.json", "REVIEW"),
        ("web/js/extension.js", "REVIEW"),
        ("tests/unit/test_scopes.py", "TEST"),
        ("tests/fixtures/ollama/ok.json", "TEST"),
        (".kiro/specs/ollama-prompt-analyzer/design.md", "SPEC"),
        (".kiro/specs/ollama-prompt-analyzer/requirements.md", "SPEC"),
        # Progress tracking, not basis text -- see classify().
        (".kiro/specs/ollama-prompt-analyzer/tasks.md", "META"),
        ("docs/requirements/requirements-design-reference.md", "SPEC"),
        (".kiro/steering/product.md", "META"),
        (".agents/skills/kiro-impl/SKILL.md", "META"),
        (".github/workflows/pr-budget.yml", "META"),
        ("tools/pr_budget.py", "META"),
        ("AGENTS.md", "META"),
        ("pyproject.toml", "REVIEW"),
    ],
)
def test_classify_assigns_expected_category(path: str, expected: str) -> None:
    assert pr_budget.classify(path) == expected


def test_classify_accepts_windows_separators() -> None:
    assert pr_budget.classify(r"tests\unit\test_scopes.py") == "TEST"


def test_parse_numstat_reads_plain_records() -> None:
    # \x00 rather than \0: a following digit would make \0 an octal escape.
    raw = "10\t2\tprompt_detailer_router/domain/a.py\x005\t0\ttests/unit/test_a.py\x00"
    assert pr_budget.parse_numstat(raw) == [
        (10, 2, "prompt_detailer_router/domain/a.py"),
        (5, 0, "tests/unit/test_a.py"),
    ]


def test_parse_numstat_counts_binary_files_as_zero_lines() -> None:
    raw = "-\t-\tdocs/diagram.png\x00"
    assert pr_budget.parse_numstat(raw) == [(0, 0, "docs/diagram.png")]


def test_parse_numstat_uses_new_path_for_renames() -> None:
    raw = "3\t1\t\x00old/path.py\x00prompt_detailer_router/new/path.py\x00"
    assert pr_budget.parse_numstat(raw) == [
        (3, 1, "prompt_detailer_router/new/path.py")
    ]


def test_parse_numstat_rejects_truncated_rename_record() -> None:
    raw = "3\t1\t\x00old/path.py\x00"
    with pytest.raises(pr_budget.MeasurementError):
        pr_budget.parse_numstat(raw)


def _report(entries):
    return pr_budget.build_report(entries, base="develop", head="HEAD")


def test_tests_do_not_consume_the_review_budget() -> None:
    """PR#7's actual shape: 1,071 source lines but 1,821 test lines."""
    report = _report(
        [
            (1071, 42, "prompt_detailer_router/infrastructure/llm_prompt_loader.py"),
            (1821, 0, "tests/unit/test_llm_prompt_loader.py"),
        ]
    )
    assert report.review.added == 1071
    assert report.buckets["TEST"].added == 1821
    assert report.verdict == "WITHIN_BUDGET"


def test_over_budget_when_review_lines_exceed_threshold() -> None:
    report = _report(
        [(pr_budget.REVIEW_MAX_LINES + 1, 0, "prompt_detailer_router/domain/a.py")]
    )
    assert report.verdict == "OVER_BUDGET"
    assert any("REVIEW_LINES" in reason for reason in report.reasons)


def test_threshold_boundary_is_inclusive() -> None:
    report = _report(
        [(pr_budget.REVIEW_MAX_LINES, 0, "prompt_detailer_router/domain/a.py")]
    )
    assert report.verdict == "WITHIN_BUDGET"


def test_over_budget_when_review_files_exceed_threshold() -> None:
    entries = [
        (1, 0, f"prompt_detailer_router/domain/m{index}.py")
        for index in range(pr_budget.REVIEW_MAX_FILES + 1)
    ]
    report = _report(entries)
    assert report.verdict == "OVER_BUDGET"
    assert any("REVIEW_FILES" in reason for reason in report.reasons)


def test_deletions_do_not_consume_the_line_budget() -> None:
    report = _report([(10, 9000, "prompt_detailer_router/domain/a.py")])
    assert report.verdict == "WITHIN_BUDGET"


def test_spec_and_code_mix_is_advisory_not_a_verdict() -> None:
    report = _report(
        [
            (10, 0, "prompt_detailer_router/domain/a.py"),
            (10, 0, ".kiro/specs/f/requirements.md"),
        ]
    )
    assert report.mixes_spec_and_code is True
    assert report.verdict == "WITHIN_BUDGET"
    assert any("§19.1" in advisory for advisory in report.advisories)


def test_task_progress_updates_do_not_trip_the_spec_mix_advisory() -> None:
    """kiro-impl flips tasks.md checkboxes on every task (see classify())."""
    report = _report(
        [
            (1000, 0, "prompt_detailer_router/domain/a.py"),
            (23, 12, ".kiro/specs/ollama-prompt-analyzer/tasks.md"),
        ]
    )
    assert report.mixes_spec_and_code is False
    assert report.advisories == []


def test_meta_only_change_does_not_trip_the_spec_mix_advisory() -> None:
    report = _report([(900, 0, "AGENTS.md"), (50, 0, ".agents/skills/x/SKILL.md")])
    assert report.mixes_spec_and_code is False
    assert report.advisories == []


def test_large_test_diff_raises_an_advisory_only() -> None:
    report = _report([(pr_budget.TEST_ADVISORY_LINES + 1, 0, "tests/unit/test_big.py")])
    assert report.verdict == "WITHIN_BUDGET"
    assert any("TEST_LINES" in advisory for advisory in report.advisories)


def test_observations_are_deduplicated_and_exclude_unmatched_paths() -> None:
    found = pr_budget.observations(
        [
            "prompt_detailer_router/infrastructure/preset_loader.py",
            "prompt_detailer_router/infrastructure/policy_loader.py",
            "prompt_detailer_router/resources/presets/detailer/face.json",
            "pyproject.toml",
        ]
    )
    assert found == ["A 外部入力検証", "D preset越境"]


def test_markdown_output_contains_the_declaration_fields() -> None:
    report = _report([(10, 0, "prompt_detailer_router/domain/a.py")])
    rendered = pr_budget.render_markdown(report)
    for key in (
        "BASE:",
        "REVIEW_LINES:",
        "REVIEW_FILES:",
        "TEST_LINES:",
        "OBSERVATIONS:",
        "VERDICT:",
        "OVER_BUDGET_REASON:",
    ):
        assert key in rendered


class _FakeStream:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty
        self.calls: list[dict] = []

    def isatty(self) -> bool:
        return self._is_tty

    def reconfigure(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_redirected_output_is_forced_to_utf8() -> None:
    """A cp932 redirect would corrupt --format json for downstream readers."""
    stream = _FakeStream(is_tty=False)
    pr_budget.configure_stream(stream)
    assert stream.calls == [{"encoding": "utf-8", "newline": "\n"}]


def test_terminal_output_keeps_console_encoding() -> None:
    stream = _FakeStream(is_tty=True)
    pr_budget.configure_stream(stream)
    assert stream.calls == [{"errors": "replace"}]


def test_configure_stream_ignores_streams_without_reconfigure() -> None:
    pr_budget.configure_stream(object())  # must not raise


def test_json_output_is_machine_readable() -> None:
    import json

    report = _report([(10, 0, "prompt_detailer_router/domain/a.py")])
    payload = json.loads(pr_budget.render_json(report))
    assert payload["verdict"] == "WITHIN_BUDGET"
    assert payload["buckets"]["REVIEW"]["added"] == 10
