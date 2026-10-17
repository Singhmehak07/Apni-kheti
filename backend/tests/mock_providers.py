"""Contract-checking mock of Sarvam, Gemini and Open-Meteo.

Validates the request shape we send (headers, fields, limits) and returns realistic
responses, so the full voice + LLM path can be exercised without API keys — in pytest
(via httpx.ASGITransport) and in the browser E2E run (as a real server on :8099).
Queue endpoints let a test decide what the "speech" said or what the "LLM" returns.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import struct
import subprocess
import wave
from collections import deque
from datetime import date, timedelta

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile

app = FastAPI(title="mock providers")
STT_QUEUE: deque[str] = deque()
LLM_QUEUE: deque[dict] = deque()
LOG: list[dict] = []
FLAGS = {"reject_response_format": False}
SARVAM_LANGS = {"pa-IN", "hi-IN", "en-IN", "unknown"}


def _beep_mp3() -> bytes:
    if shutil.which("ffmpeg"):
        try:
            return subprocess.run(["ffmpeg", "-loglevel", "quiet", "-f", "lavfi", "-i", "sine=frequency=660:duration=0.35",
                                   "-ac", "1", "-ar", "22050", "-f", "mp3", "-"], capture_output=True, check=True).stdout
        except Exception:
            pass
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0" * 1600)
    return buf.getvalue()


BEEP = _beep_mp3()


@app.post("/__mock/stt-queue")
async def push_stt(body: dict):
    STT_QUEUE.extend(body.get("items", []))
    return {"size": len(STT_QUEUE)}


@app.post("/__mock/llm-queue")
async def push_llm(body: dict):
    LLM_QUEUE.extend(body.get("items", []))
    return {"size": len(LLM_QUEUE)}


@app.post("/__mock/flags")
async def set_flags(body: dict):
    FLAGS.update(body)
    return FLAGS


@app.get("/__mock/log")
async def get_log():
    return LOG[-50:]


@app.post("/__mock/reset")
async def reset():
    STT_QUEUE.clear(); LLM_QUEUE.clear(); LOG.clear(); FLAGS["reject_response_format"] = False
    return {"ok": True}


def _wav_seconds(data: bytes) -> float | None:
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


@app.post("/speech-to-text")
async def sarvam_stt(file: UploadFile = File(...), model: str = Form("saaras:v4"), mode: str = Form("transcribe"),
                     language_code: str = Form("unknown"), keyterms: str | None = Form(None),
                     api_subscription_key: str | None = Header(None)):
    if not api_subscription_key:
        raise HTTPException(403, "missing api-subscription-key")
    if model not in ("saaras:v3", "saaras:v4"):
        raise HTTPException(422, f"bad model {model}")
    if mode not in ("transcribe", "translate", "verbatim", "translit", "codemix"):
        raise HTTPException(422, "bad mode")
    if language_code not in SARVAM_LANGS:
        raise HTTPException(422, "bad language_code")
    if keyterms is not None:
        terms = json.loads(keyterms)
        if not isinstance(terms, list) or len(terms) > 50 or model != "saaras:v4":
            raise HTTPException(422, "keyterms must be a JSON list of <=50 terms (saaras:v4 only)")
    data = await file.read()
    secs = _wav_seconds(data)
    if secs is not None and secs > 30:
        raise HTTPException(422, "audio longer than 30 seconds")
    LOG.append({"api": "sarvam_stt", "model": model, "lang": language_code, "bytes": len(data), "seconds": secs,
                "keyterms": bool(keyterms)})
    text = STT_QUEUE.popleft() if STT_QUEUE else ""
    return {"request_id": "mock-stt", "transcript": text, "language_code": language_code}


@app.post("/text-to-speech")
async def sarvam_tts(request: Request, api_subscription_key: str | None = Header(None)):
    if not api_subscription_key:
        raise HTTPException(403, "missing api-subscription-key")
    body = await request.json()
    if not body.get("text") or len(body["text"]) > 2500:
        raise HTTPException(422, "text required, max 2500 chars")
    if body.get("target_language_code") not in SARVAM_LANGS - {"unknown"}:
        raise HTTPException(422, "bad target_language_code")
    if body.get("model", "bulbul:v3") not in ("bulbul:v2", "bulbul:v3"):
        raise HTTPException(422, "bad model")
    if body.get("speaker") and body["speaker"] != body["speaker"].lower():
        raise HTTPException(422, "speaker must be lowercase for bulbul:v3")
    if not 0.5 <= float(body.get("pace", 1.0)) <= 2.0:
        raise HTTPException(422, "pace out of range")
    if body.get("output_audio_codec", "mp3") not in ("mp3", "wav", "aac", "flac", "linear16"):
        raise HTTPException(422, "bad codec")
    LOG.append({"api": "sarvam_tts", "chars": len(body["text"]), "lang": body["target_language_code"]})
    return {"request_id": "mock-tts", "audios": [base64.b64encode(BEEP).decode()]}


def _wrap(text: str) -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}


@app.post("/v1beta/models/{model}:generateContent")
async def gemini(model: str, request: Request, x_goog_api_key: str | None = Header(None)):
    if not x_goog_api_key:
        raise HTTPException(403, "missing x-goog-api-key")
    body = await request.json()
    gc = body.get("generationConfig", {})
    if "responseFormat" in gc and FLAGS["reject_response_format"]:
        LOG.append({"api": "gemini", "model": model, "style": "response_format", "thinking": "thinkingConfig" in gc,
                    "rejected": True})
        raise HTTPException(400, "Unknown name \"responseFormat\"")
    schema = (gc.get("responseFormat", {}).get("text", {}) or {}).get("schema") or gc.get("responseJsonSchema")
    if "responseFormat" in gc and gc["responseFormat"]["text"].get("mimeType") != "application/json":
        raise HTTPException(400, "mimeType must be application/json")
    parts = body["contents"][0]["parts"]
    prompt = parts[0].get("text", "")
    LOG.append({"api": "gemini", "model": model, "style": "response_format" if "responseFormat" in gc else "legacy",
                "thinking": "thinkingConfig" in gc, "has_schema": schema is not None})
    if prompt.startswith("Transcribe"):
        return _wrap(STT_QUEUE.popleft() if STT_QUEUE else "")
    if LLM_QUEUE:
        return _wrap(json.dumps(LLM_QUEUE.popleft(), ensure_ascii=False))
    if prompt.startswith("FACTS (JSON)"):
        facts = json.loads(prompt.split("\n", 1)[1])
        crops = []
        for c in facts["crops"]:
            reasons = [{"kind": "fit", "text": f} for f in c["facts"][:2]]
            reasons.append({"kind": "money", "text": "Yield will surely be 99 quintal per acre."})  # hallucination
            crops.append({"crop_id": c["crop_id"], "headline": f"{c['crop_id']} summary", "reasons": reasons})
        return _wrap(json.dumps({"crops": crops}, ensure_ascii=False))
    if prompt.startswith("PLAN:"):
        return _wrap(json.dumps({"answer": "Follow the fertiliser step in your plan.", "covered": True}))
    if "Soil Health Card" in prompt:
        return _wrap(json.dumps({"is_soil_report": True, "ph": 8.4, "ec": 0.45, "oc": 0.42}))
    return _wrap(json.dumps({"understood": False, "dont_know": False}))


@app.get("/v1/forecast")
async def forecast(latitude: float, longitude: float):
    today = date(2026, 10, 17)
    days = [(today + timedelta(days=i)).isoformat() for i in range(7)]
    return {"daily": {"time": days, "temperature_2m_max": [33, 32, 31, 30, 30, 29, 29],
                      "temperature_2m_min": [18, 17, 17, 16, 16, 15, 15],
                      "precipitation_sum": [0, 0, 12.5, 2, 0, 0, 0],
                      "precipitation_probability_max": [5, 10, 70, 30, 5, 0, 0]},
            "hourly": {"relative_humidity_2m": [55] * 168}}
