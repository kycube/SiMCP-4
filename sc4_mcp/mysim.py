"""My Sims: the five Sims a player can move into the city (re/agents/lua-udi Q5, LIVE_FACTS Phase 3).

The agent simulator (city +0x1AC) keeps five cISC4MySim* at [agent+0x14][0..4]; read through the interface's own
getters (slot 20 IsActive, 17 age, 16 sign, 18 male, 19 wealth, 25 home name, 26 job name, 11 / 12 residence /
job occupants, 14 location, 3 AsAdvisor -> the name at advisor +0x10).

Moving a Sim in is the player's path: the My Sims panel (command ToggleMySimPanel, root 0xCA1F1D9C) -> a free
slot's button -> the "Select A My Sim" dialog (root 0x6A243D9E) -> "Move In My Sim" -> the move-in tool picks a
house under the pointer (view PickOccupant; SiMCP's virtual pointer answers the house on the chosen cell).
"""

from __future__ import annotations

import struct
import time

from . import dialogs, memory, pointer

C_AGENT = 0x1AC
PANEL_ROOT = 0xCA1F1D9C
SLOT_BUTTONS = [0x8A8F410C, 0x8A8F410D, 0x8A8F410E, 0x8A8F410F, 0x8A8F4120]
SELECT_ROOT = 0x6A243D9E
SIGNS = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn",
         "aquarius", "pisces"]
WEALTH = {0: "none", 1: "low", 2: "medium", 3: "high"}


class MySimError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise MySimError("the game's code failed (slot %d, status %d)" % (slot, r.status))
    return r.ret[0] & 0xFFFFFFFF


def _slots(g) -> list[int]:
    p = g.proc
    c = memory.city_pointer(p)
    if not c:
        raise MySimError("no city is open", "load_city opens one")
    agent = p.u32(c + C_AGENT)
    arr = p.u32(agent + 0x14) if agent else 0
    return [p.u32(arr + 4 * i) for i in range(5)] if arr else []


def sims(g) -> list[dict]:
    p = g.proc
    out = []
    for i, ms in enumerate(_slots(g)):
        if not ms or not _v(g, ms, 20) & 0xFF:
            out.append({"slot": i + 1, "active": False})
            continue
        adv = _v(g, ms, 3)
        home, job = _v(g, ms, 25), _v(g, ms, 26)
        d = {"slot": i + 1, "active": True, "name": memory.rz_string(p, adv + 0x10) if adv else None,
             "age": _v(g, ms, 17) & 0xFF, "sign": SIGNS[_v(g, ms, 16) % 12], "male": bool(_v(g, ms, 18) & 0xFF),
             "wealth": WEALTH.get(_v(g, ms, 19), None), "home": memory.rz_string(p, home) if home else None,
             "job": memory.rz_string(p, job) if job else None}
        s = g.bridge.scratch(0x760)
        p.write(s, bytes(12))
        if _v(g, ms, 14, s) & 0xFF:
            x, _, z = struct.unpack("<3f", p.read(s, 12))
            d["location"] = [round(x / 16, 1), round(z / 16, 1)]
        out.append(d)
    return out


def move_in(g, x: int, z: int) -> dict:
    """Move a new My Sim into the house on cell (x, z) through the player's panel, dialog and move-in tool."""
    free = [i for i, ms in enumerate(_slots(g)) if ms and not _v(g, ms, 20) & 0xFF]
    if not free:
        raise MySimError("all five My Sim slots are taken")
    occ = pointer.building_at(g, x, z)
    if not occ:
        raise MySimError("no building on cell (%d, %d)" % (x, z), "lots(zone='residential_low') lists houses")
    try:
        def open_select() -> dict:
            g.bridge.command("GZWinClickButton %d %d" % (SLOT_BUTTONS[free[0]], PANEL_ROOT))
            time.sleep(0.5)
            return dialogs.status(g)
        st = open_select()
        if not st["open"]:                       # the panel was closed: open it as its button does, then retry
            g.bridge.command("ToggleMySimPanel")
            time.sleep(0.3)
            st = open_select()
        if not st["open"] or st["dialogs"][0]["id"] != "0x%08X" % SELECT_ROOT:
            raise MySimError("the Select A My Sim dialog did not open", "dialog_status shows what is open")
        dialogs.click(g, "Move In My Sim")
        time.sleep(0.5)
        picks = pointer.click(g, x, z, occupant=occ)
    finally:
        pointer.release(g, occ)
    time.sleep(0.5)
    now = sims(g)
    return {"moved_in": now[free[0]].get("active", False), "sim": now[free[0]], "picks": picks}
