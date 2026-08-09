"""Safe resource-id validation.

Resource ids (preset / profile / policy / template) can originate from node
STRING inputs. They are used to build filesystem paths under ``resources/``, so
they must be restricted to a safe filename stem to prevent path traversal
(``..``, absolute paths, separators, or extension injection).
"""

from __future__ import annotations

import re

from prompt_detailer_router.domain.errors import ConfigurationError

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def safe_resource_id(name: str, what: str) -> str:
    """Return ``name`` if it is a safe resource stem, else raise ConfigurationError."""

    if not isinstance(name, str) or not _SAFE_ID.match(name):
        raise ConfigurationError(
            f"Invalid {what} id: {name!r}. Only letters, digits, '-' and '_' "
            "are allowed."
        )
    return name
