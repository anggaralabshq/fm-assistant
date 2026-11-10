import pytest

from fm_assistant import positions, squad

from helpers import fixture


@pytest.mark.parametrize("mask,label", [
    (1, "GK"),
    (16, "D (C)"),
    (16 | 8 | 4, "D (RLC)"),
    (16384, "ST (C)"),
    (0x100010, "D (LC)"),
    (128 | 0x200000, "DM (R)"),
    (2048 | 4096 | 16384, "AM (RL), ST (C)"),
])
def test_decode(mask, label):
    assert positions.decode(mask) == label


def test_unknown_bits_ignored():
    assert positions.decode(2) == ""
    assert positions.decode(0) == ""


def test_normalize_adds_position():
    out = squad.normalize(fixture("squad.json"))
    assert [p["position"] for p in out["players"]] == ["ST (C)", "D (LC)", "GK"]
