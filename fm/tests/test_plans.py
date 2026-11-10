import json

import pytest

from fm_assistant import plans


def test_plan_create_writes_file_and_describe(tmp_path):
    p = plans.create([{"kind": "staff.offer", "args": {"uid": 11, "wage": 4000}}], "need a scout", "offer to 11", root=tmp_path)
    assert p["status"] == "proposed"
    assert json.loads((tmp_path / f"{p['id']}.json").read_text()) == p
    a = p["actions"][0]
    assert a["kind"] == "staff.offer" and "11" in a["describe"] and "4000" in a["describe"]
    assert plans.load(p["id"], root=tmp_path) == p
    assert [x["id"] for x in plans.list_plans(root=tmp_path)] == [p["id"]]
    assert plans.list_plans("applied", root=tmp_path) == []


def test_plan_create_validates(tmp_path):
    with pytest.raises(ValueError):
        plans.create([{"kind": "nope", "args": {}}], "r", "s", root=tmp_path)
    with pytest.raises(ValueError):
        plans.create([], "r", "s", root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_load_rejects_path_ids(tmp_path):
    with pytest.raises(ValueError):
        plans.load("../x", root=tmp_path)
