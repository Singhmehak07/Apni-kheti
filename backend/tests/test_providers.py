"""Provider contracts against the mock server (no real keys needed)."""
import asyncio
import io
import wave

from integrations import gemini, sarvam
from services import explain, tts
from tests import mock_providers as mp


def wav(seconds=1.0, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x10\x00" * int(seconds * rate))
    return buf.getvalue()


def test_sarvam_stt_contract(with_keys):
    mp.STT_QUEUE.append("ਬਠਿੰਡਾ")
    r = asyncio.run(sarvam.stt(wav(), "a.wav", "audio/wav", "pa", ["ਬਠਿੰਡਾ", "ਕਿੱਲੇ"]))
    assert r["transcript"] == "ਬਠਿੰਡਾ"
    log = mp.LOG[-1]
    assert log["model"] == "saaras:v4" and log["lang"] == "pa-IN" and log["keyterms"] and log["seconds"] == 1.0


def test_sarvam_rejects_long_audio(with_keys):
    try:
        asyncio.run(sarvam.stt(wav(31), "a.wav", "audio/wav", "pa"))
        assert False, "expected error"
    except sarvam.SarvamError as exc:
        assert "422" in str(exc)


def test_sarvam_tts_and_cache(with_keys):
    out = asyncio.run(tts.speak("ਬਿਜਾਈ ਤੋਂ 3–4 ਹਫ਼ਤੇ ਬਾਅਦ ਪਹਿਲਾ ਪਾਣੀ ਲਾਓ।", "pa"))
    assert out["provider"] == "sarvam" and len(out["urls"]) == 1 and out["cached"] is False
    assert "3 ਤੋਂ 4" in out["text"]  # ranges read naturally
    again = asyncio.run(tts.speak("ਬਿਜਾਈ ਤੋਂ 3–4 ਹਫ਼ਤੇ ਬਾਅਦ ਪਹਿਲਾ ਪਾਣੀ ਲਾਓ।", "pa"))
    assert again["cached"] is True
    assert sum(1 for l in mp.LOG if l["api"] == "sarvam_tts") == 1


def test_tts_browser_fallback_without_key():
    out = asyncio.run(tts.speak("hello", "en"))
    assert out["provider"] == "browser" and out["urls"] == []


def test_gemini_schema_fallback_to_legacy(with_keys):
    mp.FLAGS["reject_response_format"] = True
    mp.LLM_QUEUE.append({"understood": True, "dont_know": False, "district": "moga"})
    out = asyncio.run(gemini.generate_json("Farmer's answer: x", {"type": "object"}))
    assert out["district"] == "moga"
    styles = [(l["style"], l["thinking"]) for l in mp.LOG if l["api"] == "gemini"]
    assert styles == [("response_format", True), ("legacy", False)]


def test_explain_guard_drops_hallucinated_numbers(with_keys):
    view = {"facts": {"district": "moga"}, "crops": [{
        "crop_id": "wheat", "status": "feasible", "variety": "PBW 872", "sow_date_label": "5 Nov",
        "window_label": "1–15 Nov", "headline": "Good fit",
        "reasons": [{"type": "fit", "text": "5 Nov falls in the best sowing time (1–15 Nov)."},
                    {"type": "money", "text": "Base case: about ₹32,133 per acre above listed costs."}],
        "economics": {"yield_q_acre": {"base": 20.92}, "cost_rs_acre": 26443,
                      "net_rs_acre": {"low": 1, "base": 32133, "high": 2}}}]}
    out = asyncio.run(explain.explain(view, "en"))
    assert out["source"] == "llm" and out["guard_dropped"] == 1
    texts = [r["text"] for r in out["crops"][0]["reasons"]]
    assert not any("99" in t for t in texts) and len(texts) == 2
