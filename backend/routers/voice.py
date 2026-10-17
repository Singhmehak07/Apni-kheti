from __future__ import annotations

import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from integrations.http import Timer
from schemas.api import TTSPrefetch, TTSRequest
from services import stt, tts

router = APIRouter()


@router.post("/tts")
async def speak(body: TTSRequest):
    timer = Timer()
    with timer.span("tts"):
        res = await tts.speak(body.text, body.lang)
    return {**res, "timings_ms": timer.done()}


@router.post("/tts/prefetch")
async def prefetch(body: TTSPrefetch):
    return {"queued": tts.prefetch(body.texts, body.lang)}


@router.get("/tts/audio/{key}.mp3")
async def audio(key: str):
    if not re.fullmatch(r"[0-9a-f]{24}", key):
        raise HTTPException(404)
    p = tts.path_for(key)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.post("/stt")
async def transcribe(lang: str = Form("pa"), audio: UploadFile = File(...)):
    try:
        return await stt.transcribe(await audio.read(), audio.filename or "a.wav", audio.content_type or "audio/wav", lang)
    except stt.STTUnavailable as exc:
        raise HTTPException(503, f"speech service unavailable: {exc}")
