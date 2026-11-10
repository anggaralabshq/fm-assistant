"""Read-only MCP server (stdio): each tool shells out to `fm --json ...`; the CLI stays the source of truth.

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

    def argv_for(self, args: dict) -> list:
        out = list(self.argv)
        for p in self.params:
            v = args.get(p.name)
            if v is None or v is False:
                continue
            out.append(p.flag)
            if v is not True:
                out.append(str(v))
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
)


def run_tool(tool: Tool, args: dict) -> dict:
    """Run `fm --json ...`; always return the parsed envelope (errors included), never raise."""
    cmd = [sys.executable, "-m", "fm_assistant.cli", "--json", *tool.argv_for(args)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "timeout", "detail": f"fm did not finish within {TIMEOUT}s"}}
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
        srv.add_tool(_make_fn(t), name=t.name, description=t.doc + " Read-only.")
    return srv


def main():
    build_server().run()  # stdio


if __name__ == "__main__":
    main()
