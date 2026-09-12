"""PR size budget measurement (AGENTS.md §19.2 / §19.4).

Classifies the diff between a base ref and HEAD into review-bearing source,
tests, spec documents, and repository meta files, then checks the
review-bearing portion against the thresholds in AGENTS.md §19.2.

The thresholds deliberately exclude test code: AGENTS.md §14 and §19.3 require
unit tests to ship in the same PR as their implementation, so counting those
lines against the split threshold would make the rules contradict each other.

Usage::

    python tools/pr_budget.py                      # auto-detect base ref
    python tools/pr_budget.py --base origin/develop
    python tools/pr_budget.py --format markdown    # block for the PR body
    python tools/pr_budget.py --no-fail            # report only, always exit 0

Exit codes: 0 = within budget, 1 = over budget, 2 = measurement failed.
Standard library only; runs on Python 3.10.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field

# --- Thresholds (AGENTS.md §19.2) -------------------------------------------

REVIEW_MAX_LINES = 1500
REVIEW_MAX_FILES = 30
TEST_ADVISORY_LINES = 3000

# §19.2: three or more mixed review-observation classes also forces a split.
OBSERVATION_MAX_CLASSES = 3

# §19.2 counts A-E only. F is excluded because §14 requires tests in every
# implementation PR, so counting F would make two implementation classes
# trip the condition almost always -- the same contradiction this section
# removes by not counting test lines.
OBSERVATION_LABEL_TEST = "F テスト"

# --- Path classification ----------------------------------------------------

CATEGORY_REVIEW = "REVIEW"
CATEGORY_TEST = "TEST"
CATEGORY_SPEC = "SPEC"
CATEGORY_META = "META"

CATEGORY_ORDER = (CATEGORY_REVIEW, CATEGORY_TEST, CATEGORY_SPEC, CATEGORY_META)

# Prefix -> category. The first matching prefix wins, so order matters.
_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("tests/", CATEGORY_TEST),
    (".kiro/specs/", CATEGORY_SPEC),
    ("docs/", CATEGORY_SPEC),
    (".kiro/", CATEGORY_META),
    (".agents/", CATEGORY_META),
    (".github/", CATEGORY_META),
    (".claude/", CATEGORY_META),
    (".codex/", CATEGORY_META),
    (".cursor/", CATEGORY_META),
    (".gemini/", CATEGORY_META),
    ("tools/", CATEGORY_META),
    ("prompt_detailer_router/", CATEGORY_REVIEW),
    ("web/", CATEGORY_REVIEW),
)

_META_FILES = frozenset(
    {
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "README.md",
        ".gitignore",
    }
)

# Review-observation hints (AGENTS.md §22.1). Best effort only -- the author
# confirms the real classification in the PR body.
_OBSERVATION_RULES: tuple[tuple[str, str], ...] = (
    ("prompt_detailer_router/infrastructure/", "A 外部入力検証"),
    ("prompt_detailer_router/domain/forbidden_terms.py", "B 文字列後処理"),
    ("prompt_detailer_router/domain/prompt_text.py", "B 文字列後処理"),
    ("prompt_detailer_router/domain/", "C ドメイン不変条件"),
    ("prompt_detailer_router/resources/presets/", "D preset越境"),
    ("prompt_detailer_router/resources/", "E リソース"),
    ("tests/", "F テスト"),
)


def classify(path: str) -> str:
    """Return the budget category for a repository-relative path."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in _META_FILES:
        return CATEGORY_META
    # tasks.md carries checkbox and Implementation Notes updates that kiro-impl
    # writes on every task, so it is progress tracking rather than the basis
    # text §19.1 protects. Counting it as SPEC would raise the mixing advisory
    # on every implementation PR.
    if normalized.startswith(".kiro/specs/") and normalized.endswith("/tasks.md"):
        return CATEGORY_META
    for prefix, category in _PREFIX_RULES:
        if normalized.startswith(prefix):
            return category
    if normalized.endswith(".md"):
        return CATEGORY_META
    return CATEGORY_REVIEW


