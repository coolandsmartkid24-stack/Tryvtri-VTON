"""Tests for Customer Quota and Atomic Limit Enforcement."""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from backend.app.db.memory import MemoryStore


@pytest.fixture
def store():
    return MemoryStore(limit=2, window_hours=24)


@pytest.mark.asyncio
async def test_quota_allows_two_successful_tryons(store):
    customer = await store.resolve_customer(
        identity_key="email:shopper@example.com",
        identity_type="email",
        email="shopper@example.com",
    )
    cid = customer["id"]

    # Try 1: Reserve & Finalize Success
    res1 = await store.reserve_try_on(request_id="req-1", customer_id=cid, idempotency_key=None)
    assert res1["allowed"] is True
    await store.finalize_try_on(request_id="req-1", status="success", duration_ms=1200)

    # Check usage: 1 used, 1 remaining
    u1 = await store.get_usage(cid)
    assert u1["used"] == 1
    assert u1["remaining"] == 1
    assert u1["eligible"] is True

    # Try 2: Reserve & Finalize Success
    res2 = await store.reserve_try_on(request_id="req-2", customer_id=cid, idempotency_key=None)
    assert res2["allowed"] is True
    await store.finalize_try_on(request_id="req-2", status="success", duration_ms=1300)

    # Check usage: 2 used, 0 remaining
    u2 = await store.get_usage(cid)
    assert u2["used"] == 2
    assert u2["remaining"] == 0
    assert u2["eligible"] is False
    assert u2["reset_at"] is not None

    # Try 3: Reserve Denied (quota reached)
    res3 = await store.reserve_try_on(request_id="req-3", customer_id=cid, idempotency_key=None)
    assert res3["allowed"] is False
    assert res3["status"] == "denied"
    assert res3["remaining"] == 0


@pytest.mark.asyncio
async def test_failed_generations_do_not_consume_quota(store):
    customer = await store.resolve_customer(
        identity_key="shopify:cust_987",
        identity_type="shopify",
        shopify_customer_id="cust_987",
    )
    cid = customer["id"]

    # Attempt 1: Failed inference
    res1 = await store.reserve_try_on(request_id="req-fail-1", customer_id=cid, idempotency_key=None)
    assert res1["allowed"] is True
    await store.finalize_try_on(
        request_id="req-fail-1",
        status="failed",
        error_code="inference_error",
        error_message="GPU out of memory",
    )

    # Quota should still be 0 used, 2 remaining!
    u1 = await store.get_usage(cid)
    assert u1["used"] == 0
    assert u1["remaining"] == 2
    assert u1["eligible"] is True

    # Attempt 2: Another failure
    res2 = await store.reserve_try_on(request_id="req-fail-2", customer_id=cid, idempotency_key=None)
    assert res2["allowed"] is True
    await store.finalize_try_on(
        request_id="req-fail-2",
        status="failed",
        error_code="invalid_image",
    )

    u2 = await store.get_usage(cid)
    assert u2["used"] == 0
    assert u2["remaining"] == 2

    # Now 2 successes still allowed
    s1 = await store.reserve_try_on(request_id="req-ok-1", customer_id=cid, idempotency_key=None)
    assert s1["allowed"] is True
    await store.finalize_try_on(request_id="req-ok-1", status="success")

    s2 = await store.reserve_try_on(request_id="req-ok-2", customer_id=cid, idempotency_key=None)
    assert s2["allowed"] is True
    await store.finalize_try_on(request_id="req-ok-2", status="success")

    u3 = await store.get_usage(cid)
    assert u3["used"] == 2
    assert u3["remaining"] == 0


@pytest.mark.asyncio
async def test_concurrent_reservations_race_protection(store):
    customer = await store.resolve_customer(
        identity_key="session:sess_race_123",
        identity_type="session",
        session_id="sess_race_123",
    )
    cid = customer["id"]

    # Fire 5 parallel reservation requests simultaneously
    tasks = [
        store.reserve_try_on(request_id=f"race-{i}", customer_id=cid, idempotency_key=None)
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks)

    allowed_count = sum(1 for r in results if r.get("allowed") is True)
    denied_count = sum(1 for r in results if r.get("allowed") is False)

    # Exactly 2 must be allowed and 3 denied
    assert allowed_count == 2
    assert denied_count == 3


@pytest.mark.asyncio
async def test_idempotent_retry_returns_original_response(store):
    idem_key = "idem-test-token-12345"
    await store.put_idempotent_response(
        key=idem_key,
        request_id="req-original",
        status_code=200,
        payload={"success": True, "output_url": "data:image/png;base64,abc"},
    )

    cached = await store.get_idempotent_response(idem_key)
    assert cached is not None
    assert cached["request_id"] == "req-original"
    assert cached["status_code"] == 200
    assert cached["response_json"]["success"] is True
