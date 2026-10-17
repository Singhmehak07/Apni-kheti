"""Workflow steps 1–2: farmer input (voice/text/report) → extract, validate & confirm profile."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import get_settings
from db import store
from integrations.http import Timer
from knowledge import load, t
from schemas.api import Answer, LangPatch, NewSession, ProfilePatch, ReportPatch
from services import flow, recommend, report, stt
from .common import load_session

router = APIRouter()
MAX_AUDIO = 4 * 1024 * 1024
MAX_REPORT = 10 * 1024 * 1024


def _save(sid: str, st: dict) -> None:
    store.put("sessions", sid, st)


def _prefetch_context(st: dict) -> None:
    if st["fields"]["district"]["status"] == "answered":
        asyncio.get_running_loop().create_task(recommend.context(st))


@router.post("/sessions")
async def create_session(body: NewSession):
    sid = store.new_id("ses")
    st = flow.new_state(body.lang)
    _save(sid, st)
    nxt = flow.next_field(st)
    return {"session_id": sid, "lang": body.lang,
            "question": flow.question_payload(st, nxt, body.lang, get_settings().today())}


@router.get("/sessions/{sid}")
async def get_session(sid: str, lang: str | None = None):
    st = load_session(sid)
    lang = lang or st["lang"]
    nxt = flow.next_field(st)
    return {"session_id": sid, "lang": st["lang"], "done": nxt is None,
            "question": flow.question_payload(st, nxt, lang, get_settings().today()) if nxt else None,
            "profile": flow.profile_view(st, lang)}


@router.patch("/sessions/{sid}")
async def set_lang(sid: str, body: LangPatch):
    st = load_session(sid)
    st["lang"] = body.lang
    _save(sid, st)
    return await get_session(sid, body.lang)


@router.get("/questions")
async def all_questions(lang: str = "pa"):
    """All prompt texts for a language — the client prefetches their audio once."""
    qs = load("questions")
    texts = []
    for fid in qs["order"]:
        q = qs["questions"][fid]
        texts.append(t(q["prompt"], lang))
    return {"lang": lang, "texts": texts}


@router.get("/conversation/{sid}/question/{field}")
async def get_question(sid: str, field: str, lang: str | None = None):
    """One question with its options — used by the Confirm screen to edit a row."""
    st = load_session(sid)
    if field not in st["fields"]:
        raise HTTPException(422, "unknown field")
    q = flow.question_payload(st, field, lang or st["lang"], get_settings().today())
    q["attempt"], q["text"] = 0, q["base_prompt"]
    return q


@router.post("/conversation/{sid}/answer")
async def answer(sid: str, body: Answer):
    st = load_session(sid)
    if body.field not in st["fields"]:
        raise HTTPException(422, "unknown field")
    res = await flow.handle_answer(st, body.field, option_id=body.option_id, value=body.value, text=body.text,
                                   skip=body.skip, via=body.via)
    _save(sid, st)
    if body.field == "district" or any(u["field"] == "district" for u in res["understood"]):
        _prefetch_context(st)
    store.log_event(sid, "answer", {"field": body.field, "result": res["result"], "via": body.via,
                                    "timings": res["timings_ms"], "llm": res["used_llm"]})
    return res


@router.post("/conversation/{sid}/answer-audio")
async def answer_audio(sid: str, field: str = Form(...), lang: str = Form("pa"), audio: UploadFile = File(...)):
    st = load_session(sid)
    if field not in st["fields"]:
        raise HTTPException(422, "unknown field")
    data = await audio.read()
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "audio too large (max ~30 s)")
    timer = Timer()
    try:
        with timer.span("stt"):
            tr = await stt.transcribe(data, audio.filename or "answer.wav", audio.content_type or "audio/wav", lang)
    except stt.STTUnavailable as exc:
        raise HTTPException(503, f"speech service unavailable: {exc}")
    text = tr["transcript"]
    if not text:  # silence / noise: ask again without spending one of the re-ask attempts
        q = flow.question_payload(st, field, lang, get_settings().today())
        return {"result": "no_speech", "field": field, "understood": [], "feedback_code": None, "used_llm": False,
                "action": None, "done": False, "next": q, "timings_ms": timer.done(), "transcript": "",
                "stt_provider": tr["provider"], "stt_model": tr.get("model")}
    res = await flow.handle_answer(st, field, text=text, via="voice", timer=timer)
    _save(sid, st)
    if field == "district" or any(u["field"] == "district" for u in res["understood"]):
        _prefetch_context(st)
    res.update(transcript=text, stt_provider=tr["provider"], stt_model=tr.get("model"))
    store.log_event(sid, "answer_audio", {"field": field, "result": res["result"], "timings": res["timings_ms"]})
    return res


@router.post("/conversation/{sid}/back")
async def back(sid: str, lang: str | None = None):
    st = load_session(sid)
    fid = flow.go_back(st)
    _save(sid, st)
    nxt = flow.next_field(st)
    lang = lang or st["lang"]
    return {"field": fid, "question": flow.question_payload(st, nxt, lang, get_settings().today()) if nxt else None}


@router.post("/reports/{sid}")
async def upload_report(sid: str, file: UploadFile = File(...)):
    st = load_session(sid)
    data = await file.read()
    if len(data) > MAX_REPORT:
        raise HTTPException(413, "file too large")
    timer = Timer()
    with timer.span("read_report"):
        rep = await report.read_report(data, file.filename or "report", file.content_type or "")
    if rep["status"] != "unreadable":
        st["report"] = rep
        st["fields"]["soil_report"].update(status="answered", value="yes", source="report")
        _save(sid, st)
    return {**rep, "timings_ms": timer.done()}


@router.patch("/profile/{sid}/report")
async def patch_report(sid: str, body: ReportPatch):
    st = load_session(sid)
    rep = st.get("report") or {"status": "manual", "method": "manual", "params": {}, "flags": []}
    for k in ("ph", "ec", "oc"):
        v = getattr(body, k)
        if v is not None:
            spec = report.PARAMS[k]
            rep["params"][k] = {"value": v, "unit": spec["unit"], "label": spec["label"], "rating": None, "manual": True}
    rep["flags"] = report.flags(rep["params"])
    st["report"] = rep
    _save(sid, st)
    return rep


@router.get("/profile/{sid}")
async def profile(sid: str, lang: str = "pa"):
    st = load_session(sid)
    return flow.profile_view(st, lang)


@router.patch("/profile/{sid}")
async def patch_profile(sid: str, body: ProfilePatch, lang: str = "pa"):
    st = load_session(sid)
    if body.field not in st["fields"]:
        raise HTTPException(422, "unknown field")
    if body.clear:
        st["fields"][body.field].update(status="not_available", value=None, source=None)
        flow.reset_dependents(st, body.field)
        res = {"result": "not_available"}
    else:
        res = await flow.handle_answer(st, body.field, option_id=body.option_id, value=body.value, text=body.text,
                                       via="typed", editing=True)
    _save(sid, st)
    _prefetch_context(st)
    return {"result": res["result"], "profile": flow.profile_view(st, lang),
            "next": res.get("next") if res.get("result") == "unclear" else None}


@router.post("/profile/{sid}/confirm")
async def confirm(sid: str):
    st = load_session(sid)
    st["confirmed"] = True
    for f in st["fields"].values():
        if f["status"] == "pending":
            f["status"] = "not_provided"
    _save(sid, st)
    _prefetch_context(st)
    return {"confirmed": True}
