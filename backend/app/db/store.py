"""Store abstraction.

``Store`` is the single seam between the API layer and Supabase.  Every method
is async and returns plain dictionaries so tests can substitute
``app.db.memory.MemoryStore`` without a network round-trip.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Protocol

from ..config import get_settings
from ..logging_config import get_logger

log = get_logger("db")

_store: Optional["Store"] = None
_lock = threading.Lock()


class Store(Protocol):
    """Persistence operations used by the API."""

    # -- identity ---------------------------------------------------------
    async def resolve_customer(
        self,
        *,
        identity_key: str,
        identity_type: str,
        shopify_customer_id: Optional[str] = None,
        email: Optional[str] = None,
        session_id: Optional[str] = None,
        email_verified: bool = False,
    ) -> Dict[str, Any]: ...

    async def touch_customer(self, customer_id: str) -> None: ...

    # -- quota ------------------------------------------------------------
    async def get_usage(self, customer_id: str) -> Dict[str, Any]: ...

    async def reserve_try_on(
        self, *, request_id: str, customer_id: str, idempotency_key: Optional[str], **context: Any
    ) -> Dict[str, Any]: ...

    async def finalize_try_on(
        self,
        *,
        request_id: str,
        status: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        result_ref: Optional[str] = None,
    ) -> Dict[str, Any]: ...

    # -- idempotency ------------------------------------------------------
    async def get_idempotent_response(self, key: str) -> Optional[Dict[str, Any]]: ...

    async def put_idempotent_response(
        self, key: str, request_id: str, status_code: int, payload: Dict[str, Any]
    ) -> None: ...

    # -- gpu --------------------------------------------------------------
    async def record_gpu_session(
        self,
        *,
        pod_id: Optional[str],
        pod_name: Optional[str],
        gpu_model: Optional[str],
        price_per_hour: Optional[float],
        status: str,
        started_at: Optional[str] = None,
        stopped_at: Optional[str] = None,
        runtime_seconds: Optional[int] = None,
        estimated_cost_usd: float = 0.0,
        reported_spend_usd: Optional[float] = None,
        error_message: Optional[str] = None,
        provider: str = "lium",
    ) -> Dict[str, Any]: ...

    async def update_gpu_session(
        self, session_id: str, **fields: Any
    ) -> Dict[str, Any]: ...

    async def list_gpu_sessions(self, limit: int = 50) -> List[Dict[str, Any]]: ...

    async def gpu_spend_since(self, since_iso: str) -> float: ...

    # -- admin ------------------------------------------------------------
    async def create_admin(self, username: str, password_hash: str, role: str = "admin") -> Dict[str, Any]: ...

    async def get_admin(self, username: str) -> Optional[Dict[str, Any]]: ...

    async def count_admins(self) -> int: ...

    async def set_admin_password(self, username: str, password_hash: str) -> None: ...

    async def touch_admin_login(self, username: str) -> None: ...

    async def dashboard_stats(self, window_hours: int = 24) -> Dict[str, Any]: ...

    async def daily_usage(self, days: int = 30) -> List[Dict[str, Any]]: ...

    async def product_usage(self, days: int = 30) -> List[Dict[str, Any]]: ...

    async def customer_list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        window_hours: int = 24,
        limit_tries: int = 2,
    ) -> List[Dict[str, Any]]: ...

    async def recent_activity(self, limit: int = 25) -> List[Dict[str, Any]]: ...

    async def ping(self) -> bool: ...


class SupabaseStore:
    """Store backed by the Supabase PostgREST API using the secret key."""

    def __init__(self, client: Any) -> None:
        self._client = client

    # -- helpers ----------------------------------------------------------
    async def _rpc(self, name: str, params: Dict[str, Any]) -> Any:
        response = await self._client.rpc(name, params).execute()
        return response.data

    # -- identity ---------------------------------------------------------
    async def resolve_customer(self, **kwargs: Any) -> Dict[str, Any]:
        data = await self._rpc(
            "tryvtri_resolve_customer",
            {
                "p_identity_key": kwargs["identity_key"],
                "p_identity_type": kwargs["identity_type"],
                "p_shopify_customer_id": kwargs.get("shopify_customer_id"),
                "p_email": kwargs.get("email"),
                "p_session_id": kwargs.get("session_id"),
                "p_email_verified": bool(kwargs.get("email_verified", False)),
            },
        )
        if not isinstance(data, dict) or not data.get("id"):
            raise RuntimeError("customer resolution returned no row")
        return data

    async def touch_customer(self, customer_id: str) -> None:
        await (
            self._client.table("customers")
            .update({"last_activity_at": "now()"})
            .eq("id", customer_id)
            .execute()
        )

    # -- quota ------------------------------------------------------------
    async def get_usage(self, customer_id: str) -> Dict[str, Any]:
        settings = get_settings()
        return await self._rpc(
            "tryvtri_get_usage",
            {
                "p_customer_id": customer_id,
                "p_window_hours": settings.quota_window_hours,
                "p_limit": settings.free_tries_per_day,
            },
        )

    async def reserve_try_on(
        self, *, request_id: str, customer_id: str, idempotency_key: Optional[str], **context: Any
    ) -> Dict[str, Any]:
        settings = get_settings()
        return await self._rpc(
            "tryvtri_reserve_try_on",
            {
                "p_request_id": request_id,
                "p_customer_id": customer_id,
                "p_idempotency_key": idempotency_key,
                "p_window_hours": settings.quota_window_hours,
                "p_limit": settings.free_tries_per_day,
                "p_product_id": context.get("product_id"),
                "p_variant_id": context.get("variant_id"),
                "p_product_title": context.get("product_title"),
                "p_garment_category": context.get("garment_category"),
                "p_garment_url": context.get("garment_url"),
            },
        )

    async def finalize_try_on(
        self,
        *,
        request_id: str,
        status: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        result_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._rpc(
            "tryvtri_finalize_try_on",
            {
                "p_request_id": request_id,
                "p_status": status,
                "p_error_code": error_code,
                "p_error_message": error_message,
                "p_duration_ms": duration_ms,
                "p_result_ref": result_ref,
            },
        )

    # -- idempotency ------------------------------------------------------
    async def get_idempotent_response(self, key: str) -> Optional[Dict[str, Any]]:
        rows = (
            await (
                self._client.table("api_idempotency")
                .select("*")
                .eq("key", key)
                .gte("expires_at", "now()")
                .limit(1)
                .execute()
            ).data
            or []
        )
        return rows[0] if rows else None

    async def put_idempotent_response(
        self, key: str, request_id: str, status_code: int, payload: Dict[str, Any]
    ) -> None:
        try:
            await (
                self._client.table("api_idempotency")
                .upsert(
                    {
                        "key": key,
                        "request_id": request_id,
                        "status_code": status_code,
                        "response_json": payload,
                    },
                    on_conflict="key",
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — never fail the response over bookkeeping
            log.warning("idempotency_store_failed", error=str(exc))

    # -- gpu --------------------------------------------------------------
    async def record_gpu_session(self, **fields: Any) -> Dict[str, Any]:
        row = await (
            self._client.table("gpu_usage")
            .insert(fields)
            .execute()
        )
        data = row.data or []
        return data[0] if data else fields

    async def update_gpu_session(self, session_id: str, **fields: Any) -> Dict[str, Any]:
        res = await (
            self._client.table("gpu_usage")
            .update(fields)
            .eq("id", session_id)
            .execute()
        )
        data = res.data or []
        return data[0] if data else {"id": session_id, **fields}

    async def list_gpu_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        res = await (
            self._client.table("gpu_usage")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    async def gpu_spend_since(self, since_iso: str) -> float:
        rows = (
            await (
                self._client.table("gpu_usage")
                .select("estimated_cost_usd")
                .gte("created_at", since_iso)
                .execute()
            ).data
            or []
        )
        return float(sum(float(r.get("estimated_cost_usd") or 0) for r in rows))

    # -- admin ------------------------------------------------------------
    async def create_admin(self, username: str, password_hash: str, role: str = "admin") -> Dict[str, Any]:
        res = await (
            self._client.table("admin_users")
            .insert(
                {"username": username, "password_hash": password_hash, "role": role}
            )
            .execute()
        )
        data = res.data or []
        return data[0] if data else {"username": username, "role": role}

    async def get_admin(self, username: str) -> Optional[Dict[str, Any]]:
        res = await (
            self._client.table("admin_users")
            .select("*")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    async def count_admins(self) -> int:
        res = await (
            self._client.table("admin_users").select("id", count="exact").limit(1).execute()
        )
        return int(res.count or 0)

    async def set_admin_password(self, username: str, password_hash: str) -> None:
        await (
            self._client.table("admin_users")
            .update({"password_hash": password_hash})
            .eq("username", username)
            .execute()
        )

    async def touch_admin_login(self, username: str) -> None:
        from datetime import datetime, timezone

        await (
            self._client.table("admin_users")
            .update({"last_login_at": datetime.now(timezone.utc).isoformat()})
            .eq("username", username)
            .execute()
        )

    # -- analytics --------------------------------------------------------
    async def dashboard_stats(self, window_hours: int = 24) -> Dict[str, Any]:
        return await self._rpc("tryvtri_dashboard_stats", {"p_window_hours": window_hours})

    async def daily_usage(self, days: int = 30) -> List[Dict[str, Any]]:
        return await self._rpc("tryvtri_daily_usage", {"p_days": days}) or []

    async def product_usage(self, days: int = 30) -> List[Dict[str, Any]]:
        return await self._rpc("tryvtri_product_usage", {"p_days": days}) or []

    async def customer_list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        window_hours: int = 24,
        limit_tries: int = 2,
    ) -> List[Dict[str, Any]]:
        return (
            await self._rpc(
                "tryvtri_customer_list",
                {
                    "p_limit": limit,
                    "p_offset": offset,
                    "p_search": search,
                    "p_window_hours": window_hours,
                    "p_limit_tries": limit_tries,
                },
            )
            or []
        )

    async def recent_activity(self, limit: int = 25) -> List[Dict[str, Any]]:
        return await self._rpc("tryvtri_recent_activity", {"p_limit": limit}) or []

    async def ping(self) -> bool:
        try:
            await self._client.table("customers").select("id").limit(1).execute()
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("supabase_ping_failed", error=str(exc))
            return False


async def build_supabase_store() -> SupabaseStore:
    settings = get_settings()
    if not settings.has_supabase:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SECRET_KEY are not configured. "
            "Copy .env.example to .env and fill them in."
        )
    from supabase import AClient

    client = await AClient.create(settings.supabase_url, settings.supabase_secret_key)
    return SupabaseStore(client)


def get_store() -> Store:
    global _store
    if _store is None:
        raise RuntimeError("store has not been initialised")
    return _store


def set_store(store: Optional[Store]) -> None:
    """Dependency-injection hook used by the app factory and the test suite."""
    global _store
    with _lock:
        _store = store
