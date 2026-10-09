"""Building like the player: networks, zones, lots, bulldozing, trees (re/agents/build/REPORT.md, verified in
LIVE_FACTS Phase 3).

Every action replays what the game's own tool does after the player's mouse picks the cells: the same calls, the
same rules and the same charge to the city's funds, on the game's main thread (through the bridge). Nothing moves
the real mouse, and nothing is free unless the player's tool is free too.

Calls go through `Bridge.call_function`; their pointer arguments live in the bridge's scratch area (8 KB inside the
bridge's own block), so nothing is allocated in the game.
"""

from __future__ import annotations

import struct

from . import memory

G_BUDGET = 0xB43D64
FN_RZSTRING_CTOR = 0x578390
SLOT_RZSTRING_DELETE = 28
C_NETWORK_MANAGER = 0x200          # cISC4City +0x200 (city slot 38)

# Budget slots (vtable 0xAB0908)
B_SET_FUNDS, B_GET_FUNDS, B_DEPOSIT, B_WITHDRAW = 5, 6, 7, 8

# Network tool slots (generic tool vtable 0xAA8748)
NT_ADDREF, NT_RELEASE, NT_INIT, NT_SHUTDOWN, NT_RESET = 1, 2, 3, 4, 5
NT_CLEAR_FAILURE, NT_FAILED, NT_FAILURE_TEXT, NT_CLEAR_HIGHLIGHTS, NT_CLEAR_PREVIEWS = 13, 14, 15, 16, 17
NT_DRAW_LINE, NT_PLACE_SEGMENTS, NT_COST, NT_PREVIEW_UPDATE, NT_SET_ANCHORS = 18, 19, 20, 21, 22
NT_POSSIBLE_BRIDGES, NT_SET_BRIDGE, NT_BRIDGE_ALTITUDE, NT_NEIGHBOR_CONNECTION, NT_PEN_WIDTH = 30, 32, 34, 41, 45
NM_GET_TOOL = 5

NETWORKS = {"road": 0, "rail": 1, "elevated_highway": 2, "street": 3, "pipe": 4, "power_line": 5, "avenue": 6,
            "subway": 7, "light_rail": 8, "monorail": 9, "one_way_road": 10, "dirt_road": 11, "ground_highway": 12}
MAX_POINTS = 64

# scratch layout (bytes from the start of the bridge's scratch area)
S_START, S_END, S_ANCHORS, S_VECTOR, S_TEXT, S_INFO, S_BRIDGES, S_OUT = 0, 8, 16, 600, 640, 680, 760, 800


