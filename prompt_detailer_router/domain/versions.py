"""Deterministic builder version constants.

``PROMPT_BUILDER_VERSION`` is the reproducibility basis for the deterministic
prompt builders. It is separate from preset / policy / schema versions and is
supplied to a downstream Analyzer cache key so that a change to the builder
synthesis logic (independent of any preset/policy edit) invalidates cached
``upscale_prompt`` / ``DETAILER_PLAN`` outputs. Bump this whenever the builder
composition changes; snapshot tests surface the resulting output diff.

Pure domain constant: importable from every layer without a dependency cycle.
"""

from __future__ import annotations

PROMPT_BUILDER_VERSION: int = 1