def observations(paths: list[str]) -> list[str]:
    """Return the estimated §22.1 observation classes touched by ``paths``."""
    found: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        for prefix, label in _OBSERVATION_RULES:
            if normalized.startswith(prefix) and label not in found:
                found.append(label)
                break
    return sorted(found)


# --- Measurement ------------------------------------------------------------


@dataclass
class Bucket:
    added: int = 0
    deleted: int = 0
    files: int = 0


@dataclass
class Report:
    base: str
    head: str
    buckets: dict[str, Bucket]
    paths: dict[str, list[str]] = field(default_factory=dict)

    @property
    def review(self) -> Bucket:
        return self.buckets[CATEGORY_REVIEW]

    @property
    def observation_classes(self) -> list[str]:
        """Estimated §22.1 classes that count toward the §19.2 threshold.

        ``F テスト`` is filtered out explicitly rather than relying on tests
        never landing in the REVIEW bucket, so the exclusion stays visible if
        the path classification changes.
        """
        found = observations(self.paths.get(CATEGORY_REVIEW, []))
        return [label for label in found if label != OBSERVATION_LABEL_TEST]

    @property
    def over_lines(self) -> bool:
        return self.review.added > REVIEW_MAX_LINES

    @property
    def over_files(self) -> bool:
        return self.review.files > REVIEW_MAX_FILES

    @property
    def over_observations(self) -> bool:
        return len(self.observation_classes) >= OBSERVATION_MAX_CLASSES

    @property
    def mixes_spec_and_code(self) -> bool:
        """True when spec documents and implementation share one PR (§19.1)."""
        return self.buckets[CATEGORY_SPEC].files > 0 and self.review.files > 0

    @property
    def verdict(self) -> str:
        if self.over_lines or self.over_files or self.over_observations:
            return "OVER_BUDGET"
        return "WITHIN_BUDGET"

    @property
    def reasons(self) -> list[str]:
        out = []
        if self.over_lines:
            out.append(f"REVIEW_LINES {self.review.added} > {REVIEW_MAX_LINES} (§19.2)")
        if self.over_files:
            out.append(f"REVIEW_FILES {self.review.files} > {REVIEW_MAX_FILES} (§19.2)")
        if self.over_observations:
            joined = ", ".join(self.observation_classes)
            out.append(
                f"OBSERVATIONS {len(self.observation_classes)} 分類 "
                f">= {OBSERVATION_MAX_CLASSES} (§19.2, 推定): {joined}"
            )
        return out

    @property
    def advisories(self) -> list[str]:
        out = []
        if self.buckets[CATEGORY_TEST].added > TEST_ADVISORY_LINES:
            out.append(
                f"TEST_LINES {self.buckets[CATEGORY_TEST].added} "
                f"> {TEST_ADVISORY_LINES} — テスト分割を検討"
            )
        if self.mixes_spec_and_code:
            out.append("仕様文書と実装が同一PRに混在 (§19.1)")
        return out


class MeasurementError(RuntimeError):
    """Raised when the diff cannot be measured."""


def _git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:  # git missing
        raise MeasurementError(f"git を実行できません: {exc}") from exc
    if result.returncode != 0:
        raise MeasurementError(
            f"git {' '.join(args)} が失敗しました: {result.stderr.strip()}"
        )
    return result.stdout


def parse_numstat(raw: str) -> list[tuple[int, int, str]]:
    """Parse ``git diff --numstat -z`` output.

    Records are ``added TAB deleted TAB path NUL``. Renames emit an empty path
    field followed by ``old NUL new NUL``; the new path is the one counted.
    Binary files report ``-`` for both counts and contribute zero lines.
    """
    fields = raw.split("\0")
    entries: list[tuple[int, int, str]] = []
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        parts = record.split("\t")
        if len(parts) < 3:
            raise MeasurementError(f"numstat を解釈できません: {record!r}")
        added_raw, deleted_raw, path = parts[0], parts[1], parts[2]
        if path == "":
            # Rename/copy: the next two fields are the old and new paths.
            if index + 1 >= len(fields) or not fields[index + 1]:
                raise MeasurementError("numstat の rename レコードが不完全です")
            path = fields[index + 1]
            index += 2
        added = 0 if added_raw == "-" else int(added_raw)
        deleted = 0 if deleted_raw == "-" else int(deleted_raw)
        entries.append((added, deleted, path))
    return entries


