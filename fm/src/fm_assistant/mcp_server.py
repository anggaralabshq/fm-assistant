"""MCP server (stdio), read tools plus plan/apply/log: each tool shells out to `fm --json ...`; the CLI stays the source of truth.

Add a command = add one Tool(...) line to TOOLS.
"""
import inspect
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Annotated, Literal, Optional

try:
    from mcp.server.mcpserver import MCPServer as Server  # mcp 2.x
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server

TIMEOUT = 120  # seconds; the CLI itself waits up to ~95s on a heavy game screen


@dataclass(frozen=True)
class P:
    """One option. Unset (None) or False -> omitted from argv; True -> bare flag."""
    name: str
    type: object
    flag: str
    required: bool = False
    doc: str = ""


@dataclass(frozen=True)
class Tool:
    name: str
    argv: tuple
    doc: str
    params: tuple = ()
    acts: bool = False       # can change the game: description says so instead of "Read-only"
    timeout: int = TIMEOUT

    def argv_for(self, args: dict) -> list:
        out = list(self.argv)
        for p in self.params:
            v = args.get(p.name)
            if v is None or v is False:
                continue
            if p.flag:        # empty flag = positional argument
                out.append(p.flag)
            if v is not True:
                out.append(json.dumps(v) if isinstance(v, (list, dict)) else str(v))
        return out


TOP = P("top", int, "--top", doc="Rows to show.")
MAX = P("max", int, "--max", doc="Rows to read from the game.")
TEAM = P("team", Literal["first", "reserve", "youth"], "--team", doc="first (default), reserve or youth.")

TOOLS = (
    Tool("doctor", ("doctor",), "Check loader, plugin, game build, career and one read per feature."),
    Tool("game_status", ("game", "status"), "Is FM27 running, which build, is a career loaded."),
    Tool("club_budget", ("club", "budget"), "Balance, transfer budget, wage budget/committed/headroom, staff slots."),
    Tool("squad_list", ("squad", "list"), "Squad players with positions, condition, injuries.", (TEAM,)),
    Tool("squad_watch", ("squad", "watch"), "Squad players to watch within a number of days.",
         (P("within", int, "--within", doc="Look-ahead in days."), TEAM)),
    Tool("squad_depth", ("squad", "depth"), "Depth per position.", (TEAM,)),
    Tool("staff_search", ("staff", "search"), "Staff Search rows ranked for a role (scout, physio, coach_attacking...).",
         (P("role", str, "--role", required=True, doc="Role key, e.g. scout."),
          P("max_wage", float, "--max-wage", doc="Drop staff whose known wage demand is above this."), MAX, TOP)),
    Tool("staff_slots", ("staff", "slots"), "Staff slots per department."),
    Tool("staff_vacancies", ("staff", "vacancies"), "Departments with open staff slots and best candidates.", (TOP,)),
    Tool("players_search", ("players", "search"), "Player Database rows as your scouts know them.",
         (MAX, P("affordable", bool, "--affordable", doc="Only players whose known price and wage fit the budget."))),
    Tool("players_targets", ("players", "targets"), "Ranked transfer targets.", (TOP, MAX)),
    Tool("training_show", ("training", "show"), "Training calendar.",
         (P("weeks", int, "--weeks", doc="Days from today through today + 7*N."),)),
    Tool("training_load", ("training", "load"), "Sessions and matches per week, tired players."),
    Tool("briefing", ("briefing",), "Session summary: next match, injuries, tired, contracts, concerns, form, vacancies, loans."),
    Tool("fixtures", ("fixtures",), "Upcoming matches (home/away, competition) and the assistant's note on the next opponent.",
         (P("n", int, "--n", doc="Fixtures to list (max 10)."),)),
    Tool("squad_contracts", ("squad", "contracts"), "Squad status, contract end, release clause, game wage structure.", (TEAM,)),
    Tool("squad_form", ("squad", "form"), "Season and last-five form, unhappy players, club atmosphere.", (TEAM,)),
    Tool("squad_loans", ("squad", "loans"), "Players out on loan with games and rating; youth intake date."),
    Tool("inbox", ("inbox",), "Inbox messages, newest first, with unread and important marks.",
         (P("since", str, "--since", doc="Only messages on or after this date (YYYY-MM-DD)."),
          P("unread", bool, "--unread", doc="Unread messages only."), MAX)),
    Tool("tactic", ("tactic",), "Active tactic: slots, roles, who plays them, out-of-position and tired facts."),
    Tool("squad_rotation", ("squad", "rotation"), "Congested fixtures ahead: tired or injured XI players and options.",
         (P("days", int, "--days", doc="Window in days (default 7)."),)),
    Tool("trends", ("trends",), "Saves today's snapshot, then compares with the latest earlier one."),
    Tool("propose", ("plan", "create"),
         "Write a plan (nothing is sent to the game). Each action is {kind, args}; kinds: staff.approach, staff.offer, "
         "shortlist.add, shortlist.remove, scout.request_report, training.set_sessions, training.set_focus, "
         "contract.open_renewal, contract.offer_renewal. Show the plan to the owner and wait for a yes before apply.",
         (P("actions", list[dict], "--actions", required=True, doc="List of {kind, args}."),
          P("reason", str, "--reason", required=True, doc="Why, for the owner."),
          P("summary", str, "--summary", doc="One line; defaults to the action descriptions."))),
    Tool("plan_show", ("plan", "show"), "Show a plan by id: status, reason and each action.",
         (P("plan_id", str, "", required=True, doc="Plan id."),)),
    Tool("apply", ("apply",),
         "CHANGES THE GAME: backs up the save, then performs the plan's actions. Only call after the owner has "
         "explicitly approved this exact plan in this conversation; the client must ask for confirmation.",
         (P("plan_id", str, "", required=True, doc="Id of a proposed plan."),), acts=True, timeout=900),
    Tool("log", ("log",), "Last audit log entries (applies, refusals, aborts).",
         (P("n", int, "--n", doc="Entries to show (default 20)."),)),
)

WRITES = {"propose"}   # writes a plan file only, never the game


def run_tool(tool: Tool, args: dict) -> dict:
    """Run `fm --json ...`; always return the parsed envelope (errors included), never raise."""
    cmd = [sys.executable, "-m", "fm_assistant.cli", "--json", *tool.argv_for(args)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tool.timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "timeout", "detail": f"fm did not finish within {tool.timeout}s"}}
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = None
    if isinstance(out, dict):
        return out
    return {"ok": False, "error": {"code": "bad-output", "detail": (r.stderr or r.stdout).strip()[-500:]}}


def _make_fn(tool: Tool):
    def fn(**kw):
        return run_tool(tool, kw)

    params = []
    for p in sorted(tool.params, key=lambda p: not p.required):  # required first
        ann = p.type if p.required else Optional[p.type]
        params.append(inspect.Parameter(p.name, inspect.Parameter.KEYWORD_ONLY, annotation=Annotated[ann, p.doc],
                                        default=inspect.Parameter.empty if p.required else None))
    fn.__signature__ = inspect.Signature(params, return_annotation=dict)
    fn.__annotations__ = {q.name: q.annotation for q in params} | {"return": dict}
    fn.__name__ = tool.name
    return fn


def build_server():
    srv = Server("fm-assistant")
    for t in TOOLS:
        srv.add_tool(_make_fn(t), name=t.name, description=t.doc if t.acts or t.name in WRITES else t.doc + " Read-only.")
    return srv


def main():
    build_server().run()  # stdio


if __name__ == "__main__":
    main()
