"""`fm` command line: thin wrapper over the fm_assistant library. --json puts a machine envelope on stdout."""
import json
import sys

import click

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


if __name__ == "__main__":
    sys.exit(main())
