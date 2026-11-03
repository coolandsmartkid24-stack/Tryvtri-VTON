"""Pydantic schemas for Virtual Try-On API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TryOnQuotaInfo(BaseModel):
    customer_id: str
    limit: int
    window_hours: int
    used: int
    remaining: int
    in_flight: int = 0
    eligible: bool
    reset_at: Optional[str] = None


class TryOnResponse(BaseModel):
    success: bool
    request_id: str
    output_url: str
    result_image: Optional[str] = None  # alias for backward compatibility
    category: str
    duration_ms: int
    quota: TryOnQuotaInfo


class ProductContextResponse(BaseModel):
    product_id: Optional[str] = None
    variant_id: Optional[str] = None
    product_title: Optional[str] = None
    garment_url: str
    category: str
    is_valid: bool
    supported_categories: List[str] = ["tops", "bottoms", "one-pieces", "shoes", "glasses", "hats"]
    unsupported_notice: str = "Accessories, jewelry, and non-apparel items are not supported."


class CheckUsageResponse(BaseModel):
    count: int
    remaining: int
    limit: int
    eligible: bool
    reset_at: Optional[str] = None
    window_hours: int


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in_minutes: int
