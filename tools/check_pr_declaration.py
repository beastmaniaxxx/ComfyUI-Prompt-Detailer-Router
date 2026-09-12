"""Validate the ``## PR Budget`` declaration in a PR body (AGENTS.md §19.4).

``tools/pr_budget.py`` measures the diff; this script checks that the PR body
actually declares the result. The split of authority follows §19.4:

* ``REVIEW_LINES`` / ``REVIEW_FILES`` overruns are measured and cannot be
  overridden by the declaration.
* The §22.1 observation classes are the author's call. ``pr_budget.py`` only
  estimates them, so the declared ``OBSERVATIONS`` wins.

The effective verdict combines both, and the declared ``VERDICT`` must match
it. The declared line/file *numbers* are not compared against the measurement:
requiring a body edit on every push would turn the declaration into noise, and
a stale number is cosmetic while a stale verdict is not.

Usage::

    python tools/check_pr_declaration.py budget.json          # body from $PR_BODY
    python tools/check_pr_declaration.py budget.json body.md

Exit codes: 0 = declaration acceptable, 1 = problems found, 2 = bad input.
Standard library only; runs on Python 3.10.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SECTION_HEADING = "## PR Budget"

REQUIRED_FIELDS = (
    "BASE",
    "REVIEW_LINES",
    "REVIEW_FILES",
    "TEST_LINES",
    "OBSERVATIONS",
    "VERDICT",
)

# pr_budget.py stamps this marker on the estimated OBSERVATIONS line. §19.4
# rejects a declaration that still carries it, which is what forces a human to
# confirm the classification instead of pasting the estimate unchanged.
ESTIMATE_MARKER = "(推定"

# §19.2 counts classes A-E; F テスト is excluded (see AGENTS.md §19.2).
COUNTED_CLASS_LETTERS = frozenset("ABCDE")

OBSERVATIONS_NONE = "-"

_FIELD_PATTERN = re.compile(
    r"^\s*(?P<key>[A-Z_]+)\s*:[ \t]*(?P<value>.*?)\s*$",
    re.MULTILINE,
)

# Anchored to the start of a line so a prose mention of the block -- e.g.
# "PR本文には `## PR Budget` ブロックを必ず含めます" -- is not mistaken for the
# declaration itself. A plain substring search picks up that sentence first and
# then parses an empty section.
_HEADING_PATTERN = re.compile(rf"^{re.escape(SECTION_HEADING)}", re.MULTILINE)

_NEXT_HEADING_PATTERN = re.compile(r"^#{1,2} ", re.MULTILINE)


def find_sections(body: str) -> list[str]:
    """Return every ``## PR Budget`` section body, in document order."""
    sections = []
    for match in _HEADING_PATTERN.finditer(body):
        rest = body[match.end() :]
        # Stop at the next heading of the same or higher level.
        end = _NEXT_HEADING_PATTERN.search(rest)
        sections.append(rest[: end.start()] if end else rest)
    return sections


def parse_section(section: str) -> dict[str, str]:
    """Parse ``KEY: value`` pairs out of one section."""
    return {
        match.group("key"): match.group("value")
        for match in _FIELD_PATTERN.finditer(section)
    }


def parse_declaration(body: str) -> dict[str, str]:
    """Parse the declaration fields from the PR Budget section.

    When several sections match, use the first one that actually carries
    declaration fields, so an introductory section does not mask the real one.
    """
    sections = find_sections(body)
    if not sections:
        return {}
    parsed = [parse_section(section) for section in sections]
    for fields in parsed:
        if any(field in fields for field in REQUIRED_FIELDS):
            return fields
    return parsed[0]


def declared_observation_classes(value: str) -> list[str]:
    """Count the §22.1 classes declared in an ``OBSERVATIONS`` value.

    Items are comma-separated and start with their class letter (``A`` .. ``E``);
    ``F テスト`` is not counted (AGENTS.md §19.2). ``-`` means none.
    """
    stripped = value.strip()
    if not stripped or stripped == OBSERVATIONS_NONE:
        return []
    found: list[str] = []
    for raw_item in re.split(r"[,、]", stripped):
        item = raw_item.strip()
        if not item:
            continue
        letter = item[0].upper()
        if letter in COUNTED_CLASS_LETTERS and letter not in found:
            found.append(letter)
    return sorted(found)


def check(report: dict, body: str) -> list[str]:
    """Return the §19.4 problems in ``body``; empty means acceptable."""
    if not find_sections(body):
        return [
            "PR本文に `## PR Budget` ブロックがありません。"
            "`python tools/pr_budget.py --format markdown` の出力を貼ってください"
            "（AGENTS.md §19.4）。"
        ]

    declaration = parse_declaration(body)
    problems: list[str] = []

    missing = [
        field for field in REQUIRED_FIELDS if not declaration.get(field, "").strip()
    ]
    if missing:
        problems.append(
            f"申告ブロックの必須フィールドが空です: {', '.join(missing)}"
            "（AGENTS.md §19.4）。"
        )

    observations_value = declaration.get("OBSERVATIONS", "")
    if ESTIMATE_MARKER in observations_value:
        problems.append(
            "`OBSERVATIONS` に推定の注記が残っています。"
            "§22.1 の実分類を確認し、注記を削除してください（AGENTS.md §19.4）。"
        )

    # Objective overruns come from the measurement; the class mix comes from
    # the declaration when it is usable (AGENTS.md §19.4).
    over_lines = bool(report.get("over_lines"))
    over_files = bool(report.get("over_files"))
    if observations_value.strip() and ESTIMATE_MARKER not in observations_value:
        over_observations = len(declared_observation_classes(observations_value)) >= 3
    else:
        over_observations = bool(report.get("over_observations"))

    effective = (
        "OVER_BUDGET"
        if (over_lines or over_files or over_observations)
        else "WITHIN_BUDGET"
    )

    declared_verdict = declaration.get("VERDICT", "").strip().upper()
    if declared_verdict and declared_verdict != effective:
        problems.append(
            f"申告された VERDICT ({declared_verdict}) が実測と申告分類から導かれる "
            f"判定 ({effective}) と一致しません（AGENTS.md §19.4）。"
        )

    if effective == "OVER_BUDGET":
        reason = declaration.get("OVER_BUDGET_REASON", "").strip()
        if reason in ("", "N/A", "なし"):
            problems.append(
                "VERDICT: OVER_BUDGET です。PRを分割するか、"
                "`OVER_BUDGET_REASON` に分割しない理由を記載してください"
                "（AGENTS.md §19.2 / §19.3 / §19.4）。"
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: check_pr_declaration.py <budget.json> [body.md]", file=sys.stderr)
        return 2

    try:
        report = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: 計測結果を読み込めません: {exc}", file=sys.stderr)
        return 2

    if len(args) > 1:
        try:
            body = Path(args[1]).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: PR本文を読み込めません: {exc}", file=sys.stderr)
            return 2
    else:
        body = os.environ.get("PR_BODY") or ""

    for reason in report.get("reasons", []):
        print(f"over budget: {reason}")
    for advisory in report.get("advisories", []):
        print(f"advisory: {advisory}")

    problems = check(report, body)
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 1

    print("PR Budget declaration OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
