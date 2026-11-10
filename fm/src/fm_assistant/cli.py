"""`fm` command line: thin wrapper over the fm_assistant library. --json puts a machine envelope on stdout."""
import json
import sys

import click

from datetime import date, timedelta

from . import budget, players as players_mod, squad as squad_mod, staff as staff_mod, training as training_mod, watch as watch_mod
from . import doctor as doctor_mod
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


def shown(res: dict) -> str:
    return f"{res['returned']} of {res['count']} shown" if res.get("truncated") else f"{res['returned']} shown"


def slots_text(slots: dict) -> str:
    return ", ".join(f"{k} {v['used']}/{v['max']}" for k, v in slots.items())


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
    emit(st, s, table([[p["name"], p.get("age"), p["position"], p.get("condition"), p.get("injured")]
                       for p in s["players"]], ["name", "age", "position", "condition", "injured"]))


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
    text = ("Contracts ending within %d days\n" % within
            + table([[e["name"], e["age"], e["end_date"], e["days_left"], budget.fmt(e["wage"])] for e in exp],
                    ["name", "age", "ends", "days left", "wage"])
            + "\n\nInjured\n"
            + table([[i["name"], i["description"] or "?", i["return_date"] or "?",
                      "?" if i["matches_missed"] is None else (f"≥{i['matches_missed']}" if i["beyond_view"] else i["matches_missed"])]
                     for i in inj], ["name", "injury", "back", "matches missed"]))
    emit(st, {"today": today.isoformat(), "expiring": exp, "injured": inj}, text)


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
                          budget.fmt(p.get("wage")), p.get("scout_rating")] for p in res["rows"]],
                        ["name", "age", "position", "price", "wage", "scout"])
         + f"\n{shown(res)}" + (f", {len(res['rows'])} affordable" if affordable else ""))


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


if __name__ == "__main__":
    sys.exit(main())
