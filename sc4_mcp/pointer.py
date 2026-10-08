"""The virtual pointer: using the game's own tools on cells SiMCP chooses (re/agents/build section 6).

Every city tool (network, zone, plop, bulldozer, flora, disasters, dispatch, terrain brushes, My Sim move-in...)
asks the city view where the mouse points through the view's PickTerrain (vtable slot 36). The bridge hooks that
slot: while SiMCP's pointer is set (for a few seconds at most), PickTerrain answers the centre of the chosen cell,
and SiMCP presses and releases the tool's mouse button through the tool's own handlers (OnMouseDownL slot 16,
OnMouseMove 20, OnMouseUpL 18). The game then does exactly what it does for the player's click; the real mouse
never moves.

Tools are selected as the build menus select them: the view's tool dispatcher 0x7E9FA0(category, item, close
menus) (thiscall on the view, ret 0xC); the current tool is view slot 24, removed with slot 26.
"""

from __future__ import annotations

import struct
import time

from . import memory

G_VIEW = 0xB43DC4
FN_SELECT_TOOL = 0x7E9FA0
V_CURRENT_CONTROL, V_REMOVE_CONTROL = 24, 26
C_GET_ID = 0       # not used: control ids are read at +0xC
C_MOUSE_DOWN, C_MOUSE_UP, C_MOUSE_MOVE = 16, 18, 20
CATEGORY_DISASTER = 0x4A2B2464
CATEGORY_GOD_TERRAIN = 0x4A2B2462
CATEGORY_MAYOR_TERRAIN = 0x8A313C52
SCREEN = (512, 384)


class PointerError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _view(g) -> int:
    if not memory.city_pointer(g.proc):
        raise PointerError("no city is open", "load_city opens one")
    v = g.proc.u32(G_VIEW)
    if not v:
        raise PointerError("the city view is not ready")
    if not g.bridge.pick_installed():
        raise PointerError("the bridge's pointer hook is not installed", "game_status; restart the game if it persists")
    return v


def world(p, x: float, z: float) -> tuple[float, float, float]:
    """World metres of the centre of cell (x, z), at the ground's altitude there."""
    t = p.u32(memory.G_TERRAIN)
    nvx = p.u32(t + 0x38)
    base = p.u32(t + 0x6C)
    cx, cz = int(x), int(z)
    hs = [struct.unpack("<f", p.read(base + 36 * ((cz + dz) * nvx + cx + dx), 4))[0] for dz in (0, 1) for dx in (0, 1)]
    return (x + 0.5) * 16.0, sum(hs) / 4, (z + 0.5) * 16.0


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise PointerError("the game's code failed (slot %d, status %d) %s" % (slot, r.status, r.msg))
    return r.ret[0] & 0xFFFFFFFF


def select_tool(g, category: int, item: int) -> int:
    """Select a tool as its menu button does; returns the new current tool (view input control)."""
    v = _view(g)
    r = g.bridge.call_function(FN_SELECT_TOOL, [category, item, 1], this=v)
    if not r.ok:
        raise PointerError("selecting the tool failed (status %d) %s" % (r.status, r.msg))
    return current_tool(g)


def current_tool(g) -> int:
    return _v(g, _view(g), V_CURRENT_CONTROL)


def current_tool_id(g) -> int:
    c = current_tool(g)
    return g.proc.u32(c + 0xC) if c else 0


def drop_tool(g) -> None:
    """Put the current tool away (as Escape does)."""
    v = _view(g)
    if _v(g, v, V_CURRENT_CONTROL):
        _v(g, v, V_REMOVE_CONTROL, 0)


def click(g, x: float, z: float, mods: int = 0, ctrl: int | None = None) -> int:
    """Press and release the left button of the current tool on cell (x, z); returns the picks it made."""
    ctrl = ctrl or current_tool(g)
    if not ctrl:
        raise PointerError("no tool is selected")
    b = g.bridge
    before = b.pick_hits()
    b.set_pick(world(g.proc, x, z))
    try:
        _v(g, ctrl, C_MOUSE_MOVE, SCREEN[0], SCREEN[1], mods)
        _v(g, ctrl, C_MOUSE_DOWN, SCREEN[0], SCREEN[1], mods)
        _v(g, ctrl, C_MOUSE_UP, SCREEN[0], SCREEN[1], mods)
    finally:
        b.set_pick(None)
    return b.pick_hits() - before


def drag(g, cells: list[tuple[float, float]], mods: int = 0, ctrl: int | None = None, pause_s: float = 0.0) -> int:
    """Press on the first cell, move through the others, release on the last (a player's drag)."""
    ctrl = ctrl or current_tool(g)
    if not ctrl:
        raise PointerError("no tool is selected")
    b = g.bridge
    before = b.pick_hits()
    try:
        sx, sz = SCREEN
        b.set_pick(world(g.proc, *cells[0]))
        _v(g, ctrl, C_MOUSE_MOVE, sx, sz, mods)
        _v(g, ctrl, C_MOUSE_DOWN, sx, sz, mods)
        for i, c in enumerate(cells[1:], 1):
            b.set_pick(world(g.proc, *c))
            _v(g, ctrl, C_MOUSE_MOVE, sx + 8 * i, sz + 4 * i, mods)
            if pause_s:
                time.sleep(pause_s)
        _v(g, ctrl, C_MOUSE_UP, sx + 8 * (len(cells) - 1), sz + 4 * (len(cells) - 1), mods)
    finally:
        b.set_pick(None)
    return b.pick_hits() - before
