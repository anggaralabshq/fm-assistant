import pytest

from fm_assistant import actions


def test_validate_rejects_unknown_kind_and_extra_keys():
    with pytest.raises(ValueError, match="unknown kind"):
        actions.validate("staff.fire", {"uid": 1})
    with pytest.raises(ValueError, match="unexpected"):
        actions.validate("staff.approach", {"uid": 1, "wage": 5})
    with pytest.raises(ValueError, match="missing"):
        actions.validate("staff.offer", {"uid": 1})
    with pytest.raises(ValueError, match="uid"):
        actions.validate("staff.approach", {"uid": "7"})
    with pytest.raises(ValueError, match="uid"):
        actions.validate("staff.approach", {"uid": True})
    with pytest.raises(ValueError, match="months"):
        actions.validate("shortlist.add", {"uid": 1, "months": 4})
    with pytest.raises(ValueError, match="duration"):
        actions.validate("scout.request_report", {"uid": 1, "scout_uid": 2, "duration": "year"})
    with pytest.raises(ValueError, match="slot"):
        actions.validate("training.set_sessions", {"changes": [{"date": "2026-09-01", "slot": 3, "session_type": 1}]})
    with pytest.raises(ValueError, match="changes"):
        actions.validate("training.set_sessions", {"changes": []})
    with pytest.raises(ValueError, match="changes"):
        actions.validate("training.set_sessions", {"changes": [{"date": "2026-09-01", "slot": 0, "session_type": 1}] * 22})


def test_validate_fills_defaults():
    assert actions.validate("shortlist.add", {"uid": 5}) == {"uid": 5, "months": 0}
    assert actions.validate("scout.request_report", {"uid": 5, "scout_uid": 9}) == {"uid": 5, "scout_uid": 9, "duration": "week"}
    assert actions.validate("training.set_focus", {"uid": 5, "type_row": -1}) == {"uid": 5, "type_row": -1}
    ch = {"date": "2026-09-01", "slot": 2, "session_type": 4}
    assert actions.validate("training.set_sessions", {"changes": [ch]}) == {"changes": [ch]}
