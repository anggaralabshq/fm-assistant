"""Apply an approved plan: refuse on untested build, back up, then one action at a time with a one-use token."""
import json
import os
import secrets
from pathlib import Path

from . import actions, audit, backup, plans
from .client import FmError, FmUnavailable

APPLY_DIR = Path(os.environ.get("FM_ASSISTANT_APPLY_DIR") or Path.home() / ".fm-assistant" / "apply")


def _stop(plan: dict, status: str, code: str, detail: str, **extra) -> dict:
    """Nothing was sent. Audit it; `status` is the plan status afterwards."""
    audit.write({"plan_id": plan["id"], "result": code, **extra, "detail": detail})
    return {"plan_id": plan["id"], "status": status, "error": {"code": code, "detail": detail}, "actions": []}


def run(plan_id: str, client, hello: dict) -> dict:
    try:
        plan = plans.load(plan_id)
        if plan["status"] == "proposed" and hello.get("build_supported") is not True:
            plan["status"] = "refused"
            plans.update(plan)
            return _stop(plan, "refused", "refused", f"actions are disabled on untested build {hello.get('game_build')}")
        actions.check_plan([a["kind"] for a in plan["actions"]])
        for a in plan["actions"]:          # the file on disk may have been edited since the approval box
            if actions.validate(a["kind"], a["args"]) != a["args"]:
                raise ValueError(f"plan {plan_id} action {a['kind']} args changed on disk")
        plan = plans.claim(plan_id)
    except ValueError as e:
        audit.write({"plan_id": str(plan_id), "result": "bad-plan", "detail": str(e)})
        raise
    try:
        bk = backup.make()
    except backup.BackupError as e:
        plans.release(plan)
        return _stop(plan, "proposed", "backup-failed", str(e))

    APPLY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    done, stopped, tokens = [], False, []
    try:
        for i, a in enumerate(plan["actions"]):
            row = {"index": i, "kind": a["kind"], "describe": a["describe"]}
            entry = {"plan_id": plan["id"], "index": i, "kind": a["kind"], "args": a["args"], "backup_sha256": bk["sha256"]}
            if stopped:
                row["status"] = "skipped"
                audit.write({**entry, "status": "skipped", "result": "skipped"})
                done.append(row)
                continue
            token = secrets.token_hex(16)
            tokens.append(token)
            fd = os.open(APPLY_DIR / token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"plan_id": plan["id"], "index": i, "kind": a["kind"]}, f)
            try:
                res = client.call(actions.REGISTRY[a["kind"]].op, **a["args"], apply_token=token)
                if isinstance(res, dict) and res.get("verified") is True:
                    row.update(status="ok", result=res)
                else:
                    row.update(status="failed", result=res, error=(res.get("error") if isinstance(res, dict) else None)
                               or {"code": "not-verified", "detail": "the read-back did not confirm the action"})
            except FmError as e:
                row.update(status="failed", error={"code": e.code, "detail": e.detail})
            except FmUnavailable as e:
                row.update(status="failed", error={"code": "unavailable", "detail": str(e)})
            finally:
                (APPLY_DIR / token).unlink(missing_ok=True)
            audit.write({**entry, "status": row["status"], "result": row.get("result", {"error": row.get("error")})})
            stopped = row["status"] != "ok"
            done.append(row)
    finally:
        for t in tokens:     # only ours: another apply may be running
            (APPLY_DIR / t).unlink(missing_ok=True)
    ok = sum(r["status"] == "ok" for r in done)
    plan["status"] = "applied" if ok == len(done) else "partial" if ok else "failed"
    plans.update(plan)
    return {"plan_id": plan["id"], "status": plan["status"], "backup": bk, "actions": done}
