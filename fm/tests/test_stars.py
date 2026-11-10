import json

from fm_assistant import depth, stars

from helpers import fixture
from test_cli import HELLO, fake_calls, run


def R(cmin, cmax, pmin, pmax):
    f = lambda a, b: None if a is None else {"min": a, "max": b}
    return {"current": f(cmin, cmax), "potential": f(pmin, pmax)}


def test_to_stars_scale():
    assert stars.to_stars(18) == 4.0
    assert stars.to_stars(10) == 0.0
    assert stars.to_stars(15) == 2.5
    assert stars.to_stars(20) == 5.0
    # below 10 (youth mapping unverified), -1 (unscouted) and out of range: unknown, never a number
    assert [stars.to_stars(v) for v in (9, 0, -1, 21, None)] == [None] * 5


def test_stars_of_converts_ranges():
    assert stars.of(R(14, 15, 18, 20)) == {"current": [2.0, 2.5], "potential": [4.0, 5.0]}
    assert stars.of(None) == {"current": None, "potential": None}
    assert stars.of(R(None, None, 18, 18)) == {"current": None, "potential": [4.0, 4.0]}


def test_star_value_out_of_range_dropped():
    assert stars.of(R(14, 99, 18, 18))["current"] is None
    assert stars.of(R(-5, 12, 18, 18))["current"] is None
    assert stars.of(R(-1, -1, 18, 18))["current"] is None   # the game's unscouted marker


def test_star_range_text():
    assert [stars.fmt(r) for r in ([3.5, 4.0], [4.0, 4.0], None)] == ["3.5–4", "4", "?"]


def test_unscouted_stars_null_sorted_last():
    young_unscouted = {"name": "U", "age": 17, "position_mask": 16, "budget_unknown": False, "stars_raw": R(-1, -1, -1, -1)}
    old_good = {"name": "G", "age": 33, "position_mask": 16, "budget_unknown": False, "stars_raw": R(16, 16, 16, 16)}
    zero = {"name": "Z", "age": 30, "position_mask": 16, "budget_unknown": False, "stars_raw": R(10, 10, 10, 10)}
    t = depth.targets([{"slot": "D (C)"}], [young_unscouted, zero, old_good], top=3)["D (C)"]
    assert [r["name"] for r in t] == ["G", "Z", "U"]   # 0 stars (scouted) still beats unknown
    assert stars.of(young_unscouted["stars_raw"]) == {"current": None, "potential": None}


def test_targets_quality_before_youth():
    mk = lambda n, age, pot, cur, unk=False: {"name": n, "age": age, "position_mask": 16, "budget_unknown": unk,
                                              "stars_raw": R(cur, cur, pot, pot)}
    rows = [mk("old-high", 31, 20, 18), mk("young-low", 18, 12, 11), mk("mid-pot-high-cur", 25, 16, 16),
            mk("mid-pot-low-cur", 24, 16, 13), mk("same-q-younger", 20, 16, 13), mk("unk-budget", 22, 20, 20, True)]
    t = depth.targets([{"slot": "D (C)"}], rows, top=6)["D (C)"]
    assert [r["name"] for r in t] == ["old-high", "mid-pot-high-cur", "same-q-younger", "mid-pot-low-cur",
                                      "young-low", "unk-budget"]   # budget-known first; then potential, current, younger


def test_squad_list_shows_ability_and_potential(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json")})
    r = run("squad", "list")
    head = r.stdout.splitlines()[0]
    assert "ability" in head and "potential" in head
    assert "4–5" in r.stdout and "3–3.5" in r.stdout and "?" in r.stdout
    res = json.loads(run("--json", "squad", "list").stdout)["result"]
    assert res["players"][0]["stars"] == {"current": [4.0, 4.0], "potential": [4.0, 5.0]}
    assert res["players"][2]["stars"] == {"current": None, "potential": None}


def test_players_search_and_loans_show_stars(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "player_search": fixture("player_search.json"), "loans": fixture("loans.json")})
    r = run("players", "search")
    assert "ability" in r.stdout.splitlines()[0] and "potential" in r.stdout.splitlines()[0] and "2.5–3" in r.stdout
    r = run("squad", "loans")
    assert "potential" in r.stdout.splitlines()[1] and "3.5–4" in r.stdout
    res = json.loads(run("--json", "squad", "loans").stdout)["result"]
    assert res["out"][0]["stars"]["potential"] == [3.5, 4.0]


def test_targets_cli_orders_by_quality_and_shows_stars(monkeypatch, tmp_path):
    monkeypatch.setattr(depth, "USER_DEPTH", tmp_path / "none.json")
    squad = [{"name": f"P{i}", "position_mask": m, "injured": False} for i, m in enumerate([1, 1, 16, 16, 16384, 16384])]
    rows = fixture("player_search.json")
    rows["rows"][0]["position_mask"] = 8192
    fake_calls(monkeypatch, {"hello": HELLO, "squad": {"count": 6, "players": squad},
                             "club": fixture("club.json"), "player_search": rows})
    r = run("--json", "players", "targets", "--max", "50")
    assert r.exit_code == 0, r.output + r.stderr
    t = json.loads(r.stdout)["result"]["targets"]["AM (C)"]
    assert t[0]["stars"]["potential"] == [2.5, 3.0]
    assert "potential" in run("players", "targets", "--max", "50").stdout
