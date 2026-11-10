"""`fm` command line: thin wrapper over the fm_assistant library. --json puts a machine envelope on stdout."""
import json
import sys

import click

from datetime import date, timedelta

from . import budget, players as players_mod, squad as squad_mod, staff as staff_mod, training as training_mod, watch as watch_mod
from . import contracts as contracts_mod
from . import depth as depth_mod
from . import briefing as briefing_mod
from . import fixtures as fixtures_mod
from . import stars as stars_mod
from . import rolefit as rolefit_mod
from . import trends as trends_mod
from . import rotation as rotation_mod
from . import inbox as inbox_mod
from . import form as form_mod
from . import loans as loans_mod
from . import vacancies as vacancies_mod
from . import doctor as doctor_mod
from . import apply as apply_mod, audit as audit_mod, plans as plans_mod
from . import game as game_mod
from .client import FmClient, FmError, FmUnavailable

UNAVAILABLE = "FM27 is not running with the assistant plugin. Start it from Steam."


class State:
    def __init__(self, as_json: bool):
        self.json = as_json
        self.build_supported = None


def human_error(e: FmError) -> str:
    if e.code == "no-career-loaded":
        return "No career loaded."
    if e.code == "wrong-screen":
        screen = e.detail.removeprefix("expected ").split(",")[0] if e.detail.startswith("expected ") else e.detail
        return f"Open {screen} first."
    if e.code == "timeout":
        return f"FM27 did not answer in time ({e.op}). It may be on a heavy screen or still loading; try again."
    if e.code == "busy":
        return "FM27 is busy with other requests. Try again in a moment."
    if e.code == "bindings-not-captured":
        return "FM27 is still starting. Try again in a moment."
    return f"{e.code}: {e.detail}"


