"""Staff vacancies (F11): open jobs from the club op, each with ranked candidates from a staff search."""
import json
from importlib import resources
from pathlib import Path

from . import staff as staff_mod

USER_JOB_ROLES = Path.home() / ".fm-assistant" / "job_roles.json"
GROUPS = ("coaching", "recruitment", "medical")


def load_job_roles(user_path: Path | None = USER_JOB_ROLES) -> dict[int, list[str]]:
    """job_type -> role keys. Packaged map, overridden key-by-key by the owner's file when present."""
    raw = json.loads(resources.files("fm_assistant").joinpath("data/job_roles.json").read_text())
    if user_path and Path(user_path).exists():
        raw.update(json.loads(Path(user_path).read_text()))
    return {int(k): list(v) for k, v in raw.items()}


def open_jobs(club: dict) -> list[dict]:
    """Jobs below the board's target, in group order coaching, recruitment, medical."""
    out = []
    slots = club["staff_slots"]
    for group in GROUPS:
        g = slots.get(group) or {}
        for j in g.get("jobs") or []:
            if j["used"] < j["max"]:
                out.append({"group": group, "job": j["job"], "job_type": j["job_type"], "open": j["max"] - j["used"],
                            "summary": g.get("summary"), "board_feedback": g.get("board_feedback")})
    return out


def fill(jobs: list, staff: dict, roles: dict, job_roles: dict, top: int = 3) -> list[dict]:
    """Add roles and candidates to each job. Rows whose preferred_job_type equals the job's come first."""
    rows = staff["rows"]
    out = []
    for job in jobs:
        jt = job["job_type"]
        mapped = job_roles.get(jt, [])
        same = [r for r in rows if r.get("preferred_job_type") == jt]
        rest = [r for r in rows if r.get("preferred_job_type") != jt]
        best: dict = {}
        for role in mapped:
            picked = staff_mod.rank(same, role, None, roles)[:top]
            if len(picked) < top:
                picked += staff_mod.rank(rest, role, None, roles)[:top - len(picked)]
            for c in picked:
                c = {**c, "role": role}
                if c["uid"] not in best or c["score"] > best[c["uid"]]["score"]:
                    best[c["uid"]] = c
        cands = sorted(best.values(), key=lambda c: (c.get("preferred_job_type") != jt, -c["score"]))
        out.append({**job, "roles": list(mapped), "candidates": cands, "truncated": staff["truncated"],
                    "returned": staff["returned"], "count": staff["count"]})
    return out
