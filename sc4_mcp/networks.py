"""Transport and utility networks of the open city, read from the game's occupants (verified in LIVE_FACTS).

The occupant manager `[0xB43D0C]` slot 41 GetOccupantsByStandardCityCells(SC4List&, nw cell*, se cell*, type, -1)
fills a list with every occupant of a type in a rectangle (AddRef'd); slot 48 ReleaseOccupantList releases them and
empties the list. The list is one pointer to a root node {next, prev, value}; SiMCP builds both in the bridge's
scratch area (the game only allocates and frees the nodes it adds).

Network pieces (roads, rails, streets, highways, pipes, subways...) are occupants of type 0xC772BF98 (the type the
NAM DLL queries); their cISC4NetworkOccupant interface sits 4 bytes before the occupant interface. Fields of that
interface (read by its getters, slots 12 / 23 / 24 / 40 / 59): +0x13C network flags (bit i = network type i),
+0xFC piece id, +0x104 rotation (low 7 bits) and flip (bit 7), +0x10C primary network type (u8), +0x110 its edges, +0x108
count and +0x114 array of {u32 network type (low byte), u32 edges} for the other networks on the cell, +0x9C / +0xA4
position x / z in metres. Edges hold one byte per side - west, north, east, south - non-zero (low 3 bits) where the
piece connects. Pipes are a subclass with the same fields. Power lines are separate occupants: segments 0x0990B2EA (one per cell) and poles 0x2890D4DE.
"""

from __future__ import annotations

import collections
import struct
from contextlib import contextmanager

from . import memory

G_OCCUPANT_MANAGER = 0xB43D0C
OM_GET_BY_CELLS, OM_RELEASE_LIST = 41, 48
T_NETWORK, T_POWER_LINE, T_POWER_POLE = 0xC772BF98, 0x0990B2EA, 0x2890D4DE
# the getters whose fields _piece reads (GetNetworkFlag, GetActiveEdges); every network class seen shares them
# (roads etc. occupant vtable 0xAA7FF8, pipes 0xAA9730)
GETTERS = {12: 0x6E3000, 40: 0x61AE90}

NAMES = ["road", "rail", "elevated_highway", "street", "pipe", "power_line", "avenue", "subway", "light_rail",
         "monorail", "one_way_road", "dirt_road", "ground_highway"]
CHARS = {"road": "r", "rail": "t", "elevated_highway": "H", "street": "s", "pipe": "p", "power_line": "e",
         "avenue": "a", "subway": "u", "light_rail": "l", "monorail": "m", "one_way_road": "o", "dirt_road": "d",
         "ground_highway": "g"}
UNDERGROUND = {"pipe", "subway"}
CAR = {"road", "street", "avenue", "one_way_road", "dirt_road", "elevated_highway", "ground_highway"}
SIDES = "WNES"
STEP = {0: (-1, 0), 1: (0, -1), 2: (1, 0), 3: (0, 1)}       # side -> (dx, dz)


G_TRAFFIC = 0xB43DA8
TRAVEL_TYPES = ["walk", "car", "bus", "passenger_train", "freight_truck", "freight_train", "subway", "elevated_train",
                "monorail"]


class NetworkError(RuntimeError):
    pass


def _city_size(p) -> tuple[int, int]:
    lm = p.u32(memory.G_LOT_MANAGER)
    return p.u32(lm + 0x24), p.u32(lm + 0x28)


def area(p, x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1) -> tuple[int, int, int, int]:
    """A cell rectangle clamped to the city (-1 = the far edge); refused when empty."""
    nx, nz = _city_size(p)
    x0, z0 = max(0, min(int(x0), nx - 1)), max(0, min(int(z0), nz - 1))
    x1 = nx - 1 if x1 < 0 else min(int(x1), nx - 1)
    z1 = nz - 1 if z1 < 0 else min(int(z1), nz - 1)
    if x1 < x0 or z1 < z0:
        raise NetworkError("the area is empty (%d, %d .. %d, %d)" % (x0, z0, x1, z1))
    return x0, z0, x1, z1


