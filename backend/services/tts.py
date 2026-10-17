"""Text-to-speech with a disk cache, in-flight de-duplication and background prefetch."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re

from config import get_settings
from integrations import sarvam

log = logging.getLogger("tts")
_inflight: dict[str, asyncio.Future] = {}
_sems: dict[int, asyncio.Semaphore] = {}
TO = {"pa": "ਤੋਂ", "hi": "से", "en": "to"}


def speech_text(text: str, lang: str) -> str:
    """Make text read naturally: '15–20' → '15 ਤੋਂ 20', drop symbols voices stumble on."""
    s = re.sub(r"(\d)\s*[–-]\s*(\d)", rf"\1 {TO.get(lang, 'to')} \2", text)
    s = s.replace("•", " ").replace("·", " ").replace("/", " ")
    return re.sub(r"\s+", " ", s).strip()


def chunks(text: str, limit: int = 450) -> list[str]:
    parts = re.split(r"(?<=[।.!?])\s+", text)
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 <= limit:
            cur = f"{cur} {p}".strip()
        else:
            if cur:
                out.append(cur)
            while len(p) > limit:
                out.append(p[:limit])
                p = p[limit:]
            cur = p
    if cur:
        out.append(cur)
    return out


def key_for(text: str, lang: str) -> str:
    s = get_settings()
    raw = f"{s.sarvam_tts_model}|{s.sarvam_tts_speaker}|{s.tts_pace}|{lang}|{text}"
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def path_for(key: str):
    return get_settings().cache_dir / "tts" / f"{key}.mp3"


async def _synth(chunk: str, lang: str) -> str:
    key = key_for(chunk, lang)
    p = path_for(key)
    if p.exists():
        return key
    if key in _inflight:
        await _inflight[key]
        return key
    fut = asyncio.get_running_loop().create_future()
    _inflight[key] = fut
    try:
        loop_id = id(asyncio.get_running_loop())
        sem = _sems.setdefault(loop_id, asyncio.Semaphore(4))
        async with sem:
            audio = await sarvam.tts(chunk, lang)
        p.write_bytes(audio)
        fut.set_result(True)
        return key
    except Exception as exc:
        fut.set_exception(exc)
        fut.exception()  # mark retrieved
        raise
    finally:
        _inflight.pop(key, None)


async def speak(text: str, lang: str) -> dict:
    if get_settings().resolved_tts != "sarvam":
        return {"provider": "browser", "text": speech_text(text, lang), "urls": []}
    spoken = speech_text(text, lang)
    parts = chunks(spoken)
    cached = all(path_for(key_for(c, lang)).exists() for c in parts)
    try:
        keys = await asyncio.gather(*(_synth(c, lang) for c in parts))
    except Exception as exc:
        log.warning("tts failed, browser fallback: %s", exc)
        return {"provider": "browser", "text": spoken, "urls": [], "error": type(exc).__name__}
    return {"provider": "sarvam", "urls": [f"/api/v1/tts/audio/{k}.mp3" for k in keys], "cached": cached, "text": spoken}


def prefetch(texts: list[str], lang: str) -> int:
    if get_settings().resolved_tts != "sarvam":
        return 0
    todo = []
    for t in texts:
        for c in chunks(speech_text(t, lang)):
            if not path_for(key_for(c, lang)).exists():
                todo.append(c)

    async def run():
        for c in todo:
            try:
                await _synth(c, lang)
            except Exception as exc:
                log.warning("prefetch failed: %s", exc)
                return

    if todo:
        asyncio.get_running_loop().create_task(run())
    return len(todo)
