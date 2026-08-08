"""Shared pytest fixtures and path setup for the test suite.

Ensures the repository root is importable so ``prompt_detailer_router`` can be
imported without an editable install, keeping the core test suite runnable in a
plain Python environment (no ComfyUI, no Ollama).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
