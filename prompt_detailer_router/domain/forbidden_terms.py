"""Forbidden-term removal (deterministic, LLM-independent).

Pure domain logic (Requirements 9.2, 9.3, 9.5, 9.6, 9.7). Applies a shared,
versioned forbidden-terms policy to a finalized string. Matching is
``case_insensitive_literal`` with alphanumeric look-around boundaries, so a
banned word is removed as a whole word without mutilating longer words
("perfect" is not stripped from "imperfect") while ``_`` still counts as a
separator ("perfect_face" -> "face").

When at least one term is removed, the leftover separators are cleaned up by the
separator normalization of Req 9.6, applied **uniformly to the whole string**
(Req 9.7): empty bracket pairs go, each run of separators collapses to its
strongest separator, and separators against the string ends or a bracket edge
are dropped. A string with no removal is never touched beyond whitespace
normalization.
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

# Strip underscores left dangling at a token boundary after a term is removed
# (e.g. "_face" -> "face", "very__face" -> "very_face"), without touching
# intra-token underscores such as "upper_body".
_ORPHAN_UNDERSCORE_LEFT = re.compile(r"(?<![A-Za-z0-9])_+")
_ORPHAN_UNDERSCORE_RIGHT = re.compile(r"_+(?![A-Za-z0-9])")

# Separator normalization (Req 9.6). Every pattern uses a single, non-nested
# quantifier so each pass is linear in the input length with no backtracking.
_SEPARATOR_STRENGTH = {".": 3, ";": 2, ",": 1}
_SEPARATOR_RUN = re.compile(r"[\s,;.]+")
_SEPARATOR_AT_OPENING = re.compile(r"(^|[(\[{])[\s,;.]+")
_SEPARATOR_BEFORE_CLOSING = re.compile(r"[\s,;.]+([)\]}])")
# A trailing "." terminates the last sentence and is kept; a trailing "," or ";"
# lost its operand with the removed term and goes.
_SEPARATOR_AT_END = re.compile(r"[\s,;]+$")

# Characters that do not, on their own, make a bracket pair "non-empty": a pair
# enclosing only whitespace, these separators, and nested empty pairs carries no
# content. Whitespace is tested with ``str.isspace()`` rather than an ASCII list
# so this pass and the ``\s`` of the separator patterns above share one
# definition — otherwise a NBSP or an ideographic space inside a bracket would
# make the pair look substantial here and be erased by ``\s`` a pass later,
# stranding the now-empty pair in the output.
_INSUBSTANTIAL_SEPARATORS = frozenset(",;.")
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
    """Drop bracket pairs that hold no content (Req 9.6.1).

    One linear left-to-right pass with a stack. A matched pair is stripped when
    its interior holds only whitespace, separators, or nested pairs that were
    themselves stripped — so arbitrary nesting collapses in this single pass and
    the caller never re-scans per nesting level.

    A stripped pair leaves a space only when both of its neighbours are
    alphanumeric, so "face(X)eyes" cannot fuse into one word once the term inside
    is gone. When either neighbour is punctuation the pair leaves nothing, so a
    hyphen or a separator the author wrote keeps its own spacing
    ("face(X)-detail" -> "face-detail", not "face -detail").
    """

    if not any(ch in text for ch in "([{"):
        return text
    out: list[str] = []
    # Each stack frame: [index of the opener in ``out``, has_substance].
    stack: list[list] = []
    for index, ch in enumerate(text):
        if ch in _OPEN_TO_CLOSE:
            stack.append([len(out), False])
            out.append(ch)
        elif ch in _CLOSE_TO_OPEN:
            if stack and out[stack[-1][0]] == _CLOSE_TO_OPEN[ch]:
                open_index, has_substance = stack.pop()
                if has_substance:
                    out.append(ch)
                    if stack:
                        stack[-1][1] = True
                else:
                    del out[open_index:]
                    before = out[-1] if out else ""
                    after = text[index + 1] if index + 1 < len(text) else ""
                    if before.isalnum() and after.isalnum():
                        out.append(" ")
            else:
                # Unbalanced/mismatched closer: real content.
                if stack:
                    stack[-1][1] = True
                out.append(ch)
        else:
            if not (ch.isspace() or ch in _INSUBSTANTIAL_SEPARATORS) and stack:
                stack[-1][1] = True
            out.append(ch)
    return "".join(out)


def _collapse_separator_run(match: "re.Match[str]") -> str:
    """Collapse one separator run to its strongest separator (Req 9.6.2).

    A run of whitespace and separators becomes the strongest separator it holds
    plus one space (". " > "; " > ", "), so "a,, b" -> "a, b" and "a, . b" ->
    "a. b". A run with no separator at all becomes a single space.
    """

    run = match.group(0)
    strongest = ""
    strength = 0
    for ch in run:
        rank = _SEPARATOR_STRENGTH.get(ch, 0)
        if rank > strength:
            strongest = ch
            strength = rank
    return strongest + " " if strongest else " "


def _normalize_separators(text: str) -> str:
    """Apply the Req 9.6 separator normalization to the whole string.

    Four linear passes, in order: drop empty bracket pairs, collapse each
    separator run to its strongest separator, then drop separators sitting
    against the string start, a bracket edge, or the string end. Collapsing
    before the edge passes keeps every remaining run at most two characters
    long, so the edge patterns cannot backtrack over a long run.

    The end-of-string pass keeps a trailing ".", which terminates the last
    sentence of a composed prompt, and drops a trailing "," or ";", which lost
    its operand along with the removed term.
    """

    text = _strip_empty_bracket_pairs(text)
    text = _SEPARATOR_RUN.sub(_collapse_separator_run, text)
    text = _SEPARATOR_AT_OPENING.sub(r"\1", text)
    text = _SEPARATOR_BEFORE_CLOSING.sub(r"\1", text)
    text = _SEPARATOR_AT_END.sub("", text)
    return text


def apply_forbidden_terms(
    text: str, terms: Sequence[str], match: str = CASE_INSENSITIVE_LITERAL
) -> ForbiddenScanResult:
    """Remove forbidden ``terms`` from ``text`` per the ``match`` mode.

    v1 supports the ``case_insensitive_literal`` mode only; other modes raise
    ``ValueError`` rather than silently mismatching.
    """

    if match != CASE_INSENSITIVE_LITERAL:
        raise ValueError(f"Unsupported forbidden-term match mode: {match!r}")

    working = text
    removed_terms: list[str] = []
    total = 0
    for term in terms:
        if not term:
            continue
        pattern = re.compile(
            rf"{_ALNUM_LEFT}{re.escape(term)}{_ALNUM_RIGHT}", re.IGNORECASE
        )
        working, count = pattern.subn("", working)
        if count:
            removed_terms.append(term)
            total += count

    # Separator normalization runs only when something was actually removed
    # (Req 9.6): a string with no forbidden term keeps its punctuation verbatim.
    # Orphaned underscores go first: an underscore left behind by the removal is
    # itself part of the wreckage, and leaving it in place would hide the
    # separator or bracket outside it from the normalization that follows
    # ("(beautiful_), face" must reach "face", not "(), face").
    if total:
        working = _ORPHAN_UNDERSCORE_LEFT.sub("", working)
        working = _ORPHAN_UNDERSCORE_RIGHT.sub("", working)
        working = _normalize_separators(working)
    cleaned = normalize_whitespace(working)
    return ForbiddenScanResult(
        text=cleaned,
        removed_count=total,
        removed_terms=tuple(removed_terms),
    )
