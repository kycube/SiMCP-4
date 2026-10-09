"""Disasters and emergency dispatch, as the player starts them (re/agents/view-disasters Q1/Q2, LIVE_FACTS Phase 3).

Disasters: the god-mode Disasters menu items are exemplars in group 0x29B6C670; selecting one makes the
disaster tool (category 0x4A2B2464, the item's instance) and a click on the map starts it - through SiMCP's virtual
pointer (pointer.py), so the game's own tool decides: managed disasters (volcano, earthquake, robot...) call their
manager's AttemptDisasterStart with the clicked point in world metres, the others place their effect (meteors,
tornado, UFO, lightning). The disaster layer [0xB43D3C] (vtable 0xA9E390) lists what is going on.

Dispatch: the DispatchFireTool / DispatchPoliceTool commands (and the air variants) arm the dispatch tool as the
player's buttons do (founded city only); a click sends the unit if the city has a station that can (the dispatch
manager [0xB43D04] slot 5 CanDispatch, slot 6 Dispatch).
"""

from __future__ import annotations

import functools
import struct
import time

from . import gamedata, memory, pointer

G_LAYER = 0xB43D3C
G_DISPATCH = 0xB43D04
GROUP_DISASTERS = 0x29B6C670
LTEXT_GROUP = 0x8A5E03EC
P_MANAGER, P_EFFECT = 0x4A08C701, 0x4A08C700
L_GET_MANAGER, L_ONGOING, L_LOCATION_COUNT, L_LOCATION = 7, 10, 16, 17
M_ACTIVE_COUNT = 10
MANAGERS = {0xC4C90997: "volcano", 0x621CDA33: "fire", 0x42963812: "earthquake", 0x4A1332E8: "pipe burst",
            0xCA380B06: "riot", 0xEBFB0404: "toxic spill"}
DISPATCH = {"fire": ("DispatchFireTool", 1), "police": ("DispatchPoliceTool", 0),
            "fire_plane": ("DispatchFireAirTool", 5), "police_helicopter": ("DispatchPoliceAirTool", 6)}
D_COUNT = 11
TORCH_ITEM = 0xA9DE8784


class DisasterError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


@functools.lru_cache(maxsize=1)
def menu() -> list[dict]:
    """The god-mode Disasters menu, from the game's data (items with a name; pipe bursts and riots come only from
    the simulation)."""
    out = []
    for inst, ex in gamedata.exemplars(GROUP_DISASTERS):
        key = ex.get(0x8A416A99)
        name = gamedata.locale_text(key[2], key[1]) if isinstance(key, list) and len(key) == 3 else None
        if not name:
            continue
        out.append({"id": inst, "name": name, "key": name.lower().replace(" ", "_"),
                    "manager": ex.get(P_MANAGER) or 0, "order": ex.get(0x8A2602B9) or 0})
    out.sort(key=lambda d: (d["order"], d["name"]))
    return out


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise DisasterError("the game's code failed (slot %d, status %d)" % (slot, r.status))
    return r.ret[0] & 0xFFFFFFFF


def status(g) -> dict:
    """What is going on: active disasters per kind and their locations (cells)."""
    p = g.proc
    if not memory.city_pointer(p):
        raise DisasterError("no city is open", "load_city opens one")
    layer = p.u32(G_LAYER)
    active = {}
    for mid, name in MANAGERS.items():
        m = _v(g, layer, L_GET_MANAGER, mid)
        if m:
            n = _v(g, m, M_ACTIVE_COUNT)
            if n:
                active[name] = n
    locs = []
    s = g.bridge.scratch(0x600)
    for i in range(min(_v(g, layer, L_LOCATION_COUNT), 32)):
        p.write(s, bytes(12))
        if _v(g, layer, L_LOCATION, i, s, s + 4, s + 8) & 0xFF:
            inst, x, z = struct.unpack("<Iii", p.read(s, 12))
            kind = MANAGERS.get(_v(g, inst, 5), "disaster") if inst else "disaster"
            if inst:
                _v(g, inst, 2)            # GetDisasterLocationByIndex AddRef'd it
            locs.append({"kind": kind, "x": x // 16 if x > 255 else x, "z": z // 16 if z > 255 else z})
    return {"ongoing": bool(p.u32(layer + 0x40)), "active": active, "locations": locs}


def start(g, kind: str, x: int, z: int, hold_s: float = 0.3) -> dict:
    """Start a disaster from the Disasters menu at cell (x, z) with the game's own tool."""
    items = menu()
    q = kind.strip().lower().replace(" ", "_")
    hit = [d for d in items if q in (d["key"], str(d["id"]))]
    if not hit:
        raise DisasterError("unknown disaster %r" % kind, "disasters: " + ", ".join(d["key"] for d in items))
    d = hit[0]
    before = status(g)
    # the Fire button selects the torch with its own id: the disaster tool factory (0x7E9DB0) builds the torch
    # control (vtable 0xA9EB40, slot 16 OnMouseDownL ignites the picked cell) only for 0xA9DE8784; the menu exemplar
    # (4) would make the generic disaster tool, which lights nothing
    item = TORCH_ITEM if d["key"] == "fire" else d["id"]
    pointer.select_tool(g, pointer.CATEGORY_DISASTER, item)
    try:
        pointer.drag(g, [(x, z), (x, z)], pause_s=hold_s)
    finally:
        pointer.drop_tool(g)
    time.sleep(0.2)
    after = status(g)
    return {"disaster": d["name"], "at": [x, z], "ongoing": after["ongoing"], "active": after["active"],
            "started": after["active"] != before["active"] or after["ongoing"] > before["ongoing"]
            or len(after["locations"]) > len(before["locations"]),
            "note": "disasters play out while the game runs (set_paused(false) or advance_time)"}


def dispatch(g, unit: str, x: int, z: int) -> dict:
    """Send firefighters or police to cell (x, z) with the game's dispatch tool (needs a station that can)."""
    if unit not in DISPATCH:
        raise DisasterError("unknown unit %r" % unit, "units: " + ", ".join(DISPATCH))
    command, typ = DISPATCH[unit]
    p = g.proc
    d = p.u32(G_DISPATCH)
    before = _v(g, d, D_COUNT, typ) if d else 0
    r = g.bridge.command(command)
    if r.get("status") != 0 or not pointer.current_tool(g):
        raise DisasterError("the game did not arm the %s tool" % unit, "dispatch needs a founded city")
    try:
        pointer.click(g, x, z)
    finally:
        pointer.drop_tool(g)
    after = _v(g, d, D_COUNT, typ) if d else 0
    return {"unit": unit, "at": [x, z], "dispatched": after > before, "units_out": after,
            "note": "" if after > before else "no unit was sent: the city needs a station with a free unit and a "
                                                       "road route to the target"}
