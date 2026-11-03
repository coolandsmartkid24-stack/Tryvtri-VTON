"""In-memory ``Store`` used by the test-suite.

It reproduces the *semantics* of the SQL functions in
``migrations/0002_functions.sql`` — including the customer row lock (via a
per-customer ``asyncio.Lock``), the rolling window, in-flight reservations and
idempotent replays — so quota tests exercise the same rules that run in
production without needing a live Supabase project.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class MemoryStore:
    def __init__(
        self,
        *,
        limit: int = 2,
        window_hours: int = 24,
        pending_ttl_minutes: int = 15,
    ) -> None:
        self.limit = limit
        self.window_hours = window_hours
        self.pending_ttl = timedelta(minutes=pending_ttl_minutes)

        self.customers: Dict[str, Dict[str, Any]] = {}
        self.usage: List[Dict[str, Any]] = []
        self.gpu_sessions: List[Dict[str, Any]] = []
        self.admins: Dict[str, Dict[str, Any]] = {}
        self.idempotency: Dict[str, Dict[str, Any]] = {}

        self._locks: Dict[str, asyncio.Lock] = {}

    # ----------------------------------------------------------- internals --
    def _lock_for(self, customer_id: str) -> asyncio.Lock:
        if customer_id not in self._locks:
            self._locks[customer_id] = asyncio.Lock()
        return self._locks[customer_id]

    def _window_start(self) -> datetime:
        return _now() - timedelta(hours=self.window_hours)

    def _successes_in_window(self, customer_id: str) -> List[Dict[str, Any]]:
        start = self._window_start()
        return [
            u
            for u in self.usage
            if u["customer_id"] == customer_id
            and u["status"] == "success"
            and u["created_at"] >= start
        ]

    def _fresh_pending(self, customer_id: str) -> List[Dict[str, Any]]:
        cutoff = _now() - self.pending_ttl
        return [
            u
            for u in self.usage
            if u["customer_id"] == customer_id
            and u["status"] == "pending"
            and u["created_at"] >= cutoff
        ]

    def _expire_stale(self, customer_id: str) -> None:
        cutoff = _now() - self.pending_ttl
        for u in self.usage:
            if (
                u["customer_id"] == customer_id
                and u["status"] == "pending"
                and u["created_at"] < cutoff
            ):
                u["status"] = "failed"
                u["error_code"] = "reservation_expired"
                u["finished_at"] = _now()

    def _usage_payload(self, customer_id: str) -> Dict[str, Any]:
        successes = self._successes_in_window(customer_id)
        pending = self._fresh_pending(customer_id)
        used = len(successes)
        reset_at = None
        if used >= self.limit and successes:
            oldest = min(u["created_at"] for u in successes)
            reset_at = _iso(oldest + timedelta(hours=self.window_hours))
        return {
            "customer_id": customer_id,
            "limit": self.limit,
            "window_hours": self.window_hours,
            "used": used,
            "remaining": max(self.limit - used, 0),
            "in_flight": len(pending),
            "eligible": (used + len(pending)) < self.limit,
            "reset_at": reset_at,
        }

    # ------------------------------------------------------------- identity --
    async def resolve_customer(
        self,
        *,
        identity_key: str,
        identity_type: str,
        shopify_customer_id: Optional[str] = None,
        email: Optional[str] = None,
        session_id: Optional[str] = None,
        email_verified: bool = False,
    ) -> Dict[str, Any]:
        existing = next(
            (c for c in self.customers.values() if c["identity_key"] == identity_key), None
        )
        if existing:
            existing["last_activity_at"] = _now()
            if email:
                existing["email"] = email
            if shopify_customer_id:
                existing["shopify_customer_id"] = shopify_customer_id
            existing["email_verified"] = existing["email_verified"] or email_verified
            if session_id:
                existing["session_id"] = session_id
            return dict(existing)

        if session_id:
            holder = next(
                (c for c in self.customers.values() if c.get("session_id") == session_id), None
            )
            if holder and holder["identity_key"] != identity_key:
                holder["identity_key"] = identity_key
                holder["identity_type"] = identity_type
                holder["shopify_customer_id"] = shopify_customer_id or holder["shopify_customer_id"]
                holder["email"] = email or holder["email"]
                holder["email_verified"] = holder["email_verified"] or email_verified
                holder["last_activity_at"] = _now()
                return dict(holder)

        row = {
            "id": str(uuid.uuid4()),
            "identity_key": identity_key,
            "identity_type": identity_type,
            "shopify_customer_id": shopify_customer_id,
            "email": email,
            "email_verified": email_verified,
            "session_id": session_id,
            "created_at": _now(),
            "last_activity_at": _now(),
        }
        self.customers[row["id"]] = row
        return dict(row)

    async def touch_customer(self, customer_id: str) -> None:
        if customer_id in self.customers:
            self.customers[customer_id]["last_activity_at"] = _now()

    # --------------------------------------------------------------- quota --
    async def get_usage(self, customer_id: str) -> Dict[str, Any]:
        async with self._lock_for(customer_id):
            return self._usage_payload(customer_id)

    async def reserve_try_on(
        self, *, request_id: str, customer_id: str, idempotency_key: Optional[str], **context: Any
    ) -> Dict[str, Any]:
        async with self._lock_for(customer_id):
            dup = next((u for u in self.usage if u["request_id"] == request_id), None)
            if dup:
                snapshot = self._usage_payload(customer_id)
                return {
                    "allowed": dup["status"] != "failed",
                    "duplicate": True,
                    "status": dup["status"],
                    "usage_id": dup["id"],
                    "used": snapshot["used"],
                    "remaining": snapshot["remaining"],
                    "in_flight": snapshot["in_flight"],
                    "reset_at": snapshot["reset_at"],
                    "reason": None,
                }

            self._expire_stale(customer_id)
            successes = self._successes_in_window(customer_id)
            pending = self._fresh_pending(customer_id)
            used = len(successes)

            if used + len(pending) >= self.limit:
                reset = None
                if successes:
                    oldest = min(u["created_at"] for u in successes)
                    reset = _iso(oldest + timedelta(hours=self.window_hours))
                else:
                    reset = _iso(_now() + timedelta(hours=self.window_hours))
                return {
                    "allowed": False,
                    "duplicate": False,
                    "status": "denied",
                    "usage_id": None,
                    "used": used,
                    "remaining": max(self.limit - used, 0),
                    "in_flight": len(pending),
                    "reset_at": reset,
                    "reason": "quota_exceeded",
                }

            row = {
                "id": str(uuid.uuid4()),
                "request_id": request_id,
                "idempotency_key": idempotency_key,
                "customer_id": customer_id,
                "product_id": context.get("product_id"),
                "variant_id": context.get("variant_id"),
                "product_title": context.get("product_title"),
                "garment_category": context.get("garment_category"),
                "garment_url": context.get("garment_url"),
                "status": "pending",
                "error_code": None,
                "error_message": None,
                "duration_ms": None,
                "result_ref": None,
                "created_at": _now(),
                "finished_at": None,
            }
            self.usage.append(row)
            return {
                "allowed": True,
                "duplicate": False,
                "status": "pending",
                "usage_id": row["id"],
                "used": used,
                "remaining": max(self.limit - used - 1, 0),
                "in_flight": len(pending),
                "reset_at": None,
                "reason": None,
            }

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
        row = next((u for u in self.usage if u["request_id"] == request_id), None)
        if row is None:
            return {"ok": False, "reason": "unknown_request"}
        if row["status"] != "pending":
            return {
                "ok": False,
                "reason": "already_finalised",
                "status": row["status"],
                "customer_id": row["customer_id"],
            }

        async with self._lock_for(row["customer_id"]):
            row["status"] = status
            row["error_code"] = error_code
            row["error_message"] = (error_message or "")[:1000] or None
            row["duration_ms"] = duration_ms
            row["result_ref"] = result_ref
            row["finished_at"] = _now()
            snapshot = self._usage_payload(row["customer_id"])

        return {
            "ok": True,
            "status": status,
            "customer_id": row["customer_id"],
            "used": snapshot["used"],
            "remaining": snapshot["remaining"],
            "reset_at": snapshot["reset_at"],
        }

    # --------------------------------------------------------- idempotency --
    async def get_idempotent_response(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.idempotency.get(key)
        if not row or row["expires_at"] < _now():
            return None
        return dict(row)

    async def put_idempotent_response(
        self, key: str, request_id: str, status_code: int, payload: Dict[str, Any]
    ) -> None:
        self.idempotency[key] = {
            "key": key,
            "request_id": request_id,
            "status_code": status_code,
            "response_json": payload,
            "expires_at": _now() + timedelta(hours=24),
        }

    # ----------------------------------------------------------------- gpu --
    async def record_gpu_session(self, **fields: Any) -> Dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "provider": fields.get("provider", "lium"),
            "pod_id": fields.get("pod_id"),
            "pod_name": fields.get("pod_name"),
            "gpu_model": fields.get("gpu_model"),
            "price_per_hour": fields.get("price_per_hour"),
            "status": fields.get("status", "starting"),
            "started_at": fields.get("started_at"),
            "stopped_at": fields.get("stopped_at"),
            "runtime_seconds": fields.get("runtime_seconds"),
            "estimated_cost_usd": fields.get("estimated_cost_usd", 0),
            "reported_spend_usd": fields.get("reported_spend_usd"),
            "error_message": fields.get("error_message"),
        }
        self.gpu_sessions.append(row)
        return dict(row)

    async def update_gpu_session(self, session_id: str, **fields: Any) -> Dict[str, Any]:
        for row in self.gpu_sessions:
            if row["id"] == session_id:
                row.update(fields)
                return dict(row)
        return {"id": session_id, **fields}

    async def list_gpu_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in reversed(self.gpu_sessions[-limit:])]

    async def gpu_spend_since(self, since_iso: str) -> float:
        since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        return float(
            sum(
                float(r.get("estimated_cost_usd") or 0)
                for r in self.gpu_sessions
                if r.get("started_at")
                and datetime.fromisoformat(str(r["started_at"]).replace("Z", "+00:00")) >= since
            )
        )

    # --------------------------------------------------------------- admin --
    async def create_admin(self, username: str, password_hash: str, role: str = "admin") -> Dict[str, Any]:
        self.admins[username] = {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": _now(),
            "last_login_at": None,
        }
        return dict(self.admins[username])

    async def get_admin(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.admins.get(username)
        return dict(row) if row else None

    async def count_admins(self) -> int:
        return len(self.admins)

    async def set_admin_password(self, username: str, password_hash: str) -> None:
        if username in self.admins:
            self.admins[username]["password_hash"] = password_hash

    async def touch_admin_login(self, username: str) -> None:
        if username in self.admins:
            self.admins[username]["last_login_at"] = _now()

    # ----------------------------------------------------------- analytics --
    async def dashboard_stats(self, window_hours: int = 24) -> Dict[str, Any]:
        start = _now() - timedelta(hours=window_hours)
        successes = [u for u in self.usage if u["status"] == "success"]
        failed = [u for u in self.usage if u["status"] == "failed"]
        pending = [u for u in self.usage if u["status"] == "pending"]

        per_customer: Dict[str, int] = {}
        for u in successes:
            if u["created_at"] >= start:
                per_customer[u["customer_id"]] = per_customer.get(u["customer_id"], 0) + 1
        exhausted = sum(1 for v in per_customer.values() if v >= 2)

        return {
            "total_customers": len(self.customers),
            "demo_customers": len({u["customer_id"] for u in successes}),
            "successful_tryons": len(successes),
            "failed_tryons": len(failed),
            "pending_tryons": len(pending),
            "free_tries_consumed": len(successes),
            "exhausted_customers": exhausted,
            "eligible_customers": max(len(self.customers) - exhausted, 0),
            "success_last_window": sum(1 for u in successes if u["created_at"] >= start),
            "window_hours": window_hours,
            "gpu_sessions": len(self.gpu_sessions),
            "gpu_runtime_seconds": sum(int(r.get("runtime_seconds") or 0) for r in self.gpu_sessions),
            "gpu_estimated_cost_usd": round(
                sum(float(r.get("estimated_cost_usd") or 0) for r in self.gpu_sessions), 4
            ),
        }

    async def daily_usage(self, days: int = 30) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, int]] = {}
        cutoff = _now() - timedelta(days=days)
        for u in self.usage:
            if u["created_at"] < cutoff:
                continue
            day = u["created_at"].strftime("%Y-%m-%d")
            b = buckets.setdefault(day, {"day": day, "total": 0, "success": 0, "failed": 0})
            b["total"] += 1
            if u["status"] == "success":
                b["success"] += 1
            elif u["status"] == "failed":
                b["failed"] += 1
        return [buckets[k] for k in sorted(buckets)]

    async def product_usage(self, days: int = 30) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        cutoff = _now() - timedelta(days=days)
        for u in self.usage:
            if u["created_at"] < cutoff or not u.get("product_id"):
                continue
            b = buckets.setdefault(
                u["product_id"],
                {
                    "product_id": u["product_id"],
                    "product_title": u.get("product_title"),
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                },
            )
            b["total"] += 1
            if u["status"] == "success":
                b["success"] += 1
            elif u["status"] == "failed":
                b["failed"] += 1
        return sorted(buckets.values(), key=lambda r: r["total"], reverse=True)[:50]

    async def customer_list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        window_hours: int = 24,
        limit_tries: int = 2,
    ) -> List[Dict[str, Any]]:
        start = _now() - timedelta(hours=window_hours)
        out: List[Dict[str, Any]] = []
        for c in self.customers.values():
            if search:
                hay = f"{c.get('email') or ''} {c.get('shopify_customer_id') or ''} {c['identity_key']}"
                if search.lower() not in hay.lower():
                    continue
            rows = [u for u in self.usage if u["customer_id"] == c["id"]]
            ok = [u for u in rows if u["status"] == "success"]
            bad = [u for u in rows if u["status"] == "failed"]
            in_window = [u for u in ok if u["created_at"] >= start]
            used = len(in_window)
            oldest = min((u["created_at"] for u in in_window), default=None)
            out.append(
                {
                    "customer_id": c["id"],
                    "identity_type": c["identity_type"],
                    "email": c.get("email"),
                    "shopify_customer_id": c.get("shopify_customer_id"),
                    "email_verified": c.get("email_verified", False),
                    "created_at": _iso(c["created_at"]),
                    "last_activity_at": _iso(c["last_activity_at"]),
                    "successful_tryons": len(ok),
                    "failed_tryons": len(bad),
                    "remaining_tries": max(limit_tries - used, 0),
                    "last_tryon_at": _iso(max((u["created_at"] for u in ok), default=None))
                    if ok
                    else None,
                    "next_eligible_at": _iso(oldest + timedelta(hours=window_hours))
                    if (used >= limit_tries and oldest)
                    else None,
                    "quota_exhausted": used >= limit_tries,
                }
            )
        out.sort(key=lambda r: r["last_activity_at"], reverse=True)
        return out[offset : offset + limit]

    async def recent_activity(self, limit: int = 25) -> List[Dict[str, Any]]:
        rows = sorted(self.usage, key=lambda u: u["created_at"], reverse=True)[:limit]
        out = []
        for u in rows:
            c = self.customers.get(u["customer_id"], {})
            out.append(
                {
                    "request_id": u["request_id"],
                    "customer_id": u["customer_id"],
                    "email": c.get("email"),
                    "product_id": u.get("product_id"),
                    "product_title": u.get("product_title"),
                    "status": u["status"],
                    "error_code": u.get("error_code"),
                    "duration_ms": u.get("duration_ms"),
                    "created_at": _iso(u["created_at"]),
                }
            )
        return out

    async def ping(self) -> bool:
        return True
