"""Unit tests for ``ollama_url`` validation and endpoint construction.

Requirements 10.1-10.5, 10.20, 11.4: every URL component follows the decision
table, a syntactically invalid host is a configuration error *before* any
connection attempt (never classification (a)), and the endpoint path is always
exactly ``/api/chat``.
"""

import pytest

from prompt_detailer_router.domain.connection_settings import parse_ollama_url
from prompt_detailer_router.domain.errors import ConfigurationError


# --- scheme ---

@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "https://example.com"])
def test_http_and_https_are_accepted(url: str) -> None:
    assert parse_ollama_url(url).scheme in ("http", "https")


def test_scheme_is_case_insensitive() -> None:
    assert parse_ollama_url("HTTP://127.0.0.1:11434").scheme == "http"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://127.0.0.1:11434",
        "file:///tmp/ollama",
        "ws://127.0.0.1:11434",
        "127.0.0.1:11434",
        "//127.0.0.1:11434",
        "",
    ],
)
def test_other_schemes_are_configuration_errors(url: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url(url)


# --- userinfo (v1 does not support authenticated Ollama) ---

@pytest.mark.parametrize(
    "url",
    [
        "http://user@127.0.0.1:11434",
        "http://user:pass@127.0.0.1:11434",
        "http://:pass@127.0.0.1:11434",
    ],
)
def test_userinfo_is_rejected(url: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url(url)


# --- host: IPv6 literal ---

@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("http://[::1]:11434", "::1"),
        ("http://[2001:db8::1]:11434", "2001:db8::1"),
        # ipaddress' canonical form for an IPv4-mapped literal.
        ("http://[::ffff:127.0.0.1]", "::ffff:7f00:1"),
        # A non-compressed literal normalizes to the canonical form.
        ("http://[2001:0db8:0000:0000:0000:0000:0000:0001]", "2001:db8::1"),
    ],
)
def test_ipv6_literals_are_accepted(url: str, host: str) -> None:
    endpoint = parse_ollama_url(url)
    assert endpoint.host == host
    assert endpoint.is_ipv6 is True


@pytest.mark.parametrize(
    "url",
    [
        "http://[::1",
        "http://[not-an-ipv6]:11434",
        "http://[]:11434",
        "http://[127.0.0.1]:11434",
        "http://::1:11434",
    ],
)
def test_malformed_ipv6_literals_are_rejected(url: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url(url)


# --- host: IPv4 ---

@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0", "255.255.255.255", "10.0.0.7"])
def test_ipv4_hosts_are_accepted(host: str) -> None:
    endpoint = parse_ollama_url(f"http://{host}:11434")
    assert endpoint.host == host
    assert endpoint.is_ipv6 is False


@pytest.mark.parametrize(
    "host",
    ["256.1.1.1", "1.2.3", "1.2.3.4.5", "999.999.999.999", "1..2.3", "1.2.3.", ".1.2.3"],
)
def test_malformed_ipv4_hosts_are_rejected(host: str) -> None:
    # Digits-and-dots only is judged as IPv4 (Requirement 10.1, host row).
    with pytest.raises(ConfigurationError):
        parse_ollama_url(f"http://{host}:11434")


# --- host: DNS name ---

@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "example.com",
        "ollama.internal.example.com",
        "ollama_server",
        "my-ollama-1",
        "a",
        "x" * 63,
    ],
)
def test_dns_hosts_are_accepted(host: str) -> None:
    endpoint = parse_ollama_url(f"http://{host}:11434")
    assert endpoint.host == host
    assert endpoint.is_ipv6 is False


def test_dns_host_case_is_preserved_on_the_endpoint() -> None:
    assert parse_ollama_url("http://Ollama.Example.COM").host == "Ollama.Example.COM"


@pytest.mark.parametrize(
    "host",
    [
        "bad host",
        "ex%2Fample.com",
        "ex%2fample.com",
        "-leading.example.com",
        "trailing-.example.com",
        "example.com.",
        "exa mple",
        "exam!ple.com",
        "exam:ple",
        "under..score",
        "x" * 64,
        ".".join(["label"] * 43),  # > 253 characters overall
    ],
)
def test_malformed_dns_hosts_are_configuration_errors(host: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url(f"http://{host}:11434")


def test_empty_host_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url("http://:11434")


# --- port ---

def test_explicit_port_is_used() -> None:
    assert parse_ollama_url("http://127.0.0.1:11434").port == 11434


@pytest.mark.parametrize(
    ("url", "port"),
    [("http://example.com", 80), ("https://example.com", 443)],
)
def test_omitted_port_falls_back_to_the_scheme_default(url: str, port: int) -> None:
    assert parse_ollama_url(url).port == port


@pytest.mark.parametrize("port", ["0", "65536", "99999", "-1", "abc", "11434x", "1 1"])
def test_invalid_ports_are_rejected(port: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url(f"http://127.0.0.1:{port}")


def test_trailing_colon_means_an_omitted_port() -> None:
    # "host:" carries no port; RFC 3986 reads an empty port as omitted, which is
    # the "省略" row of the Requirement 10.1 table, not a syntax error.
    assert parse_ollama_url("http://127.0.0.1:").port == 80


@pytest.mark.parametrize("port", ["1", "65535"])
def test_port_range_boundaries_are_accepted(port: str) -> None:
    assert parse_ollama_url(f"http://127.0.0.1:{port}").port == int(port)


# --- path / query / fragment ---

@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://127.0.0.1:11434/"])
def test_empty_or_root_path_is_accepted(url: str) -> None:
    assert parse_ollama_url(url).host == "127.0.0.1"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/ollama",
        "http://127.0.0.1:11434/api/chat",
        "http://127.0.0.1:11434//",
    ],
)
def test_path_prefixes_are_rejected(url: str) -> None:
    # v1 does not support a reverse proxy under a path prefix (Requirement 10.5).
    with pytest.raises(ConfigurationError):
        parse_ollama_url(url)


