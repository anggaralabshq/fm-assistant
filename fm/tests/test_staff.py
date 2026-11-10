import json

import pytest

from fm_assistant import staff

from helpers import fixture

ROLES = {"coach_attacking": {"Attacking": 3, "Technical": 2, "Tactical": 1, "Determination": 1, "Motivating": 1}}


def test_score_weighted_mean():
    s = fixture("staff_search.json")["rows"][0]
    # (16*3 + 14*2 + 12 + 15 + 13) / 8 = 116 / 8 = 14.5
    assert staff.score(s, "coach_attacking", ROLES) == 14.5


def test_score_skips_missing_attributes():
    assert staff.score({"attributes": {"Attacking": 20}}, "coach_attacking", ROLES) == 20.0
    assert staff.score({"attributes": {}}, "coach_attacking", ROLES) == 0.0


def test_rank_orders_by_score():
    ranked = staff.rank(fixture("staff_search.json")["rows"], "coach_attacking", None, ROLES)
    assert [r["uid"] for r in ranked] == [12, 11, 13]
    assert all("score" in r for r in ranked)


def test_rank_drops_only_known_over_budget():
    ranked = staff.rank(fixture("staff_search.json")["rows"], "coach_attacking", 1000, ROLES)
    assert [r["uid"] for r in ranked] == [11, 13]
    assert [r["over_budget"] for r in ranked] == [False, None]


def test_packaged_roles_have_the_plan_keys():
    roles = staff.load_roles(user_path=None)
    assert {"coach_attacking", "coach_defending", "coach_fitness", "scout", "recruitment_analyst", "performance_analyst",
            "physio", "sports_scientist", "set_piece_coach", "director_of_football"} <= roles.keys()
    assert roles["scout"] == {"JudgingPlayerAbility": 3, "JudgingPlayerPotential": 3, "Adaptability": 1}


def test_role_override_merges(tmp_path):
    p = tmp_path / "staff_roles.json"
    p.write_text(json.dumps({"scout": {"JudgingPlayerAbility": 5}}))
    roles = staff.load_roles(user_path=p)
    assert roles["scout"] == {"JudgingPlayerAbility": 5, "JudgingPlayerPotential": 3, "Adaptability": 1}
    assert roles["physio"] == staff.load_roles(user_path=None)["physio"]


def test_unknown_role_lists_valid_keys():
    with pytest.raises(ValueError) as e:
        staff.score({"attributes": {}}, "chef", ROLES)
    assert "coach_attacking" in str(e.value)
