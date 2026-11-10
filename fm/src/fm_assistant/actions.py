"""Closed registry of actions the assistant may perform after approval. Nothing outside REGISTRY is ever sent to the plugin."""
from dataclasses import dataclass, field
from datetime import date
from typing import Callable


@dataclass(frozen=True)
class Kind:
    op: str
    required: dict
    optional: dict
    describe: Callable[[dict], str]
    defaults: dict = field(default_factory=dict)
    choices: dict = field(default_factory=dict)     # arg -> allowed values


REGISTRY = {
    "staff.approach": Kind("act_staff_approach", {"uid": int}, {}, lambda a: f"approach staff {a['uid']} to sign"),
    "staff.offer": Kind("act_staff_offer", {"uid": int, "wage": int}, {},
                        lambda a: f"offer staff {a['uid']} a contract at wage {a['wage']}"),
    "shortlist.add": Kind("act_shortlist_add", {"uid": int}, {"months": int},
                          lambda a: f"add player {a['uid']} to the shortlist (months {a['months']})",
                          {"months": 0}, {"months": (0, 1, 3, 6, 12)}),
    "shortlist.remove": Kind("act_shortlist_remove", {"uid": int}, {}, lambda a: f"remove player {a['uid']} from the shortlist"),
    "scout.request_report": Kind("act_scout_request", {"uid": int, "scout_uid": int}, {"duration": str},
                                 lambda a: f"ask scout {a['scout_uid']} for a {a['duration']} report on player {a['uid']}",
                                 {"duration": "week"}, {"duration": ("week", "month", "full")}),
    "training.set_sessions": Kind("act_training_sessions", {"changes": list}, {},
                                  lambda a: f"set {len(a['changes'])} training session(s): "
                                  + ", ".join(f"{c['date']} slot {c['slot']} -> {c['session_type']}" for c in a["changes"])),
    "training.set_focus": Kind("act_training_focus", {"uid": int, "type_row": int}, {},
                               lambda a: f"set individual focus of player {a['uid']} to row {a['type_row']}"),
    "contract.open_renewal": Kind("act_contract_open", {"uid": int}, {}, lambda a: f"open contract renewal talks with player {a['uid']}"),
    "contract.offer_renewal": Kind("act_contract_offer", {"uid": int}, {},
                                   lambda a: f"send the prepared renewal offer to player {a['uid']}"),
}


def _is(v, t):
    return isinstance(v, t) and not (t is int and isinstance(v, bool))


def _change(c, i):
    if not isinstance(c, dict) or set(c) != {"date", "slot", "session_type"}:
        raise ValueError(f"changes[{i}] needs exactly date, slot, session_type")
    try:
        date.fromisoformat(c["date"])
    except (TypeError, ValueError):
        raise ValueError(f"changes[{i}].date must be YYYY-MM-DD") from None
    if not _is(c["slot"], int) or not 0 <= c["slot"] <= 2:
        raise ValueError(f"changes[{i}].slot must be 0-2")
    if not _is(c["session_type"], int):
        raise ValueError(f"changes[{i}].session_type must be an int")


def validate(kind: str, args: dict) -> dict:
    k = REGISTRY.get(kind)
    if k is None:
        raise ValueError(f"unknown kind {kind!r}; allowed: {', '.join(REGISTRY)}")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    allowed = {**k.required, **k.optional}
    if extra := sorted(set(args) - set(allowed)):
        raise ValueError(f"{kind}: unexpected arg(s) {', '.join(extra)}")
    if miss := sorted(set(k.required) - set(args)):
        raise ValueError(f"{kind}: missing arg(s) {', '.join(miss)}")
    out = {**k.defaults, **args}
    for name, t in allowed.items():
        if not _is(out[name], t):
            raise ValueError(f"{kind}: {name} must be {t.__name__}")
        if name in k.choices and out[name] not in k.choices[name]:
            raise ValueError(f"{kind}: {name} must be one of {list(k.choices[name])}")
    if "uid" in out and out["uid"] < 0 or "scout_uid" in out and out["scout_uid"] < 0:
        raise ValueError(f"{kind}: uid must be >= 0")
    if "wage" in out and out["wage"] <= 0:
        raise ValueError(f"{kind}: wage must be > 0")
    if "type_row" in out and out["type_row"] < -1:
        raise ValueError(f"{kind}: type_row must be >= -1")
    if "changes" in out:
        if not 1 <= len(out["changes"]) <= 21:
            raise ValueError(f"{kind}: changes needs 1-21 items")
        for i, c in enumerate(out["changes"]):
            _change(c, i)
    return out
