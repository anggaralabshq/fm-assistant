"""Plans: <PLANS_DIR>/<id>.json. Status: proposed, applied, partial, failed, refused."""
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from . import actions

PLANS_DIR = Path(os.environ.get("FM_ASSISTANT_PLANS_DIR") or Path.home() / ".fm-assistant" / "plans")
ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")


def create(acts: list, reason: str, summary: str, root=None) -> dict:
    if not acts:
        raise ValueError("a plan needs at least one action")
    items = []
    for a in acts:
        args = actions.validate(a.get("kind"), a.get("args", {}))
        items.append({"kind": a["kind"], "args": args, "describe": actions.REGISTRY[a["kind"]].describe(args)})
    now = datetime.now()
    plan = {"id": f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "created": now.isoformat(timespec="seconds"),
            "status": "proposed", "reason": reason, "summary": summary or "; ".join(i["describe"] for i in items),
            "actions": items}
    update(plan, root)
    return plan


def _path(plan_id: str, root) -> Path:
    if not ID.fullmatch(str(plan_id)):
        raise ValueError(f"bad plan id {plan_id!r}")
    return Path(root or PLANS_DIR) / f"{plan_id}.json"


def update(plan: dict, root=None) -> None:
    p = _path(plan["id"], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2))


def load(plan_id: str, root=None) -> dict:
    try:
        return json.loads(_path(plan_id, root).read_text())
    except FileNotFoundError:
        raise ValueError(f"no plan {plan_id}") from None


def list_plans(status: str | None = None, root=None) -> list:
    d = Path(root or PLANS_DIR)
    plans = [json.loads(f.read_text()) for f in sorted(d.glob("*.json"))] if d.is_dir() else []
    return [p for p in plans if status in (None, p["status"])]
