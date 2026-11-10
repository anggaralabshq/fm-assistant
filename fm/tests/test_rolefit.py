import json

from fm_assistant import rolefit

from helpers import fixture
from test_cli import HELLO, fake_calls, run


def sq(uid, mask, condition=95, injured=False, **extra):
    return {"uid": uid, "name": f"Pemain {uid}", "position_mask": mask, "condition": condition, "injured": injured, **extra}


# squad matching tests/fixtures/tactic.json (slot 9 AM (L) is empty); 104 plays out of position, 105 is injured,
# 106 is tired, 107 has left the club (not in the squad list)
SQUAD = {"players": [sq(101, 1), sq(102, 4), sq(103, 16), sq(104, 128, best_oop_role="Libero"), sq(105, 8, -1, True),
                     sq(106, 128, 70), sq(108, 1024), sq(109, 2048), sq(111, 16384), sq(120, 4096)]}


def by_index(rows):
    return {r["index"]: r for r in rows}


def test_empty_slot_and_injured_player():
    rows = by_index(rolefit.check(fixture("tactic.json"), SQUAD))
    assert len(rows) == 11
    empty = rows[9]
    assert empty["player"] is None and empty["natural"] is None and empty["injured"] is None
    assert empty["position_label"] == "AM (L)"
    assert rows[4]["injured"] is True and rows[4]["player"] == {"uid": 105, "name": "Pemain 105"}
    left = rows[6]   # in the tactic but gone from the squad: listed, nothing known, no crash
    assert left["player"]["uid"] == 107 and left["natural"] is None and left["injured"] is None and left["condition"] is None


def test_natural_uses_covers():
    rows = by_index(rolefit.check(fixture("tactic.json"), SQUAD))
    assert rows[0]["natural"] is True                      # GK
    assert rows[3]["natural"] is False                     # DM-only player in D (C)
    assert rows[3]["best_oop_role"] == "Libero"
    assert rows[2]["best_oop_role"] is None
    assert rows[5]["natural"] is True and rows[5]["condition"] == 70


def test_unknown_slot_label_gives_natural_none():
    tactic = {**fixture("tactic.json")}
    tactic["slots"] = [{**tactic["slots"][0], "position_label": "Libero?"}]
    assert rolefit.check(tactic, SQUAD)[0]["natural"] is None


def test_tactic_text_has_no_advice_words(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "tactic": fixture("tactic.json"), "squad": SQUAD})
    r = run("tactic")
    assert r.exit_code == 0, r.output + r.stderr
    low = r.stdout.lower()
    assert not any(w in low for w in ("should", "change", "ganti", "suggest", "recommend"))
    assert "Serangan Cepat" in r.stdout and "empty" in low
    assert "out of position: Pemain 104" in r.stdout
    assert "injured/tired in XI:" in r.stdout and "Pemain 105" in r.stdout and "Pemain 106" in r.stdout


def test_tactic_json_shape(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "tactic": fixture("tactic.json"), "squad": SQUAD})
    res = json.loads(run("--json", "tactic").stdout)["result"]
    assert ("squad", {"team": "first"}) in calls
    assert set(res) == {"name", "mentality", "slots", "fit"} and len(res["fit"]) == 11
    assert set(res["fit"][0]) == {"index", "position_label", "role", "player", "natural", "injured", "condition",
                                  "best_oop_role"}
