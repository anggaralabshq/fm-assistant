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


def test_covers():
    assert positions.covers(16 | 8, "D (C)")
    assert positions.covers(2048 | 4096 | 16384, "ST (C)")
    assert not positions.covers(16384, "D (C)")
    assert positions.covers(16 | 0x100000, "D (L)")
    assert not positions.covers(16 | 0x100000, "D (R)")
    assert positions.covers(1, "GK")
    assert positions.covers(32768, "ST (C)")
    with pytest.raises(ValueError):
        positions.covers(1, "nope")


def test_normalize_adds_position():
    out = squad.normalize(fixture("squad.json"))
    assert [p["position"] for p in out["players"]] == ["ST (C)", "D (LC)", "GK"]
