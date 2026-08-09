"""Bundled resource path resolution.

Resolves files under the packaged ``resources`` directory by chaining
single-argument ``joinpath`` calls. On Python 3.10 the ``importlib.resources``
``Traversable.joinpath`` accepts only a single child (multi-argument support was
added in 3.11), so a multi-argument call would raise ``TypeError`` for zip- or
namespace-based package layouts. Chaining keeps resource access working across
supported layouts.
"""

from __future__ import annotations

from importlib.resources import files
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # ``importlib.resources.abc`` only exists on Python 3.11+.
    from importlib.abc import Traversable

_RESOURCES_ANCHOR = "prompt_detailer_router.resources"


def resource_file(*parts: str) -> "Traversable":
    """Return the resource at ``resources/<parts...>`` (3.10-safe chaining)."""

    node = files(_RESOURCES_ANCHOR)
    for part in parts:
        node = node.joinpath(part)
    return node