@contextmanager
def occupants(g, typ: int, x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1):
    """The occupants of one type in a cell rectangle (inclusive), held until the block ends."""
    p, b = g.proc, g.bridge
    if not memory.city_pointer(p):
        raise NetworkError("no city is open")
    x0, z0, x1, z1 = area(p, x0, z0, x1, z1)
    om = p.u32(G_OCCUPANT_MANAGER)
    s_ = b.scratch(0x1F00, 0x30)
    lst, root, nw, se = s_, s_ + 0x10, s_ + 0x20, s_ + 0x28
    p.write(lst, struct.pack("<I", root))
    p.write(root, struct.pack("<III", root, root, 0))
    p.write(nw, struct.pack("<ii", x0, z0))
    p.write(se, struct.pack("<ii", x1, z1))
    try:
        r = b.call_function(p.u32(p.u32(om) + 4 * OM_GET_BY_CELLS), [lst, nw, se, typ, 0xFFFFFFFF], this=om)
        if not r.ok:
            raise NetworkError("the occupant query failed: %s" % r.msg)
        items, n = [], p.u32(root)
        while n != root and len(items) < 1_000_000:
            items.append(p.u32(n + 8))
            n = p.u32(n)
        yield items
    finally:                       # release whatever the game put in the list, even after a partial fill
        if p.u32(root) != root:
            b.call_function(p.u32(p.u32(om) + 4 * OM_RELEASE_LIST), [lst], this=om)


def _sides(edges: int) -> int:
    return sum(1 << k for k in range(4) if (edges >> (8 * k)) & 7)


def _side_text(bits: int) -> str:
    return "".join(SIDES[k] for k in range(4) if bits >> k & 1)


_known: dict[int, bool] = {}