class FmGroup(click.Group):
    """Maps library errors to one stderr line and an exit code (2 unavailable, 3 game-side error/refusal)."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except FmUnavailable as e:
            fail(ctx, 2, "unavailable", str(e), UNAVAILABLE)
        except FmError as e:
            fail(ctx, 3, e.code, e.detail, human_error(e))
        except game_mod.Refused as e:
            fail(ctx, 3, "refused", str(e), str(e))
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            # ponytail: unexpected data shape (renamed game property, untested build) -> one line, no traceback
            fail(ctx, 3, "internal", f"{type(e).__name__}: {e}",
                 f"Unexpected data from the game ({type(e).__name__}: {e}). Run `fm doctor`; the game build may be untested.")


def fail(ctx, code: int, err: str, detail: str, message: str):
    st = ctx.find_object(State)
    if st and st.json:
        click.echo(json.dumps({"ok": False, "error": {"code": err, "detail": detail}}, ensure_ascii=False))
    click.echo(message, err=True)
    ctx.exit(code)


def check_build(st: State, h: dict) -> None:
    st.build_supported = h.get("build_supported")
    if st.build_supported is False:
        click.echo(f"warning: game build {h.get('game_build')} is not tested with this plugin "
                   f"(tested: {', '.join(h.get('tested_builds', []))})", err=True)


def need_hello(st: State) -> dict:
    """hello before a data command: surfaces an unsupported build once per command."""
    h = FmClient().call("hello")
    check_build(st, h)
    return h


def emit(st: State, result, text: str | None = None) -> None:
    if st.json:
        click.echo(json.dumps({"ok": True, "build_supported": st.build_supported, "result": result}, ensure_ascii=False))
    else:
        click.echo(text if text is not None else json.dumps(result, ensure_ascii=False, indent=2))


def kv(d: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in d.items())


@click.group(cls=FmGroup)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable envelope on stdout.")
@click.pass_context
def main(ctx, as_json):
    """Read-only FM27 assistant manager."""
    ctx.obj = State(as_json)


@main.group()
def game():
    """Start, restart and load the game (never saves)."""


@game.command()
@click.pass_obj
def status(st):
    s = game_mod.status()
    if s.get("running"):
        check_build(st, s)
    emit(st, s, kv(s))


@game.command()
@click.pass_obj
def launch(st):
    h = game_mod.launch()
    check_build(st, h)
    emit(st, h, kv(h))


@game.command("load-recent")
@click.pass_obj
def load_recent(st):
    h = game_mod.load_recent()
    check_build(st, h)
    emit(st, h, kv(h))


@game.command()
@click.option("--load", is_flag=True, help="Load the most recent save after the restart.")
@click.option("--allow-career", is_flag=True, help="Allow killing a career this tool loaded itself.")
@click.pass_obj
def restart(st, load, allow_career):
    h = game_mod.restart(load, allow_career)
    check_build(st, h)
    emit(st, h, kv(h))


@main.command()
@click.pass_obj
@click.pass_context
def doctor(ctx, st):
    """Check loader, plugin, build and one read per feature."""
    items = doctor_mod.run()
    lines = [f"{'ok  ' if i['ok'] else ('warn' if i['check'] == 'game build supported' else 'FAIL')} "
             f"{i['check']}{': ' + i['detail'] if i['detail'] else ''}" for i in items]
    emit(st, items, "\n".join(lines))
    if any(not i["ok"] and i["check"] != "game build supported" for i in items):
        ctx.exit(1)


@main.command()
@click.argument("op")
@click.argument("args", default="{}")
@click.pass_obj
def call(st, op, args):
    """Developer aid: send one raw op with JSON args, e.g. fm call prop_check '{"names": ["Wage"]}'."""
    emit(st, FmClient(timeout=95).call(op, **json.loads(args)))


def table(rows: list[list], header: list[str]) -> str:
    rows = [[("" if c is None else str(c)) for c in r] for r in [header, *rows]]
    w = [max(len(r[i]) for r in rows) for i in range(len(header))]
    return "\n".join("  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip() for r in rows)


def star_cols(p: dict) -> list[str]:
    return [stars_mod.fmt(p["stars"]["current"]), stars_mod.fmt(p["stars"]["potential"])]


def warn_line(res: dict) -> str:
    return "\nwarnings: " + "; ".join(map(str, res["warnings"])) if res.get("warnings") else ""


def shown(res: dict) -> str:
    return f"{res['returned']} of {res['count']} shown" if res.get("truncated") else f"{res['returned']} shown"


def slots_text(slots: dict) -> str:
    return ", ".join(f"{k} {v['used']}/{v['max']}" for k, v in slots.items())


@main.command("briefing")
@click.option("--no-snapshot", is_flag=True, help="Do not save today's trend snapshot.")
@click.pass_obj
def briefing_cmd(st, no_snapshot):
    """Session briefing: next match, injuries, tired, contracts, concerns, form, vacancies, loans (no slow searches)."""
    need_hello(st)
    c = FmClient()
    parts = {}
    for op, args in (("squad", {"team": "first"}), ("training", {}), ("fixtures", {"n": 5}), ("form", {"team": "first"}),
                     ("club", {}), ("loans", {})):
        try:
            parts[op] = c.call(op, **args)
        except FmError as e:  # one failed part never hides the others; FmUnavailable still stops the command
            parts[op] = {"error": e.code}
    today = (parts.get("squad") or {}).get("today") or (parts.get("fixtures") or {}).get("today")
    since = (date.fromisoformat(today) - timedelta(days=1)).isoformat() if today else None
    try:
        parts["inbox"] = c.call("inbox", since=since, tab="all", max=20)
    except FmError as e:
        parts["inbox"] = {"error": e.code}
    b = briefing_mod.build(parts)
    if not no_snapshot and all(isinstance(parts.get(k), dict) and "error" not in parts[k] for k in ("club", "squad", "form")):
        try:
            trends_mod.save(trends_mod.snapshot(parts["club"], parts["squad"], parts["form"]))
        except (OSError, KeyError, TypeError, ValueError):  # a snapshot problem never hides the briefing
            click.echo("warning: could not save the trend snapshot", err=True)
    emit(st, b, briefing_mod.text(b))


@main.command("inbox")
@click.option("--since", help="Only messages on or after this date (YYYY-MM-DD).")
@click.option("--unread", is_flag=True, help="Unread messages only.")
@click.option("--max", "max_", type=click.IntRange(1, 200), default=20, show_default=True)
@click.pass_obj
def inbox_cmd(st, since, unread, max_):
    """Inbox messages, newest first ('*' unread, '!' important)."""
    need_hello(st)
    res = FmClient().call("inbox", since=since, tab="unread" if unread else "all", max=max_)
    emit(st, res, inbox_mod.text(res, since))


def _snapshot() -> dict:
    c = FmClient()
    return trends_mod.snapshot(c.call("club"), c.call("squad", team="first"), c.call("form", team="first"))


@main.command("snapshot")
@click.pass_obj
def snapshot_cmd(st):
    """Save today's club and squad state for trends (kept in ~/.fm-assistant/snapshots, not in the repo)."""
    need_hello(st)
    snap = _snapshot()
    path = trends_mod.save(snap)
    emit(st, {"path": str(path), "date": snap["date"], "players": len(snap["players"])}, f"saved {path}")


