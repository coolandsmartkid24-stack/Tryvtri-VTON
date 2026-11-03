"""Vercel / ASGI entrypoint for TryVtri FastAPI backend."""

from app.main import app

# Vercel Function configuration
max_duration = 60

# Export app for ASGI servers (Uvicorn, Vercel)
__all__ = ["app", "max_duration"]
