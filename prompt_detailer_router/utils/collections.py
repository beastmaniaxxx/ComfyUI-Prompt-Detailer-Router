"""Small pure collection helpers (no external dependencies)."""

from __future__ import annotations

from typing import Iterable, TypeVar

T = TypeVar("T")


def ordered_unique(items: Iterable[T]) -> tuple[T, ...]:
    """Return items with duplicates removed, preserving first-occurrence order."""

    seen: set[T] = set()
    result: list[T] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)