@main.command("trends")
@click.pass_obj
def trends_cmd(st):
    """Save today's snapshot, then compare with the latest earlier one of this club."""
    need_hello(st)
    snap = _snapshot()
    later = trends_mod.later_snapshot(snap["club_uid"], snap["date"])
    prev = None if later else trends_mod.load_previous(snap["club_uid"], snap["date"])   # read before saving
    path = trends_mod.save(snap)
    d = trends_mod.diff(prev, snap) if prev else None
    emit(st, {"saved": str(path), "date": snap["date"], "previous": prev and prev["date"], "diff": d,
              "later_snapshot": later}, trends_mod.text(snap, prev, d, later))


@main.group()
def club():
    """Club finances."""


@club.command("budget")
@click.pass_obj
def club_budget(st):
    need_hello(st)
    c = FmClient().call("club")
    c["wage_headroom"] = budget.wage_headroom(c)
    emit(st, c, kv({"club": c["name"], "balance": budget.fmt(c.get("balance")), "status": c.get("financial_status"),
                    "transfer budget": budget.fmt(c["transfer_budget"]), "wage budget": budget.fmt(c["wage_budget"]),
                    "wage committed": budget.fmt(c["wage_committed"]),
                    "wage headroom": budget.fmt(c.get("wage_remaining")),
                    "staff slots": slots_text(c["staff_slots"])}))


@main.group()
def squad():
    """Squad overview."""


@squad.command("list")
@click.option("--team", type=click.Choice(["first", "reserve", "youth"]), default="first", show_default=True)
@click.pass_obj
def squad_list(st, team):
    need_hello(st)
    s = squad_mod.normalize(FmClient().call("squad", team=team))
    emit(st, s, table([[p["name"], p.get("age"), p["position"], p.get("condition"), p.get("injured"),
                        *star_cols(p)] for p in s["players"]],
                      ["name", "age", "position", "condition", "injured", "ability", "potential"]) + warn_line(s))


@squad.command("watch")
@click.option("--within", type=click.IntRange(0), default=180, show_default=True, help="Contract window in days.")
@click.option("--team", type=click.Choice(["first", "reserve", "youth"]), default="first", show_default=True)
@click.pass_obj
def squad_watch(st, within, team):
    need_hello(st)
    s = FmClient().call("squad", team=team)
    today = date.fromisoformat(s["today"])
    days, _ = _training_days()
    exp = watch_mod.expiring(s["players"], today, within)
    inj = watch_mod.injuries(s["players"], today, days)
    if team != "first":  # the training calendar is the first team's: its matches are not this team's
        inj = [{**i, "matches_missed": None, "beyond_view": False} for i in inj]
    text = ("Contracts ending within %d days\n" % within
            + table([[e["name"], e["age"], e["end_date"], e["days_left"], budget.fmt(e["wage"])] for e in exp],
                    ["name", "age", "ends", "days left", "wage"])
            + "\n\nInjured\n"
            + table([[i["name"], i["description"] or "?", i["return_date"] or "?",
                      "?" if i["matches_missed"] is None else (f"≥{i['matches_missed']}" if i["beyond_view"] else i["matches_missed"])]
                     for i in inj], ["name", "injury", "back", "matches missed"]))
    emit(st, {"today": today.isoformat(), "expiring": exp, "injured": inj}, text)


@squad.command("contracts")
@click.option("--team", type=click.Choice(["first", "reserve", "youth"]), default="first", show_default=True)
@click.pass_obj
def squad_contracts(st, team):
    """Contract end, squad status, release clause and the game's advised wage cap per status."""
    need_hello(st)
    c = FmClient()
    s = c.call("squad", team=team)
    structure = c.call("club")["wage_structure"]
    today = date.fromisoformat(s["today"])
    rows = contracts_mod.table(s["players"], structure, today)
    flag = {True: "yes", False: "no", None: "?"}
    text = (table([[r["name"], r["age"], (r["squad_status"] or {}).get("display"), r["end_date"], r["days_left"],
                    budget.fmt(r["wage"]), budget.fmt(r["release_clause"]) if r["release_clause"] else "none",
                    flag[r["renewal_offer"]], r["advised_max"]] for r in rows],
                   ["name", "age", "status", "ends", "days left", "wage", "release", "renewal offer", "advice for status"])
            + "\n\nWage structure\n"
            + table([[w["status"], w["count"], w["average"], w["highest"], w["lowest"], w["advised_max"],
                      w["total"]["display"], flag[w["over"]]] for w in structure],
                    ["status", "count", "average", "highest", "lowest", "advised max", "total", "over"]))
    emit(st, {"today": today.isoformat(), "players": rows, "wage_structure": structure}, text)


