"""Workflow steps 3–7: context → evaluate → compare → choose → growing guidance + follow-ups."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import get_settings
from db import store
from integrations.http import Timer
from knowledge import crops
from schemas.api import AskRequest, LangOnly, PlanRequest, RecRequest
from services import assistant, explain, plan, recommend, stt
from .common import load_session

router = APIRouter()


@router.post("/context/{sid}/prefetch")
async def prefetch(sid: str):
    st = load_session(sid)
    import asyncio
    asyncio.get_running_loop().create_task(recommend.context(st))
    return {"queued": True}


@router.get("/context/{sid}")
async def get_context(sid: str):
    st = load_session(sid)
    timer = Timer()
    ctx = await recommend.context(st, timer)
    return {**ctx, "timings_ms": timer.done()}


@router.post("/recommendations")
async def create_recommendation(body: RecRequest):
    st = load_session(body.session_id)
    timer = Timer()
    ctx = await recommend.context(st, timer)
    with timer.span("rules_economics"):
        rec = recommend.evaluate(st, ctx, get_settings().today())
    rid = store.new_id("rec")
    rec.update(id=rid, session_id=body.session_id, context=ctx, timings_ms=timer.done())
    store.put("recommendations", rid, rec, session_id=body.session_id)
    return recommend.view(rec, body.lang)


def _rec(rid: str) -> dict:
    rec = store.get("recommendations", rid)
    if not rec:
        raise HTTPException(404, "recommendation not found")
    return rec


@router.get("/recommendations/{rid}")
async def get_recommendation(rid: str, lang: str = "pa"):
    return recommend.view(_rec(rid), lang)


@router.post("/recommendations/{rid}/explain")
async def explain_recommendation(rid: str, body: LangOnly):
    v = recommend.view(_rec(rid), body.lang)
    return await explain.explain(v, body.lang)


@router.post("/plans")
async def create_plan(body: PlanRequest):
    rec = _rec(body.recommendation_id)
    if body.crop_id not in crops():
        raise HTTPException(422, "unknown crop")
    today = get_settings().today()
    p = plan.build(rec, body.crop_id, today)
    pid = store.new_id("plan")
    p["id"] = pid
    store.put("plans", pid, p, session_id=rec["session_id"], recommendation_id=rec["id"])
    return plan.view(p, body.lang, today)


def _plan(pid: str) -> dict:
    p = store.get("plans", pid)
    if not p:
        raise HTTPException(404, "plan not found")
    return p


@router.get("/plans/{pid}")
async def get_plan(pid: str, lang: str = "pa"):
    return plan.view(_plan(pid), lang, get_settings().today())


@router.post("/assistant")
async def ask(body: AskRequest):
    pv = plan.view(_plan(body.plan_id), body.lang, get_settings().today())
    return await assistant.ask(body.text, pv, body.lang)


@router.post("/assistant/audio")
async def ask_audio(plan_id: str = Form(...), lang: str = Form("pa"), audio: UploadFile = File(...)):
    pv = plan.view(_plan(plan_id), lang, get_settings().today())
    timer = Timer()
    try:
        with timer.span("stt"):
            tr = await stt.transcribe(await audio.read(), audio.filename or "q.wav", audio.content_type or "audio/wav", lang)
    except stt.STTUnavailable as exc:
        raise HTTPException(503, f"speech service unavailable: {exc}")
    res = await assistant.ask(tr["transcript"], pv, lang, timer)
    return {**res, "transcript": tr["transcript"]}
