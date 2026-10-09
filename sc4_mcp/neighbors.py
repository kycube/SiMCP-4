"""Neighbour connections and neighbour deals (re/agents/networks-deals Q2; verified in LIVE_FACTS).

The neighbours simulator `N = [0xB43D8C]` (vtable 0xAB1EE0) keeps two lists (sentinel*, nodes {next, prev, item +8}):
connections at +0x1C (cSC4NeighborConnection: +0x24 connection type, +0x28 / +0x2C edge cell, +0x30 / +0x34 the
neighbour's region tile, +0x38 flags, bit 1 = inactive) and the city's deals at +0x20 (cSC4NeighborDeal: +0x20 type,
+0x24 / +0x28 the partner's tile, +0x34 amount, +0x48 amount used, +0x50 int64 monthly money, cRZDates at +0x58
start / +0x60 end, +0x78 flags: 1 offered, 2 running, 4 cancelled). Slots 32 / 33 give the month's deal income and
expense.

The player's path (Budget window -> Neighbor Deals, builder 0x77E600): opening the panel calls N slot 25
ProposeDeals(list&, 1), which proposes every deal the connections and both cities' surplus / need allow (N slot 24)
and adds it to the city's deals - running. A row's button (0x78BCA0) cancels a running deal (deal slot 34 Cancel,
then slot 37 SetFlags(1 offered, on)) or starts an offered one (deal slot 35 Activate). The advisor only points to
the panel; there is no accept dialog.
"""

from __future__ import annotations

import struct

from . import memory

G_NEIGHBORS, G_OM = 0xB43D8C, 0xB43D0C
N_PROPOSE_DEALS, N_INCOME, N_EXPENSE = 25, 32, 33
DEAL_CANCEL, DEAL_ACTIVATE, DEAL_SET_FLAGS = 34, 35, 37
OM_RELEASE_LIST = 48

DEAL_TYPES = {0x4773FFE0: "buy_power", 0x4773FFE1: "sell_power", 0x4773FFE2: "buy_water",
              0x4773FFE3: "sell_water", 0x4773FFE4: "export_garbage", 0x4773FFE5: "import_garbage"}
CONNECTION_TYPES = {1: "rail", 2: "road", 3: "highway", 4: "power_line", 5: "pipe", 6: "subway", 7: "light_rail",
                    8: "avenue", 9: "ferry", 10: "dirt_road", 11: "monorail", 12: "ground_highway"}
FLAGS = {1: "offered", 2: "running", 4: "cancelled", 8: "blocked_8", 0x10: "blocked_10", 0x20: "blocked_20",
         0x100: "locked"}
UNITS = {"power": "MWh per month", "water": "cubic metres per month", "garbage": "tons per month"}


class NeighborError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise NeighborError("the game's code failed (slot %d): %s" % (slot, r.msg))
    return r.ret[0] & 0xFFFFFFFF


def _sim(g) -> int:
    p = g.proc
    if not memory.city_pointer(p):
        raise NeighborError("no city is open")
    return p.u32(G_NEIGHBORS)


def _walk(p, sentinel: int) -> list[int]:
    out, n = [], p.u32(sentinel)
    while n and n != sentinel and len(out) < 10000:
        out.append(p.u32(n + 8))
        n = p.u32(n)
    return out


def _day(p, a: int) -> str:
    return "%04d-%02d-%02d" % memory.jdn_to_date(p.u32(a + 4))


def connections(g) -> list[dict]:
    p = g.proc
    out = []
    for c in _walk(p, p.u32(_sim(g) + 0x1C)):
        t, ex, ez, nx, nz = struct.unpack("<5i", p.read(c + 0x24, 20))
        out.append({"network": CONNECTION_TYPES.get(t, t), "edge_cell": [ex, ez], "neighbour_tile": [nx, nz],
                    "active": not (p.u8(c + 0x38) & 2)})
    return out


def _deal(p, d: int, i: int) -> dict:
    typ = DEAL_TYPES.get(p.u32(d + 0x20), "0x%08X" % p.u32(d + 0x20))
    fl = p.u32(d + 0x78)
    goods = typ.split("_")[1] if "_" in typ else None      # an unknown type keeps its hex id
    return {"index": i, "deal": typ, "partner_tile": list(struct.unpack("<ii", p.read(d + 0x24, 8))),
            "amount": p.u32(d + 0x34), "used": p.u32(d + 0x48), "unit": UNITS.get(goods),
            "monthly_money": struct.unpack("<q", p.read(d + 0x50, 8))[0],
            "money_is": "income" if typ.startswith(("sell", "import")) else "expense",
            "state": [n for b, n in FLAGS.items() if fl & b] or ["0x%X" % fl],
            "start": _day(p, d + 0x58), "end": _day(p, d + 0x60)}


def deals(g) -> dict:
    p = g.proc
    n = _sim(g)
    items = [_deal(p, d, i) for i, d in enumerate(_walk(p, p.u32(n + 0x20)))]
    return {"deals": items, "monthly_income": _v(g, n, N_INCOME), "monthly_expense": _v(g, n, N_EXPENSE),
            "connections": connections(g)}


def open_deals(g) -> dict:
    """What opening the Budget window's Neighbor Deals panel does: every deal now possible is proposed and starts."""
    p, b = g.proc, g.bridge
    n = _sim(g)
    before = len(_walk(p, p.u32(n + 0x20)))
    s = b.scratch(0x1E00)
    lst, root = s, s + 0x10
    p.write(lst, struct.pack("<I", root))
    p.write(root, struct.pack("<III", root, root, 0))
    try:
        _v(g, n, N_PROPOSE_DEALS, lst, 1)
    finally:
        if p.u32(root) != root:      # release what the call handed back (AddRef'd), as the panel's list does
            om = p.u32(G_OM)
            _v(g, om, OM_RELEASE_LIST, lst)
    out = deals(g)
    out["new_deals"] = len(out["deals"]) - before
    if not out["connections"]:
        out["hint"] = ("deals need a connection to a neighbour city: a power line (power), a pipe (water) or a road "
                       "(garbage) built to the map edge with build_network(connect_neighbor=true)")
    return out


def _pick(g, index: int) -> int:
    p = g.proc
    items = _walk(p, p.u32(_sim(g) + 0x20))
    if not 0 <= index < len(items):
        raise NeighborError("no deal %d" % index, "neighbor_deals lists them with their index")
    return items[index]


def cancel_deal(g, index: int) -> dict:
    """The panel's "Cancel Deal" button."""
    p = g.proc
    d = _pick(g, index)
    if not p.u32(d + 0x78) & 2:
        raise NeighborError("deal %d is not running" % index)
    before = _deal(p, d, index)
    _v(g, d, DEAL_CANCEL)
    _v(g, d, DEAL_SET_FLAGS, 1, 1)
    return {"cancelled": before, "now": deals(g)}


def start_deal(g, index: int) -> dict:
    """The panel's "Initiate Deal" button for an offered deal."""
    p = g.proc
    d = _pick(g, index)
    fl = p.u32(d + 0x78)
    if fl & 2:
        raise NeighborError("deal %d is already running" % index)
    if not fl & 1 or fl & 0x138:
        raise NeighborError("deal %d cannot start (state %s)" % (index, _deal(p, d, index)["state"]))
    ok = _v(g, d, DEAL_ACTIVATE) & 0xFF
    return {"started": bool(ok), "now": deals(g)}
