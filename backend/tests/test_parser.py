from datetime import date

import pytest

from services.extract import field_ready_options, opportunistic, parse_field
from services.numbers import find_numbers
from knowledge import load

T = date(2026, 10, 17)


@pytest.mark.parametrize("text,expected", [
    ("ਸਾਢੇ ਪੰਜ", [5.5]), ("ਡੇਢ", [1.5]), ("ढाई", [2.5]), ("two and a half", [2.5]), ("twenty five", [25]),
    ("ਵੀਹ ਹਜ਼ਾਰ", [20000]), ("डेढ़ लाख", [150000]), ("੧੨", [12]), ("२०", [20]), ("20,000", [20000]), ("15k", [15000]),
    ("ਸਵਾ ਦੋ", [2.25]), ("पौने चार", [3.75]),
])
def test_numbers(text, expected):
    assert find_numbers(text) == expected


@pytest.mark.parametrize("field,text,status,value", [
    ("district", "ਮੈਂ ਬਠਿੰਡੇ ਤੋਂ ਹਾਂ", "ok", "bathinda"),
    ("district", "bhatinda", "ok", "bathinda"),
    ("district", "ਫਿਰੋਜ਼ਪੁਰ", "ok", "ferozepur"),
    ("district", "ਫ਼ਿਰੋਜ਼ਪੁਰ", "ok", "ferozepur"),  # nukta variant
    ("district", "ropar", "ok", "rupnagar"),
    ("district", "मोहाली", "ok", "sas_nagar"),
    ("district", "ਪਤਾ ਨਹੀਂ", "unknown", None),
    ("district", "ਕੋਈ ਗੱਲ ਨਹੀਂ", "unclear", None),
    ("soil_report", "ਨਹੀਂ ਜੀ", "ok", "no"),
    ("soil_report", "हां है", "ok", "yes"),
    ("water_source", "ਨਹਿਰੀ ਪਾਣੀ ਤੇ ਮੋਟਰ ਵੀ", "ok", "both"),
    ("water_source", "सिर्फ बारिश", "ok", "rain"),
    ("water_source", "tubewell", "ok", "tubewell"),
    ("water_quality", "ਖਾਰਾ", "ok", "salty"),
    ("usual_crop", "ਕਣਕ", "ok", "wheat"),
    ("usual_crop", "सरसों", "ok", "raya"),
    ("previous_crop", "ਬਾਸਮਤੀ ਲਾਈ ਸੀ", "ok", "basmati"),
    ("previous_crop", "ਝੋਨਾ", "ok", "paddy"),
    ("tractor", "ਆਪਣਾ ਨਹੀਂ, ਕਿਰਾਏ ਤੇ", "ok", "rent"),
    ("tractor", "ਨਹੀਂ ਹੈ", "ok", "none"),
    ("tractor", "ਹਾਂ ਆਪਣਾ ਹੈ", "ok", "own"),
])
def test_choice_fields(field, text, status, value):
    r = parse_field(field, text, T)
    assert r.status == status
    assert r.value == value


def test_land_units_and_validation():
    assert parse_field("land_area", "ਸਾਢੇ ਪੰਜ ਕਿੱਲੇ", T).value["acres"] == 5.5
    assert parse_field("land_area", "12 kanal", T).value["acres"] == 1.5
    assert parse_field("land_area", "2 hectare", T).value["acres"] == pytest.approx(4.942)
    assert parse_field("land_area", "ਪੰਜ", T).value == {"acres": 5.0, "amount": 5.0, "unit": "killa"}
    r = parse_field("land_area", "ਦੋ ਵਿੱਘੇ", T)
    assert (r.status, r.code) == ("invalid", "bigha_unit")
    assert parse_field("land_area", "0 acre", T).code == "invalid_area"
    assert parse_field("land_area", "900 killa", T).code == "invalid_area"


def test_soil_salt_flag():
    r = parse_field("soil_type", "ਰੇਤਲੀ ਤੇ ਥੋੜ੍ਹਾ ਕੱਲਰ", T)
    assert r.value == "sandy" and r.extra["salt_concern"] is True
    assert parse_field("soil_type", "मैरा", T).value == "loam"


def test_irrigations():
    assert parse_field("irrigations", "ਚਾਰ ਪਾਣੀ", T).value["bucket"] == "3-4"
    assert parse_field("irrigations", "ਜਿੰਨੇ ਮਰਜ਼ੀ", T).value["bucket"] == "5+"
    assert parse_field("irrigations", "ਕੋਈ ਨਹੀਂ", T).value["bucket"] == "0"


def test_field_ready_dates():
    assert parse_field("field_ready", "ਨਵੰਬਰ ਦੇ ਪਹਿਲੇ ਹਫ਼ਤੇ", T).value["date"] == "2026-11-04"
    assert parse_field("field_ready", "10 ਦਿਨਾਂ ਵਿੱਚ", T).value["date"] == "2026-10-27"
    assert parse_field("field_ready", "15 november", T).value["date"] == "2026-11-15"
    r = parse_field("field_ready", "नवंबर", T)
    assert r.status == "unclear" and r.code == "month_half"
    opts = field_ready_options(T, load("questions")["field_ready_options"])
    assert [o["id"] for o in opts] == ["this_week", "late_oct", "nov_1h", "nov_2h", "december"]
    late = field_ready_options(date(2026, 11, 20), load("questions")["field_ready_options"])
    assert [o["id"] for o in late] == ["this_week", "nov_2h", "december"]  # late Nov still ahead


def test_budget():
    assert parse_field("budget", "ਵੀਹ ਹਜ਼ਾਰ", T).value == {"rs_per_acre": 20000}
    assert parse_field("budget", "15000", T).value == {"rs_per_acre": 15000}
    assert parse_field("budget", "ਪਤਾ ਨਹੀਂ", T).status == "unknown"


def test_one_answer_fills_many():
    found = opportunistic("ਬਠਿੰਡੇ ਵਿੱਚ 5 ਕਿੱਲੇ ਨਹਿਰੀ ਪਾਣੀ, ਝੋਨੇ ਤੋਂ ਬਾਅਦ ਕਣਕ", "soil_report")
    assert found["district"].value == "bathinda"
    assert found["land_area"].value["acres"] == 5
    assert found["water_source"].value == "canal"
    assert found["previous_crop"].value == "paddy"
    assert found["usual_crop"].value == "wheat"
