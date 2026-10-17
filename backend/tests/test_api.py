"""End-to-end API: interview → confirm → recommendations → explain → plan → assistant."""
import io
import wave
from pathlib import Path

from tests import mock_providers as mp

SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "samples"


def _answers(c, sid, items):
    last = None
    for item in items:
        last = c.post(f"/api/v1/conversation/{sid}/answer", json=item).json()
    return last


def test_full_flow_no_keys(client):
    cfg = client.get("/api/v1/config").json()
    assert cfg["ml_status"] == "skipped" and cfg["stt_provider"] == "browser" and cfg["llm"]["enabled"] is False
    sid = client.post("/api/v1/sessions", json={"lang": "pa"}).json()["session_id"]
    up = client.post(f"/api/v1/reports/{sid}", files={"file": ("card.pdf", (SAMPLES / "sample_soil_health_card_ludhiana.pdf").read_bytes(), "application/pdf")}).json()
    assert up["count"] == 12
    last = _answers(client, sid, [
        {"field": "district", "text": "ਲੁਧਿਆਣਾ"}, {"field": "land_area", "text": "ਢਾਈ ਕਿੱਲੇ"},
        {"field": "soil_type", "option_id": "loam"}, {"field": "water_source", "option_id": "tubewell"},
        {"field": "water_quality", "option_id": "sweet"}, {"field": "irrigations", "option_id": "5+"},
        {"field": "usual_crop", "option_id": "wheat"}, {"field": "previous_crop", "option_id": "paddy"},
        {"field": "field_ready", "option_id": "nov_1h"}, {"field": "tractor", "option_id": "own"},
        {"field": "budget", "skip": True}])
    assert last["done"] is True
    prof = client.get(f"/api/v1/profile/{sid}?lang=en").json()
    by = {i["field"]: i for i in prof["items"]}
    assert by["soil_report"]["provenance"] == "report" and by["budget"]["status"] == "not_available"
    assert client.post(f"/api/v1/profile/{sid}/confirm").json()["confirmed"]
    rec = client.post("/api/v1/recommendations", json={"session_id": sid, "lang": "pa"}).json()
    assert rec["ml_status"] == "skipped" and rec["weather"]["status"] == "ok"
    top = rec["crops"][0]
    assert top["crop_id"] == "wheat" and top["status"] == "feasible"
    assert {c["crop_id"] for c in rec["crops"]} == {"wheat", "raya", "gram", "barley"}
    ex = client.post(f"/api/v1/recommendations/{rec['id']}/explain", json={"lang": "pa"}).json()
    assert ex["source"] == "template" and ex["crops"][0]["reasons"]
    plan = client.post("/api/v1/plans", json={"recommendation_id": rec["id"], "crop_id": "wheat", "lang": "hi"}).json()
    ids = [s["id"] for s in plan["steps"]]
    assert ids[0] in ("weather", "prep") and "harvest" in ids and ids[-1] == "sell"
    prep = next(s for s in plan["steps"] if s["id"] == "prep")
    assert "धान के बाद" in prep["text"]  # after-paddy variant
    seed = next(s for s in plan["steps"] if s["id"] == "seed")
    assert "112.5" in seed["text"]  # 45 kg/acre × 2.5 acres
    ans = client.post("/api/v1/assistant", json={"plan_id": plan["id"], "text": "यूरिया कब डालें?", "lang": "hi"}).json()
    assert ans["source"] == "plan" and "यूरिया" in ans["answer"]


def test_voice_answer_with_mock_providers(with_keys, client):
    sid = client.post("/api/v1/sessions", json={"lang": "pa"}).json()["session_id"]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x20\x00" * 16000)
    mp.STT_QUEUE.extend(["ਨਹੀਂ ਜੀ", "ਬਠਿੰਡੇ ਵਿੱਚ ਪੰਜ ਕਿੱਲੇ"])
    r1 = client.post(f"/api/v1/conversation/{sid}/answer-audio", data={"field": "soil_report", "lang": "pa"},
                     files={"audio": ("a.wav", buf.getvalue(), "audio/wav")}).json()
    assert r1["transcript"] == "ਨਹੀਂ ਜੀ" and r1["result"] == "accepted" and r1["stt_provider"] == "sarvam"
    assert "stt" in r1["timings_ms"]
    r2 = client.post(f"/api/v1/conversation/{sid}/answer-audio", data={"field": "district", "lang": "pa"},
                     files={"audio": ("a.wav", buf.getvalue(), "audio/wav")}).json()
    assert {u["field"] for u in r2["understood"]} == {"district", "land_area"}
    assert r2["next"]["field"] == "soil_type"


def test_llm_extraction_fallback_for_unclear_text(with_keys, client):
    sid = client.post("/api/v1/sessions", json={"lang": "pa"}).json()["session_id"]
    _answers(client, sid, [{"field": "soil_report", "option_id": "no"}, {"field": "district", "option_id": "sangrur"},
                           {"field": "land_area", "value": {"amount": 4, "unit": "killa"}},
                           {"field": "soil_type", "option_id": "loam"}, {"field": "water_source", "option_id": "canal"}])
    r = client.post(f"/api/v1/conversation/{sid}/answer", json={"field": "irrigations", "text": "ਤਿੰਨ ਕੁ ਵਾਰ ਨਹਿਰ ਆਉਂਦੀ"}).json()
    # deterministic parser already catches ਤਿੰਨ → no LLM needed
    assert r["result"] == "accepted" and r["used_llm"] is False
    mp.LLM_QUEUE.clear()
    mp.LLM_QUEUE.append({"understood": True, "dont_know": False, "usual_crop": "wheat"})
    r = client.post(f"/api/v1/conversation/{sid}/answer", json={"field": "usual_crop", "text": "ਓਹੀ ਜੋ ਸਾਰੇ ਬੀਜਦੇ ਨੇ, ਰੋਟੀ ਵਾਲੀ"}).json()
    assert r["used_llm"] is True and r["result"] == "accepted"


def test_tts_endpoint_serves_cached_audio(with_keys, client):
    r = client.post("/api/v1/tts", json={"text": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "lang": "pa"}).json()
    assert r["provider"] == "sarvam"
    audio = client.get(r["urls"][0])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"


def test_question_for_edit(client):
    sid = client.post("/api/v1/sessions", json={"lang": "hi"}).json()["session_id"]
    q = client.get(f"/api/v1/conversation/{sid}/question/water_source").json()
    assert q["field"] == "water_source" and {o["id"] for o in q["options"]} == {"canal", "tubewell", "both", "rain"}
    assert client.get(f"/api/v1/conversation/{sid}/question/nope").status_code == 422


def test_silent_audio_does_not_use_a_retry(with_keys, client):
    sid = client.post("/api/v1/sessions", json={"lang": "en"}).json()["session_id"]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 8000)
    mp.STT_QUEUE.append("")
    r = client.post(f"/api/v1/conversation/{sid}/answer-audio", data={"field": "soil_report", "lang": "en"},
                    files={"audio": ("a.wav", buf.getvalue(), "audio/wav")}).json()
    assert r["result"] == "no_speech" and r["next"]["field"] == "soil_report" and r["next"]["attempt"] == 0
