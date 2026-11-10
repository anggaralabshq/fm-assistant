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
