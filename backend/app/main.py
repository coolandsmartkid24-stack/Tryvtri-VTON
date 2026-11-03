"""FastAPI Application Entrypoint for TryVtri FASHN VTON 1.5.

Provides:
- Virtual Try-On endpoint for Shopify storefront widget (Zero API credentials)
- Secure image validation & SSRF protection
- On-Demand Lium GPU lifecycle management
- Supabase atomic quota and analytics
- Admin Dashboard REST APIs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import time
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

from .api.admin import router as admin_router
from .api.gpu import router as gpu_router
from .api.tryon import router as tryon_router
from .config import get_settings
from .core.errors import ApiError, api_error_handler, unhandled_error_handler
from .core.request_ids import new_request_id
from .core.security import hash_password
from .db.store import build_supabase_store, get_store, set_store
from .db.memory import MemoryStore
from .logging_config import configure_logging, get_logger
from .services.gpu_manager import get_gpu_manager

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan manager for backend startup and clean shutdown."""
    settings = get_settings()
    configure_logging(level=settings.log_level)
    log.info("tryvtri_backend_starting", environment=settings.environment)

    # Initialize persistence
    if settings.has_supabase:
        try:
            store = await build_supabase_store()
            set_store(store)
            log.info("supabase_connected_successfully", url=settings.supabase_url)
        except Exception as exc:
            log.error("failed_to_connect_supabase_falling_back_to_memory", error=str(exc))
            set_store(MemoryStore(limit=settings.free_tries_per_day, window_hours=settings.quota_window_hours))
    else:
        log.warning("no_supabase_credentials_using_in_memory_store")
        set_store(MemoryStore(limit=settings.free_tries_per_day, window_hours=settings.quota_window_hours))

    # Bootstrap administrator account if configured
    store = get_store()
    try:
        admin_count = await store.count_admins()
        if admin_count == 0 and settings.admin_password:
            hashed = hash_password(settings.admin_password)
            await store.create_admin(settings.admin_username, hashed, role="owner")
            log.info("bootstrapped_admin_user", username=settings.admin_username)
    except Exception as exc:
        log.warning("admin_bootstrap_warning", error=str(exc))

    gpu_mgr = get_gpu_manager()
    log.info("gpu_manager_initialized", status=gpu_mgr.status, mock_mode=gpu_mgr.mock_mode)

    yield

    # Clean shutdown
    log.info("tryvtri_backend_shutting_down")
    if gpu_mgr.is_running and not settings.using_fixed_inference:
        await gpu_mgr.stop_gpu(reason="backend_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="TryVtri FASHN VTON 1.5 Virtual Try-On API",
        description="Production virtual try-on engine for Shopify storefronts with on-demand Lium GPU.",
        version="1.5.0",
        lifespan=lifespan,
    )

    # 1. CORS Configuration (Allows storefronts without manual merchant domain setup)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Request ID & Timing Middleware
    @app.middleware("http")
    async def request_id_and_timing_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-Id") or new_request_id()
        request.state.request_id = req_id
        start_t = time.perf_counter()

        response = await call_next(request)

        duration_ms = int((time.perf_counter() - start_t) * 1000)
        response.headers["X-Request-Id"] = req_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        return response

    # 3. Exception Handlers
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    # 4. Include Routers
    app.include_router(tryon_router)
    app.include_router(gpu_router)
    app.include_router(admin_router)

    # 5. Core Health Check
    @app.get("/health", tags=["Health"])
    async def health_check():
        store = get_store()
        db_ok = False
        try:
            db_ok = await store.ping()
        except Exception:
            pass

        gpu_mgr = get_gpu_manager()
        return {
            "status": "ok" if db_ok else "degraded",
            "environment": settings.environment,
            "database_connected": db_ok,
            "gpu": gpu_mgr.get_status_payload(),
        }

    # 6. Mount built dashboard if present
    possible_dist_dirs = [
        Path(__file__).resolve().parents[1] / "static",
        Path(__file__).resolve().parent / "static",
        Path(__file__).resolve().parents[2] / "dashboard" / "dist",
    ]
    mounted_dist: Optional[Path] = None
    for candidate in possible_dist_dirs:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            app.mount("/dashboard", StaticFiles(directory=str(candidate), html=True), name="dashboard")
            mounted_dist = candidate
            log.info("mounted_static_dashboard", path=str(candidate))
            break

    @app.get("/", tags=["Root"])
    async def root_redirect():
        if mounted_dist:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/dashboard/")
        return {
            "service": "TryVtri FASHN VTON 1.5 API",
            "version": "1.5.0",
            "status": "online",
            "docs": "/docs",
            "dashboard": "/dashboard",
        }

    return app


app = create_app()
