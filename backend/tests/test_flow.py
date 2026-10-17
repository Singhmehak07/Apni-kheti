import asyncio

from services import flow


def run(coro):
    return asyncio.run(coro)


def test_chip_flow_and_skips():
    st = flow.new_state("en")
    assert flow.next_field(st) == "soil_report"
    run(flow.handle_answer(st, "soil_report", option_id="no"))
    run(flow.handle_answer(st, "district", option_id="ludhiana"))
    run(flow.handle_answer(st, "land_area", value={"amount": 8, "unit": "kanal"}))
    assert st["fields"]["land_area"]["value"]["acres"] == 1.0
    run(flow.handle_answer(st, "soil_type", option_id="loam"))
    res = run(flow.handle_answer(st, "water_source", option_id="rain"))
    # rain-only: water quality is skipped and irrigations derived as 0
    assert st["fields"]["water_quality"]["status"] == "skipped"
    assert st["fields"]["irrigations"]["value"] == {"bucket": "0", "count": 0}
    assert st["fields"]["irrigations"]["source"] == "derived"
    assert res["next"]["field"] == "usual_crop"


def test_reask_twice_then_not_provided():
    st = flow.new_state("pa")
    run(flow.handle_answer(st, "soil_report", option_id="no"))
    r1 = run(flow.handle_answer(st, "district", text="ਹਮ"))
    assert r1["result"] == "unclear" and r1["next"]["field"] == "district" and r1["next"]["attempt"] == 1
    assert r1["next"]["text"].startswith("ਮਾਫ਼ ਕਰਨਾ")
    r2 = run(flow.handle_answer(st, "district", text="ਹੰਜੀ"))
    assert r2["result"] == "unclear" and r2["next"]["attempt"] == 2
    r3 = run(flow.handle_answer(st, "district", text="ਊਂ"))
    assert r3["result"] == "not_provided"
    assert st["fields"]["district"]["value"] is None
    assert r3["next"]["field"] == "land_area"


def test_dont_know_leaves_empty():
    st = flow.new_state("hi")
    run(flow.handle_answer(st, "soil_report", option_id="no"))
    r = run(flow.handle_answer(st, "district", text="पता नहीं"))
    assert r["result"] == "not_available"
    assert st["fields"]["district"] == {**st["fields"]["district"], "status": "not_available", "value": None}
    r = run(flow.handle_answer(st, "land_area", skip=True))
    assert st["fields"]["land_area"]["status"] == "not_available"


def test_invalid_area_reasks_with_specific_message():
    st = flow.new_state("en")
    run(flow.handle_answer(st, "soil_report", option_id="no"))
    run(flow.handle_answer(st, "district", option_id="moga"))
    r = run(flow.handle_answer(st, "land_area", text="3 bigha"))
    assert r["result"] == "unclear" and r["feedback_code"] == "bigha_unit"
    assert "Bigha size differs" in r["next"]["text"]


def test_multi_fill_and_back():
    st = flow.new_state("pa")
    run(flow.handle_answer(st, "soil_report", option_id="no"))
    r = run(flow.handle_answer(st, "district", text="ਬਠਿੰਡੇ ਵਿੱਚ ਸਾਢੇ ਪੰਜ ਕਿੱਲੇ ਨੇ, ਨਹਿਰੀ ਪਾਣੀ"))
    fields = [u["field"] for u in r["understood"]]
    assert fields[0] == "district" and "land_area" in fields and "water_source" in fields
    assert r["next"]["field"] == "soil_type"
    back = flow.go_back(st)
    assert back == "district" and st["fields"]["district"]["status"] == "pending"
