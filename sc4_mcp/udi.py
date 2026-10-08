"""U-Drive-It: missions and driving (re/agents/lua-udi Q2-Q4, LIVE_FACTS Phase 3).

Offers come from the City Situations advisor (id 29): each active advice is a mission (guid at advice +0x8C).
start_mission asks the city situation manager (city +0x1EC, vtable 0xA97E58) to show it, as the game's own scripts
do (slot 21 InitiateSituationByGuid): it picks a vehicle of the mission's kind that is out in the city - so the
city must be running for a few seconds first - and opens the offer dialog (Accept / Free Drive / Cancel), answered
with close_dialog. While driving, the player-drive control [0xB21D74] holds the vehicle at +0x30; SiMCP presses and
releases keys through that control's own key handlers (slots 14 / 15), exactly the player's keyboard path, and
reads the vehicle's position (automaton slot 7) and heading (slot 15). Mission state: status +0xA48 (3 running,
1 success, 2 failure), elapsed seconds +0xA8C, time limit +0xA94, target occupant +0xA50 (occupant slot 8
position, 11 cells).
"""

from __future__ import annotations

import math
import struct
import time

from . import memory

G_ADVISORS = 0xB43D34
G_DRIVE_CONTROL = 0xB21D74
C_SITUATIONS = 0x1EC
ADVISOR_SITUATIONS = 29
SM_INITIATE_BY_GUID = 21
S_STATUS, S_ACTIVE, S_AUTO, S_TARGET, S_TARGETS, S_ELAPSED, S_LIMIT = 0xA48, 0x9F4, 0xA4C, 0xA50, 0xA5C, 0xA8C, 0xA94
CTRL_KEY_DOWN, CTRL_KEY_UP, CTRL_AUTO = 14, 15, 0x30
AUTO_POSITION, AUTO_HEADING = 7, 15
OCC_POSITION, OCC_CELLS = 8, 11
STATUS = {3: "running", 1: "success", 2: "failure", 4: "none", 5: "ended"}
KEYS = {"accelerate": 0x26, "brake": 0x28, "left": 0x25, "right": 0x27, "special": 0x20, "alternate": 0x0D,
        "off_road": 0x10, "climb": 0x24, "dive": 0x23, "power_up": 0xBE, "power_down": 0xBC}
ESCAPE = 0x1B


class DriveError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise DriveError("the game's code failed (slot %d, status %d)" % (slot, r.status))
    return r.ret[0] & 0xFFFFFFFF


def _city(g) -> int:
    c = memory.city_pointer(g.proc)
    if not c:
        raise DriveError("no city is open", "load_city opens one")
    return c