def test_query_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url("http://127.0.0.1:11434/?a=b")


def test_fragment_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url("http://127.0.0.1:11434/#section")


# --- endpoint construction (Requirement 10.2) ---

@pytest.mark.parametrize(
    ("url", "chat_url"),
    [
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434/api/chat"),
        ("http://example.com", "http://example.com:80/api/chat"),
        ("https://example.com", "https://example.com:443/api/chat"),
        ("http://[::1]:11434", "http://[::1]:11434/api/chat"),
        ("http://[2001:db8::1]", "http://[2001:db8::1]:80/api/chat"),
    ],
)
def test_chat_url_is_built_from_the_validated_components(url: str, chat_url: str) -> None:
    assert parse_ollama_url(url).chat_url == chat_url


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://[::1]:11434/"])
def test_chat_url_path_is_always_exactly_api_chat(url: str) -> None:
    assert parse_ollama_url(url).chat_url.endswith("/api/chat")
    assert parse_ollama_url(url).chat_url.count("/api/chat") == 1


# --- cache identity (Requirement 11.4) ---

@pytest.mark.parametrize(
    ("url", "identity"),
    [
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("http://Ollama.Example.COM", "http://ollama.example.com:80"),
        ("https://Example.com:8443", "https://example.com:8443"),
        ("http://[2001:DB8::1]:11434", "http://[2001:db8::1]:11434"),
    ],
)
def test_cache_identity_lowercases_the_host_and_uses_the_effective_port(
    url: str, identity: str
) -> None:
    assert parse_ollama_url(url).cache_identity == identity


def test_cache_identity_excludes_path_query_and_userinfo() -> None:
    identity = parse_ollama_url("http://127.0.0.1:11434/").cache_identity
    assert identity == "http://127.0.0.1:11434"


# --- control characters and whitespace (Requirements 10.1, 10.20) ---

@pytest.mark.parametrize(
    "url",
    [
        "http://local\nhost:11434",
        "http://local\rhost:11434",
        "http://local\thost:11434",
        "http://local host:11434",
        "http://localhost:114\n34",
        "ht\ntp://localhost:11434",
        "http://localhost:11434/\n",
        "http://localhost\x7f:11434",
        "http://local\x00host:11434",
    ],
)
def test_control_characters_and_inner_whitespace_are_rejected(url: str) -> None:
    """``urlsplit`` deletes these, so the host check runs on a different string.

    Without a pre-parse guard ``http://local\\nhost:11434`` is accepted as
    ``localhost`` and the request goes somewhere the user never typed
    (Requirements 10.1, 10.20).
    """
    with pytest.raises(ConfigurationError):
        parse_ollama_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "  http://127.0.0.1:11434",
        "http://127.0.0.1:11434  ",
        "\thttp://127.0.0.1:11434\n",
        "http://127.0.0.1:11434\n",
    ],
)
def test_surrounding_whitespace_is_rejected_uniformly(url: str) -> None:
    """Surrounding spaces were already errors; tabs and newlines now match.

    ``urlsplit`` deletes tab/CR/LF but keeps spaces, so identical-looking
    padding was an error or a silent success depending on the character used.
    """
    with pytest.raises(ConfigurationError):
        parse_ollama_url(url)


# --- unexpected input types never leak a raw exception ---

@pytest.mark.parametrize("value", [None, 11434, [], {}, b"http://127.0.0.1"])
def test_non_string_input_is_a_configuration_error(value: object) -> None:
    with pytest.raises(ConfigurationError):
        parse_ollama_url(value)  # type: ignore[arg-type]


def test_endpoint_is_immutable() -> None:
    endpoint = parse_ollama_url("http://127.0.0.1:11434")
    with pytest.raises(Exception):
        endpoint.port = 1  # type: ignore[misc]
