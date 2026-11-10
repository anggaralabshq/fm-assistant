from datetime import date, timedelta

import pytest

from fm_assistant import training

from helpers import fixture


def test_assign_dates_month_view():
    nums = [27, 28, 29, 30, 31, 1, 2, 3, 4, 5]
    dates = training.assign_dates(nums, date(2026, 8, 3))
    assert dates[0] == date(2026, 7, 27)
    assert dates[-1] == date(2026, 8, 5)


def test_assign_dates_ambiguous_raises():
    start = date(2026, 7, 5)
    nums = [(start + timedelta(d)).day for d in range(32)]   # Jul 5 .. Aug 5: the 5th appears twice
    with pytest.raises(ValueError, match="ambiguous"):
        training.assign_dates(nums, date(2026, 8, 5))


def test_assign_dates_today_missing_raises():
    with pytest.raises(ValueError, match="today"):
        training.assign_dates([10, 11, 12], date(2026, 8, 3))


def test_week_load_counts_matches():
    cal = fixture("training.json")
    sq = fixture("squad.json")["players"]
    load = training.week_load(training.with_dates(cal), sq)
    assert load["weeks"]["2026-W31"]["matches"] == 2      # Jul 27 .. Aug 2
    assert load["weeks"]["2026-W32"]["matches"] == 1
    assert load["weeks"]["2026-W31"]["sessions"]["Istirahat"] == 11
    assert [p["name"] for p in load["tired"]] == ["広瀬 圭"]   # condition 81 < 85
