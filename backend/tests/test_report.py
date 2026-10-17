import asyncio
from pathlib import Path

from services.report import read_report

SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "samples"


def test_reads_all_12_parameters_from_pdf():
    data = (SAMPLES / "sample_soil_health_card_bathinda.pdf").read_bytes()
    rep = asyncio.run(read_report(data, "card.pdf", "application/pdf"))
    assert rep["status"] == "ok" and rep["method"] == "pdf_text" and rep["count"] == 12
    p = rep["params"]
    assert p["ph"]["value"] == 8.9 and p["ec"]["value"] == 1.12 and p["oc"]["value"] == 0.31
    assert p["n"]["value"] == 188 and p["p"]["value"] == 14.2 and p["zn"]["value"] == 0.48
    assert rep["flags"] == ["saline"]  # EC > 0.8; pH 8.9 is below the 9.3 alkali limit


def test_unreadable_image_without_llm():
    rep = asyncio.run(read_report(b"\xff\xd8\xff\xe0 not really a jpeg", "photo.jpg", "image/jpeg"))
    assert rep["status"] == "unreadable" and rep["params"] == {}


def test_image_uses_gemini_vision_when_configured(with_keys):
    rep = asyncio.run(read_report(b"\xff\xd8\xff\xe0 fake", "photo.jpg", "image/jpeg"))
    assert rep["method"] == "gemini_vision" and rep["params"]["ph"]["value"] == 8.4
