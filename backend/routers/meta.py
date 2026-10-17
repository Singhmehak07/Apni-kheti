from fastapi import APIRouter

from config import get_settings

router = APIRouter()


@router.get("/config")
async def config():
    s = get_settings()
    return {
        "stt_provider": s.resolved_stt, "tts_provider": s.resolved_tts,
        "stt_model": s.sarvam_stt_model if s.resolved_stt == "sarvam" else (s.gemini_stt_model if s.resolved_stt == "gemini" else None),
        "tts_model": s.sarvam_tts_model if s.resolved_tts == "sarvam" else None,
        "llm": {"enabled": s.llm_enabled, "model": s.gemini_model if s.llm_enabled else None},
        "market": "live" if s.data_gov_api_key else "snapshot",
        "ml_status": "enabled" if s.ml_enabled else "skipped", "engine": "rules_v1",
        "languages": ["pa", "hi", "en"], "today": s.today().isoformat(), "max_audio_s": 25,
    }


@router.get("/health")
async def health():
    return {"ok": True}
