"""Vercel / ASGI entrypoint for TryVtri FastAPI backend."""

from app.main import app

# Export app for ASGI servers (Uvicorn, Vercel)
__all__ = ["app"]
