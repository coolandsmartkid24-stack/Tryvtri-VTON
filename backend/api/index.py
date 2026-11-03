"""Vercel Serverless Function entrypoint."""

import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_root = str(Path(__file__).resolve().parents[1])
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.main import app

__all__ = ["app"]
