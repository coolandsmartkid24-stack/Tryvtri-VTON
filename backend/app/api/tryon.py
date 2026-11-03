"""Storefront virtual try-on API routes.

Zero Shopify Credentials Requirement:
- No Shopify API key, admin token, or OAuth required.
- Storefront Liquid and widget code supplies product context directly.
- Garment images downloaded securely from public CDN with SSRF protection.
"""

from __future__ import annotations

import base64
import time
from typing import Optional

from fastapi import APIRouter, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..core.errors import ImageRejected, QuotaExceeded, ValidationError
from ..core.request_ids import new_request_id, normalise_idempotency_key
from ..db.store import get_store
from ..logging_config import get_logger
from ..schemas.tryon import (
    CheckUsageResponse,
    ProductContextResponse,
    TryOnQuotaInfo,
    TryOnResponse,
)
from ..services.gpu_manager import get_gpu_manager
from ..services.image_service import (
    download_garment_image,
    sanitize_image_bytes,
    validate_image_url,
    validate_person_upload,
)
from ..services.inference_client import run_vton_inference, validate_category

router = APIRouter(tags=["Storefront Try-On"])
log = get_logger("api.tryon")


def _resolve_identity(
    shopify_customer_id: Optional[str],
    email: Optional[str],
    session_id: Optional[str],
) -> tuple[str, str]:
    """Determine the strongest identity key and type."""
    if shopify_customer_id and shopify_customer_id.strip():
        return f"shopify:{shopify_customer_id.strip()}", "shopify"
    if email and email.strip():
        return f"email:{email.strip().lower()}", "email"
    if session_id and session_id.strip():
        return f"session:{session_id.strip()}", "session"
    return f"session:{new_request_id()}", "session"


