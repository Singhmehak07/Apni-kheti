"""Gemini REST client: structured JSON output, audio transcription and document reading.

Primary request style uses generationConfig.responseFormat (current API). If the
server rejects it (400), we retry once with the legacy responseMimeType +
responseJsonSchema form and without thinkingConfig, so model upgrades don't break us.
"""
from __future__ import annotations

import base64
import json
import logging

from config import get_settings
from . import http

log = logging.getLogger("gemini")


class GeminiError(RuntimeError):
    pass


def _gen_config(schema: dict | None, style: str, thinking: bool, temperature: float) -> dict:
    s = get_settings()
    cfg: dict = {"temperature": temperature}
    if schema is not None:
        if style == "response_format":
            cfg["responseFormat"] = {"text": {"mimeType": "application/json", "schema": schema}}
        else:
            cfg["responseMimeType"] = "application/json"
            cfg["responseJsonSchema"] = schema
    if thinking and s.gemini_thinking_level:
        cfg["thinkingConfig"] = {"thinkingLevel": s.gemini_thinking_level}
    return cfg


def _text_of(data: dict) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiError(f"no candidates: {str(data)[:200]}") from exc
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


async def generate(parts: list[dict], *, schema: dict | None = None, system: str | None = None,
                   model: str | None = None, temperature: float = 0.2, timeout: float | None = None) -> str:
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY not set")
    models_to_try = [model or s.gemini_model]
    if "3.8" in models_to_try[0]:
        models_to_try.append("gemini-2.5-flash")
    headers = {"x-goog-api-key": s.gemini_api_key, "Content-Type": "application/json"}
    styles = [s.gemini_schema_style, "legacy" if s.gemini_schema_style != "legacy" else "response_format"]
    attempts = [(styles[0], True), (styles[1], False)]
    last_err = ""
    for cur_model in models_to_try:
        url = f"{s.gemini_base_url.rstrip('/')}/v1beta/models/{cur_model}:generateContent"
        for style, thinking in attempts:
            body: dict = {"contents": [{"role": "user", "parts": parts}],
                          "generationConfig": _gen_config(schema, style, thinking, temperature)}
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}
            resp = await http.request("POST", url, json=body, headers=headers, timeout=timeout or s.llm_timeout_s)
            if resp.status_code == 200:
                return _text_of(resp.json())
            last_err = f"{resp.status_code}: {resp.text[:300]}"
            if resp.status_code == 429:
                log.warning("gemini %s quota 429, trying fallback model: %s", cur_model, last_err)
                break
            if resp.status_code != 400:
                break
            log.warning("gemini 400 with style=%s thinking=%s, retrying: %s", style, thinking, last_err)
        else:
            continue
        if resp.status_code == 200:
            return _text_of(resp.json())
    raise GeminiError(last_err)


async def generate_json(prompt: str, schema: dict, *, system: str | None = None, model: str | None = None,
                        extra_parts: list[dict] | None = None, timeout: float | None = None) -> dict:
    parts = [{"text": prompt}] + (extra_parts or [])
    text = await generate(parts, schema=schema, system=system, model=model, timeout=timeout)
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"invalid JSON from model: {text[:200]}") from exc


def inline(data: bytes, mime: str) -> dict:
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}


LANG_NAMES = {"pa": "Punjabi (Gurmukhi script)", "hi": "Hindi (Devanagari script)", "en": "English"}


async def transcribe(audio: bytes, mime: str, lang: str, vocabulary: list[str] | None = None) -> str:
    s = get_settings()
    vocab = ", ".join(vocabulary or [])
    prompt = (f"Transcribe this farmer's spoken answer exactly. Expected language: {LANG_NAMES.get(lang, lang)}; "
              f"the farmer may mix Punjabi, Hindi and English. Write in the script of the spoken language. "
              f"Likely words: {vocab}. Return only the transcript text, no notes.")
    text = await generate([{"text": prompt}, inline(audio, mime)], model=s.gemini_stt_model, temperature=0.0)
    return text.strip()
