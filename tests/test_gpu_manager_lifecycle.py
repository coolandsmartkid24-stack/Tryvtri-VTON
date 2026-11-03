"""Tests for Lium GPU Lifecycle Management and Cost Tracking."""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from backend.app.services.gpu_manager import GpuManager


@pytest.mark.asyncio
async def test_gpu_manager_lease_starts_and_tracks_concurrency():
    mgr = GpuManager()
    mgr.mock_mode = True

    assert mgr.status == "stopped"
    assert mgr.active_requests == 0
    assert mgr.queued_requests == 0

    # Acquire lease
    async with mgr.lease() as endpoint:
        assert mgr.status == "running"
        assert mgr.active_requests == 1
        assert "http" in endpoint

    # Released
    assert mgr.active_requests == 0
    assert mgr.status == "running"  # Still running until idle timeout or manual stop


@pytest.mark.asyncio
async def test_gpu_manager_refuses_to_stop_while_active_request_running():
    mgr = GpuManager()
    mgr.mock_mode = True

    async with mgr.lease():
        assert mgr.active_requests == 1
        # Try to stop GPU while request running
        await mgr.stop_gpu(reason="test")
        # Status MUST remain running!
        assert mgr.status == "running"

    # Now that active_requests == 0, stop is permitted
    assert mgr.active_requests == 0
    await mgr.stop_gpu(reason="test_after_release")
    assert mgr.status == "stopped"


@pytest.mark.asyncio
async def test_gpu_manager_cost_and_runtime_calculation():
    mgr = GpuManager()
    mgr.mock_mode = True
    mgr.price_per_hour = 0.36  # RTX 5080 rate

    await mgr.start_gpu()
    assert mgr.status == "running"
    assert mgr.started_at is not None

    # Simulate 1 hour (3600 seconds) elapsed
    mgr.started_at = datetime.now(timezone.utc) - timedelta(seconds=3600)

    # Check status payload
    payload = mgr.get_status_payload()
    assert payload["current_session_runtime_seconds"] >= 3600
    assert payload["current_session_cost_usd"] >= 0.36

    # Stop and verify accumulated cost
    await mgr.stop_gpu(reason="runtime_test")
    assert mgr.status == "stopped"
    assert mgr.total_runtime_seconds >= 3600
    assert mgr.total_estimated_cost_usd >= 0.36


@pytest.mark.asyncio
async def test_gpu_concurrency_lock_prevents_duplicate_instances():
    mgr = GpuManager()
    mgr.mock_mode = True

    # Run two leases concurrently
    async def worker():
        async with mgr.lease() as ep:
            await asyncio.sleep(0.05)
            return ep

    results = await asyncio.gather(worker(), worker())
    # Both workers should have received the SAME endpoint
    assert results[0] == results[1]
    assert mgr.pod_id is not None
