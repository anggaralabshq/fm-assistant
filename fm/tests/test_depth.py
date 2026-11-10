import json

from fm_assistant import depth, positions

from helpers import fixture
from test_cli import HELLO, fake_calls, run


def P(name, mask, injured=False):
    return {"name": name, "position_mask": mask, "injured": injured}


SQUAD = [
    P("Kiper Satu", 1, injured=True),
    P("Bek Tengah", 16),
    P("Bek Kiri Tengah", 16 | 8),          # D (LC)
    P("Bek Kiri Mod", 16 | 0x100000),      # D (C) with left modifier
    P("Gelandang Bertahan", 128),
    P("Penyerang", 16384),
    P("Tanpa Posisi", 0),
]
MIN2 = {s: 2 for s in positions.SLOTS}


def by_slot(res):
    return {s["slot"]: s for s in res["slots"]}


def test_depth_counts_every_covered_slot():
    res = depth.depth(SQUAD, MIN2)
    s = by_slot(res)
    assert s["D (C)"]["count"] == 3
    assert s["D (L)"]["names"] == ["Bek Kiri Tengah", "Bek Kiri Mod"]
    assert s["D (R)"]["count"] == 0
    assert [x["slot"] for x in res["slots"]] == positions.SLOTS


def test_fit_excludes_injured():
    s = by_slot(depth.depth(SQUAD, MIN2))
    gk = s["GK"]
    assert (gk["count"], gk["fit"], gk["thin"], gk["min"]) == (1, 0, True, 2)
    assert s["D (C)"]["thin"] is False


def test_depth_unknown_mask():
    res = depth.depth(SQUAD, MIN2)
    assert res["unknown_position"] == ["Tanpa Posisi"]
    assert all("Tanpa Posisi" not in s["names"] for s in res["slots"])
    assert depth.depth([P("Cuma Sisi", 0x100000)], MIN2)["unknown_position"] == ["Cuma Sisi"]


def test_minimums_override(tmp_path):
    assert depth.load_minimums(tmp_path / "none.json") == MIN2
    f = tmp_path / "depth.json"
    f.write_text(json.dumps({"GK": 3, "ST (C)": 1}))
    m = depth.load_minimums(f)
    assert (m["GK"], m["ST (C)"], m["DM"]) == (3, 1, 2)
    assert by_slot(depth.depth(SQUAD, m))["ST (C)"]["thin"] is False


def test_targets_order_budget_known_then_young():
    rows = [
        {"name": "A", "age": 30, "position_mask": 16, "budget_unknown": False},
        {"name": "B", "age": 18, "position_mask": 16, "budget_unknown": True},
        {"name": "C", "age": 22, "position_mask": 16, "budget_unknown": False},
        {"name": "D", "age": 19, "position_mask": 16 | 0x100000, "budget_unknown": False},
        {"name": "E", "age": 20, "position_mask": 16384, "budget_unknown": False},
    ]
    slots = [{"slot": "D (C)"}, {"slot": "D (L)"}]
    t = depth.targets(slots, rows, top=4)
    assert [r["name"] for r in t["D (C)"]] == ["D", "C", "A", "B"]
    assert [r["name"] for r in t["D (L)"]] == ["D"]
    assert [r["name"] for r in depth.targets(slots, rows, top=1)["D (C)"]] == ["D"]


def test_players_targets_only_for_thin_slots(monkeypatch, tmp_path):
    monkeypatch.setattr(depth, "USER_DEPTH", tmp_path / "none.json")
    squad = [P(f"Pemain {i}", m) for i, m in enumerate([1, 1, 16, 16, 16384, 16384])]
    # fixture: Eko AM(C) 20, Faisal ST 25, Gilang D(C) 18
    calls = fake_calls(monkeypatch, {"hello": HELLO, "squad": {"count": 6, "players": squad},
                                     "club": fixture("club.json"), "player_search": fixture("player_search.json")})
    r = run("--json", "players", "targets", "--max", "50")
    assert r.exit_code == 0, r.output + r.stderr
    out = json.loads(r.stdout)["result"]
    assert ("squad", {"team": "first"}) in calls and ("player_search", {"max": 50}) in calls
    thin = {s["slot"] for s in out["slots"] if s["thin"]}
    assert not thin & {"GK", "D (C)", "ST (C)"}
    assert "AM (C)" in thin
    assert set(out["targets"]) == thin
    assert [p["name"] for p in out["targets"]["AM (C)"]] == ["Eko Saputra"]
    assert all(positions.covers(p["position_mask"], slot) for slot, ps in out["targets"].items() for p in ps)


def test_squad_depth_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(depth, "USER_DEPTH", tmp_path / "none.json")
    fake_calls(monkeypatch, {"hello": HELLO, "squad": {"count": 1, "players": SQUAD}})
    r = run("squad", "depth")
    assert r.exit_code == 0, r.output + r.stderr
    assert "GK" in r.stdout and "0/2" in r.stdout and "Tanpa Posisi" in r.stdout
