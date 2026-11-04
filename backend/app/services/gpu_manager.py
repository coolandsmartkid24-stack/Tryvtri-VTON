"""On-demand Lium GPU Lifecycle Manager.

Manages the lifecycle of an NVIDIA RTX 5080 GPU on Lium:
- Activates GPU on-demand when a customer requests virtual try-on.
- Protects against duplicate pod launches via an asyncio lock.
- Tracks active and queued requests.
- Auto-terminates / sleeps GPU after 10 minutes of inactivity (no active or queued requests).
- Never shuts down while an inference request is running.
- Tracks startup, shutdown, runtime, and estimated spend at ~$0.36/hour.
- Records all GPU sessions to Supabase `gpu_sessions` / `gpu_usage` table.
- Supports mock / local mode for test-suites and local development without incurring charges.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from ..config import get_settings
from ..core.errors import GpuError
from ..logging_config import get_logger

log = get_logger("gpu_manager")

# Internal ports the GPU services listen on:
#  - 8888: IDM-VTON multi-category API (start_idm_vton.sh / api/main.py)
#  - 8000: FASHN VTON 1.5 inference service (tryon_service/app.py)
_POD_INTERNAL_PORTS = ("8888", "8000")


def _parse_ports_mapping(raw: Any) -> Dict[str, Any]:
    """Normalise a Lium pod ports_mapping (dict or JSON string) into a dict."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _external_port_for(ports: Dict[str, Any], settings) -> Optional[str]:
    """Pick the externally exposed port for the inference service.

    Preference order:
    1. The configured LIUM_INFERENCE_PORT (internal port) if present in the map.
    2. The known pod service ports (8888 / 8000).
    3. A pod that exposes exactly one port.
    """
    if not ports:
        return None

    candidates: list[str] = []
    if settings.lium_inference_port:
        candidates.append(str(settings.lium_inference_port))
    candidates.extend(_POD_INTERNAL_PORTS)

    for internal in candidates:
        if internal in ports:
            return str(ports[internal])
    if len(ports) == 1:
        return str(ports[next(iter(ports))])
    return None


def _ssh_host(ssh_connect_cmd: Optional[str]) -> Optional[str]:
    """Extract the pod's public host from its ssh connect command."""
    if not ssh_connect_cmd:
        return None
    match = re.search(r"root@([^\s]+)", ssh_connect_cmd)
    if match:
        return match.group(1)
    match = re.search(r"@([^\s]+)", ssh_connect_cmd)
    if match:
        return match.group(1)
    return None


def _pod_public_endpoint(pod_info: Dict[str, Any], settings) -> Optional[str]:
    """Derive the public http://host:port endpoint of a pod's inference service.

    Lium exposes only the ports listed in `ports_mapping` (internal -> external);
    the public host equals the pod's SSH host. Falls back to the structured
    "ip"/"host" fields + the configured internal port when a mapping is absent.
    """
    ports = _parse_ports_mapping(pod_info.get("ports_mapping"))

    host = _ssh_host(pod_info.get("ssh_connect_cmd"))
    port = _external_port_for(ports, settings)

    if host is None:
        host = pod_info.get("ip") or pod_info.get("host") or settings.lium_inference_host or None
    if port is None and settings.lium_inference_port:
        port = str(settings.lium_inference_port)

    if not host or not port:
        return None
    return f"http://{host}:{port}"


