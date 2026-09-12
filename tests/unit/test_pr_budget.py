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


def test_three_observation_classes_are_over_budget() -> None:
    """§19.2's third split condition, not only lines and files."""
    report = _report(
        [
            (50, 0, "prompt_detailer_router/infrastructure/preset_loader.py"),  # A
            (50, 0, "prompt_detailer_router/domain/detailer_plan.py"),  # C
            (10, 0, "prompt_detailer_router/resources/presets/face.json"),  # D
        ]
    )
    assert report.observation_classes == [
        "A 外部入力検証",
        "C ドメイン不変条件",
        "D preset越境",
    ]
    assert report.over_observations is True
    assert report.verdict == "OVER_BUDGET"
    assert any("OBSERVATIONS" in reason for reason in report.reasons)


def test_two_observation_classes_stay_within_budget() -> None:
    report = _report(
        [
            (50, 0, "prompt_detailer_router/infrastructure/preset_loader.py"),  # A
            (50, 0, "prompt_detailer_router/domain/detailer_plan.py"),  # C
        ]
    )
    assert report.over_observations is False
    assert report.verdict == "WITHIN_BUDGET"


def test_test_class_is_excluded_from_the_observation_count() -> None:
    """§14 puts tests in every implementation PR, so F must not count (§19.2)."""
    report = _report(
        [
            (50, 0, "prompt_detailer_router/infrastructure/preset_loader.py"),  # A
            (50, 0, "prompt_detailer_router/domain/detailer_plan.py"),  # C
            (900, 0, "tests/unit/test_preset_loader.py"),  # F -- not counted
        ]
    )
    assert pr_budget.OBSERVATION_LABEL_TEST not in report.observation_classes
    assert report.verdict == "WITHIN_BUDGET"


def test_observation_count_appears_in_every_output_format() -> None:
    import json as json_module

    report = _report(
        [
            (50, 0, "prompt_detailer_router/infrastructure/a.py"),
            (50, 0, "prompt_detailer_router/domain/b.py"),
            (10, 0, "prompt_detailer_router/resources/presets/c.json"),
        ]
    )
    assert "OVER_BUDGET" in pr_budget.render_text(report)
    assert "OVER_BUDGET" in pr_budget.render_markdown(report)
    payload = json_module.loads(pr_budget.render_json(report))
    assert payload["over_observations"] is True
    assert len(payload["observations"]) == 3
    assert payload["thresholds"]["observation_max_classes"] == 3


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


# --- Base ref resolution ----------------------------------------------------


@pytest.fixture
def fake_refs(monkeypatch):
    """Control which refs 'exist' without touching a real repository."""

    def install(existing: set[str], gh_base: str | None = None):
        monkeypatch.setattr(pr_budget, "ref_exists", lambda ref: ref in existing)
        monkeypatch.setattr(pr_budget, "base_from_gh", lambda: gh_base)

    return install


def test_resolve_ref_prefers_the_remote_tracking_form(fake_refs) -> None:
    fake_refs({"origin/main", "main"})
    assert pr_budget.resolve_ref("main") == "origin/main"


def test_resolve_ref_falls_back_to_a_local_only_branch(fake_refs) -> None:
    fake_refs({"main"})
    assert pr_budget.resolve_ref("main") == "main"


def test_resolve_ref_returns_none_when_unresolvable(fake_refs) -> None:
    fake_refs(set())
    assert pr_budget.resolve_ref("main") is None


def test_gh_base_name_is_resolved_to_a_remote_tracking_ref(fake_refs) -> None:
    """A fresh clone has origin/main but no local main branch."""
    fake_refs({"origin/main"}, gh_base="main")
    assert pr_budget.resolve_base(None) == "origin/main"


def test_unresolvable_gh_base_falls_through_to_the_defaults(fake_refs) -> None:
    fake_refs({"origin/develop"}, gh_base="deleted-branch")
    assert pr_budget.resolve_base(None) == "origin/develop"


def test_explicit_base_is_resolved_to_a_remote_tracking_ref(fake_refs) -> None:
    fake_refs({"origin/feature"})
    assert pr_budget.resolve_base("feature") == "origin/feature"


def test_unresolvable_explicit_base_raises_a_usable_message(fake_refs) -> None:
    fake_refs({"origin/main"})
    with pytest.raises(pr_budget.MeasurementError) as excinfo:
        pr_budget.resolve_base("only-on-remote")
    message = str(excinfo.value)
    assert "only-on-remote" in message
    assert "git fetch" in message


def test_no_candidate_resolves_raises(fake_refs) -> None:
    fake_refs(set())
    with pytest.raises(pr_budget.MeasurementError):
        pr_budget.resolve_base(None)


def test_measure_rejects_an_unresolvable_head(fake_refs) -> None:
    fake_refs({"origin/main"})
    with pytest.raises(pr_budget.MeasurementError) as excinfo:
        pr_budget.measure("origin/main", "no-such-head")
    assert "no-such-head" in str(excinfo.value)


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