def build_report(entries: list[tuple[int, int, str]], base: str, head: str) -> Report:
    buckets = {name: Bucket() for name in CATEGORY_ORDER}
    paths: dict[str, list[str]] = {name: [] for name in CATEGORY_ORDER}
    for added, deleted, path in entries:
        category = classify(path)
        bucket = buckets[category]
        bucket.added += added
        bucket.deleted += deleted
        bucket.files += 1
        paths[category].append(path)
    return Report(base=base, head=head, buckets=buckets, paths=paths)


def ref_exists(ref: str) -> bool:
    """True when ``ref`` resolves in this clone."""
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def resolve_ref(name: str) -> str | None:
    """Resolve a branch name to a ref that exists locally.

    ``gh pr view`` reports a plain branch name (``main``), which does not
    resolve in a clone that only has remote-tracking refs. Prefer the
    remote-tracking form, since that is what a fresh clone or a CI checkout
    actually has.
    """
    for candidate in (f"origin/{name}", name):
        if ref_exists(candidate):
            return candidate
    return None


def base_from_gh() -> str | None:
    """Return the open PR's base branch name, or None when unavailable."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "baseRefName"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:  # gh not installed
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout).get("baseRefName") or None
    except ValueError:
        return None


def resolve_base(explicit: str | None) -> str:
    """Resolve the base ref: explicit flag, then the open PR, then fallbacks.

    Every candidate is verified before being returned, so the caller never
    reaches ``git diff`` with an unresolvable revision.
    """
    if explicit:
        resolved = resolve_ref(explicit)
        if resolved is None:
            raise MeasurementError(
                f"base ref '{explicit}' を解決できません。"
                f"`git fetch origin {explicit}` を実行するか、"
                "解決可能な ref を --base で指定してください。"
            )
        return resolved

    name = base_from_gh()
    if name:
        resolved = resolve_ref(name)
        if resolved is not None:
            return resolved

    for candidate in ("origin/develop", "develop", "origin/main", "main"):
        if ref_exists(candidate):
            return candidate

    raise MeasurementError("base ref を特定できません。--base で明示してください。")


def measure(base: str, head: str) -> Report:
    # Same-kind guard as resolve_base: never hand git an unresolvable revision.
    if not ref_exists(head):
        raise MeasurementError(f"head ref '{head}' を解決できません。")
    raw = _git(["diff", "--numstat", "-z", "-M", f"{base}...{head}"])
    return build_report(parse_numstat(raw), base, head)


# --- Rendering --------------------------------------------------------------


def render_text(report: Report) -> str:
    review = report.review
    lines = [
        f"PR Budget  base={report.base}  head={report.head}",
        "",
        f"{'区分':<10}{'追加':>8}{'削除':>8}{'ファイル':>10}",
        "-" * 38,
    ]
    labels = {
        CATEGORY_REVIEW: "REVIEW",
        CATEGORY_TEST: "TEST",
        CATEGORY_SPEC: "SPEC",
        CATEGORY_META: "META",
    }
    for name in CATEGORY_ORDER:
        bucket = report.buckets[name]
        lines.append(
            f"{labels[name]:<10}{bucket.added:>8}{bucket.deleted:>8}{bucket.files:>10}"
        )
    lines += [
        "-" * 38,
        f"REVIEW_LINES: {review.added} / {REVIEW_MAX_LINES}",
        f"REVIEW_FILES: {review.files} / {REVIEW_MAX_FILES}",
        f"OBSERVATIONS: {', '.join(report.observation_classes) or '-'}"
        f"  ({len(report.observation_classes)} / {OBSERVATION_MAX_CLASSES} 分類, 推定)",
        f"VERDICT: {report.verdict}",
    ]
    for reason in report.reasons:
        lines.append(f"  ! {reason}")
    for advisory in report.advisories:
        lines.append(f"  - {advisory}")
    return "\n".join(lines)


def render_markdown(report: Report) -> str:
    review = report.review
    observed = ", ".join(report.observation_classes) or "-"
    lines = [
        "## PR Budget (AGENTS.md §19.2 / §19.4)",
        "",
        "```text",
        f"BASE: {report.base}",
        f"REVIEW_LINES: {review.added} / {REVIEW_MAX_LINES}",
        f"REVIEW_FILES: {review.files} / {REVIEW_MAX_FILES}",
        f"TEST_LINES: {report.buckets[CATEGORY_TEST].added}",
        f"SPEC_LINES: {report.buckets[CATEGORY_SPEC].added}",
        f"META_LINES: {report.buckets[CATEGORY_META].added}",
        f"OBSERVATIONS: {observed}  (推定 — 実分類を確認して修正すること)",
        f"VERDICT: {report.verdict}",
        f"OVER_BUDGET_REASON: {'; '.join(report.reasons) or 'N/A'}",
        "```",
    ]
    if report.advisories:
        lines.append("")
        for advisory in report.advisories:
            lines.append(f"- 注意: {advisory}")
    return "\n".join(lines)


def render_json(report: Report) -> str:
    payload = {
        "base": report.base,
        "head": report.head,
        "verdict": report.verdict,
        "thresholds": {
            "review_max_lines": REVIEW_MAX_LINES,
            "review_max_files": REVIEW_MAX_FILES,
            "test_advisory_lines": TEST_ADVISORY_LINES,
            "observation_max_classes": OBSERVATION_MAX_CLASSES,
        },
        # The declaration in the PR body overrides these estimated classes;
        # over_lines / over_files are objective and cannot be overridden.
        "over_lines": report.over_lines,
        "over_files": report.over_files,
        "over_observations": report.over_observations,
        "buckets": {
            name: {
                "added": report.buckets[name].added,
                "deleted": report.buckets[name].deleted,
                "files": report.buckets[name].files,
            }
            for name in CATEGORY_ORDER
        },
        "observations": report.observation_classes,
        "reasons": report.reasons,
        "advisories": report.advisories,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def configure_stream(stream: object) -> None:
    """Make ``stream`` safe for this tool's Japanese output.

    On Windows, a redirected stdout encodes with the locale code page, which
    corrupts ``--format json`` output for downstream readers. Force UTF-8 when
    the output is redirected, and keep the console encoding (tolerating
    unencodable characters) when it is a terminal.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    is_tty = bool(getattr(stream, "isatty", lambda: False)())
    if is_tty:
        reconfigure(errors="replace")
    else:
        reconfigure(encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PR の差分規模を AGENTS.md §19.2 の閾値に照らして計測する。"
    )
    parser.add_argument("--base", help="比較元 ref (省略時は自動判定)")
    parser.add_argument("--head", default="HEAD", help="比較先 ref (既定: HEAD)")
    parser.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="出力形式 (markdown は PR 本文へ貼る申告ブロック)",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="超過していても終了コード 0 を返す",
    )
    args = parser.parse_args(argv)
    configure_stream(sys.stdout)

    try:
        base = resolve_base(args.base)
        report = measure(base, args.head)
    except MeasurementError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    renderers = {
        "text": render_text,
        "markdown": render_markdown,
        "json": render_json,
    }
    print(renderers[args.format](report))

    if args.no_fail:
        return 0
    return 1 if report.verdict == "OVER_BUDGET" else 0


if __name__ == "__main__":
    raise SystemExit(main())
