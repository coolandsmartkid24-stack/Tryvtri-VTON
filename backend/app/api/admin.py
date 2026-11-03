"""Admin authentication and analytics endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Query

from ..config import get_settings
from ..core.errors import NotFound, Unauthorized, ValidationError
from ..core.security import (
    bearer_token,
    create_admin_token,
    decode_admin_token,
    hash_password,
    password_strength_ok,
    verify_password,
)
from ..db.store import get_store
from ..logging_config import get_logger
from ..schemas.tryon import AdminLoginRequest, AdminLoginResponse
from ..services.gpu_manager import get_gpu_manager

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])
log = get_logger("api.admin")


def get_current_admin(authorization: str = Header(None)) -> Dict[str, Any]:
    """Verify admin JWT from Authorization header."""
    token = bearer_token(authorization)
    return decode_admin_token(token)


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest):
    """Authenticate administrator and return signed JWT."""
    username = payload.username.strip()
    password = payload.password
    store = get_store()
    settings = get_settings()

    admin = await store.get_admin(username)
    if not admin:
        # Check bootstrap if no admin in DB
        admin_count = await store.count_admins()
        if admin_count == 0 and settings.admin_password and username == settings.admin_username:
            if password == settings.admin_password:
                hashed = hash_password(password)
                admin = await store.create_admin(username, hashed, role="owner")
                log.info("bootstrapped_initial_admin_account", username=username)

    if not admin or not verify_password(password, admin.get("password_hash", "")):
        log.warning("admin_login_failed_invalid_credentials", username=username)
        raise Unauthorized("Invalid username or password.")

    await store.touch_admin_login(username)
    role = admin.get("role", "admin")
    token = create_admin_token(username, role=role)

    log.info("admin_login_successful", username=username, role=role)
    return AdminLoginResponse(
        access_token=token,
        token_type="bearer",
        username=username,
        role=role,
        expires_in_minutes=settings.jwt_ttl_minutes,
    )


@router.get("/dashboard")
async def get_admin_dashboard(
    window_hours: int = Query(24, ge=1, le=168),
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Real database statistics for dashboard overview."""
    store = get_store()
    gpu_mgr = get_gpu_manager()

    stats = await store.dashboard_stats(window_hours=window_hours)
    gpu_status = gpu_mgr.get_status_payload()

    return {
        "window_hours": window_hours,
        "metrics": {
            "total_registered_customers": stats.get("total_customers", 0),
            "customers_used_demo": stats.get("demo_customers", 0),
            "total_successful_tryons": stats.get("successful_tryons", 0),
            "total_failed_tryons": stats.get("failed_tryons", 0),
            "total_free_tries_consumed": stats.get("free_tries_consumed", 0),
            "customers_quota_exhausted": stats.get("exhausted_customers", 0),
            "customers_currently_eligible": stats.get("eligible_customers", 0),
            "success_last_window": stats.get("success_last_window", 0),
        },
        "gpu": gpu_status,
    }


@router.get("/customers")
async def get_admin_customers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    window_hours: int = Query(24, ge=1, le=168),
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Customer management listing with quota status and history."""
    store = get_store()
    settings = get_settings()

    customers = await store.customer_list(
        limit=limit,
        offset=offset,
        search=search,
        window_hours=window_hours,
        limit_tries=settings.free_tries_per_day,
    )
    return {
        "limit": limit,
        "offset": offset,
        "count": len(customers),
        "customers": customers,
    }


@router.get("/usage")
async def get_admin_usage(
    days: int = Query(30, ge=1, le=365),
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Usage analytics: daily trends, product-wise breakdown, and recent activity feed."""
    store = get_store()
    daily = await store.daily_usage(days=days)
    products = await store.product_usage(days=days)
    recent = await store.recent_activity(limit=30)
    gpu_sessions = await store.list_gpu_sessions(limit=30)

    return {
        "days": days,
        "daily_usage": daily,
        "product_usage": products,
        "recent_activity": recent,
        "gpu_sessions": gpu_sessions,
    }
