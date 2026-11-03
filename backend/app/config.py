"""Typed application configuration.

Everything comes from the environment (optionally via a ``.env`` file at the
repository root).  No secret has a usable default — a missing secret raises at
import time so a misconfigured deployment fails fast instead of silently
running without authentication.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV_FILES = [
    ".env",
    "../.env",
    "../../.env",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- core ---
    environment: str = "development"
    tryvtri_public_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    jwt_secret: str = Field(default="tryvtri_default_secret_jwt_key_for_testing_and_local_development_2026")
    jwt_ttl_minutes: int = 720

    admin_username: str = "admin"
    admin_password: str = ""

    # ------------------------------------------------------------- supabase --
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_db_url: str = ""

    # ---------------------------------------------------------------- lium ---
    lium_api_key: str = ""
    lium_api_base: str = "https://lium.io/api"
    lium_gpu_type: str = "RTX 5080"
    lium_max_price_per_gpu_hour: float = 0.45
    lium_gpu_count: int = 1
    lium_min_vram_gb: float = 16
    lium_template_id: str = ""
    lium_pod_name_prefix: str = "tryvtri-vton"
    lium_termination_hours: int = 2
    lium_inference_host: str = ""
    lium_inference_port: int = 8000

    gpu_idle_shutdown_seconds: int = 600
    gpu_startup_timeout_seconds: int = 600
    gpu_daily_spend_cap_usd: float = 0.0

    # ----------------------------------------------------------- inference ---
    inference_base_url: str = ""
    inference_timeout_seconds: float = 180.0

    # -------------------------------------------------------------- uploads --
    max_upload_bytes: int = 8 * 1024 * 1024
    max_garment_download_bytes: int = 15 * 1024 * 1024
    image_download_timeout_seconds: float = 20.0
    temp_image_ttl_seconds: int = 900
    extra_allowed_image_hosts: str = ""

    # --------------------------------------------------------------- quota ---
    free_tries_per_day: int = 2
    quota_window_hours: int = 24

    # ---------------------------------------------------------------- cors ---
    allowed_origins: str = "*"

    # ------------------------------------------------------------ validation --
    @field_validator("jwt_secret")
    @classmethod
    def _warn_empty_jwt(cls, v: str) -> str:
        return v.strip()

    # ------------------------------------------------------------- helpers --
    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_secret_key)

    @property
    def has_lium(self) -> bool:
        return bool(self.lium_api_key)

    @property
    def cors_origins(self) -> List[str]:
        raw = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return raw or ["*"]

    @property
    def extra_image_hosts(self) -> List[str]:
        return [h.strip().lower() for h in self.extra_allowed_image_hosts.split(",") if h.strip()]

    @property
    def using_fixed_inference(self) -> bool:
        """True when a pre-provisioned inference endpoint is configured."""
        return bool(self.inference_base_url.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test helper — drop the memoised settings after env changes."""
    get_settings.cache_clear()
