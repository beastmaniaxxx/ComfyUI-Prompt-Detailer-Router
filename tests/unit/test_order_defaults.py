"""Unit tests for scope default order (domain/order_defaults).

Covers Requirement 10.7: deterministic default order per scope.
"""

import pytest

from prompt_detailer_router.domain import order_defaults

EXPECTED = {
    "hair": 20,
    "face": 30,
    "hands": 40,
    "upper_body": 50,
    "body": 60,
    "clothing": 70,
    "generic": 90,
}


@pytest.mark.parametrize("scope,order", EXPECTED.items())
def test_default_order_matches_table(scope: str, order: int) -> None:
    assert order_defaults.default_order_for(scope) == order


def test_default_order_table_covers_all_seven_scopes() -> None:
    assert set(order_defaults.DEFAULT_ORDER) == set(EXPECTED)


def test_unknown_scope_raises_key_error() -> None:
    with pytest.raises(KeyError):
        order_defaults.default_order_for("nose")
