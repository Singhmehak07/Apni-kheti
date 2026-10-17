"""Runtime configuration. Every provider, model name and URL is overridable via env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(BASE_DIR / ".env")
IST = ZoneInfo("Asia/Kolkata")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    sarvam_api_key: str = field(default_factory=lambda: _env("SARVAM_API_KEY"))
    data_gov_api_key: str = field(default_factory=lambda: _env("DATA_GOV_API_KEY"))

    gemini_base_url: str = field(default_factory=lambda: _env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"))
    sarvam_base_url: str = field(default_factory=lambda: _env("SARVAM_BASE_URL", "https://api.sarvam.ai"))
    open_meteo_url: str = field(default_factory=lambda: _env("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"))
    data_gov_base_url: str = field(default_factory=lambda: _env("DATA_GOV_BASE_URL", "https://api.data.gov.in/resource"))
    agmarknet_resource_id: str = field(default_factory=lambda: _env("AGMARKNET_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070"))

    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    gemini_stt_model: str = field(default_factory=lambda: _env("GEMINI_STT_MODEL", "gemini-3.5-flash-lite"))
    gemini_vision_model: str = field(default_factory=lambda: _env("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite"))
    gemini_schema_style: str = field(default_factory=lambda: _env("GEMINI_SCHEMA_STYLE", "response_format"))
    gemini_thinking_level: str = field(default_factory=lambda: _env("GEMINI_THINKING_LEVEL", "low"))

    sarvam_stt_model: str = field(default_factory=lambda: _env("SARVAM_STT_MODEL", "saaras:v4"))
    sarvam_stt_mode: str = field(default_factory=lambda: _env("SARVAM_STT_MODE", "transcribe"))
    sarvam_tts_model: str = field(default_factory=lambda: _env("SARVAM_TTS_MODEL", "bulbul:v3"))
    sarvam_tts_speaker: str = field(default_factory=lambda: _env("SARVAM_TTS_SPEAKER", "shubh"))
    tts_pace: float = field(default_factory=lambda: float(_env("TTS_PACE", "0.9")))

    # auto = best available provider for the configured keys
    stt_provider: str = field(default_factory=lambda: _env("STT_PROVIDER", "auto"))   # auto|sarvam|gemini|browser
    tts_provider: str = field(default_factory=lambda: _env("TTS_PROVIDER", "auto"))   # auto|sarvam|browser
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))   # auto|gemini|none
    ml_enabled: bool = field(default_factory=lambda: _env("ML_ENABLED", "false").lower() == "true")

    http_timeout_s: float = field(default_factory=lambda: float(_env("HTTP_TIMEOUT_S", "12")))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("LLM_TIMEOUT_S", "8")))
    max_reasks: int = 2

    db_path: Path = field(default_factory=lambda: Path(_env("DB_PATH", str(BASE_DIR / "data" / "apni_kheti.db"))))
    cache_dir: Path = field(default_factory=lambda: Path(_env("CACHE_DIR", str(BASE_DIR / "data" / "cache"))))
    frontend_dist: Path = field(default_factory=lambda: Path(_env("FRONTEND_DIST", str(ROOT_DIR / "frontend" / "dist"))))
    app_today: str = field(default_factory=lambda: _env("APP_TODAY"))

    # ---- resolved providers -------------------------------------------------
    @property
    def resolved_stt(self) -> str:
        p = self.stt_provider
        if p == "auto":
            return "sarvam" if self.sarvam_api_key else ("gemini" if self.gemini_api_key else "browser")
        if p == "sarvam" and not self.sarvam_api_key:
            return "browser"
        if p == "gemini" and not self.gemini_api_key:
            return "browser"
        return p

    @property
    def resolved_tts(self) -> str:
        p = self.tts_provider
        if p in ("auto", "sarvam"):
            return "sarvam" if self.sarvam_api_key else "browser"
        return "browser"

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none" and bool(self.gemini_api_key)

    def today(self) -> date:
        if self.app_today:
            return date.fromisoformat(self.app_today)
        return datetime.now(IST).date()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    (s.cache_dir / "tts").mkdir(parents=True, exist_ok=True)
    return s


def reset_settings() -> None:
    get_settings.cache_clear()
