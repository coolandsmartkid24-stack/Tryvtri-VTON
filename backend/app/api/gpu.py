"""GPU lifecycle and monitoring endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException

from ..core.errors import Unauthorized
from ..core.security import bearer_token, decode_admin_token
from ..logging_config import get_logger
from ..services.gpu_manager import get_gpu_manager

router = APIRouter(tags=["GPU Lifecycle"])
log = get_logger("api.gpu")


def get_current_admin(authorization: str = Header(None)) -> Dict[str, Any]:
    """Dependency for admin-only endpoints."""
    token = bearer_token(authorization)
    return decode_admin_token(token)


@router.get("/gpu/status")
async def get_gpu_status():
    """Return current GPU state, runtime, active/queued requests, and estimated cost."""
    mgr = get_gpu_manager()
    return mgr.get_status_payload()


@router.post("/admin/gpu/start")
async def admin_start_gpu(_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Admin manual trigger to wake up the GPU."""
    mgr = get_gpu_manager()
    log.info("admin_manual_gpu_start_requested", admin=_admin.get("sub"))
    endpoint = await mgr.start_gpu()
    return {
        "success": True,
        "message": "GPU started successfully.",
        "status": mgr.status,
        "pod_id": mgr.pod_id,
        "endpoint": endpoint,
    }


@router.post("/admin/gpu/stop")
async def admin_stop_gpu(_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Admin manual trigger to shut down the GPU."""
    mgr = get_gpu_manager()
    log.info("admin_manual_gpu_stop_requested", admin=_admin.get("sub"))
    if mgr.active_requests > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot stop GPU: {mgr.active_requests} active try-on request(s) currently running.",
        )
    await mgr.stop_gpu(reason="admin_manual_stop")
    return {
        "success": True,
        "message": "GPU stopped successfully.",
        "status": mgr.status,
    }
