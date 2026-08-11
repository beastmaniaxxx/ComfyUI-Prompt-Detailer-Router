"""Cache-key computation for Analyzer results.

Pure domain logic (Requirements 11.3-11.5, 11.13). The key covers everything
that can change the output: the request itself, the destination, the generation
options, and the id/version of *every* resource that influences the result.
``keep_alive``, UI settings, and diagnostics formatting are deliberately absent
-- none of them changes what is produced (Requirement 11.5).

The components are serialized as canonical JSON (sorted keys, fixed separators)
and hashed, rather than concatenated into a string. Concatenation would let two
different component sets collapse onto the same text -- ``model="ab"`` with an
empty hint versus ``model="a"`` with hint ``"b"`` -- and silently serve a cached
result for a different request.

Requirement 11.13 makes ``resources`` a closed rule rather than a list to keep
in sync by hand: it carries the whole fingerprint, so adding a resource to the
fingerprint adds it to the key.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CacheKeyComponents:
    """Everything a cached Analyzer result depends on.

    ``resources`` holds ``(kind, id, version)`` triples as produced by
    ``resource_fingerprint``; ``timeout`` is the effective timeout of
    Requirement 10.12 and ``endpoint_identity`` the normalized destination of
    Requirement 11.4.
    """

    original_prompt: str
    requested_scopes: tuple[str, ...]
    dropped_scopes: tuple[str, ...]
    subject_hint: str
    endpoint_identity: str
    model: str
    seed: int
    temperature: float
    timeout: float
    failure_mode: str
    resources: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        # ``frozen=True`` blocks rebinding but not mutation of a list passed in,
        # which would let the key input change after construction.
        object.__setattr__(self, "requested_scopes", tuple(self.requested_scopes))
        object.__setattr__(self, "dropped_scopes", tuple(self.dropped_scopes))
        object.__setattr__(
            self, "resources", tuple(tuple(entry) for entry in self.resources)
        )


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def compute_cache_key(components: CacheKeyComponents) -> str:
    """Return the deterministic cache key for ``components``.

    Equal components always give the same key; a difference in any single
    component gives a different one (Requirement 11.11's precondition).
    """

    payload = asdict(components)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
