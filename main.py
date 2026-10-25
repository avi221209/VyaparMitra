"""
VyaparMitra - Root ASGI Entrypoint
Used by hosting platforms (Render, Railway, Heroku, etc.)
that default to running `uvicorn main:app --host 0.0.0.0 --port $PORT`.
"""

import sys
from pathlib import Path

# Ensure root directory is on Python search path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.main import app

__all__ = ["app"]
