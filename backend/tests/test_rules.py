from datetime import date

from services import economics
from services.rules import evaluate_crop

T = date(2026, 10, 17)
PRICE = {"kind": "msp_benchmark", "min": 2610, "avg": 2610, "max": 2610, "scope": "MSP", "date": "2026-09-30", "source_id": "pib_msp"}


def facts(**kw):
    base = {"district": "ludhiana", "zone": "central", "acres": 5, "soil_type": "loam", "salt_concern": False,
            "water_source": "tubewell", "water_quality": "sweet", "irrigations": 5, "irrigations_bucket": "5+",
            "usual_crop": "wheat", "previous_crop": "paddy", "sow_date": date(2026, 11, 5), "tractor": "own",
            "budget": None, "ph": None, "ec": None, "oc": None, "missing": []}
    base.update(kw)
    return base


def codes(ev):
    return [r["code"] for r in ev["reasons"]]


def test_wheat_timely_irrigated_feasible():
    ev = evaluate_crop("wheat", facts(), None, T)
    assert ev["status"] == "feasible"
    assert "sow_optimal" in codes(ev) and "after_paddy_wheat" in codes(ev)


def test_wheat_rainfed_not_suitable_but_gram_ok():
    f = facts(irrigations=0, irrigations_bucket="0", water_source="rain", sow_date=date(2026, 10, 20))
    assert evaluate_crop("wheat", f, None, T)["status"] == "not_suitable"
    g = evaluate_crop("gram", f, None, T)
    assert "water_rainfed" in codes(g)
    assert g["window"] == ["2026-10-10", "2026-10-25"]  # rainfed desi gram window


def test_wheat_late_penalty_in_economics():
    ev = evaluate_crop("wheat", facts(sow_date=date(2026, 12, 6)), None, T)
    assert ev["status"] == "conditional" and ev["late_weeks"] == 3 and ev["timing"] == "late"
    eco = economics.compute("wheat", ev, facts(), PRICE)
    assert eco["late_penalty_q"] == 4.5
    assert eco["yield_q_acre"]["base"] == round(20.92 - 4.5, 2)
    assert eco["cost_rs_acre"] == round(1264 * 20.92)


def test_saline_report_blocks_gram_and_favours_barley():
    f = facts(ec=1.2, ph=8.2)
    assert evaluate_crop("gram", f, None, T)["status"] == "not_suitable"
    b = evaluate_crop("barley", f, None, T)
    assert "salt_tolerant" in codes(b) and b["status"] == "feasible"
    w = evaluate_crop("wheat", f, None, T)
    assert "salt_extra_n" in codes(w) and w["status"] == "conditional"


def test_reported_kallar_is_a_flag_not_a_measurement():
    g = evaluate_crop("gram", facts(salt_concern=True, soil_type="salt_affected"), None, T)
    assert g["status"] == "conditional" and "salt_reported" in codes(g)


def test_unknown_irrigation_needs_info_for_wheat_only():
    f = facts(irrigations=None, irrigations_bucket=None)
    assert evaluate_crop("wheat", f, None, T)["status"] == "insufficient_information"
    assert evaluate_crop("raya", f, None, T)["status"] == "feasible"


def test_sw_zone_variety():
    r = evaluate_crop("raya", facts(district="bathinda", zone="south_western"), None, T)
    assert r["variety"]["name"] == "RCH 1" and "zone_variety" in codes(r)


def test_weather_cautions():
    wx = {"status": "ok", "summary": {"wettest_day": "2026-10-19", "wettest_mm": 12.5, "tmax_max": 33}}
    g = evaluate_crop("gram", facts(sow_date=date(2026, 10, 26), previous_crop="cotton"), wx, T)
    assert "weather_rain" in codes(g) and "weather_warm_gram" in codes(g)
    assert g["status"] == "feasible"  # weather is advice, never a status change


def test_template_explain_keeps_cautions():
    from services.explain import template
    view = {"crops": [{"crop_id": "raya", "status": "feasible", "headline": "h", "reasons": [
        {"type": "fit", "text": "a"}, {"type": "fit", "text": "b"}, {"type": "fit", "text": "c"},
        {"type": "money", "text": "m"}, {"type": "money", "text": "m2"}, {"type": "caution", "text": "salt"}]}]}
    kinds = [r["kind"] for r in template(view)["crops"][0]["reasons"]]
    assert kinds == ["fit", "fit", "money", "caution"]