def _is_pod_running(state: Any) -> bool:
    return str(state or "").strip().lower() in ("running", "active")


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

        # Compliance guard: block all GPU spend/activation while paused
        # (e.g. pending confirmation of commercial-use licensing).
        if settings.gpu_call_paused and not self.mock_mode:
            self.pod_id = None
            self.pod_name = None
            self._inference_endpoint = None
            self.status = "stopped"
            raise GpuError(
                "GPU operations are currently paused by the administrator "
                "(commercial-use licensing pending for the model weights). "
                "No GPU will be started and no further spend will occur."
            )

        # If already running and healthy, return immediately
        if self.status == "running" and self._inference_endpoint:
            return self._inference_endpoint

        async with self._lock:
            # Double-check inside lock
            if self.status == "running" and self._inference_endpoint:
                return self._inference_endpoint

            await self._cancel_idle_timer()

            # 1) If fixed inference URL configured (e.g. Lium RTX 5080 pod)
            if settings.using_fixed_inference and not self.mock_mode:
                log.info("waking_gpu_fixed_inference_endpoint", url=settings.inference_base_url)
                self.status = "starting"
                self.started_at = _now()
                self.pod_id = "rtx5080-lium"
                self.pod_name = "lium-rtx5080-tryvtri"
                self._inference_endpoint = settings.inference_base_url.rstrip("/")

                await self._record_start()

                # Verify health and wake pipeline with retry loop
                headers = {}
                if settings.inference_api_key:
                    headers["X-Inference-Key"] = settings.inference_api_key

                is_healthy = False
                last_exc = None
                for attempt in range(1, 6):
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            # Attempt wake endpoint
                            try:
                                await client.post(f"{self._inference_endpoint}/wake", headers=headers, timeout=5.0)
                            except Exception:
                                pass
                            # Confirm healthy
                            h_resp = await client.get(f"{self._inference_endpoint}/health", timeout=5.0)
                            if h_resp.status_code == 200:
                                is_healthy = True
                                break
                    except Exception as exc:
                        last_exc = exc
                        log.warning("gpu_health_check_attempt_failed", attempt=attempt, error=str(exc))
                        if attempt < 5:
                            await asyncio.sleep(2.0)

                if not is_healthy:
                    # The configured URL is unreachable. Lium pod hosts/ports move
                    # on restarts, so re-resolve the endpoint from the Lium API
                    # before giving up.
                    discovered = await self._discover_existing_pod(settings)
                    if discovered:
                        self._inference_endpoint = discovered
                        self.pod_name = settings.lium_pod_name_prefix or self.pod_name
                        is_healthy = True
                        log.info("gpu_endpoint_rediscovered_via_lium", endpoint=discovered)

                if not is_healthy:
                    self.status = "error"
                    await self._record_error(str(last_exc or "Health check failed"))
                    raise GpuError(
                        "Failed to connect to GPU inference service "
                        f"({self._inference_endpoint}): {last_exc}. "
                        "The Lium pod is likely stopped or its public port moved — "
                        "restart the pod and verify INFERENCE_BASE_URL / pod ports."
                    )

                self.status = "running"
                log.info("gpu_pod_active_and_ready", endpoint=self._inference_endpoint)
                return self._inference_endpoint

            # 2) If mock mode is explicitly set OR no Lium API key configured, operate in mock mode
            if self.mock_mode or not settings.has_lium:
                log.info("using_mock_gpu_mode")
                self.mock_mode = True
                self.status = "starting"
                self.pod_id = f"mock-pod-{int(time.time())}"
                self.pod_name = f"{settings.lium_pod_name_prefix}-mock"
                self.started_at = _now()

                # Record in database
                await self._record_start()

                # Simulate short startup delay
                await asyncio.sleep(0.01)
                self.status = "running"
                self._inference_endpoint = f"http://127.0.0.1:{settings.lium_inference_port}"
                log.info("mock_gpu_pod_ready", pod_id=self.pod_id)
                return self._inference_endpoint

            # 3) Real Lium Cloud Pod dynamic lifecycle (Rent on-demand via Lium API)
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

            # An earlier rent of this project's pod may still exist (Lium hosts/
            # ports move on restarts, but the pod keeps billing). Reuse it before
            # renting a second billable instance.
            existing = await self._discover_existing_pod(settings)
            if existing:
                self.pod_id = self.pod_id or "rtx5080-lium"
                self._inference_endpoint = existing
                self.status = "running"
                log.info("gpu_pod_reexisting_active", endpoint=existing)
                return existing

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
                        f"{settings.lium_api_base.rstrip('/')}/executors/rent-by-spec",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code not in (200, 201):
                        self.status = "error"
                        err_text = resp.text
                        log.error("lium_pod_creation_failed", status=resp.status_code, body=err_text)
                        if resp.status_code == 402:
                            raise GpuError(
                                "Lium account has insufficient balance (HTTP 402 BALANCE_REQUIRED). "
                                "Top up the Lium account to rent an RTX 5080 pod."
                            )
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

    async def _discover_existing_pod(self, settings) -> Optional[str]:
        """Best-effort discovery of an already-rented pod managed by this project.

        Lists the account's pods, matches the pod-name prefix, and derives the
        inference endpoint from the pod's ports_mapping + SSH host. Returns None
        (never raises) when the pod cannot be found or the API call fails.
        """
        if not settings.has_lium:
            return None
        base = settings.lium_api_base.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{base}/pods", headers={"X-API-Key": settings.lium_api_key})
                if resp.status_code == 402:
                    log.warning("lium_discovery_blocked_balance_required")
                    return None
                if resp.status_code != 200:
                    log.warning("lium_discovery_failed", status=resp.status_code)
                    return None
                pods = resp.json()
                if isinstance(pods, dict):
                    pods = pods.get("pods") or pods.get("data") or []
                prefix = settings.lium_pod_name_prefix or ""
                for pod in pods if isinstance(pods, list) else []:
                    name = str(pod.get("pod_name") or pod.get("name") or "")
                    if prefix and not name.startswith(prefix):
                        continue
                    state = pod.get("status") or pod.get("state")
                    if not _is_pod_running(state):
                        continue
                    endpoint = _pod_public_endpoint(pod, settings)
                    if not endpoint:
                        continue
                    headers = {}
                    if settings.inference_api_key:
                        headers["X-Inference-Key"] = settings.inference_api_key
                    try:
                        probe = await client.get(f"{endpoint}/health", headers=headers, timeout=5.0)
                        if probe.status_code == 200:
                            log.info("lium_existing_pod_discovered", pod_name=name, endpoint=endpoint)
                            return endpoint
                    except Exception:
                        continue
        except Exception as exc:
            log.debug("lium_discovery_error", error=str(exc))
        return None

    async def _wait_for_pod_healthy(self, settings) -> str:
        """Poll the pod status and try-on health endpoint until healthy or timeout."""
        timeout = settings.gpu_startup_timeout_seconds
        start_t = time.time()
        headers = {"X-API-Key": settings.lium_api_key}

        while (time.time() - start_t) < timeout:
            await asyncio.sleep(5)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{settings.lium_api_base.rstrip('/')}/pods/{self.pod_id}",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        pod_info = resp.json()
                        if _is_pod_running(pod_info.get("status") or pod_info.get("state")):
                            endpoint = _pod_public_endpoint(pod_info, settings)
                            if endpoint:
                                try:
                                    h_resp = await client.get(f"{endpoint}/health", timeout=3.0)
                                    if h_resp.status_code == 200:
                                        return endpoint
                                except Exception:
                                    pass
                    elif resp.status_code == 402:
                        raise GpuError(
                            "Lium account has insufficient balance (HTTP 402). "
                            "Top up the Lium account or set INFERENCE_BASE_URL to a running pod."
                        )
            except GpuError:
                raise
            except Exception as e:
                log.debug("polling_pod_status_retry", error=str(e))

        raise GpuError(f"GPU pod startup timed out after {timeout} seconds.")

    async def stop_gpu(self, reason: str = "manual") -> None:
        """Shut down or sleep the GPU instance if no active requests are executing."""
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

            # If fixed inference endpoint: send sleep signal to clear VRAM and enter standby
            if settings.using_fixed_inference and not self.mock_mode and self._inference_endpoint:
                try:
                    headers = {}
                    if settings.inference_api_key:
                        headers["X-Inference-Key"] = settings.inference_api_key
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(f"{self._inference_endpoint}/sleep", headers=headers)
                except Exception as exc:
                    log.warning("gpu_sleep_notification_failed", error=str(exc))

                self.status = "stopped"
                self._inference_endpoint = None
                await self._record_stop(duration_seconds, cost)
                return

            # If mock mode
            if self.mock_mode or not self.pod_id:
                self.status = "stopped"
                self._inference_endpoint = None
                await self._record_stop(duration_seconds, cost)
                return

            # Dynamic Lium pod termination
            try:
                headers = {"X-API-Key": settings.lium_api_key}
                async with httpx.AsyncClient(timeout=20.0) as client:
                    await client.delete(
                        f"{settings.lium_api_base.rstrip('/')}/pods/{self.pod_id}",
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