def _piece(p, occ: int) -> dict | None:
    """One network piece read from memory: {x, z, networks: {name: side bits}, piece, rotation, flip}."""
    vt = p.u32(occ - 4)
    if vt not in _known:
        _known[vt] = all(p.u32(vt + 4 * slot) == fn for slot, fn in GETTERS.items())
    if not _known[vt]:
        return None
    raw = p.read(occ - 4, 0x140)
    flags = struct.unpack_from("<I", raw, 0x13C)[0] & 0x1FFF
    primary = raw[0x10C]                  # a byte: the next three are not part of it
    e0, extra = struct.unpack_from("<II", raw, 0x110)
    nets = {}
    if primary < len(NAMES):
        nets[NAMES[primary]] = _sides(e0)
    cnt = raw[0x108]
    if cnt and extra:
        ab = p.read(extra, 8 * cnt)
        for k in range(cnt):
            t, e = struct.unpack_from("<II", ab, 8 * k)
            if (t & 0xFF) < len(NAMES):
                nets[NAMES[t & 0xFF]] = nets.get(NAMES[t & 0xFF], 0) | _sides(e)
    for i, name in enumerate(NAMES):           # a flagged network without its own edge record
        if flags >> i & 1 and name not in nets:
            nets[name] = 0
    x, z = struct.unpack_from("<f", raw, 0x9C)[0], struct.unpack_from("<f", raw, 0xA4)[0]
    return {"x": int(x // 16), "z": int(z // 16), "networks": nets, "piece": struct.unpack_from("<I", raw, 0xFC)[0],
            "rotation": raw[0x104] & 0x7F, "flip": raw[0x104] >> 7}


def piece_cells(g, x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1) -> dict:
    """{(x, z): [{network: side bits}, ...]} - one dict per network piece (a junction piece holds two networks;
    an elevated highway and the road under it are two pieces)."""
    p = g.proc
    out: dict = collections.defaultdict(list)
    with occupants(g, T_NETWORK, x0, z0, x1, z1) as items:
        for o in items:
            pc = _piece(p, o)
            if pc:
                out[(pc["x"], pc["z"])].append(pc["networks"])
    return dict(out)


def _power_cells(g, x0, z0, x1, z1) -> set:
    """Cells with a power line: wire segments from memory ([O+0x40], [O+0x44], checked against GetPosition for
    37 of 37), poles by GetPosition (slot 8), 16 to a frame."""
    p, b = g.proc, g.bridge
    found = set()
    with occupants(g, T_POWER_LINE, x0, z0, x1, z1) as items:
        for o in items:
            found.add(struct.unpack("<ii", p.read(o + 0x40, 8)))
    with occupants(g, T_POWER_POLE, x0, z0, x1, z1) as items:
        base = b.scratch(0x1F40, 16 * 12)
        for c in range(0, len(items), 16):
            chunk = items[c:c + 16]
            p.write(base, bytes(12 * len(chunk)))
            r = b.call_sequence([(8, o, [base + 12 * k], 1 << 15) for k, o in enumerate(chunk)])
            if not r.ok:
                continue
            for k in range(len(chunk)):
                if r.ret[k] & 0xFF:
                    x, _, z = struct.unpack("<3f", p.read(base + 12 * k, 12))
                    found.add((int(x // 16), int(z // 16)))
    return {c for c in found if x0 <= c[0] and z0 <= c[1] and (x1 < 0 or c[0] <= x1) and (z1 < 0 or c[1] <= z1)}


def cells(g, x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1, power: bool = True) -> dict:
    """{(x, z): {network name: side bits}} for every network piece (and power line) in the rectangle."""
    out: dict = collections.defaultdict(dict)
    for cell, plist in piece_cells(g, x0, z0, x1, z1).items():
        for nets in plist:
            for k, bits in nets.items():
                out[cell][k] = out[cell].get(k, 0) | bits
    if power:
        for cell in _power_cells(g, x0, z0, x1, z1):
            out[cell].setdefault("power_line", 0)
        _power_sides(out)
    return dict(out)


def _power_sides(out: dict) -> None:
    """Power lines carry no edge record: they connect to power-line neighbours."""
    for (x, z), nets in out.items():
        if "power_line" in nets:
            nets["power_line"] = sum(1 << k for k, (dx, dz) in STEP.items()
                                     if "power_line" in out.get((x + dx, z + dz), {}))


def traffic(g) -> dict:
    """{(x, z): {travel type: trips}} - the traffic simulator's per-cell use (what the Traffic Volume view and the
    network query window show): the hash at TrafficSim +0x17C..+0x180 of nodes {next, key ev<<24 | type<<16 | x<<8 |
    z, TrafficEdgeDensity (16 u16 edge flows, u16 use +0x20)}, morning and evening commutes summed."""
    p = g.proc
    if not memory.city_pointer(p):
        raise NetworkError("no city is open")
    ts = p.u32(G_TRAFFIC)
    b0, b1 = p.u32(ts + 0x17C), p.u32(ts + 0x180)
    n = (b1 - b0) // 4
    if not 0 < n < 1 << 22:
        return {}
    out: dict = collections.defaultdict(dict)
    for head in struct.unpack("<%dI" % n, p.read(b0, 4 * n)):
        node, guard = head, 0
        while node and guard < 100000:
            raw = p.read(node, 0x2A)
            nxt, key = struct.unpack_from("<II", raw)
            use = struct.unpack_from("<H", raw, 0x28)[0]
            tt, x, z = (key >> 16) & 0xFF, (key >> 8) & 0xFF, key & 0xFF
            if use:
                name = TRAVEL_TYPES[tt] if tt < len(TRAVEL_TYPES) else str(tt)
                out[(x, z)][name] = out[(x, z)].get(name, 0) + use
            node, guard = nxt, guard + 1
    return dict(out)


def pieces(g, x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1) -> list[dict]:
    """Every network piece in the rectangle with its piece id, rotation and connected sides per network."""
    p = g.proc
    res = []
    with occupants(g, T_NETWORK, x0, z0, x1, z1) as items:
        for o in items:
            pc = _piece(p, o)
            if pc:
                pc["networks"] = {k: _side_text(v) for k, v in pc["networks"].items()}
                pc["piece"] = "0x%08X" % pc["piece"]
                res.append(pc)
    return sorted(res, key=lambda d: (d["z"], d["x"]))


def network_map(g, network: str = "", x0: int = 0, z0: int = 0, x1: int = -1, z1: int = -1) -> dict:
    """A character map of the networks (one row per cell row) with the connected sides as hex digits."""
    p = g.proc
    if network and network not in NAMES:
        raise NetworkError("unknown network %r (one of %s)" % (network, ", ".join(NAMES)))
    x0, z0, x1, z1 = area(p, x0, z0, x1, z1)
    data = cells(g, x0, z0, x1, z1, power=network in ("", "power_line"))
    counts = collections.Counter(k for nets in data.values() for k in nets)
    rows, edges, links = [], [], []
    for z in range(z0, z1 + 1):
        r, e = [], []
        for x in range(x0, x1 + 1):
            nets = data.get((x, z), {})
            shown = {k: v for k, v in nets.items()
                     if (k == network if network else k not in UNDERGROUND)}
            if not shown:
                r.append(".")
                e.append(".")
                continue
            r.append(CHARS[next(iter(shown))] if len(shown) == 1 else "+")
            bits = 0
            for v in shown.values():
                bits |= v
            e.append("%x" % bits)
        rows.append("".join(r))
        edges.append("".join(e))
    from . import neighbors
    try:
        links = neighbors.connections(g)
    except Exception:  # noqa: BLE001 - the map is still useful without them
        links = []
    return {"area": [x0, z0, x1, z1], "network": network or "surface (all but pipes and subways)",
            "legend": {**{v: k for k, v in CHARS.items()}, "+": "two or more networks", ".": "none"},
            "edges_legend": "hex digit of connected sides: 1 west, 2 north, 4 east, 8 south",
            "counts": dict(counts), "rows": rows, "edges": edges, "neighbour_connections": links}


def route(g, start: tuple[int, int], goal: tuple[int, int], kind: str = "car") -> list[tuple[int, int]]:
    """The shortest path of cells from start to goal along connected pieces (car networks, or one named network)."""
    if kind != "car" and kind not in NAMES:
        raise NetworkError("kind is 'car' or a network name")
    nx, nz = _city_size(g.proc)
    for c in (start, goal):
        if not (0 <= c[0] < nx and 0 <= c[1] < nz):
            raise NetworkError("cell %s is outside the city" % (tuple(c),))
    if kind == "power_line":
        return shortest_path(cells(g), tuple(start), tuple(goal), kind)
    return shortest_path_pieces(piece_cells(g), tuple(start), tuple(goal), kind)


def shortest_path_pieces(pieces: dict, start: tuple[int, int], goal: tuple[int, int], kind: str = "car") -> list:
    """Breadth-first search over (cell, network): a step to a neighbour stays on one network and needs that side on
    both cells; the network changes only inside a piece that holds both (a junction) - so an elevated highway does
    not lead onto the road under it."""
    allowed = CAR if kind == "car" else {kind}

    def bits_of(c, net):
        b_ = 0
        for nets in pieces.get(c, []):
            b_ |= nets.get(net, 0)
        return b_

    starts = [(start, n) for nets in pieces.get(start, []) for n in nets if n in allowed]
    if not starts:
        raise NetworkError("no %s network on the start cell %s" % (kind, start))
    prev = {s_: None for s_ in starts}
    q = collections.deque(starts)
    while q:
        state = q.popleft()
        c, net = state
        if c == goal:
            path = []
            while state is not None:
                if not path or path[-1] != state[0]:
                    path.append(state[0])
                state = prev[state]
            return path[::-1]
        nxt = []
        for side, (dx, dz) in STEP.items():
            n = (c[0] + dx, c[1] + dz)
            if bits_of(c, net) >> side & 1 and bits_of(n, net) >> ((side + 2) & 3) & 1:
                nxt.append((n, net))
        for nets in pieces.get(c, []):
            if net in nets:
                nxt += [(c, other) for other in nets if other != net and other in allowed]
        for st in nxt:
            if st not in prev:
                prev[st] = state
                q.append(st)
    raise NetworkError("no %s route from %s to %s" % (kind, start, goal))


def shortest_path(data: dict, start: tuple[int, int], goal: tuple[int, int], kind: str = "car") -> list:
    """The same over merged cells {(x, z): {network: side bits}} (each cell taken as one piece)."""
    return shortest_path_pieces({c: [nets] for c, nets in data.items()}, start, goal, kind)


def unjoined_ends(g, ends: list[tuple[int, int]], network: str) -> list[tuple[int, int]]:
    """Built end cells of a drag that touch another network piece on a side neither of them connects (a road
    built beside a street's dead end, for instance)."""
    if network not in NAMES or not ends:
        return []
    xs = [c[0] for c in ends]
    zs = [c[1] for c in ends]
    data = cells(g, min(xs) - 1, min(zs) - 1, max(xs) + 1, max(zs) + 1, power=network == "power_line")
    out = []
    for end in ends:
        end = tuple(end)
        bits = 0
        for v in data.get(end, {}).values():
            bits |= v
        for side, (dx, dz) in STEP.items():
            n = (end[0] + dx, end[1] + dz)
            other = data.get(n, {})
            if not other:
                continue
            back = 0
            for v in other.values():
                back |= v
            if not bits >> side & 1 and not back >> ((side + 2) & 3) & 1 and \
                    (set(other) & CAR if network in CAR else network in other):
                out.append(end)
                break
    return out
