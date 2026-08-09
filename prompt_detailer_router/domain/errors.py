"""Project error hierarchy (Requirement 14.3).

Distinguishes user-facing errors (recoverable, safe to present) from internal
errors (unexpected invariant breaks). Pure domain module: no external imports.
"""

from __future__ import annotations


class PDRError(Exception):
    """Base class for all Prompt-Detailer-Router errors."""


class PDRUserError(PDRError):
    """Base class for errors that are meaningful to present to the user."""


class ConfigurationError(PDRUserError):
    """A preset, profile, or policy resource is missing or misconfigured."""


class PlanDecodeError(PDRUserError):
    """Incoming JSON is malformed, shape-invalid, or has unknown fields."""


class PlanValidationError(PDRUserError):
    """A plan violates one or more business invariants."""


class PDRInternalError(PDRError):
    """An unexpected internal inconsistency; not a user-facing condition."""
