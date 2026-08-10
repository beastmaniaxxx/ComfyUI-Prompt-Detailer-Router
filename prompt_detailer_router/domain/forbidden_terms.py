"""Forbidden-term removal (deterministic, LLM-independent).

Pure domain logic (Requirements 9.2, 9.3, 9.5). Applies a shared, versioned
forbidden-terms policy to a finalized string. Matching is
``case_insensitive_literal`` with word boundaries so a banned word is removed as
a whole word without mutilating longer words (e.g. "perfect" is not stripped
from "imperfect"). Separator/bracket repair after removal is confined to the
exact spots a term was removed, so punctuation that was already in the input is
preserved — both away from any removal (the ellipsis in "cinematic... portrait")
and directly against one ("face... beautiful eyes" -> "face... eyes").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from prompt_detailer_router.domain.prompt_text import normalize_whitespace

CASE_INSENSITIVE_LITERAL = "case_insensitive_literal"

# Underscores are common word separators in generation prompts, so a forbidden
# term must be matched when delimited by ``_`` (e.g. "perfect_face"). Using
# alphanumeric look-arounds treats ``_`` as a boundary while still refusing
# matches inside longer words like "imperfect".
_ALNUM_LEFT = r"(?<![A-Za-z0-9])"
_ALNUM_RIGHT = r"(?![A-Za-z0-9])"

# A private sentinel marks each spot where a term was removed, so separator and
# bracket repair (Req 9.3) can be confined to the immediate neighbourhood of a
# removal. It is a control character that never appears in a normal prompt (any
# stray occurrence in the input is stripped up front).
_SENTINEL = "\x00"
_S = re.escape(_SENTINEL)

# Strip underscores left dangling at a token boundary after a term is removed
# (e.g. "_face" -> "face", "very__face" -> "very_face"), without touching
# intra-token underscores such as "upper_body".
_ORPHAN_UNDERSCORE_LEFT = re.compile(r"(?<![A-Za-z0-9])_+")
_ORPHAN_UNDERSCORE_RIGHT = re.compile(r"_+(?![A-Za-z0-9])")

# A maximal run of whitespace/separators/sentinels. A run that contains at least
# one sentinel marks a removal neighbourhood and is collapsed in ONE match by
# ``_collapse_removal_run``; a run without a sentinel is unrelated punctuation
# (e.g. an ellipsis) and is left untouched. This single, non-nested quantifier
# scans each character once — no per-separator passes, no catastrophic
# backtracking — so an arbitrarily long separator run adjacent to a removal is
# repaired in a single linear pass regardless of its length.
_REMOVAL_RUN = re.compile(rf"[\s,;.{_S}]+")
_SEPARATORS = ",;."

# Two or more consecutive dots are an ellipsis: authored content, never a
# delimiter this module invented. When one sits on a side of a removal run it is
# kept verbatim instead of being collapsed into a single separator, so
# "face... beautiful eyes" -> "face... eyes" rather than "face. eyes".
_ELLIPSIS = re.compile(r"\.{2,}")
_OPENERS_STR = "([{"
_CLOSERS_STR = ")]}"

# Characters that do not, on their own, make a bracket pair "non-empty": a pair
# enclosing only these (and nested empty pairs) is an artifact of a removal.
_INSUBSTANTIAL = frozenset(" \t\r\n\f\v,;.") | {_SENTINEL}
_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_TO_OPEN = {close: opener for opener, close in _OPEN_TO_CLOSE.items()}


@dataclass(frozen=True, slots=True)
class ForbiddenScanResult:
    """Result of removing forbidden terms from a text.

    ``text`` is the cleaned, whitespace-normalized output. ``removed_count`` is
    the total number of occurrences removed. ``removed_terms`` lists the distinct
    policy terms that matched, in policy order.
    """

    text: str
    removed_count: int
    removed_terms: tuple[str, ...]


def _strip_empty_bracket_pairs(text: str) -> str:
    """Drop bracket pairs that wrapped a removal and now enclose only artifacts.

    A single linear left-to-right pass with a stack. A matched bracket pair is
    stripped (replaced by one sentinel) only when its interior holds no real
    content AND it contained at least one sentinel — i.e. it actually wrapped a
    removed term. A genuinely empty pair the user wrote (``()`` with no removal
    inside) is left untouched, keeping the repair confined to removal sites.
    Arbitrary nesting (e.g. "((( sentinel )))") collapses in this one pass, so
    the caller never re-scans per nesting level — avoiding quadratic blow-up.
    """

    if not any(ch in text for ch in "([{"):
        return text
    out: list[str] = []
    # Each stack frame: [open index in ``out``, has_substance, has_sentinel].
    stack: list[list] = []
    for ch in text:
        if ch in _OPEN_TO_CLOSE:
            stack.append([len(out), False, False])
            out.append(ch)
        elif ch in _CLOSE_TO_OPEN:
            if stack and out[stack[-1][0]] == _CLOSE_TO_OPEN[ch]:
                open_index, has_substance, has_sentinel = stack.pop()
                if not has_substance and has_sentinel:
                    del out[open_index:]
                    out.append(_SENTINEL)
                    if stack:
                        stack[-1][2] = True
                else:
                    # Real content, or a genuinely empty user-written pair: keep
                    # it, and treat it as substance for the enclosing pair.
                    out.append(ch)
                    if stack:
                        stack[-1][1] = True
            else:
                # Unbalanced/mismatched closer: real content.
                if stack:
                    stack[-1][1] = True
                out.append(ch)
        elif ch == _SENTINEL:
            if stack:
                stack[-1][2] = True
            out.append(ch)
        else:
            if ch not in _INSUBSTANTIAL and stack:
                stack[-1][1] = True
            out.append(ch)
    return "".join(out)


def _collapse_removal_run(match: "re.Match[str]") -> str:
    """Collapse one whitespace/separator/sentinel run that spans a removal.

    Runs without a sentinel are unrelated punctuation and returned unchanged. A
    run that held a removal is replaced by:
      * nothing, if it sat against a boundary — the string start/end or the
        inside edge of a bracket — i.e. the removed term was the leading/trailing
        element, so the single delimiter group in play lost its operand;
      * otherwise one delimiter survives to join the two neighbours that the
        removed term stood between. When exactly one side of the run holds an
        ellipsis, that side is authored punctuation belonging to its neighbour
        and is kept verbatim ("face... X eyes" -> "face... eyes",
        "face, X... hair" -> "face... hair"); when both sides hold one, the left
        side wins;
      * failing that, one separator from a side that has one — the left side
        first — plus a space ("a,, X ,, b" -> "a, b"), or a single space when
        neither side had a separator ("a X b" -> "a b"), or nothing when the run
        had no whitespace either (an underscore-joined removal such as
        "very_X_face", left for the orphan-underscore step to rejoin).
    """

    run = match.group(0)
    if _SENTINEL not in run:
        return run
    text = match.string
    start, end = match.start(), match.end()
    at_left_boundary = start == 0 or text[start - 1] in _OPENERS_STR
    at_right_boundary = end == len(text) or text[end] in _CLOSERS_STR
    if at_left_boundary or at_right_boundary:
        return ""
    # Only the sides of the run touch surviving text; anything between the first
    # and last sentinel separated removed terms from each other and is dropped.
    left = run[: run.index(_SENTINEL)]
    right = run[run.rindex(_SENTINEL) + 1 :]
    if _ELLIPSIS.search(left):
        return left
    if _ELLIPSIS.search(right):
        return right
    separators = [ch for ch in left if ch in _SEPARATORS] or [
        ch for ch in right if ch in _SEPARATORS
    ]
    if separators:
        return separators[0] + " "
    if any(ch.isspace() for ch in run):
        return " "
    return ""


def _repair_removal_sites(working: str) -> str:
    """Clean up separators/brackets left exactly where terms were removed.

    Two linear passes, so cost is bounded regardless of separator-run length or
    bracket nesting depth (no unbounded fixpoint, no per-separator iteration):

    1. Strip bracket pairs that wrapped a removal (``_strip_empty_bracket_pairs``),
       collapsing any nesting depth in one stack pass.
    2. Collapse each whitespace/separator/sentinel run that spans a removal
       (``_collapse_removal_run``) in one regex pass; unrelated punctuation
       (runs with no sentinel) is preserved.

    Finally, underscores orphaned by the removal are tidied. Repair stays
    confined to removal sites, so punctuation elsewhere is untouched.
    """

    working = _strip_empty_bracket_pairs(working)
    working = _REMOVAL_RUN.sub(_collapse_removal_run, working)
    # Every sentinel lives inside a collapsed run above, so none remain; this is
    # a defensive no-op for any not adjacent to a run.
    working = working.replace(_SENTINEL, "")
    working = _ORPHAN_UNDERSCORE_LEFT.sub("", working)
    working = _ORPHAN_UNDERSCORE_RIGHT.sub("", working)
    return working


def apply_forbidden_terms(
    text: str, terms: Sequence[str], match: str = CASE_INSENSITIVE_LITERAL
) -> ForbiddenScanResult:
    """Remove forbidden ``terms`` from ``text`` per the ``match`` mode.

    v1 supports the ``case_insensitive_literal`` mode only; other modes raise
    ``ValueError`` rather than silently mismatching.
    """

    if match != CASE_INSENSITIVE_LITERAL:
        raise ValueError(f"Unsupported forbidden-term match mode: {match!r}")

    # The sentinel is an internal marker; never let one from the input survive.
    working = text.replace(_SENTINEL, "")
    removed_terms: list[str] = []
    total = 0
    for term in terms:
        if not term:
            continue
        pattern = re.compile(
            rf"{_ALNUM_LEFT}{re.escape(term)}{_ALNUM_RIGHT}", re.IGNORECASE
        )
        working, count = pattern.subn(_SENTINEL, working)
        if count:
            removed_terms.append(term)
            total += count

    # Repair only where a term was actually removed; unrelated input (including
    # legitimate ellipses or empty brackets) is preserved verbatim.
    if total:
        working = _repair_removal_sites(working)
    cleaned = normalize_whitespace(working)
    return ForbiddenScanResult(
        text=cleaned,
        removed_count=total,
        removed_terms=tuple(removed_terms),
    )
