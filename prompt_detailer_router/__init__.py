"""ComfyUI-Prompt-Detailer-Router backend package.

Layered architecture (one-directional dependencies):

    application -> domain
    application -> infrastructure
    infrastructure -> resources

``domain`` stays pure: it must not import ComfyUI, Ollama, filesystem, or
``jsonschema``. ``jsonschema`` is confined to ``infrastructure``.

This package initializer intentionally holds no domain logic.
"""

__all__: list[str] = []
