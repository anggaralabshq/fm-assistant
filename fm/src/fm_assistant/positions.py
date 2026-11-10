"""Decode the game's PositionMask bit flags into FM-style labels.

Bit table ported from fm-dof-mcp PositionDecode.cs (MIT), itself recovered from the game's
PlayingDataFlags.PositionMask. LEFT/RIGHT_SIDED are modifiers on a central slot (half-space), not slots.
"""
GK = 1
LEFT_SIDED, RIGHT_SIDED = 0x100000, 0x200000
# label, right, left, centre, has native side flags
GROUPS = [
    ("D", 4, 8, 16, True),
    ("WB", 32, 64, 0, True),
    ("DM", 0, 0, 128, False),
    ("M", 256, 512, 1024, True),
    ("AM", 2048, 4096, 8192, True),
    ("ST", 32768, 65536, 16384, True),
]


SLOTS = ["GK", "D (R)", "D (L)", "D (C)", "WB (R)", "WB (L)", "DM", "M (R)", "M (L)", "M (C)",
         "AM (R)", "AM (L)", "AM (C)", "ST (C)"]


def covers(mask: int, slot: str) -> bool:
    """Can a player with this mask play the slot? Own bit; side slots also centre bit + matching side modifier."""
    if slot not in SLOTS:
        raise ValueError(f"unknown slot {slot!r}")
    if slot == "GK":
        return bool(mask & GK)
    label, _, side = slot.partition(" ")
    side = side.strip("()")
    for lab, right, left, centre, _native in GROUPS:
        if lab != label:
            continue
        if side == "":
            return bool(mask & centre)
        if side == "C":
            return bool(mask & (centre | (32768 | 65536 if lab == "ST" else 0)))
        own, modifier = (right, RIGHT_SIDED) if side == "R" else (left, LEFT_SIDED)
        return bool(mask & own) or bool(centre and mask & centre and mask & modifier)
    raise ValueError(f"unknown slot {slot!r}")


def decode(mask: int) -> str:
    """e.g. 16|8|4 -> "D (RLC)"; unknown or empty -> ""."""
    parts = ["GK"] if mask & GK else []
    for label, right, left, centre, native in GROUPS:
        r, l, c = bool(mask & right), bool(mask & left), bool(mask & centre)
        if not (r or l or c):
            continue
        mod_r, mod_l = bool(mask & RIGHT_SIDED), bool(mask & LEFT_SIDED)
        if not native:  # DM: a side modifier replaces the bare label with a half-space side
            sides = ("R" if mod_r else "") + ("L" if mod_l else "")
            parts.append(f"{label} ({sides})" if sides else label)
            continue
        if c:
            r, l = r or mod_r, l or mod_l
        sides = ("R" if r else "") + ("L" if l else "") + ("C" if c else "")
        parts.append(f"{label} ({sides})" if sides else label)
    return ", ".join(parts)