@router.post("/try-on-vton", response_model=TryOnResponse)
@router.post("/api/tryon/2d")
async def try_on_vton(
    request: Request,
    person_image: UploadFile = File(..., description="Customer full body photo"),
    garment_url: Optional[str] = Form(None, description="Publicly accessible garment image URL from storefront"),
    garment_image: Optional[UploadFile] = File(None, description="Optional direct garment upload"),
    category: str = Form("tops", description="tops | bottoms | one-pieces"),
    shopify_customer_id: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    product_id: Optional[str] = Form(None),
    variant_id: Optional[str] = Form(None),
    product_title: Optional[str] = Form(None),
    shop: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None),
    idempotency_header: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Core Virtual Try-On endpoint using FASHN VTON 1.5.

    1. Validates request and checks atomic 2-try/24h rolling quota.
    2. Wakes on-demand Lium GPU if stopped.
    3. Runs FASHN VTON 1.5 inference with person and garment image.
    4. Free try is consumed ONLY on success; failures never burn quota.
    """
    request_id = getattr(request.state, "request_id", None) or new_request_id()
    store = get_store()
    gpu_mgr = get_gpu_manager()
    settings = get_settings()

    # 1. Validate garment category (strictly tops, bottoms, one-pieces)
    clean_category = validate_category(category)

    # 2. Check Idempotency
    raw_idem = idempotency_key or idempotency_header
    clean_idem = normalise_idempotency_key(raw_idem)
    if clean_idem:
        cached = await store.get_idempotent_response(clean_idem)
        if cached and cached.get("response_json"):
            log.info("returning_cached_idempotent_tryon", idem_key=clean_idem)
            return JSONResponse(status_code=cached.get("status_code", 200), content=cached["response_json"])

    # 3. Resolve customer identity
    identity_key, identity_type = _resolve_identity(shopify_customer_id, email, session_id)
    customer = await store.resolve_customer(
        identity_key=identity_key,
        identity_type=identity_type,
        shopify_customer_id=shopify_customer_id,
        email=email,
        session_id=session_id,
        email_verified=bool(shopify_customer_id),
    )
    customer_id = customer["id"]

    # 4. Atomic quota reservation
    reservation = await store.reserve_try_on(
        request_id=request_id,
        customer_id=customer_id,
        idempotency_key=clean_idem,
        product_id=product_id,
        variant_id=variant_id,
        product_title=product_title,
        garment_category=clean_category,
        garment_url=garment_url,
    )

    if not reservation.get("allowed", False):
        used = reservation.get("used", settings.free_tries_per_day)
        reset_at = reservation.get("reset_at")
        log.info("quota_exceeded_denied", customer_id=customer_id, used=used)
        raise QuotaExceeded(
            f"You have used your free demo limit of {settings.free_tries_per_day} try-ons. "
            f"Next try available after {reset_at or '24 hours'}.",
            details={
                "customer_id": customer_id,
                "used": used,
                "remaining": 0,
                "limit": settings.free_tries_per_day,
                "reset_at": reset_at,
                "window_hours": settings.quota_window_hours,
            },
        )

    # 5. Validate customer uploaded photo
    try:
        raw_person = await person_image.read()
        person_bytes, _ = validate_person_upload(raw_person)
    except Exception as exc:
        await store.finalize_try_on(
            request_id=request_id,
            status="failed",
            error_code="invalid_person_image",
            error_message=str(exc),
        )
        raise

    # 6. Retrieve and validate garment image
    try:
        if garment_image and garment_image.filename:
            raw_garment = await garment_image.read()
            garment_bytes, _ = sanitize_image_bytes(raw_garment, label="garment upload")
        elif garment_url and garment_url.strip():
            garment_bytes, _ = await download_garment_image(garment_url.strip())
        else:
            raise ValidationError("Either garment_url or garment_image must be provided.")
    except Exception as exc:
        await store.finalize_try_on(
            request_id=request_id,
            status="failed",
            error_code="invalid_garment_image",
            error_message=str(exc),
        )
        raise

    # 7. GPU Lease and Inference execution
    start_time = time.perf_counter()
    duration_ms = 0
    try:
        async with gpu_mgr.lease() as endpoint:
            log.info("dispatching_inference_to_gpu", endpoint=endpoint, category=clean_category)
            result_bytes, mime = await run_vton_inference(
                endpoint=endpoint,
                person_bytes=person_bytes,
                garment_bytes=garment_bytes,
                category=clean_category,
                mock_mode=gpu_mgr.mock_mode,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
    except Exception as exc:
        # Failure does NOT consume a try!
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        log.exception("tryon_inference_failed", request_id=request_id, error=str(exc))
        await store.finalize_try_on(
            request_id=request_id,
            status="failed",
            error_code="inference_error",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        raise

    # 8. Encode result to data URL (safe, self-contained, no public customer image leaks)
    b64_data = base64.b64encode(result_bytes).decode("ascii")
    result_data_url = f"data:{mime};base64,{b64_data}"

    # 9. Finalize try-on successfully in Supabase (consumes 1 try)
    await store.finalize_try_on(
        request_id=request_id,
        status="success",
        duration_ms=duration_ms,
        result_ref="data_url",
    )

    # 10. Fetch updated quota
    quota_data = await store.get_usage(customer_id)
    quota_info = TryOnQuotaInfo(
        customer_id=str(customer_id),
        limit=quota_data.get("limit", settings.free_tries_per_day),
        window_hours=quota_data.get("window_hours", settings.quota_window_hours),
        used=quota_data.get("used", 1),
        remaining=quota_data.get("remaining", 1),
        in_flight=quota_data.get("in_flight", 0),
        eligible=quota_data.get("eligible", True),
        reset_at=quota_data.get("reset_at"),
    )

    response_payload = {
        "success": True,
        "request_id": request_id,
        "output_url": result_data_url,
        "result_image": result_data_url,
        "category": clean_category,
        "duration_ms": duration_ms,
        "quota": quota_info.model_dump(),
    }

    # Store idempotent response if requested
    if clean_idem:
        await store.put_idempotent_response(clean_idem, request_id, 200, response_payload)

    return JSONResponse(status_code=200, content=response_payload)


@router.get("/tryvtry-vton/products", response_model=ProductContextResponse)
async def get_storefront_product(
    garment_url: str = Query(..., description="Storefront product or variant image URL"),
    product_id: Optional[str] = Query(None),
    variant_id: Optional[str] = Query(None),
    product_title: Optional[str] = Query(None),
    category: Optional[str] = Query("tops"),
):
    """Retrieve and validate product image information supplied by the storefront.

    Zero Shopify Credentials:
    Does NOT call Shopify Admin API. Validates the storefront-supplied URL directly.
    """
    clean_cat = "tops"
    try:
        if category:
            clean_cat = validate_category(category)
    except Exception:
        clean_cat = "tops"

    try:
        validated_url = validate_image_url(garment_url)
        is_valid = True
    except ImageRejected:
        validated_url = garment_url
        is_valid = False

    return ProductContextResponse(
        product_id=product_id,
        variant_id=variant_id,
        product_title=product_title,
        garment_url=validated_url,
        category=clean_cat,
        is_valid=is_valid,
        supported_categories=["tops", "bottoms", "one-pieces"],
        unsupported_notice="FASHN VTON 1.5 supports tops, bottoms, and one-pieces. Accessories, sunglasses, footwear, and jewelry are not supported.",
    )


@router.get("/tryvtri-vton/check-usage", response_model=CheckUsageResponse)
@router.get("/api/widget/check-usage")
async def check_usage(
    email: Optional[str] = Query(None),
    shopify_customer_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    shop: Optional[str] = Query(None),
):
    """Check remaining try-on quota before prompting for photo upload."""
    store = get_store()
    settings = get_settings()

    identity_key, identity_type = _resolve_identity(shopify_customer_id, email, session_id)
    customer = await store.resolve_customer(
        identity_key=identity_key,
        identity_type=identity_type,
        shopify_customer_id=shopify_customer_id,
        email=email,
        session_id=session_id,
    )
    usage = await store.get_usage(customer["id"])

    return CheckUsageResponse(
        count=usage.get("used", 0),
        remaining=usage.get("remaining", settings.free_tries_per_day),
        limit=usage.get("limit", settings.free_tries_per_day),
        eligible=usage.get("eligible", True),
        reset_at=usage.get("reset_at"),
        window_hours=usage.get("window_hours", settings.quota_window_hours),
    )
