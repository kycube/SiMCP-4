"""Terraforming with the game's terrain brushes (re/agents/build section 5, LIVE_FACTS Phase 3).

The city view's terrain buttons create the brush tool (ctor 0x4D9430(brush, god), vtable 0xA92A10) through the
tool dispatcher: in a founded city the mayor-mode buttons (category 0x8A313C52) - raise 0xEA33E2FD
MayorMountainHill, lower 0x0A33E37B MayorValleyDefault, level 0x4A524342 MayorLevelBrush - each application
charged to the funds (WithdrawFunds; the brush stops when the city cannot pay); before founding, god mode's brushes
(category 0x4A2B2462, free): the brush exemplars with a menu order in group 0x6A01FC2A. The brush works while the
button is held: SiMCP's virtual pointer holds it on the chosen cells and moves it along them; the effect grows with
the time held, as for the player.
"""

from __future__ import annotations

import functools
import re
import time

from . import gamedata, memory, pointer

CATEGORY_MAYOR, CATEGORY_GOD = 0x8A313C52, 0x4A2B2462
MAYOR = {"raise": 0xEA33E2FD, "lower": 0x0A33E37B, "level": 0x4A524342}
GROUP_BRUSHES = 0x6A01FC2A
C_ESTABLISHED = 0x25


class TerrainError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


@functools.lru_cache(maxsize=1)
def god_brushes() -> dict[str, int]:
    """God mode's terrain brushes (those with a menu order), named from the exemplars."""
    out = {}
    for inst, ex in gamedata.exemplars(GROUP_BRUSHES):
        if ex.get(0x8A2602B9) is None or ex.get(0x8A2602B8) is None:
            continue
        name = ex.get(0x20) or "brush_%08x" % inst
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", name.replace("Brush", "")).lower().strip("_")
        out[name.replace("god_", "")] = inst
    return out


def brushes(g) -> dict:
    p = g.proc
    c = memory.city_pointer(p)
    if not c:
        raise TerrainError("no city is open", "load_city opens one")
    founded = bool(p.u8(c + C_ESTABLISHED))
    return {"mode": "mayor" if founded else "god", "brushes": sorted(MAYOR if founded else god_brushes())}


def apply(g, brush: str, cells: list[tuple[int, int]], seconds: float = 1.0) -> dict:
    """Hold a terrain brush on the cells (moving along them) for `seconds`, as the player holds the mouse."""
    from .build import _Caller
    from .layers import terrain
    p = g.proc
    c = memory.city_pointer(p)
    if not c:
        raise TerrainError("no city is open", "load_city opens one")
    founded = bool(p.u8(c + C_ESTABLISHED))
    table = MAYOR if founded else god_brushes()
    if brush not in table:
        raise TerrainError("brush %r is not available in %s mode" % (brush, "mayor" if founded else "god"),
                           "brushes: " + ", ".join(sorted(table)))
    if not cells:
        raise TerrainError("give at least one cell")
    nx, nz = p.u32(c + memory.C_CELLS_X), p.u32(c + memory.C_CELLS_Z)
    for x, z in cells:
        if not (0 <= x < nx and 0 <= z < nz):
            raise TerrainError("cell (%d, %d) is outside the city" % (x, z))
    seconds = max(0.1, min(float(seconds), 10.0))
    k = _Caller(g)
    funds0 = k.funds()
    alt = terrain(p)["altitude"]
    before = [round(alt[z][x], 2) for x, z in cells]
    ctrl = pointer.select_tool(g, CATEGORY_MAYOR if founded else CATEGORY_GOD, table[brush])
    b = g.bridge
    steps = max(1, int(seconds / 0.1))
    try:
        b.set_pick(pointer.world(p, *cells[0]), 5000)
        pointer._v(g, ctrl, pointer.C_MOUSE_MOVE, *pointer.SCREEN, 0)
        pointer._v(g, ctrl, pointer.C_MOUSE_DOWN, *pointer.SCREEN, 0)
        for i in range(steps):
            cell = cells[min(len(cells) - 1, i * len(cells) // steps)]
            b.set_pick(pointer.world(p, *cell), 5000)
            time.sleep(0.1)
            pointer._v(g, ctrl, pointer.C_MOUSE_MOVE, pointer.SCREEN[0] + i % 2, pointer.SCREEN[1], 0)
        pointer._v(g, ctrl, pointer.C_MOUSE_UP, *pointer.SCREEN, 0)
    finally:
        b.set_pick(None)
        pointer.drop_tool(g)
    alt = terrain(p)["altitude"]
    return {"brush": brush, "mode": "mayor" if founded else "god",
            "cells": [{"cell": [x, z], "before": bf, "after": round(alt[z][x], 2)} for (x, z), bf in zip(cells, before)],
            "charged": funds0 - k.funds()}
