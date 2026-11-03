"""Live Supabase integration tests using configured credentials."""

import pytest
from backend.app.config import get_settings
from backend.app.db.store import build_supabase_store


@pytest.mark.asyncio
async def test_live_supabase_store_connection():
    settings = get_settings()
    if not settings.has_supabase:
        pytest.skip("Supabase credentials not configured in environment")

    store = await build_supabase_store()
    # 1. Ping database
    is_alive = await store.ping()
    assert is_alive is True, "Supabase database ping failed"

    # 2. Query real dashboard stats RPC
    stats = await store.dashboard_stats(window_hours=24)
    assert isinstance(stats, dict)
    assert "total_customers" in stats
    assert "successful_tryons" in stats
    assert "failed_tryons" in stats
    assert "free_tries_consumed" in stats
