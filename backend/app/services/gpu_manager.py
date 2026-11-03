"""On-demand Lium GPU Lifecycle Manager.

Manages the lifecycle of an NVIDIA RTX 5080 GPU on Lium:
- Activates GPU on-demand when a customer requests virtual try-on.
- Protects against duplicate pod launches via an asyncio lock.
- Tracks active and queued requests.
- Auto-terminates GPU after 10 minutes of inactivity (no active or queued requests).
- Never shuts down while an inference request is running.
- Tracks startup, shutdown, runtime, and estimated spend at ~$0.36/hour.
- Records all GPU sessions to Supabase `gpu_usage` table.
- Supports mock / local mode for test-suites and local development without incurring charges.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import time
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from ..config import get_settings
from ..core.errors import GpuError
from ..logging_config import get_logger

log = get_logger("gpu_manager")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GpuManager:
    """Orchestrates Lium GPU pod allocation, health checking, and idle termination."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.status = "stopped"  # stopped, starting, running, stopping, error
        self.pod_id: Optional[str] = None
        self.pod_name: Optional[str] = None
        self.gpu_model: str = "RTX 5080"
        self.price_per_hour: float = 0.36
        self.active_requests: int = 0
        self.queued_requests: int = 0
        self.started_at: Optional[datetime] = None
        self.stopped_at: Optional[datetime] = None
        self.last_activity: datetime = _now()
        self.current_session_id: Optional[str] = None
        self.total_runtime_seconds: int = 0
        self.total_estimated_cost_usd: float = 0.0

        self._inference_endpoint: Optional[str] = None
        self._idle_task: Optional[asyncio.Task] = None
        self.mock_mode: bool = False

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    def get_status_payload(self) -> Dict[str, Any]:
        """Return formatted status for API and Admin Dashboard."""
        current_session_runtime = 0
        current_session_cost = 0.0
        if self.started_at and self.status in ("running", "starting"):
            current_session_runtime = int((_now() - self.started_at).total_seconds())
            current_session_cost = round((current_session_runtime / 3600.0) * self.price_per_hour, 4)

        return {
            "status": self.status,
            "gpu_model": self.gpu_model,
            "pod_id": self.pod_id,
            "pod_name": self.pod_name,
            "price_per_hour": self.price_per_hour,
            "active_requests": self.active_requests,
            "queued_requests": self.queued_requests,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "current_session_runtime_seconds": current_session_runtime,
            "current_session_cost_usd": current_session_cost,
            "total_runtime_seconds": self.total_runtime_seconds + current_session_runtime,
            "total_estimated_cost_usd": round(self.total_estimated_cost_usd + current_session_cost, 4),
            "inference_endpoint": self._inference_endpoint if self.is_running else None,
            "mock_mode": self.mock_mode,
        }

    async def _cancel_idle_timer(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
            self._idle_task = None

    def _schedule_idle_shutdown(self) -> None:
        """Schedule shutdown after GPU_IDLE_SHUTDOWN_SECONDS of zero active requests."""
        settings = get_settings()
        timeout = settings.gpu_idle_shutdown_seconds

        async def _idle_wait():
            try:
                log.info("gpu_idle_timer_started", seconds=timeout)
                await asyncio.sleep(timeout)
                async with self._lock:
                    if self.active_requests == 0 and self.queued_requests == 0 and self.status == "running":
                        log.info("gpu_idle_timeout_reached_stopping")
                        await self.stop_gpu(reason="idle_timeout")
            except asyncio.CancelledError:
                log.debug("gpu_idle_timer_cancelled")

        # Cancel any existing task before creating new
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(_idle_wait())

    async def start_gpu(self) -> str:
        """Start or wake the GPU instance and return healthy inference endpoint."""
        settings = get_settings()

        # If already running and healthy, return immediately
        if self.status == "running" and self._inference_endpoint:
            return self._inference_endpoint

        async with self._lock:
            # Double-check inside lock
            if self.status == "running" and self._inference_endpoint:
                return self._inference_endpoint

            await self._cancel_idle_timer()

            # 1) If fixed inference URL configured, use it directly (e.g. dev/staging container)
            if settings.using_fixed_inference:
                log.info("using_fixed_inference_endpoint", url=settings.inference_base_url)
                self.status = "running"
                self.pod_id = "fixed-endpoint"
                self.pod_name = "local-tryon-service"
                self.started_at = _now()
                self._inference_endpoint = settings.inference_base_url.rstrip("/")
                return self._inference_endpoint

            # 2) If no Lium API key configured, operate in mock mode
            if not settings.has_lium:
                log.info("no_lium_api_key_using_mock_gpu_mode")
                self.mock_mode = True
                self.status = "starting"
                self.pod_id = f"mock-pod-{int(time.time())}"
                self.pod_name = f"{settings.lium_pod_name_prefix}-mock"
                self.started_at = _now()

                # Record in database
                await self._record_start()

                # Simulate short startup delay
                await asyncio.sleep(0.1)
                self.status = "running"
                self._inference_endpoint = f"http://127.0.0.1:{settings.lium_inference_port}"
                log.info("mock_gpu_pod_ready", pod_id=self.pod_id)
                return self._inference_endpoint

            # 3) Real Lium Cloud Pod lifecycle
            self.status = "starting"
            self.started_at = _now()
            self.pod_name = f"{settings.lium_pod_name_prefix}-{int(time.time())}"

            # Check spend cap
            if settings.gpu_daily_spend_cap_usd > 0:
                from ..db.store import get_store

                try:
                    store = get_store()
                    today_spend = await store.gpu_spend_since(_now().date().isoformat())
                    if today_spend >= settings.gpu_daily_spend_cap_usd:
                        self.status = "error"
                        raise GpuError(
                            f"Daily GPU budget limit (${settings.gpu_daily_spend_cap_usd}) reached. "
                            "Contact administrator."
                        )
                except Exception as exc:
                    if isinstance(exc, GpuError):
                        raise
                    log.warning("could_not_check_spend_cap", error=str(exc))

            try:
                headers = {
                    "X-API-Key": settings.lium_api_key,
                    "Content-Type": "application/json",
                }
                payload = {
                    "gpu_type": settings.lium_gpu_type,
                    "gpu_count": settings.lium_gpu_count,
                    "max_price_per_hour": settings.lium_max_price_per_gpu_hour,
                    "name": self.pod_name,
                    "template_id": settings.lium_template_id or None,
                    "auto_terminate_hours": settings.lium_termination_hours,
                }

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{settings.lium_api_base.rstrip('/')}/v1/pods",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code not in (200, 201):
                        self.status = "error"
                        err_text = resp.text
                        log.error("lium_pod_creation_failed", status=resp.status_code, body=err_text)
                        raise GpuError(f"Failed to launch Lium GPU instance: HTTP {resp.status_code} - {err_text}")

                    data = resp.json()
                    self.pod_id = str(data.get("id") or data.get("pod_id"))

                await self._record_start()

                # Poll pod health until healthy
                endpoint = await self._wait_for_pod_healthy(settings)
                self.status = "running"
                self._inference_endpoint = endpoint
                log.info("lium_gpu_pod_active", pod_id=self.pod_id, endpoint=endpoint)
                return endpoint

            except Exception as exc:
                self.status = "error"
                log.exception("gpu_startup_error", error=str(exc))
                await self._record_error(str(exc))
                raise GpuError(f"GPU startup failed: {str(exc)}")

    async def _wait_for_pod_healthy(self, settings) -> str:
        """Poll the pod status and try-on health endpoint until healthy or timeout."""
        timeout = settings.gpu_startup_timeout_seconds
        start_t = time.time()
        headers = {"X-API-Key": settings.lium_api_key}

        while (time.time() - start_t) < timeout:
            await asyncio.sleep(5)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Query pod info
                    resp = await client.get(
                        f"{settings.lium_api_base.rstrip('/')}/v1/pods/{self.pod_id}",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        pod_info = resp.json()
                        state = pod_info.get("status") or pod_info.get("state")
                        if state in ("running", "active"):
                            # Determine host & port
                            host = settings.lium_inference_host or pod_info.get("ip") or pod_info.get("host")
                            port = settings.lium_inference_port
                            ports_mapping = pod_info.get("ports_mapping") or {}
                            if str(port) in ports_mapping:
                                port = ports_mapping[str(port)]

                            if host:
                                endpoint = f"http://{host}:{port}"
                                # Test health
                                try:
                                    h_resp = await client.get(f"{endpoint}/health", timeout=3.0)
                                    if h_resp.status_code == 200:
                                        return endpoint
                                except Exception:
                                    pass
            except Exception as e:
                log.debug("polling_pod_status_retry", error=str(e))

        raise GpuError(f"GPU pod startup timed out after {timeout} seconds.")

    async def stop_gpu(self, reason: str = "manual") -> None:
        """Shut down the GPU instance if no active requests are executing."""
        if self.status == "stopped":
            return

        if self.active_requests > 0:
            log.warning("cannot_stop_gpu_active_requests_in_progress", active=self.active_requests)
            return

        async with self._lock:
            if self.active_requests > 0:
                log.warning("cannot_stop_gpu_active_requests_in_progress", active=self.active_requests)
                return

            await self._cancel_idle_timer()
            prev_status = self.status
            self.status = "stopping"
            self.stopped_at = _now()

            duration_seconds = 0
            cost = 0.0
            if self.started_at:
                duration_seconds = int((self.stopped_at - self.started_at).total_seconds())
                cost = round((duration_seconds / 3600.0) * self.price_per_hour, 6)

            self.total_runtime_seconds += duration_seconds
            self.total_estimated_cost_usd += cost

            log.info(
                "gpu_stopping",
                pod_id=self.pod_id,
                reason=reason,
                runtime_seconds=duration_seconds,
                cost_usd=cost,
            )

            settings = get_settings()

            if self.mock_mode or settings.using_fixed_inference or not self.pod_id:
                # Mock or fixed shutdown
                self.status = "stopped"
                self._inference_endpoint = None
                await self._record_stop(duration_seconds, cost)
                return

            try:
                headers = {"X-API-Key": settings.lium_api_key}
                async with httpx.AsyncClient(timeout=20.0) as client:
                    await client.delete(
                        f"{settings.lium_api_base.rstrip('/')}/v1/pods/{self.pod_id}",
                        headers=headers,
                    )
            except Exception as exc:
                log.error("failed_to_terminate_lium_pod", pod_id=self.pod_id, error=str(exc))
            finally:
                self.status = "stopped"
                self._inference_endpoint = None
                await self._record_stop(duration_seconds, cost)

    async def _record_start(self) -> None:
        try:
            from ..db.store import get_store

            store = get_store()
            rec = await store.record_gpu_session(
                pod_id=self.pod_id,
                pod_name=self.pod_name,
                gpu_model=self.gpu_model,
                price_per_hour=self.price_per_hour,
                status="starting",
                started_at=self.started_at.isoformat() if self.started_at else None,
                provider="lium" if not self.mock_mode else "mock",
            )
            self.current_session_id = rec.get("id")
        except Exception as exc:
            log.warning("db_record_gpu_start_failed", error=str(exc))

    async def _record_stop(self, runtime: int, cost: float) -> None:
        if not self.current_session_id:
            return
        try:
            from ..db.store import get_store

            store = get_store()
            await store.update_gpu_session(
                self.current_session_id,
                status="stopped",
                stopped_at=self.stopped_at.isoformat() if self.stopped_at else None,
                runtime_seconds=runtime,
                estimated_cost_usd=cost,
            )
        except Exception as exc:
            log.warning("db_record_gpu_stop_failed", error=str(exc))
        finally:
            self.current_session_id = None

    async def _record_error(self, message: str) -> None:
        if not self.current_session_id:
            return
        try:
            from ..db.store import get_store

            store = get_store()
            await store.update_gpu_session(
                self.current_session_id,
                status="error",
                error_message=message,
                stopped_at=_now().isoformat(),
            )
        except Exception:
            pass

    @asynccontextmanager
    async def lease(self) -> AsyncGenerator[str, None]:
        """Lease the GPU for an inference execution.

        Increments queued/active counters, ensures GPU is ready, cancels idle timer,
        and schedules idle shutdown upon release if no other requests are pending.
        """
        self.queued_requests += 1
        try:
            endpoint = await self.start_gpu()
        finally:
            self.queued_requests = max(0, self.queued_requests - 1)

        self.active_requests += 1
        await self._cancel_idle_timer()
        self.last_activity = _now()
        try:
            yield endpoint
        finally:
            self.active_requests = max(0, self.active_requests - 1)
            self.last_activity = _now()
            if self.active_requests == 0 and self.queued_requests == 0:
                self._schedule_idle_shutdown()


# Singleton GPU manager instance
_gpu_manager: Optional[GpuManager] = None


def get_gpu_manager() -> GpuManager:
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GpuManager()
    return _gpu_manager


def set_gpu_manager(mgr: Optional[GpuManager]) -> None:
    global _gpu_manager
    _gpu_manager = mgr
