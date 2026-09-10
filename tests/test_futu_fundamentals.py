"""Tests for futu_fundamentals -- the point-in-time contract.

No network and no OpenD here. The parsing and the as-of filter are what decide
whether a backtest is honest, so those are what get locked down. A look-ahead
bug in `latest_asof` would silently manufacture alpha that cannot be traded, and
it would look like a great result rather than an error.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import futu_fundamentals as ff


def _rec(periods):
    return {"symbol": "US.TEST", "periods": periods}


def _p(end, avail, **vals):
    return {"period_text": end[:7], "period_end": end, "available_date": avail,
            "values": vals}


# ---------------------------------------------------------------------------
# the as-of filter: this is the whole point of the module
# ---------------------------------------------------------------------------

def test_latest_asof_hides_unpublished_quarters():
    """A quarter that has ENDED but not been REPORTED must be invisible."""
    rec = _rec([_p("2024-03-31", "2024-05-15", roe=10.0),
                _p("2024-06-30", "2024-08-14", roe=20.0)])
    assert ff.latest_asof(rec, "2024-05-14") == {}          # day before print
    assert ff.latest_asof(rec, "2024-05-15")["roe"] == 10.0  # day of print
    assert ff.latest_asof(rec, "2024-08-13")["roe"] == 10.0  # still the old one
    assert ff.latest_asof(rec, "2024-08-14")["roe"] == 20.0


def test_latest_asof_picks_the_most_recent_available_not_the_newest_existing():
    """Out-of-order availability must not return a future quarter."""
    rec = _rec([_p("2023-12-31", "2024-02-14", roe=5.0),
                _p("2024-09-30", "2024-11-14", roe=9.0),
                _p("2024-03-31", "2024-05-15", roe=7.0)])
    assert ff.latest_asof(rec, "2024-06-01")["roe"] == 7.0
    assert ff.latest_asof(rec, "2024-12-01")["roe"] == 9.0


def test_latest_asof_returns_empty_when_nothing_is_known_yet():
    rec = _rec([_p("2026-03-31", "2026-05-15", roe=1.0)])
    assert ff.latest_asof(rec, "2000-01-01") == {}


def test_latest_asof_can_restrict_to_requested_fields():
    rec = _rec([_p("2024-03-31", "2024-05-15", roe=10.0, gross_margin=40.0)])
    only = ff.latest_asof(rec, "2024-06-01", fields=["roe"])
    assert only == {"roe": 10.0}


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def _page(reports, structure=None):
    return {"next_key": "-1",
            "structure_list": structure or [
                {"field_id": 14029, "display_name": "净资产收益率（ROE）"},
                {"field_id": 14002, "display_name": "毛利率"}],
            "report_list": reports}


def test_periods_from_data_maps_field_ids_to_names():
    page = _page([{
        "period_text": "2024/Q1", "date_time_str": "2024-03-31",
        "financial_type": "Q1", "fiscal_year": 2024,
        "item_list": [{"field_id": 14029, "data": 12.5},
                      {"field_id": 14002, "data": 44.0}],
    }])
    reps = ff._periods_from_data(page)
    assert len(reps) == 1
    assert reps[0]["values"]["roe"] == 12.5
    assert reps[0]["values"]["gross_margin"] == 44.0
    assert reps[0]["period_end"] == "2024-03-31"


def test_periods_from_data_applies_the_report_lag():
    page = _page([{"period_text": "2024/Q1", "date_time_str": "2024-03-31",
                   "item_list": []}])
    rep = ff._periods_from_data(page)[0]
    assert rep["available_date"] > rep["period_end"]
    assert rep["available_date"] == "2024-05-15"   # 2024-03-31 + 45d


def test_periods_from_data_falls_back_to_the_display_name():
    """Unknown field ids must not be silently dropped if a name exists."""
    page = _page([{"period_text": "2024/Q1", "date_time_str": "2024-03-31",
                   "item_list": [{"field_id": 99999, "data": 3.0}]}],
                 structure=[{"field_id": 99999, "display_name": "some_metric"}])
    assert ff._periods_from_data(page)[0]["values"]["some_metric"] == 3.0


def test_periods_from_data_skips_rows_without_a_date():
    page = _page([{"period_text": "2024/Q1", "item_list": [{"field_id": 14029, "data": 1.0}]}])
    assert ff._periods_from_data(page) == []


def test_periods_from_data_ignores_non_numeric_values():
    page = _page([{"period_text": "2024/Q1", "date_time_str": "2024-03-31",
                   "item_list": [{"field_id": 14029, "data": "N/A"},
                                 {"field_id": 14002, "data": 44.0}]}])
    vals = ff._periods_from_data(page)[0]["values"]
    assert "roe" not in vals and vals["gross_margin"] == 44.0


def test_periods_from_data_handles_an_empty_payload():
    assert ff._periods_from_data({}) == []
    assert ff._periods_from_data(None) == []


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------

def test_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(ff, "CACHE_DIR", str(tmp_path))
    rec = {"symbol": "US.X", "periods": [_p("2024-03-31", "2024-05-15", roe=1.0)]}
    json.dump(rec, open(ff.cache_path("US.X"), "w", encoding="utf-8"))
    got = ff.load_cache()
    assert "US.X" in got and got["US.X"]["periods"][0]["values"]["roe"] == 1.0


def test_load_cache_ignores_records_without_periods(tmp_path, monkeypatch):
    monkeypatch.setattr(ff, "CACHE_DIR", str(tmp_path))
    json.dump({"symbol": "US.EMPTY", "periods": []},
              open(os.path.join(str(tmp_path), "US_EMPTY.json"), "w", encoding="utf-8"))
    json.dump({"symbol": "US.GOOD", "periods": [_p("2024-03-31", "2024-05-15", roe=2.0)]},
              open(os.path.join(str(tmp_path), "US_GOOD.json"), "w", encoding="utf-8"))
    got = ff.load_cache()
    assert list(got) == ["US.GOOD"]


def test_load_cache_survives_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ff, "CACHE_DIR", str(tmp_path))
    open(os.path.join(str(tmp_path), "bad.json"), "w").write("{not json")
    assert ff.load_cache() == {}


# ---------------------------------------------------------------------------
# writable-dir fallback
# ---------------------------------------------------------------------------

def test_writable_dir_uses_the_first_usable_candidate(tmp_path):
    good = tmp_path / "good"
    other = tmp_path / "other"
    assert ff._writable_dir(str(good), str(other)) == str(good)


def test_writable_dir_skips_an_unusable_candidate(tmp_path, monkeypatch):
    """A path that cannot be written must fall through, not raise."""
    blocked = tmp_path / "blocked"
    good = tmp_path / "good"
    real_makedirs = os.makedirs

    def fake_makedirs(path, *a, **kw):
        if str(path).startswith(str(blocked)):
            raise PermissionError("denied")
        return real_makedirs(path, *a, **kw)

    monkeypatch.setattr(os, "makedirs", fake_makedirs)
    assert ff._writable_dir(str(blocked), str(good)) == str(good)


def test_writable_dir_accepts_a_dir_whose_cleanup_is_blocked(tmp_path, monkeypatch):
    """Regression: a delete shim that refuses os.remove must not disqualify an
    otherwise writable directory.

    This really happened. safe-delete blocks os.remove on this host, and the
    first version of the probe required the cleanup to succeed, so a perfectly
    writable directory was rejected and the code silently fell through to the
    temp dir. Writing is the only property that matters.
    """
    good = tmp_path / "good"
    other = tmp_path / "other"

    def refuse_remove(path, *a, **kw):
        raise PermissionError("delete shim refused")

    monkeypatch.setattr(os, "remove", refuse_remove)
    assert ff._writable_dir(str(good), str(other)) == str(good)


# ---------------------------------------------------------------------------
# configuration guards
# ---------------------------------------------------------------------------

def test_report_lag_is_conservative():
    """Too small a lag leaks the future; anything under a month is unsafe for
    a quarterly report."""
    assert ff.REPORT_LAG_DAYS >= 30


def test_quality_field_ids_are_mapped_to_real_names():
    for fid, name in ff.FIELDS.items():
        assert isinstance(fid, int) and isinstance(name, str) and name
    assert ff.FIELDS[14029] == "roe"
    assert ff.FIELDS[14031] == "roic"
    assert ff.FIELDS[14002] == "gross_margin"
