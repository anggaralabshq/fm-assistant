import json

from fm_assistant import staff, vacancies

from helpers import fixture
from test_cli import HELLO, fake_calls, run

ROLES = {"scout": {"JudgingPlayerAbility": 1}, "physio": {"Physiotherapy": 1}}
JOB_ROLES = {14: ["scout"], 12: ["physio"]}


def row(uid, job_type, ability, **extra):
    return {"uid": uid, "name": f"S{uid}", "preferred_job_type": job_type,
            "attributes": {"JudgingPlayerAbility": ability, "Physiotherapy": ability}, **extra}


def staff_res(rows, count=None, truncated=False):
    return {"count": count or len(rows), "returned": len(rows), "truncated": truncated, "rows": rows}


def jobs(*types):
    return [j for j in vacancies.open_jobs(fixture("club_jobs.json")) if j["job_type"] in types]


def test_open_jobs_only_below_max():
    out = vacancies.open_jobs(fixture("club_jobs.json"))
    assert [j["job_type"] for j in out] == [14, 44, 12, 46]
    assert [j["open"] for j in out] == [2, 1, 1, 1]
    assert out[0]["group"] == "recruitment" and out[0]["summary"] == "3 lowongan"


def test_open_count_matches_summary_digits():
    out = vacancies.open_jobs(fixture("club_jobs.json"))
    for group, n in (("recruitment", 3), ("medical", 2)):
        assert sum(j["open"] for j in out if j["group"] == group) == n


def test_fill_prefers_matching_job_type():
    rows = [row(1, 14, 9), row(2, 14, 8), row(3, 14, 7), row(4, 58, 11)]
    out = vacancies.fill(jobs(14), staff_res(rows), ROLES, JOB_ROLES, top=3)[0]
    assert [c["uid"] for c in out["candidates"]] == [1, 2, 3]
    assert out["candidates"][0]["score"] == 9.0 and out["candidates"][0]["role"] == "scout"


def test_fill_tops_up_from_other_rows():
    rows = [row(1, 14, 9), row(4, 58, 11), row(5, 58, 10)]
    out = vacancies.fill(jobs(14), staff_res(rows), ROLES, JOB_ROLES, top=3)[0]
    assert [c["uid"] for c in out["candidates"]] == [1, 4, 5]


def test_fill_dedups_across_roles_keeping_best_score():
    r = row(1, 104, 9)
    r["attributes"] = {"JudgingPlayerAbility": 9, "Physiotherapy": 15}
    out = vacancies.fill([{"job_type": 104}], staff_res([r]), ROLES, {104: ["scout", "physio"]}, top=3)[0]
    assert [(c["uid"], c["role"], c["score"]) for c in out["candidates"]] == [(1, "physio", 15.0)]


def test_unmapped_job_listed_without_candidates():
    out = vacancies.fill(jobs(46), staff_res([row(1, 46, 9)]), ROLES, JOB_ROLES)[0]
    assert out["roles"] == [] and out["candidates"] == []


def test_vacancies_carry_truncation():
    out = vacancies.fill(jobs(14, 46), staff_res([row(1, 14, 9)], count=5000, truncated=True), ROLES, JOB_ROLES)
    assert all(j["truncated"] is True and j["count"] == 5000 and j["returned"] == 1 for j in out)


def test_job_roles_override_merges(tmp_path):
    p = tmp_path / "job_roles.json"
    p.write_text(json.dumps({"16": ["director_of_football"], "14": ["recruitment_analyst"]}))
    merged = vacancies.load_job_roles(user_path=p)
    base = vacancies.load_job_roles(user_path=None)
    assert merged[16] == ["director_of_football"] and merged[14] == ["recruitment_analyst"]
    assert merged[12] == base[12] == ["physio"]
    assert base[104] == ["coach_attacking", "coach_defending", "coach_fitness", "coach_goalkeeping"]
    assert 16 not in base and all(r in staff.load_roles(user_path=None) for v in base.values() for r in v)


def test_staff_vacancies_text_says_ranked_among(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club_jobs.json"),
                             "staff_search": staff_res([row(1, 14, 9)], count=5000, truncated=True)})
    r = run("staff", "vacancies")
    assert r.exit_code == 0, r.output
    assert "ranked among 1 of 5000" in r.stdout
    assert "Pemandu Bakat: 2 open" in r.stdout
    j = json.loads(run("--json", "staff", "vacancies").stdout)["result"]
    assert (j["count"], j["returned"], j["truncated"]) == (5000, 1, True) and len(j["jobs"]) == 4


def test_fill_counts_rows_preferring_the_job():
    out = vacancies.fill(jobs(14, 12), staff_res([row(1, 14, 9), row(2, 14, 7), row(3, 58, 12)]), ROLES, JOB_ROLES)
    assert [j["matching"] for j in out] == [2, 0]


def test_staff_vacancies_text_warns_when_no_row_prefers_the_job(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club_jobs.json"),
                             "staff_search": staff_res([row(1, 14, 9), row(2, 58, 12)])})
    r = run("staff", "vacancies")
    assert r.exit_code == 0, r.output
    physio = r.stdout.split("Fisioterapis")[1]
    assert "0 of 2 searched staff prefer this job" in physio.split("\n\n")[0]


def test_staff_vacancies_drop_own_club_staff(monkeypatch):
    club = {**fixture("club_jobs.json"), "uid": 900001}
    fake_calls(monkeypatch, {"hello": HELLO, "club": club,
                             "staff_search": staff_res([row(1, 14, 20, club_uid=900001), row(2, 14, 9, club_uid=None)])})
    j = json.loads(run("--json", "staff", "vacancies").stdout)["result"]
    assert all(c["uid"] != 1 for job in j["jobs"] for c in job["candidates"])