def offers(g) -> list[dict]:
    """Missions the City Situations advisor offers now: title, guid, description."""
    p = g.proc
    _city(g)
    sys_ = p.u32(G_ADVISORS)
    hdr = p.u32(sys_ + 0x4C)
    stack, cur, node = [], p.u32(hdr + 4), None
    while (cur and cur != hdr) or stack:
        while cur and cur != hdr:
            stack.append(cur)
            cur = p.u32(cur + 8)
        cur = stack.pop()
        if p.u32(cur + 0x10) == ADVISOR_SITUATIONS:
            node = cur
            break
        cur = p.u32(cur + 0xC)
    if not node:
        return []
    from .city import _text
    I = p.u32(node + 0x14)
    vb, ve = p.u32(I + 0x7C), p.u32(I + 0x80)
    out = []
    for i in range(min((ve - vb) // 16, 200)):
        adv = p.u32(vb + 16 * i)
        if adv and p.u32(adv + 0x70) & 2:
            out.append({"mission": memory.rz_string(p, adv + 0x30), "guid": "0x%08X" % p.u32(adv + 0x8C),
                        "description": _text(memory.rz_string(p, adv + 0x50, 2000))})
    return out


def _vec(g, obj: int, slot: int) -> tuple[float, float, float]:
    s = g.bridge.scratch(0x700)
    g.proc.write(s, bytes(12))
    _v(g, obj, slot, s)
    return struct.unpack("<3f", g.proc.read(s, 12))


def status(g) -> dict:
    """The mission and the vehicle: status, time, target (cells and position), vehicle position (cells),
    heading (unit vector; x east, z south) and speed estimate."""
    p = g.proc
    sm = p.u32(_city(g) + C_SITUATIONS)
    st = p.u32(sm + S_STATUS)
    out = {"mission": STATUS.get(st, st), "elapsed_s": round(p.f32(sm + S_ELAPSED), 1),
           "time_limit_s": round(p.f32(sm + S_LIMIT), 1)}
    adv = p.u32(sm + S_ACTIVE)
    if adv:
        out["title"] = memory.rz_string(p, adv + 0x30 + 4) or memory.rz_string(p, adv + 0x30)
    tgt = p.u32(sm + S_TARGET)
    if tgt and st == 3:
        tx, _, tz = _vec(g, tgt, OCC_POSITION)
        s = g.bridge.scratch(0x720)
        p.write(s, bytes(16))
        _v(g, tgt, OCC_CELLS, s)
        out["target"] = {"x": round(tx / 16, 2), "z": round(tz / 16, 2), "cells": list(struct.unpack("<4i", p.read(s, 16)))}
    ctrl = p.u32(G_DRIVE_CONTROL)
    out["driving"] = bool(ctrl and p.u32(ctrl + CTRL_AUTO))
    if out["driving"]:
        auto = p.u32(ctrl + CTRL_AUTO)
        x, y, z = _vec(g, auto, AUTO_POSITION)
        hx, _, hz = _vec(g, auto, AUTO_HEADING)
        out["vehicle"] = {"x": round(x / 16, 2), "z": round(z / 16, 2), "altitude": round(y, 1),
                          "heading": [round(hx, 3), round(hz, 3)]}
        if "target" in out:
            out["target"]["distance_cells"] = round(math.hypot(out["target"]["x"] - x / 16, out["target"]["z"] - z / 16), 1)
    return out


def start(g, mission: str) -> dict:
    """Ask the game to offer a mission (by title or guid); it opens the offer dialog."""
    p = g.proc
    sm = p.u32(_city(g) + C_SITUATIONS)
    q = mission.strip().lower()
    hit = [o for o in offers(g) if q in (o["mission"].lower(), o["guid"].lower())]
    if not hit:
        raise DriveError("no offered mission matches %r" % mission, "missions() lists the offers")
    ok = _v(g, sm, SM_INITIATE_BY_GUID, int(hit[0]["guid"], 16), 0, 0) & 0xFF
    time.sleep(0.5)
    from . import dialogs
    st = dialogs.status(g)
    out = {"mission": hit[0]["mission"], "offered": bool(ok), "dialog": st["dialogs"][0] if st["open"] else None}
    if not ok:
        out["hint"] = ("the game found no vehicle for it: let the city run a little (set_paused(false) for a few "
                       "seconds) so vehicles are out, then try again; close the result dialog first")
    return out


def drive(g, keys: list[str], seconds: float) -> dict:
    """Hold the given keys for `seconds` (as the player would), release them, and report the state."""
    p = g.proc
    ctrl = p.u32(G_DRIVE_CONTROL)
    if not ctrl or not p.u32(ctrl + CTRL_AUTO):
        raise DriveError("not driving", "accept a mission (or Free Drive) first")
    bad = [k for k in keys if k not in KEYS]
    if bad:
        raise DriveError("unknown keys %s" % bad, "keys: " + ", ".join(KEYS))
    seconds = max(0.0, min(float(seconds), 10.0))
    down = []
    try:
        for k in keys:
            _v(g, ctrl, CTRL_KEY_DOWN, KEYS[k], 0)
            down.append(k)
        time.sleep(seconds)
    finally:
        for k in down:
            if p.u32(G_DRIVE_CONTROL) == ctrl:
                _v(g, ctrl, CTRL_KEY_UP, KEYS[k], 0)
    return status(g)


def stop(g) -> dict:
    """Stop driving (the Escape key), as the player does."""
    p = g.proc
    ctrl = p.u32(G_DRIVE_CONTROL)
    if ctrl:
        _v(g, ctrl, CTRL_KEY_DOWN, ESCAPE, 0)
        if p.u32(G_DRIVE_CONTROL) == ctrl:
            _v(g, ctrl, CTRL_KEY_UP, ESCAPE, 0)
    return {"driving": bool(p.u32(G_DRIVE_CONTROL))}