@squad.command("form")
@click.option("--team", type=click.Choice(["first", "reserve", "youth"]), default="first", show_default=True)
@click.pass_obj
def squad_form(st, team):
    """Season rating, last five matches and squad concerns. 'no matches yet' = nothing played, not bad form."""
    need_hello(st)
    f = FmClient().call("form", team=team)
    rows = form_mod.summary(f)
    fl = form_mod.flags(rows)

    def rate(v, none="no matches yet"):
        return none if v is None else f"{v:.2f}"

    def names(key):
        return ", ".join(r["name"] for r in fl[key]) or "none"

    text = (table([[r["name"], r["apps"], rate(r["rating"]), rate(r["last5_rating"], "-"), r["last5_minutes"],
                    "-" if r["morale"] is None else f"{r['morale']} {r['morale_text'] or ''}".strip(),
                    ", ".join(r["unhappy"]), "yes" if r["concern"] else ""] for r in rows],
                  ["name", "apps", "rating", "last 5", "last 5 min", "morale", "unhappy with", "concern"])
            + f"\n\nLow form (last 5 under {form_mod.LOW_FORM}): {names('low_form')}"
            + f"\nUnused (no appearances): {names('unused')}"
            + f"\nUnhappy: {names('unhappy')}"
            + f"\nConcerns: {names('concerns')}"
            + f"\nClub atmosphere: {(f.get('atmosphere') or {}).get('text') or '?'}")
    emit(st, {"today": f["today"], "team": f["team"], "players": rows, "flags": fl,
              "atmosphere": f.get("atmosphere")}, text)


@squad.command("loans")
@click.pass_obj
def squad_loans(st):
    """Players out on loan with their appearances, and the next youth intake."""
    need_hello(st)
    res = loans_mod.normalize(FmClient().call("loans"))
    flagged = loans_mod.flags(res["out"], date.fromisoformat(res["today"]))
    if res["out"]:
        head = "Out on loan\n" + table(
            [[l["name"], l.get("age"), l["club"]["name"], l.get("start_date"), l.get("end_date"), l["apps"],
              "no matches yet" if l["rating"] is None else f"{l['rating']:.2f}", l.get("agreed_time"),
              l.get("actual_time"), *star_cols(l)] for l in res["out"]],
            ["name", "age", "club", "from", "to", "apps", "rating", "agreed time", "actual time", "ability", "potential"])
    else:
        head = "Out on loan: none"
    text = (head + "\n" + loans_mod.intake_line(res.get("intake"))
            + (f"\nFlagged (no appearances {loans_mod.UNUSED_AFTER_DAYS}+ days into the loan): "
               + ", ".join(l["name"] for l in flagged) if flagged else "") + warn_line(res))
    emit(st, {**res, "flagged": flagged}, text)


@squad.command("rotation")
@click.option("--days", type=click.IntRange(1, 30), default=7, show_default=True, help="Window in days.")
@click.pass_obj
def squad_rotation(st, days):
    """Options for tired or injured XI players when 2+ matches fall in the window (facts, no instructions)."""
    need_hello(st)
    c = FmClient()
    tactic = c.call("tactic")
    sq = c.call("squad", team="first")
    fx = c.call("fixtures", n=10)
    fo = form_mod.summary(c.call("form", team="first"))
    rows = rolefit_mod.check(tactic, sq)
    h = rotation_mod.hints(rows, sq["players"], fx.get("upcoming") or [], date.fromisoformat(fx["today"]), fo, days)
    emit(st, {**h, "window_days": days}, rotation_mod.text(h, days))


def _depth_for(team: str = "first") -> dict:
    s = squad_mod.normalize(FmClient().call("squad", team=team))
    return depth_mod.depth(s["players"], depth_mod.load_minimums(depth_mod.USER_DEPTH))


