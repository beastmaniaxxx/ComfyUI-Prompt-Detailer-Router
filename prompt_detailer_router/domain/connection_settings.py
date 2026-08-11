"""Connection-setting validation: URL, timeout, temperature, keep_alive.

Pure domain logic (Requirements 10.1-10.9, 10.12, 10.17-10.20, 11.4). Anything
decidable locally is decided here, *before* any socket is opened, so a typo in
the URL surfaces as a configuration error -- classification (h) -- instead of a
connection failure that looks like "Ollama is down" (Requirement 10.20).

No clamping, no rounding to a boundary, no substituting a default: an
out-of-range value is an error, and the only transformation applied is the
truncation of ``timeout`` to three decimals (Requirement 10.12).

Host and keep_alive matching use ``ipaddress`` plus single-quantifier regexes
applied per label, so no nested quantifier can backtrack catastrophically
(AGENTS.md 22.3).
"""

from __future__ import annotations

import ipaddress
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from urllib.parse import urlsplit

from prompt_detailer_router.domain.errors import ConfigurationError

_ALLOWED_SCHEMES = ("http", "https")
_DEFAULT_PORTS = {"http": 80, "https": 443}

# Single quantifier, applied to one label at a time: the label list is split in
# Python rather than expressed as a nested group.
_DNS_LABEL = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
_DIGITS_AND_DOTS = re.compile(r"^[0-9.]+$")
_PORT = re.compile(r"^[0-9]{1,5}$")
_KEEP_ALIVE = re.compile(r"^-?[0-9]+(\.[0-9]+)?(ns|us|ms|s|m|h)?$")

_MAX_DNS_NAME_LENGTH = 253
_MIN_TIMEOUT = 0.1
_MAX_TIMEOUT = 600.0
_TIMEOUT_QUANTUM = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class OllamaEndpoint:
    """A validated Ollama origin.

    ``host`` holds an IPv6 address in canonical form without brackets, and a
    DNS name exactly as the user typed it. Bracketing is applied where the
    authority is assembled, so both ``chat_url`` and ``cache_identity`` follow
    the same rule.
    """

    scheme: str
    host: str
    port: int
    is_ipv6: bool

    def _authority(self, host: str) -> str:
        return f"[{host}]:{self.port}" if self.is_ipv6 else f"{host}:{self.port}"

    @property
    def chat_url(self) -> str:
        """The request target: the origin plus exactly ``/api/chat``."""

        return f"{self.scheme}://{self._authority(self.host)}/api/chat"

    @property
    def cache_identity(self) -> str:
        """Normalized destination identity for the cache key (Requirement 11.4)."""

        return f"{self.scheme}://{self._authority(self.host.lower())}"


@dataclass(frozen=True, slots=True)
class KeepAlive:
    """A validated ``keep_alive`` and the wire form it is sent as.

    Ollama reads a JSON number as seconds and parses a JSON string as a
    duration, so a unitless value must not be sent quoted (Requirement 10.22).
    """

    raw: str
    wire_value: float | int | str


def _fail(message: str) -> ConfigurationError:
    return ConfigurationError(message)


def _validate_ipv6_literal(literal: str) -> str:
    try:
        return str(ipaddress.IPv6Address(literal))
    except ValueError as exc:
        raise _fail(
            f"ollama_url host '[{literal}]' is not a valid IPv6 address."
        ) from exc


def _validate_ipv4(host: str) -> str:
    try:
        ipaddress.IPv4Address(host)
    except ValueError as exc:
        raise _fail(
            f"ollama_url host '{host}' looks like an IPv4 address but is not a "
            "valid one (four octets of 0-255 are required)."
        ) from exc
    return host


def _validate_dns_name(host: str) -> str:
    if len(host) > _MAX_DNS_NAME_LENGTH:
        raise _fail(
            f"ollama_url host is longer than {_MAX_DNS_NAME_LENGTH} characters."
        )
    if host.endswith("."):
        raise _fail("ollama_url host must not end with a dot.")
    for label in host.split("."):
        if not _DNS_LABEL.match(label):
            raise _fail(
                f"ollama_url host label '{label}' is invalid: labels must be "
                "1-63 characters of letters, digits, '-' or '_'."
            )
        if label.startswith("-") or label.endswith("-"):
            raise _fail(
                f"ollama_url host label '{label}' must not start or end with '-'."
            )
    return host


def _split_host_and_port(hostport: str) -> tuple[str, bool, str]:
    """Return ``(host, is_ipv6, port_text)`` from an authority without userinfo."""

    if hostport.startswith("["):
        closing = hostport.find("]")
        if closing == -1:
            raise _fail("ollama_url has an unterminated IPv6 literal.")
        host = _validate_ipv6_literal(hostport[1:closing])
        rest = hostport[closing + 1 :]
        if rest and not rest.startswith(":"):
            raise _fail("ollama_url has trailing characters after the IPv6 literal.")
        return host, True, rest[1:] if rest else ""

    if hostport.count(":") > 1:
        raise _fail(
            "ollama_url host contains ':'; an IPv6 address must be written in "
            "square brackets."
        )
    host, _, port_text = hostport.partition(":")
    if not host:
        raise _fail("ollama_url must contain a host.")
    if _DIGITS_AND_DOTS.match(host):
        return _validate_ipv4(host), False, port_text
    return _validate_dns_name(host), False, port_text


