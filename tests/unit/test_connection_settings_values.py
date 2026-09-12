"""Unit tests for numeric settings and ``keep_alive``.

Requirements 10.6-10.9, 10.12, 10.17-10.19, 10.22: no clamping to a boundary and
no substitution of a default, truncation (not rounding) of ``timeout`` to three
decimals, and a wire type for ``keep_alive`` that depends on whether a unit was
given.
"""

import math

import pytest

from prompt_detailer_router.domain.connection_settings import (
    effective_timeout,
    parse_keep_alive,
    validate_model_name,
    validate_temperature,
)
from prompt_detailer_router.domain.errors import ConfigurationError


# --- timeout: range (Requirements 10.7, 10.8) ---

@pytest.mark.parametrize("value", [0.1, 0.5, 1, 120.0, 599.999, 600, 600.0])
def test_timeout_inside_the_range_is_accepted(value: float) -> None:
    assert 0.1 <= effective_timeout(value) <= 600


@pytest.mark.parametrize(
    "value", [0.0999, 0.09, 0.0, -0.1, -1, 600.001, 601, 10_000]
)
def test_timeout_outside_the_range_is_a_configuration_error(value: float) -> None:
    with pytest.raises(ConfigurationError):
        effective_timeout(value)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf")]
)
def test_non_finite_timeout_is_rejected(value: float) -> None:
    with pytest.raises(ConfigurationError):
        effective_timeout(value)


@pytest.mark.parametrize("value", ["120", None, [], {}, True])
def test_non_numeric_timeout_is_rejected(value: object) -> None:
    with pytest.raises(ConfigurationError):
        effective_timeout(value)  # type: ignore[arg-type]


def test_out_of_range_timeout_is_not_clamped() -> None:
    # 700 must not silently become 600 (Requirement 10.8).
    with pytest.raises(ConfigurationError):
        effective_timeout(700.0)


# --- timeout: truncation to three decimals (Requirement 10.12) ---

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.1, 0.1),
        (120.0, 120.0),
        (0.1004, 0.1),
        (0.1005, 0.1),
        (0.1009, 0.1),
        (1.2345, 1.234),
        (1.9999, 1.999),
        (599.9999, 599.999),
        (12.5, 12.5),
    ],
)
def test_timeout_is_truncated_never_rounded_up(value: float, expected: float) -> None:
    assert effective_timeout(value) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("value", [0.1, 0.1009, 1.2345, 599.9999, 600.0])
def test_effective_timeout_never_exceeds_the_requested_value(value: float) -> None:
    assert effective_timeout(value) <= value


@pytest.mark.parametrize("value", [0.1, 0.1004, 1.2345, 600.0])
def test_effective_timeout_stays_inside_the_valid_range(value: float) -> None:
    result = effective_timeout(value)
    assert 0.1 <= result <= 600
    assert math.isfinite(result)


def test_effective_timeout_is_idempotent() -> None:
    once = effective_timeout(1.2345)
    assert effective_timeout(once) == once


# --- temperature (Requirement 10.9) ---

@pytest.mark.parametrize("value", [0, 0.0, 0.2, 1, 2.5])
def test_non_negative_finite_temperature_is_accepted(value: float) -> None:
    assert validate_temperature(value) == float(value)


@pytest.mark.parametrize("value", [-0.0001, -1, -100.0])
def test_negative_temperature_is_rejected(value: float) -> None:
    with pytest.raises(ConfigurationError):
        validate_temperature(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_temperature_is_rejected(value: float) -> None:
    with pytest.raises(ConfigurationError):
        validate_temperature(value)


@pytest.mark.parametrize("value", ["0.2", None, [], True])
def test_non_numeric_temperature_is_rejected(value: object) -> None:
    with pytest.raises(ConfigurationError):
        validate_temperature(value)  # type: ignore[arg-type]


# --- model name (Requirement 10.6) ---

@pytest.mark.parametrize("name", ["llama3", "qwen2.5:7b", "my-model:latest"])
def test_model_name_is_accepted(name: str) -> None:
    assert validate_model_name(name) == name


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n", "  \t\n "])
def test_blank_model_name_is_rejected_without_an_implicit_default(blank: str) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        validate_model_name(blank)
    # Raising (rather than returning a substituted name) is the contract; the
    # message says so explicitly.
    assert "no implicit default" in str(excinfo.value).lower()


@pytest.mark.parametrize("value", [None, 1, [], {}])
def test_non_string_model_name_is_rejected(value: object) -> None:
    with pytest.raises(ConfigurationError):
        validate_model_name(value)  # type: ignore[arg-type]


# --- keep_alive: accepted forms and wire type (Requirements 10.17, 10.22) ---

@pytest.mark.parametrize(
    ("raw", "wire"),
    [("0", 0), ("-1", -1), ("300", 300), ("5", 5)],
)
def test_unitless_keep_alive_is_sent_as_a_json_number(raw: str, wire: int) -> None:
    parsed = parse_keep_alive(raw)
    assert parsed.wire_value == wire
    assert isinstance(parsed.wire_value, int)
    assert not isinstance(parsed.wire_value, str)


@pytest.mark.parametrize("raw", ["1.5", "0.25", "-1.5"])
def test_unitless_decimal_keep_alive_is_sent_as_a_json_number(raw: str) -> None:
    parsed = parse_keep_alive(raw)
    assert parsed.wire_value == float(raw)
    assert isinstance(parsed.wire_value, float)


@pytest.mark.parametrize(
    "raw", ["1ns", "1us", "1ms", "30s", "5m", "1h", "-1m", "0.5h", "300s"]
)
def test_keep_alive_with_a_single_unit_is_sent_as_a_json_string(raw: str) -> None:
    parsed = parse_keep_alive(raw)
    assert parsed.wire_value == raw
    assert isinstance(parsed.wire_value, str)


@pytest.mark.parametrize("unit", ["ns", "us", "ms", "s", "m", "h"])
def test_all_six_units_are_accepted(unit: str) -> None:
    assert parse_keep_alive(f"10{unit}").wire_value == f"10{unit}"


def test_raw_value_is_preserved() -> None:
    assert parse_keep_alive("5m").raw == "5m"


# --- keep_alive: rejected forms (Requirements 10.18, 10.19) ---

@pytest.mark.parametrize(
    "raw",
    [
        "1h30m",  # compound units are out of scope for v1
        "2m30s",
        "",
        " ",
        " 5m",
        "5m ",
        "+5m",
        "5S",
        "5M",
        "abc",
        "m",
        "s5",
        "5x",
        "1.2.3",
        "5,5m",
        "--1",
        "1e3",
        "0x10",
        "5m5",
        # `$` matches before a trailing newline, so these slipped through and
        # the newline reached the wire value (Requirements 10.17, 10.18).
        "5m\n",
        "5m\r",
        "5m\r\n",
        "300\n",
        "-1\n",
        "\n5m",
    ],
)
def test_unsupported_keep_alive_forms_are_configuration_errors(raw: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_keep_alive(raw)


@pytest.mark.parametrize("value", [None, 5, 5.0, [], {}])
def test_non_string_keep_alive_is_rejected(value: object) -> None:
    with pytest.raises(ConfigurationError):
        parse_keep_alive(value)  # type: ignore[arg-type]


def test_keep_alive_is_immutable() -> None:
    parsed = parse_keep_alive("5m")
    with pytest.raises(Exception):
        parsed.raw = "1h"  # type: ignore[misc]