def depth_text(res: dict) -> str:
    text = table([[s["slot"], f"{s['fit']}/{s['min']}" + (" thin" if s["thin"] else ""), ", ".join(s["names"])]
                  for s in res["slots"]], ["slot", "fit/min", "names"])
    if res["unknown_position"]:
        text += "\nunknown position: " + ", ".join(res["unknown_position"])
    return text


@squad.command("depth")
@click.option("--team", type=click.Choice(["first", "reserve", "youth"]), default="first", show_default=True)
@click.pass_obj
def squad_depth(st, team):
    """Players per position slot (positions only, no formation); thin = fit players below the minimum."""
    need_hello(st)
    res = _depth_for(team)
    emit(st, res, depth_text(res))


@main.command()
@click.option("--n", type=click.IntRange(1, 10), default=5, show_default=True, help="Upcoming fixtures to read.")
@click.pass_obj
def fixtures(st, n):
    """Next fixtures, the assistant's note on the next opponent and its most used formation."""
    need_hello(st)
    res = FmClient().call("fixtures", n=n)
    today = date.fromisoformat(res["today"])

    def with_days(f):
        return f and {**f, "days_until": fixtures_mod.days_until(f, today)}

    out = {**res, "next": with_days(res.get("next")), "upcoming": [with_days(f) for f in res.get("upcoming") or []]}
    emit(st, out, fixtures_mod.text(res))


@main.command("tactic")
@click.pass_obj
def tactic_cmd(st):
    """The active tactic: slots, roles and who plays them, with position fit and condition facts (no advice)."""
    need_hello(st)
    c = FmClient()
    t = c.call("tactic")
    rows = rolefit_mod.check(t, c.call("squad", team="first"))
    emit(st, {**t, "fit": rows}, rolefit_mod.text(t, rows, table))


@main.group()
def staff():
    """Staff search and slots (F11)."""


@staff.command("search")
@click.option("--role", required=True, help="Role key from staff_roles.json, e.g. coach_attacking, scout.")
@click.option("--max-wage", type=float, help="Drop staff whose known wage demand is above this (base-currency value).")
@click.option("--max", "max_", type=click.IntRange(1, 1000), default=1000, show_default=True, help="Rows to read.")
@click.option("--top", type=click.IntRange(1), default=10, show_default=True)
@click.pass_obj
def staff_search(st, role, max_wage, max_, top):
    roles = staff_mod.load_roles()
    if role not in roles:
        raise click.BadParameter(f"valid: {', '.join(sorted(roles))}", param_hint="--role")
    need_hello(st)
    res = FmClient().call("staff_search", max=max_)
    ranked = staff_mod.rank(res["rows"], role, max_wage, roles)[:top]
    out = {**res, "role": role, "rows": ranked}
    emit(st, out, table([[s["score"], s["name"], s.get("age"), s.get("preferred_job"),
                          budget.fmt(s.get("wage_demand")), budget.fmt(s.get("current_wage")), "" if max_wage is None else {True: "over", False: "ok", None: "?"}[s["over_budget"]]]
                         for s in ranked], ["score", "name", "age", "job", "wage demand", "current wage", "budget"])
         + f"\n{shown(res)}")


@staff.command("slots")
@click.pass_obj
def staff_slots(st):
    need_hello(st)
    slots = FmClient().call("club")["staff_slots"]
    emit(st, slots, slots_text(slots))


@staff.command("vacancies")
@click.option("--top", type=click.IntRange(1), default=3, show_default=True, help="Candidates per role.")
@click.pass_obj
def staff_vacancies(st, top):
    """Open staff jobs (below the board's target) with ranked candidates."""
    roles, job_roles = staff_mod.load_roles(), vacancies_mod.load_job_roles()
    need_hello(st)
    c = FmClient()
    club_ = c.call("club")
    res = c.call("staff_search", max=1000)
    own = club_.get("uid")  # the Staff Search filter may include the club's own staff
    pool = {**res, "rows": [r for r in res["rows"] if own is None or r.get("club_uid") != own]}
    jobs = vacancies_mod.fill(vacancies_mod.open_jobs(club_), pool, roles, job_roles, top)
    blocks = []
    for j in jobs:
        head = f"{j['job']}: {j['open']} open" + (f" — {j['summary']}" if j.get("summary") else "")
        if not j["roles"]:
            blocks.append(head + "\n  no role mapping, no candidates")
            continue
        t = table([[s["score"], s["role"], s["name"], s.get("age"), s.get("preferred_job"),
                    budget.fmt(s.get("wage_demand")), budget.fmt(s.get("current_wage"))] for s in j["candidates"]],
                  ["score", "role", "name", "age", "job", "wage demand", "current wage"])
        if not j["matching"]:
            t += (f"\n0 of {j['returned']} searched staff prefer this job: set the game's Staff Search filter"
                  " to this job for better candidates")
        blocks.append(head + "\n" + "\n".join("  " + ln for ln in t.splitlines()))
    text = "\n\n".join(blocks) or "No open staff jobs."
    if res["truncated"]:
        text += f"\nranked among {res['returned']} of {res['count']}"
    emit(st, {"jobs": jobs, "count": res["count"], "returned": res["returned"], "truncated": res["truncated"]}, text)


