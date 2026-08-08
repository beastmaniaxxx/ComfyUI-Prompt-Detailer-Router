"""Default detailer ``order`` per scope.

Pure domain constants (Requirement 10.7). Used by the Plan Builder when a
detailer preset does not specify ``default_order``, and by safe fallback tasks.
Lower ``order`` runs earlier in the intended detailer sequence.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

DEFAULT_ORDER: Mapping[str, int] = MappingProxyType(
    {
        "hair": 20,
        "face": 30,
        "hands": 40,
        "upper_body": 50,
        "body": 60,
        "clothing": 70,
        "generic": 90,
    }
)


def default_order_for(scope: str) -> int:
    """Return the default order for ``scope``.

    Raises ``KeyError`` for scopes without a defined default order.
    """

    return DEFAULT_ORDER[scope]