def _resolve_port(port_text: str, scheme: str) -> int:
    if port_text == "":
        return _DEFAULT_PORTS[scheme]
    if not _PORT.match(port_text):
        raise _fail(
            f"ollama_url port '{port_text}' is not a decimal integer."
        )
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise _fail(f"ollama_url port {port} is outside the range 1-65535.")
    return port


def parse_ollama_url(raw: str) -> OllamaEndpoint:
    """Validate ``ollama_url`` against the Requirement 10.1 decision table."""

    if not isinstance(raw, str):
        raise _fail(
            f"ollama_url must be a string, got {type(raw).__name__}."
        )
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        # e.g. an unterminated IPv6 literal; never let a raw ValueError escape
        # to the user (Requirement 10.16).
        raise _fail(f"ollama_url could not be parsed as a URL ({exc}).") from exc

    if parts.scheme not in _ALLOWED_SCHEMES:
        raise _fail(
            f"ollama_url scheme must be 'http' or 'https', got "
            f"'{parts.scheme}'."
        )

    netloc = parts.netloc
    if "@" in netloc:
        userinfo, _, hostport = netloc.rpartition("@")
        if userinfo:
            raise _fail(
                "ollama_url must not contain a user name or password "
                "(authenticated Ollama is not supported)."
            )
    else:
        hostport = netloc

    host, is_ipv6, port_text = _split_host_and_port(hostport)
    port = _resolve_port(port_text, parts.scheme)

    if parts.path not in ("", "/"):
        raise _fail(
            "ollama_url must not contain a path: give the origin only, for "
            "example 'http://127.0.0.1:11434'."
        )
    if parts.query:
        raise _fail("ollama_url must not contain a query string.")
    if parts.fragment:
        raise _fail("ollama_url must not contain a fragment.")

    return OllamaEndpoint(
        scheme=parts.scheme, host=host, port=port, is_ipv6=is_ipv6
    )


def validate_model_name(raw: str) -> str:
    """Reject an empty or whitespace-only model name (Requirement 10.6)."""

    if not isinstance(raw, str):
        raise _fail(f"ollama_model must be a string, got {type(raw).__name__}.")
    if not raw.strip():
        raise _fail(
            "ollama_model is empty: set the Ollama model to use. There is no "
            "implicit default model."
        )
    return raw


def _require_finite_number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(f"{what} must be a number, got {type(value).__name__}.")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise _fail(f"{what} must be a finite number.")
    return number


def validate_temperature(value: float) -> float:
    """Reject negative and non-finite temperatures (Requirement 10.9)."""

    number = _require_finite_number(value, "temperature")
    if number < 0:
        raise _fail(f"temperature must be 0 or greater, got {number}.")
    return number


def effective_timeout(value: float) -> float:
    """Validate ``timeout`` and truncate it to three decimals.

    Truncation (never rounding) keeps the effective timeout at or below what the
    user asked for, and makes runs that share a cache key share a timeout
    (Requirement 10.12). The 0.1 lower bound is far enough from the quantum that
    truncation can never produce 0.
    """

    number = _require_finite_number(value, "timeout")
    if not _MIN_TIMEOUT <= number <= _MAX_TIMEOUT:
        raise _fail(
            f"timeout must be between {_MIN_TIMEOUT} and {_MAX_TIMEOUT} seconds "
            f"(inclusive), got {number}."
        )
    try:
        truncated = Decimal(str(number)).quantize(_TIMEOUT_QUANTUM, rounding=ROUND_DOWN)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the checks above
        raise _fail(f"timeout could not be normalized: {number}.") from exc
    return float(truncated)


def parse_keep_alive(raw: str) -> KeepAlive:
    """Validate ``keep_alive`` and decide its wire type (Requirements 10.17-10.19, 10.22).

    Only a decimal number, optionally carrying a *single* unit, is accepted.
    Compound forms such as ``1h30m`` are out of scope for v1 because matching
    them needs a nested quantifier.
    """

    if not isinstance(raw, str):
        raise _fail(f"keep_alive must be a string, got {type(raw).__name__}.")
    match = _KEEP_ALIVE.match(raw)
    if not match:
        raise _fail(
            f"keep_alive '{raw}' is not supported: use a decimal number of "
            "seconds (e.g. '0', '-1', '300') or a number with one unit "
            "(ns, us, ms, s, m, h), e.g. '5m'. Compound forms like '1h30m' are "
            "not supported."
        )
    has_fraction = match.group(1) is not None
    unit = match.group(2)
    if unit:
        return KeepAlive(raw=raw, wire_value=raw)
    return KeepAlive(raw=raw, wire_value=float(raw) if has_fraction else int(raw))