class BuildError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _f32(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


class _Caller:
    def __init__(self, g):
        self.g, self.p, self.b = g, g.proc, g.bridge
        self.b.attach()
        self.s = self.b.scratch()

    def v(self, obj: int, slot: int, *args) -> int:
        """Call virtual method `slot` of obj; returns EAX (unsigned)."""
        r = self.b.call_function(self.p.u32(self.p.u32(obj) + 4 * slot), list(args), this=obj)
        if not r.ok:
            raise BuildError("the game's code failed (slot %d, status %d) %s" % (slot, r.status, r.msg),
                             "the game is still running; game_status shows its state")
        return r.ret[0] & 0xFFFFFFFF

    def funds(self) -> int:
        budget = self.p.u32(G_BUDGET)
        return struct.unpack("<q", self.p.read(budget + 0x28, 8))[0]

    def withdraw(self, amount: int) -> bool:
        """The budget's WithdrawFunds (slot 8): False (nothing changed) when the city cannot pay."""
        if amount <= 0:
            return True
        return bool(self.v(self.p.u32(G_BUDGET), B_WITHDRAW, amount & 0xFFFFFFFF, (amount >> 32) & 0xFFFFFFFF) & 0xFF)

    def text_out(self, obj: int, slot: int) -> str:
        """Call a method that fills a cIGZString& (a cRZString made in scratch by the game's constructor)."""
        addr = self.s + S_TEXT
        self.p.write(addr, bytes(0x14))
        r = self.b.call_function(FN_RZSTRING_CTOR, [], this=addr)
        if not r.ok:
            return ""
        try:
            self.v(obj, slot, addr)
            return memory.rz_string(self.p, addr, 500)
        finally:
            self.v(addr, SLOT_RZSTRING_DELETE, 0)


def _city(g) -> int:
    c = memory.city_pointer(g.proc)
    if not c:
        raise BuildError("no city is open", "load_city opens one from the region view")
    return c


def _check_cells(g, points):
    c = _city(g)
    nx, nz = g.proc.u32(c + memory.C_CELLS_X), g.proc.u32(c + memory.C_CELLS_Z)
    for x, z in points:
        if not (0 <= x < nx and 0 <= z < nz):
            raise BuildError("cell (%d, %d) is outside the city (0..%d, 0..%d)" % (x, z, nx - 1, nz - 1),
                             "city_status gives the city's size in cells")
    return c


def _leg(k: _Caller, t: int, typ: int, a: tuple[int, int], b: tuple[int, int], width: int, build: bool,
         connect_neighbor: bool, bridge: int) -> dict:
    """One drag from cell a to cell b, as the network tool's UI does it (preview 0x645640, commit 0x645370)."""
    p, s = k.p, k.s
    (x0, z0), (x1, z1) = a, b
    if width > 1:      # wide networks: the UI moves the start back one cell along a positive drag axis
        dx, dz = x1 - x0, z1 - z0
        if x0 > 0 and 2 * dx >= abs(dz):
            x0 -= 1
        if z0 > 0 and 2 * dz >= abs(dx):
            z0 -= 1

    def prepare(preferred: int):
        k.v(t, NT_RESET)
        k.v(t, NT_SET_BRIDGE, preferred & 0xFFFFFFFF)
        k.v(t, NT_BRIDGE_ALTITUDE, _f32(-1.0))

    def place(commit: int, neighbor: int):
        k.v(t, NT_SET_ANCHORS, s + S_VECTOR)
        k.v(t, NT_PLACE_SEGMENTS, commit, 1, neighbor, typ)

    out: dict = {"from": [x0, z0], "to": [x1, z1]}
    prepare(-1)
    k.v(t, NT_PREVIEW_UPDATE, 1)
    k.v(t, NT_CLEAR_FAILURE)
    p.write(s + S_START, struct.pack("<iiii", x0, z0, x1, z1))
    if not k.v(t, NT_DRAW_LINE, s + S_START, s + S_END, 1, typ) & 0xFF:
        reason = k.text_out(t, NT_FAILURE_TEXT) if k.v(t, NT_FAILED) & 0xFF else ""
        out.update(possible=False, reason=reason or "the game cannot lay a network between these cells")
        return out
    x1, z1 = struct.unpack("<ii", p.read(s + S_END, 8))      # the tool may clip the end
    out["to"] = [x1, z1]
    anchors = s + S_ANCHORS
    p.write(anchors, struct.pack("<iiii", x0, z0, x1, z1))
    p.write(s + S_VECTOR, struct.pack("<3I", anchors, anchors + 16, anchors + 16))
    place(0, 0)
    cost = k.v(t, NT_COST)
    out["cost"] = cost
    if k.v(t, NT_FAILED) & 0xFF:
        out.update(possible=False, reason=k.text_out(t, NT_FAILURE_TEXT) or "the game refuses this route")
        return out
    preferred = -1
    p.write(s + S_BRIDGES, bytes(12))
    if k.v(t, NT_POSSIBLE_BRIDGES, s + S_BRIDGES) & 0xFF:     # the player picks one in a dialog
        b0, b1 = struct.unpack("<II", p.read(s + S_BRIDGES, 8))
        choices = list(struct.unpack("<%di" % ((b1 - b0) // 4), p.read(b0, b1 - b0))) if 0 < b1 - b0 < 256 else []
        if choices:
            pick = bridge if 0 <= bridge < len(choices) else 0
            out.update(bridge_choices=len(choices), bridge=pick)
            preferred = choices[pick]
            prepare(preferred)
            place(0, 0)
            cost = k.v(t, NT_COST)
            out["cost"] = cost
    out["possible"] = True
    if not build:
        return out
    funds = k.funds()
    if not k.withdraw(cost):
        out.update(built=False, reason="the city cannot pay %d (funds %d)" % (cost, funds))
        return out
    prepare(preferred)
    place(0, 1)
    p.write(s + S_INFO, bytes(64))
    neighbor = bool(k.v(t, NT_NEIGHBOR_CONNECTION, s + S_INFO) & 0xFF) and not (k.v(t, NT_FAILED) & 0xFF)
    if neighbor:
        out["neighbor_connection"] = "made" if connect_neighbor else "not made (connect_neighbor=false)"
    prepare(preferred)
    place(1, 1 if (neighbor and connect_neighbor) else 0)
    k.v(t, NT_CLEAR_PREVIEWS)
    k.v(t, NT_CLEAR_HIGHLIGHTS)
    out.update(built=True, charged=funds - k.funds())
    return out


def network(g, kind: str, points: list[tuple[int, int]], build: bool = True, connect_neighbor: bool = False,
            bridge: int = -1) -> dict:
    """Drag a network from cell to cell through `points`, one drag per leg, as the player does with the game's
    network tool: the game's path solver lays each leg (the end may be clipped), its cost is charged to the city's
    funds (WithdrawFunds; a leg the city cannot pay is not built) and it is built with the usual construction.
    build=False only reports each leg's cost (later legs' estimates ignore the earlier legs)."""
    if kind not in NETWORKS:
        raise BuildError("unknown network %r" % kind, "networks: " + ", ".join(NETWORKS))
    pts = [(int(x), int(z)) for x, z in points]
    if not 2 <= len(pts) <= MAX_POINTS:
        raise BuildError("give 2 to %d points" % MAX_POINTS, "e.g. [[10, 20], [30, 20]] for a straight line")
    c = _check_cells(g, pts)
    typ = NETWORKS[kind]
    k = _Caller(g)
    t = k.v(k.p.u32(c + C_NETWORK_MANAGER), NM_GET_TOOL, typ, 1)
    if not t:
        raise BuildError("the game has no %s tool" % kind)
    k.v(t, NT_ADDREF)
    k.v(t, NT_INIT)
    legs: list[dict] = []
    funds0 = k.funds()
    try:
        k.p.write(k.s + S_OUT, bytes(8))
        k.v(t, NT_PEN_WIDTH, k.s + S_OUT, k.s + S_OUT + 4)
        width = k.p.i32(k.s + S_OUT)
        for a, b in zip(pts, pts[1:]):
            leg = _leg(k, t, typ, a, b, width, build, connect_neighbor, bridge)
            legs.append(leg)
            if not leg.get("possible") or (build and not leg.get("built")):
                break
    finally:
        try:
            k.v(t, NT_CLEAR_PREVIEWS)
            k.v(t, NT_CLEAR_HIGHLIGHTS)
            k.v(t, NT_RESET)
            k.v(t, NT_SHUTDOWN)
        finally:
            k.v(t, NT_RELEASE)
    out = {"network": kind, "legs": legs, "cost": sum(x.get("cost", 0) for x in legs)}
    if build:
        out.update(built=all(x.get("built") for x in legs) and len(legs) == len(pts) - 1,
                   charged=funds0 - k.funds())
    else:
        out["possible"] = all(x.get("possible") for x in legs)
    out["funds"] = k.funds()
    return out


# ------------------------------------------------------------------------------------------------------- zoning
G_ZONE_MANAGER = 0xB43D14
G_ZONE_DEVELOPER = 0xB43DB0
FN_CELL_REGION_CTOR = 0x442640     # SC4CellRegion<long>(SC4Rect<long> const*, bool) thiscall
FN_CELL_MAP_FREE = 0x441A60        # frees the cell map's rows (this = region + 0x10)
ZM_PLACE_ZONE = 11
ZD_SET_OPTIONS = 7
ZONE_TYPES = {"dezone": 0, "residential_low": 1, "residential_medium": 2, "residential_high": 3,
              "commercial_low": 4, "commercial_medium": 5, "commercial_high": 6, "agriculture": 7,
              "industrial_medium": 8, "industrial_high": 9, "military": 10, "airport": 11, "seaport": 12,
              "spaceport": 13, "landfill": 14}
ZONE_ERRORS = {1: "the city cannot pay", 2: "the ground is too steep or not zonable", 3: "the area is too small",
               4: "the area is too large for one drag"}
S_RECT, S_REGION, S_COST, S_ERR = 0x200, 0x220, 0x250, 0x258


def _place_zone(k: _Caller, typ: int, x0: int, z0: int, x1: int, z1: int, place: bool) -> dict:
    p, s = k.p, k.s
    p.write(s + S_RECT, struct.pack("<4i", x0, z0, x1, z1))
    p.write(s + S_REGION, bytes(0x24))
    p.write(s + S_COST, bytes(12))
    r = k.b.call_function(FN_CELL_REGION_CTOR, [s + S_RECT, 1], this=s + S_REGION)
    if not r.ok:
        raise BuildError("the game could not make the cell region (status %d)" % r.status)
    try:
        zm = p.u32(G_ZONE_MANAGER)
        ok = k.v(zm, ZM_PLACE_ZONE, s + S_REGION, typ, 1 if place else 0, 0, 1, 0, 1 if typ else 0,
                 s + S_COST, s + S_ERR, 0) & 0xFF
    finally:
        k.b.call_function(FN_CELL_MAP_FREE, [], this=s + S_REGION + 0x10)
    cost = struct.unpack("<q", p.read(s + S_COST, 8))[0]
    err = p.i32(s + S_ERR)
    out = {"area": [x0, z0, x1, z1], "cost": cost, "ok": bool(ok)}
    if not ok or err:
        out["error"] = ZONE_ERRORS.get(err, "the game refused (code %d)" % err)
    return out


def zone(g, kind: str, x0: int, z0: int, x1: int, z1: int, build: bool = True, streets: bool = True,
         alternate: bool = False) -> dict:
    """Zone (or de-zone) the cells x0..x1, z0..z1 as the player's zone tool does: the zone manager's PlaceZone with
    the tool's own arguments, so the cost is the game's (charged by PlaceZone itself; nothing is zoned if the city
    cannot pay) and its rules apply (slope, size). Areas larger than one drag (32 x 32 cells, 48 for agriculture)
    are zoned in several drags, as the player would. streets=False is a Ctrl-drag (no automatic streets);
    alternate=True an Alt-drag."""
    if kind not in ZONE_TYPES:
        raise BuildError("unknown zone %r" % kind, "zones: " + ", ".join(ZONE_TYPES))
    x0, x1 = sorted((int(x0), int(x1)))
    z0, z1 = sorted((int(z0), int(z1)))
    _check_cells(g, [(x0, z0), (x1, z1)])
    typ = ZONE_TYPES[kind]
    k = _Caller(g)
    k.v(k.p.u32(G_ZONE_DEVELOPER), ZD_SET_OPTIONS, 1 if alternate else 0, 1 if streets else 0, 0)
    step = 48 if typ == 7 else 32
    drags = []
    funds0 = k.funds()
    for zz in range(z0, z1 + 1, step):
        for xx in range(x0, x1 + 1, step):
            d = _place_zone(k, typ, xx, zz, min(xx + step - 1, x1), min(zz + step - 1, z1), build)
            drags.append(d)
            if build and d.get("error") == ZONE_ERRORS[1]:
                break
    out = {"zone": kind, "drags": drags, "cost": sum(d["cost"] for d in drags)}
    if build:
        out["charged"] = funds0 - k.funds()
    out["funds"] = k.funds()
    return out


# ------------------------------------------------------------------------------------------------- plopping lots
FACINGS = {"north": 0, "east": 1, "south": 2, "west": 3}


def plop(g, what: str, x: int, z: int, facing: str = "north") -> dict:
    """Plop a building from the build menus with its north-west corner at cell (x, z), as the player's plop tool
    does (the game's PlaceLot core 0x4C1740: placement rules, funds check, the plop cost charged). Only what the
    menus offer now is allowed: a locked reward, an unreached building or an excluded one is refused, as its
    greyed menu button would. `what` is a name or a lot / building id from build_menu; facing is the side the
    lot's front faces (north = toward smaller z)."""
    from . import catalog
    if facing not in FACINGS:
        raise BuildError("unknown facing %r" % facing, "north, east, south or west")
    _check_cells(g, [(x, z)])
    k = _Caller(g)
    hits = catalog.find(k, what)
    if not hits:
        raise BuildError("nothing in the build menus matches %r" % what, "build_menu lists what can be plopped")
    if len({h["lot"] for h in hits}) > 1:
        raise BuildError("%r matches %d items" % (what, len(hits)),
                         "use one of the lot ids: " + ", ".join("0x%08X %s" % (h["lot"], h["name"]) for h in hits[:12]))
    item = hits[0]
    state = catalog.availability(k, [item])[0]
    out = {"name": item["name"], "lot": "0x%08X" % item["lot"], "cost": item["cost"]}
    if state != "available":
        out.update(placed=False, reason="the menu does not offer it now (%s): a locked reward or a requirement "
                   "not met yet" % ("greyed" if state == "greyed" else "hidden"))
        return out
    f = FACINGS[facing]
    sx, sz = item["size"]
    if f in (1, 3):
        sx, sz = sz, sx
    cx, cz = x + sx // 2, z + sz // 2          # PlaceLot centres the lot on this cell corner
    _check_cells(g, [(x + sx - 1, z + sz - 1)])
    funds = k.funds()
    r = g.bridge.command("PlaceLot %d %d %d %d 1 0" % (item["lot"], cx, cz, f))
    charged = funds - k.funds()
    placed = r.get("status") == 0
    out.update(placed=placed, area=[x, z, x + sx - 1, z + sz - 1], facing=facing, charged=charged)
    if not placed:
        out["reason"] = "the game refused the spot (occupied, too steep, water, or not affordable)"
    return out


# ---------------------------------------------------------------------------------------------------- bulldozing
G_DEMOLITION = 0xB43D00
D_DEMOLISH_REGION = 6


def _demolish(k: _Caller, x0: int, z0: int, x1: int, z1: int, commit: bool) -> int:
    p, s = k.p, k.s
    p.write(s + S_RECT, struct.pack("<4i", x0, z0, x1, z1))
    p.write(s + S_REGION, bytes(0x24))
    p.write(s + S_COST, bytes(8))
    r = k.b.call_function(FN_CELL_REGION_CTOR, [s + S_RECT, 1], this=s + S_REGION)
    if not r.ok:
        raise BuildError("the game could not make the cell region (status %d)" % r.status)
    try:
        k.v(p.u32(G_DEMOLITION), D_DEMOLISH_REGION, 1 if commit else 0, s + S_REGION, 1, 1, 0, 0, s + S_COST,
            0, 0, 0, 0)
    finally:
        k.b.call_function(FN_CELL_MAP_FREE, [], this=s + S_REGION + 0x10)
    return struct.unpack("<q", p.read(s + S_COST, 8))[0]


def bulldoze(g, x0: int, z0: int, x1: int, z1: int, build: bool = True) -> dict:
    """Bulldoze everything on the cells x0..x1, z0..z1 (buildings, lots, networks, trees), as the player's
    bulldozer does: the game's demolition dry run gives the cost, the cost is taken from the funds (the bulldozer
    does not check the funds, so they can go below zero, as in the game), then the demolition runs.
    build=False only reports the cost."""
    x0, x1 = sorted((int(x0), int(x1)))
    z0, z1 = sorted((int(z0), int(z1)))
    _check_cells(g, [(x0, z0), (x1, z1)])
    k = _Caller(g)
    cost = _demolish(k, x0, z0, x1, z1, False)
    out = {"area": [x0, z0, x1, z1], "cost": cost}
    if not build:
        return out
    funds = k.funds()
    if cost:
        budget = k.p.u32(G_BUDGET)
        left = funds - cost
        k.v(budget, B_SET_FUNDS, left & 0xFFFFFFFF, (left >> 32) & 0xFFFFFFFF)
    _demolish(k, x0, z0, x1, z1, True)
    out.update(done=True, charged=funds - k.funds())
    return out


# ---------------------------------------------------------------------------------------------------------- trees
G_FLORA, G_AURA = 0xB43D80, 0xB43D60
F_STATIC_DATA, F_ADD_OCCUPANT, AURA_EFFECT = 7, 17, 6
GROUP_FLORA = 0xE83E0437
P_ICON = 0x8A2602B8


def tree_types() -> list[dict]:
    """The trees of the game's flora menu (flora exemplars with a menu icon), from the game's data, and the
    trees SiMCP designed (design_tree)."""
    from . import gamedata
    out = []
    for inst, ex in gamedata.exemplars(GROUP_FLORA):
        if not ex.get(P_ICON):
            continue
        key = ex.get(0x8A416A99)
        name = gamedata.locale_text(key[2], key[1]) if isinstance(key, list) and len(key) == 3 else None
        out.append({"id": "0x%08X" % inst, "name": name or ex.get(0x20), "exemplar": ex.get(0x20)})
    from . import trees
    return out + trees.designed()           # SiMCP's own tree designs (loaded at the game's start)


def _altitude(p, x: float, z: float) -> float:
    t = p.u32(memory.G_TERRAIN)
    nvx = p.u32(t + 0x38)
    base = p.u32(t + 0x6C)
    cx, cz = int(x // 16), int(z // 16)
    hs = [struct.unpack("<f", p.read(base + 36 * ((cz + dz) * nvx + cx + dx), 4))[0] for dz in (0, 1) for dx in (0, 1)]
    return sum(hs) / 4


def trees(g, kind: str, x0: int, z0: int, x1: int, z1: int, build: bool = True) -> dict:
    """Plant one tree of `kind` (an id or name from tree_types) at the centre of each cell x0..x1, z0..z1, as the
    player's flora tool does: a tree is planted only while the city can pay for it, each one charged
    (WithdrawFunds) after the game places it. build=False only reports the cost."""
    types = tree_types()
    q = kind.strip().lower()
    hit = [t for t in types if q in (t["id"].lower(), (t["name"] or "").lower(), (t["exemplar"] or "").lower())]
    if not hit:
        raise BuildError("unknown tree %r" % kind, "trees: " + ", ".join("%s (%s)" % (t["name"], t["id"]) for t in types))
    typ = int(hit[0]["id"], 16)
    x0, x1 = sorted((int(x0), int(x1)))
    z0, z1 = sorted((int(z0), int(z1)))
    _check_cells(g, [(x0, z0), (x1, z1)])
    k = _Caller(g)
    p, s = k.p, k.s
    data = k.v(p.u32(G_FLORA), F_STATIC_DATA, typ)
    if not data:
        raise BuildError("the game has no flora data for %s" % hit[0]["name"])
    each = struct.unpack("<q", p.read(data + 0x160, 8))[0]
    cells = [(x, z) for z in range(z0, z1 + 1) for x in range(x0, x1 + 1)]
    out = {"tree": hit[0]["name"], "cost_each": each, "cells": len(cells), "cost": each * len(cells)}
    if not build:
        return out
    funds0, planted = k.funds(), 0
    for x, z in cells:
        if k.funds() < each:
            out["stopped"] = "the city cannot pay for more trees"
            break
        wx, wz = (x + 0.5) * 16, (z + 0.5) * 16
        p.write(s + S_OUT, struct.pack("<3f", wx, _altitude(p, wx, wz), wz))
        if k.v(p.u32(G_FLORA), F_ADD_OCCUPANT, typ, s + S_OUT, 0):
            k.withdraw(each)
            k.v(p.u32(G_AURA), AURA_EFFECT, _f32(wx), _f32(wz), 1)
            planted += 1
    out.update(planted=planted, charged=funds0 - k.funds())
    return out