@main.group()
def players():
    """Player search respecting scouting knowledge (F6)."""


@players.command("search")
@click.option("--max", "max_", type=click.IntRange(1, 1000), default=200, show_default=True)
@click.option("--affordable", is_flag=True, help="Keep players whose known price and wage fit the club budget.")
@click.pass_obj
def players_search(st, max_, affordable):
    need_hello(st)
    c = FmClient()
    res = players_mod.normalize(c.call("player_search", max=max_))
    if affordable:
        club_ = c.call("club")
        res["rows"] = players_mod.affordable(res["rows"], club_["transfer_budget"]["value"], budget.wage_headroom(club_))
    emit(st, res, table([[p["name"], p.get("age"), p["position"], budget.fmt(p.get("asking_price") or p.get("value")),
                          budget.fmt(p.get("wage")), p.get("scout_rating"), *star_cols(p)] for p in res["rows"]],
                        ["name", "age", "position", "price", "wage", "scout", "ability", "potential"])
         + f"\n{shown(res)}" + (f", {len(res['rows'])} affordable" if affordable else "") + warn_line(res))


@players.command("targets")
@click.option("--top", type=click.IntRange(1), default=5, show_default=True, help="Candidates per thin slot.")
@click.option("--max", "max_", type=click.IntRange(1, 1000), default=1000, show_default=True, help="Rows to read.")
@click.pass_obj
def players_targets(st, top, max_):
    """Affordable scouting targets for each thin position slot of the first team."""
    need_hello(st)
    c = FmClient()
    sq = squad_mod.normalize(c.call("squad", team="first"))
    res = depth_mod.depth(sq["players"], depth_mod.load_minimums(depth_mod.USER_DEPTH))
    thin = [s for s in res["slots"] if s["thin"]]
    found = players_mod.normalize(c.call("player_search", max=max_))
    club_ = c.call("club")
    own = (sq.get("club") or {}).get("uid")  # the Player Database filter may include the owner's own club
    others = [r for r in found["rows"] if own is None or r.get("club_uid") != own]
    rows = players_mod.affordable(others, club_["transfer_budget"]["value"], budget.wage_headroom(club_))
    picked = depth_mod.targets(thin, rows, top)
    out = {**res, "targets": picked, "searched": {k: found.get(k) for k in ("count", "returned", "truncated")}}
    parts = [depth_text(res)]
    for s in thin:
        parts.append(f"\n{s['slot']} (fit {s['fit']}/{s['min']})")
        parts.append(table([[p["name"], p.get("age"), p["position"], budget.fmt(p.get("asking_price") or p.get("value")),
                             budget.fmt(p.get("wage")), p.get("scout_rating"), *star_cols(p), "budget?" if p["budget_unknown"] else ""]
                            for p in picked[s["slot"]]], ["name", "age", "position", "price", "wage", "scout", "ability", "potential", ""])
                     if picked[s["slot"]] else "no affordable candidates")
    parts.append(f"\n{shown(found)}, {len(rows)} affordable")
    emit(st, out, "\n".join(parts))


@main.group()
def training():
    """Training calendar and squad load (F10)."""


def _training_days() -> tuple[list, date]:
    cal = FmClient().call("training")
    try:
        return training_mod.with_dates(cal), date.fromisoformat(cal["today"])
    except ValueError as e:
        raise FmError("training", "wrong-screen", f"expected TrainingScreen on the current month ({e})") from e


