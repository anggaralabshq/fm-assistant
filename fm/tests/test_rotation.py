import json
from datetime import date

from fm_assistant import rolefit, rotation

from helpers import fixture
from test_cli import HELLO, fake_calls, run

TODAY = date(2026, 9, 14)


def sq(uid, mask, condition=95, injured=False):
    return {"uid": uid, "name": f"Pemain {uid}", "position_mask": mask, "condition": condition, "injured": injured}


def fx(day, n=1):
    return {"date": f"2026-09-{day:02d}", "opponent": {"uid": 900000 + n, "name": f"Lawan {n}"}, "home": True,
            "competition": "Liga"}


# XI from tests/fixtures/tactic.json; 105 injured (D L), 106 tired (DM), 107 left, slot 9 empty
PLAYERS = [sq(101, 1), sq(102, 4), sq(103, 16), sq(104, 16), sq(105, 8, -1, True), sq(106, 128, 70), sq(108, 1024),
           sq(109, 2048), sq(111, 16384),
           # bench
           sq(201, 8, 99), sq(202, 8, 80), sq(203, 8 | 16, 97), sq(204, 8, 95), sq(205, 8, -1, True),   # D (L) covers
           sq(206, 128, 92), sq(207, 16384, 99)]
SQUAD = {"players": PLAYERS}
FORM = [{"uid": 201, "last5_rating": 7.1}, {"uid": 202, "last5_rating": 6.0}, {"uid": 203, "last5_rating": None},
        {"uid": 204, "last5_rating": 7.5}, {"uid": 206, "last5_rating": 6.8}]
TWO = [fx(16, 1), fx(20, 2)]


def hints(upcoming=TWO, players=PLAYERS, **kw):
    rows = rolefit.check(fixture("tactic.json"), {"players": players})
    return rotation.hints(rows, players, upcoming, TODAY, FORM, **kw)


def test_no_hints_without_congestion():
    h = hints([fx(16, 1), fx(28, 2)])   # second match is outside the 7 day window
    assert h == {"matches_in_window": 1, "at_risk": [], "options": {}}
    assert hints([])["matches_in_window"] == 0
    assert "no congested fixtures in the next 7 days" in rotation.text(h, 7)


def test_injured_xi_player_at_risk():
    h = hints()
    assert h["matches_in_window"] == 2
    risk = {r["slot"]: r for r in h["at_risk"]}
    assert set(risk) == {4, 5}   # injured D (L) and tired DM; the empty slot and the player who left are skipped
    assert risk[4]["player"]["uid"] == 105 and risk[4]["injured"] is True
    assert risk[5]["condition"] == 70
    assert hints(condition_min=60)["at_risk"][0]["slot"] == 4   # only the injured one is left


def test_options_cover_slot_and_exclude_xi():
    h = hints()
    ids = lambda slot: [o["uid"] for o in h["options"][slot]]
    assert ids(4) == [201, 203, 204]   # D (L): condition desc, max 3; injured 205 and the tired-but-fit 202 trail
    assert ids(5) == [206]             # DM: bench only, XI player 106 excluded
    for slot, opts in h["options"].items():
        label = next(r["position_label"] for r in rolefit.check(fixture("tactic.json"), SQUAD) if r["index"] == slot)
        assert all(o["natural"] is True for o in opts)
        assert not {o["uid"] for o in opts} & {101, 102, 103, 104, 105, 106, 108, 109, 111}, label
    assert h["options"][4][0]["last5_rating"] == 7.1


def test_options_tiebreak_last5_null_last():
    ps = PLAYERS + [sq(210, 8, 97), sq(211, 8, 97)]
    form = FORM + [{"uid": 210, "last5_rating": 6.0}, {"uid": 211, "last5_rating": 7.0}]
    rows = rolefit.check(fixture("tactic.json"), {"players": ps})
    h = rotation.hints(rows, ps, TWO, TODAY, form)
    assert [o["uid"] for o in h["options"][4]] == [201, 211, 210]   # 99 first; 97s by last5 desc; 203 (null) falls off


def test_rotation_cli(monkeypatch):
    fixtures = {**fixture("fixtures.json"), "today": "2026-09-14", "upcoming": TWO}
    form = {"today": "2026-09-14", "team": "first", "concerns": [], "players": [
        {"uid": f["uid"], "name": "x", "season": [], "last5": {"rating": f["last5_rating"], "valid": f["last5_rating"] is not None,
                                                              "minutes": [90]}} for f in FORM]}
    calls = fake_calls(monkeypatch, {"hello": HELLO, "squad": SQUAD, "tactic": fixture("tactic.json"),
                                     "fixtures": fixtures, "form": form})
    r = run("--json", "squad", "rotation", "--days", "7")
    assert r.exit_code == 0, r.output + r.stderr
    res = json.loads(r.stdout)["result"]
    assert res["matches_in_window"] == 2 and res["window_days"] == 7
    assert ("squad", {"team": "first"}) in calls and ("form", {"team": "first"}) in calls
    text = run("squad", "rotation").stdout
    assert "Pemain 105" in text and "Pemain 201" in text
    for word in ("should", "change", "ganti", "recommend"):
        assert word not in text.lower()