@training.command("show")
@click.option("--weeks", type=click.IntRange(0), default=2, show_default=True, help="Days from today through today + 7*N.")
@click.pass_obj
def training_show(st, weeks):
    need_hello(st)
    days, today = _training_days()
    end = (today + timedelta(days=7 * weeks)).isoformat()
    days = [d for d in days if today.isoformat() <= d["date"] <= end]
    emit(st, {"today": today.isoformat(), "days": days},
         table([[d["date"], d.get("match") or "", *d["sessions"]] for d in days], ["date", "match", "s1", "s2", "s3"]))


@training.command("load")
@click.pass_obj
def training_load(st):
    need_hello(st)
    days, _ = _training_days()
    load = training_mod.week_load(days, FmClient().call("squad", team="first")["players"])
    text = "\n".join(f"{w}: {v['matches']} match(es); " + ", ".join(f"{k} {n}" for k, n in v["sessions"].items())
                     for w, v in load["weeks"].items())
    text += "\ntired: " + (", ".join(p["name"] for p in load["tired"]) or "none")
    emit(st, load, text)


def _val(s: str):
    try:
        return json.loads(s)
    except ValueError:
        return s


def plan_text(p: dict) -> str:
    return "\n".join([f"{p['id']}  {p['status']}  {p['created']}", f"reason: {p['reason']}", f"summary: {p['summary']}",
                      *(f"{i}. {a['kind']}: {a['describe']}" for i, a in enumerate(p["actions"]))])


@main.group()
def plan():
    """Plans to approve before `fm apply`."""


@plan.command("create")
@click.argument("kind", required=False)
@click.option("--arg", "args_", multiple=True, metavar="K=V", help="Action argument; V is JSON when it parses, else text.")
@click.option("--file", "file_", type=click.Path(exists=True, dir_okay=False), help="JSON list of {kind, args}.")
@click.option("--actions", "actions_", help="The same JSON list, inline.")
@click.option("--reason", required=True)
@click.option("--summary", default="")
@click.pass_context
def plan_create(ctx, kind, args_, file_, actions_, reason, summary):
    st = ctx.find_object(State)
    try:
        if file_ or actions_:
            acts = json.loads(actions_ or open(file_).read())
        elif kind:
            acts = [{"kind": kind, "args": {k: _val(v) for k, _, v in (a.partition("=") for a in args_)}}]
        else:
            raise ValueError("give a kind, --file or --actions")
        p = plans_mod.create(acts, reason, summary)
    except (ValueError, TypeError, AttributeError) as e:
        fail(ctx, 3, "invalid-plan", str(e), f"invalid plan: {e}")
    emit(st, p, plan_text(p))


@plan.command("show")
@click.argument("plan_id")
@click.pass_obj
def plan_show(st, plan_id):
    p = plans_mod.load(plan_id)
    emit(st, p, plan_text(p))


@plan.command("list")
@click.option("--status", type=click.Choice(["proposed", "applied", "partial", "failed", "refused"]))
@click.pass_obj
def plan_list(st, status):
    ps = plans_mod.list_plans(status)
    emit(st, ps, "\n".join(f"{p['id']}  {p['status']}  {p['summary']}" for p in ps) or "no plans")


@main.command("apply")
@click.argument("plan_id")
@click.pass_context
def apply_cmd(ctx, plan_id):
    """Back up the save, then perform an approved plan in the game. Only run after the owner said yes."""
    st = ctx.find_object(State)
    h = need_hello(st)
    res = apply_mod.run(plan_id, FmClient(), h)
    if res.get("error"):     # nothing was sent
        fail(ctx, 3, res["error"]["code"], res["error"]["detail"], res["error"]["detail"])
    lines = []
    for r in res["actions"]:
        word = {"ok": "ok", "failed": "FAIL", "skipped": "SKIP"}[r["status"]]
        why = (r.get("result") or {}).get("answer") if r["status"] == "ok" else \
            f"{r['error']['code']}: {r['error']['detail']}" if r["status"] == "failed" else "not attempted"
        lines.append(f"{word} {r['describe']}: {why}")
    lines.append(f"backup: {res['backup']['path']} (sha256 {res['backup']['sha256'][:12]})")
    emit(st, res, "\n".join(lines))
    if res["status"] != "applied":
        ctx.exit(3)


@main.command("log")
@click.option("--n", type=click.IntRange(1), default=20, show_default=True)
@click.pass_obj
def log_cmd(st, n):
    """Last audit log entries (applies, refusals, aborts)."""
    rows = audit_mod.tail(n)
    emit(st, rows, "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) or "log is empty")


if __name__ == "__main__":
    sys.exit(main())
