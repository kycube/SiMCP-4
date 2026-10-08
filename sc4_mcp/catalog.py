"""What the player can plop: the game's build menus, read from the game's loaded lots and exemplars (so plugins
are included, with the game's own override order), with the menus' availability rules.

Sources (re/agents/lots, re/agents/formats, LIVE_FACTS Phase 3):
- Lot configurations: the lot configuration manager's hash table (buckets [0xB216CC]..[0xB216D0], node {next, IID,
  cSC4LotConfiguration*}). A configuration has its name (cRZString +0xC), size (bytes +0x20/+0x21), zone types (an
  STLport bit vector +0x44: {word*, bit, word*, bit, end}), and objects (vector +0x90 of 0x34-byte rows; a row of
  type 0 is the building, its IIDs in a vector at +0x28). Ploppable lots allow zone 15 ("plopped").
- Building exemplars: BuildingDevelopmentSim [0xB43D68] slot 14 GetBuildingKeyFromType -> the resource manager
  [0xB43CA8] slot 3 GetResource(key, 0xA52160F5) -> exemplar slot 7 = its property holder. The holder keeps a
  sorted vector {id, cSCProperty*} of its own properties at +0x8 and one merged with its cohorts at +0x18. A property
  holds a cIGZVariant at +0x4: value (or array pointer) at +0x8, type u16 at +0x12 (0x8000 = array), count +0x14.
- Menu rules (0x7EFF40): a building appears in a menu when its OccupantGroups (0xAA1DD396) contain the menu's group;
  a City Exclusion Group (0xEA2E078B) greys it while CivicBuildingSim [0xB43DB4] slot 5 says excluded; a
  Conditional Building (0xEA3209F8) needs slot 6's status with bit 2 (unlocked) and is hidden with bit 1.
"""

from __future__ import annotations

import struct

from . import memory

G_LOT_TABLE_BEGIN, G_LOT_TABLE_END = 0xB216CC, 0xB216D0
G_BDS, G_RESOURCES, G_CIVIC = 0xB43D68, 0xB43CA8, 0xB43DB4
IID_EXEMPLAR = 0xA52160F5
BDS_KEY_FROM_TYPE, BDS_BUILDING_NAME = 14, 38
RM_GET_RESOURCE, EX_HOLDER = 3, 7
CIVIC_EXCLUDED, CIVIC_CONDITIONAL = 5, 6
ZONE_PLOPPED = 15

P_GROUPS, P_PLOP_COST, P_BULLDOZE_COST, P_ORDER = 0xAA1DD396, 0x49CAC341, 0x099AFACD, 0x8A2602B9
P_CONDITIONAL, P_EXCLUSION, P_SIZE, P_NAME, P_ITEM_NAME = 0xEA3209F8, 0xEA2E078B, 0x27812810, 0x20, 0x899AFBAD
P_LOT_KEY, P_MONTHLY = 0xEA260589, 0xEA54D286

MENUS = {0x1006: "parks", 0x1300: "transport", 0x130A: "ferry", 0x1400: "power", 0x1401: "water",
         0x1402: "garbage", 0x1500: "police", 0x1501: "jail", 0x1502: "fire", 0x1503: "education",
         0x1504: "education", 0x1505: "education", 0x1506: "education", 0x1507: "health", 0x1508: "airports",
         0x150A: "landmarks", 0x150B: "rewards", 0x1519: "other"}

_VFMT = {1: "?", 2: "B", 3: "b", 4: "H", 5: "h", 6: "I", 7: "i", 8: "Q", 9: "q", 10: "f", 11: "d"}


def _bits(p, a: int) -> set[int]:
    w0, b0, w1, b1 = struct.unpack("<4I", p.read(a, 16))
    n = (w1 - w0) * 8 + b1 - b0
    if not w0 or not 0 <= n <= 256:
        return set()
    raw = p.read(w0, (n + 31) // 32 * 4)
    return {i for i in range(n) if raw[(b0 + i) // 8] >> ((b0 + i) % 8) & 1}


def lot_configurations(p) -> list[tuple[int, int]]:
    """[(lot IID, cSC4LotConfiguration*)] of every lot the game loaded."""
    b0, b1 = p.u32(G_LOT_TABLE_BEGIN), p.u32(G_LOT_TABLE_END)
    if not b0 or b1 <= b0 or b1 - b0 > 4 << 20:
        return []
    out = []
    for n in struct.unpack("<%dI" % ((b1 - b0) // 4), p.read(b0, b1 - b0)):
        k = 0
        while n and k < 10000:
            out.append((p.u32(n + 4), p.u32(n + 8)))
            n = p.u32(n)
            k += 1
    return out


def lot_summary(p, lc: int) -> dict:
    sx, sz = p.read(lc + 0x20, 2)
    rows0, rows1 = p.u32(lc + 0x90), p.u32(lc + 0x94)
    buildings = []
    if rows0 and 0 < rows1 - rows0 <= 0x34 * 2000:
        for r in range(rows0, rows1, 0x34):
            if p.u8(r) == 0:
                i0, i1 = p.u32(r + 0x28), p.u32(r + 0x2C)
                if i0 and 0 < i1 - i0 <= 4096:
                    buildings += list(struct.unpack("<%dI" % ((i1 - i0) // 4), p.read(i0, i1 - i0)))
    return {"name": memory.rz_string(p, lc + 0xC), "size": [sx, sz], "zones": sorted(_bits(p, lc + 0x44)),
            "buildings": buildings}


def _value(p, prop: int):
    t = p.u16(prop + 0x12)
    base = t & 0x7FFF
    if t & 0x8000:
        ptr, n = p.u32(prop + 8), p.u32(prop + 0x14)
        if base in (12, 14):
            return p.read(ptr, min(n, 1024)).split(b"\0", 1)[0].decode("latin-1") if ptr else ""
        f = _VFMT.get(base)
        if not f or not ptr or n > 4096:
            return None
        return list(struct.unpack("<%d%s" % (n, f), p.read(ptr, n * struct.calcsize(f))))
    f = _VFMT.get(base)
    return struct.unpack("<" + f, p.read(prop + 8, struct.calcsize(f)))[0] if f else None


def holder_properties(p, holder: int, ids=None) -> dict[int, object]:
    """{property id: value} from an exemplar's property holder (merged with its cohorts)."""
    v0, v1 = p.u32(holder + 0x18), p.u32(holder + 0x1C)
    if not v0 or not 0 < v1 - v0 <= 8 * 4096:
        v0, v1 = p.u32(holder + 0x8), p.u32(holder + 0xC)
    if not v0 or not 0 < v1 - v0 <= 8 * 4096:
        return {}
    pairs = struct.unpack("<%dI" % ((v1 - v0) // 4), p.read(v0, v1 - v0))
    out = {}
    for i in range(0, len(pairs), 2):
        pid, prop = pairs[i], pairs[i + 1]
        if prop and (ids is None or pid in ids):
            out[pid] = _value(p, prop)
    return out


HOLDER_VTABLE = 0xAAF038       # cISCPropertyHolder of a loaded exemplar, at exemplar + 0x1C
SEQ_SLOT = 1 << 15


class Exemplars:
    """Building exemplars loaded through the game's resource manager, many per bridge round trip (a call into the
    game waits for its next frame), released when done."""

    def __init__(self, k):
        self.k, self.p, self.b = k, k.p, k.b
        self.held: list[int] = []

    def fetch(self, iids: list[int]) -> dict[int, int]:
        """{building IID: property holder} for the buildings the game knows."""
        p, b = self.p, self.b
        bds, rm = p.u32(G_BDS), p.u32(G_RESOURCES)
        base = self.k.s + 0x400
        out: dict[int, int] = {}
        for c in range(0, len(iids), 14):
            chunk = iids[c:c + 14]
            p.write(base, bytes(32 * len(chunk)))
            calls = []
            for j, iid in enumerate(chunk):
                key = base + 32 * j
                calls.append((BDS_KEY_FROM_TYPE, bds, [iid, key], SEQ_SLOT))
                calls.append((RM_GET_RESOURCE, rm, [key, IID_EXEMPLAR, key + 16, 0, 0], SEQ_SLOT))
            r = b.call_sequence(calls)
            if not r.ok:
                raise RuntimeError("loading exemplars failed (status %d) %s" % (r.status, r.msg))
            for j, iid in enumerate(chunk):
                ex = p.u32(base + 32 * j + 16)
                if not ex:
                    continue
                self.held.append(ex)
                holder = ex + 0x1C if p.u32(ex + 0x1C) == HOLDER_VTABLE else self.k.v(ex, EX_HOLDER)
                out[iid] = holder
        return out

    def close(self):
        for c in range(0, len(self.held), 28):
            try:
                self.b.call_sequence([(2, ex, [], SEQ_SLOT) for ex in self.held[c:c + 28]])
            except Exception:  # noqa: BLE001 - releasing is best effort
                pass
        self.held = []


def building_names(k, iids: list[int]) -> dict[int, str]:
    """The names the game shows for buildings (BuildingDevelopmentSim slot 38), 16 per round trip."""
    p, b = k.p, k.b
    bds = p.u32(G_BDS)
    out = {}
    for c in range(0, len(iids), 16):
        chunk = iids[c:c + 16]
        r = b.call_sequence([(BDS_BUILDING_NAME, bds, [iid], SEQ_SLOT) for iid in chunk])
        for j, iid in enumerate(chunk):
            sp = r.ret[j] & 0xFFFFFFFF
            out[iid] = memory.rz_string(p, sp) if r.ok and sp else None
    return out


def _first(v):
    return (v[0] if v else None) if isinstance(v, list) else v


def availability(k, items: list[dict]) -> list[str]:
    """For each item ({"building", "props"}): 'available', 'greyed' (excluded, locked or not yet reached) or
    'hidden', by the build menu's rules; the checks run 16 per round trip."""
    p, b = k.p, k.b
    civic = p.u32(G_CIVIC)
    states = ["available"] * len(items)
    if not civic:
        return states
    checks = []      # (item index, kind, call)
    for n, it in enumerate(items):
        group = _first(it["props"].get(P_EXCLUSION))
        if group:
            checks.append((n, "excl", (CIVIC_EXCLUDED, civic, [group], SEQ_SLOT)))
        if _first(it["props"].get(P_CONDITIONAL)):
            checks.append((n, "cond", (CIVIC_CONDITIONAL, civic, [it["building"]], SEQ_SLOT)))
    for c in range(0, len(checks), 16):
        chunk = checks[c:c + 16]
        r = b.call_sequence([x[2] for x in chunk])
        if not r.ok:
            raise RuntimeError("availability checks failed (status %d) %s" % (r.status, r.msg))
        for j, (n, kind, _) in enumerate(chunk):
            v = r.ret[j] & 0xFFFFFFFF
            if kind == "excl" and v & 0xFF and states[n] == "available":
                states[n] = "greyed"
            elif kind == "cond":
                flags = p.u16(v) if v else 0
                if flags & 1:
                    states[n] = "hidden"
                elif not flags & 2 and states[n] == "available":
                    states[n] = "greyed"
    return states


def _menus(groups) -> list[str]:
    out = []
    for gid in groups or []:
        if gid in MENUS and MENUS[gid] not in out:
            out.append(MENUS[gid])
    return out


_static: dict = {}


def _menu_items(k) -> list[dict]:
    """The menu items with what does not change during a session (cached per game process)."""
    p = k.p
    key = (p.pid, p.u32(G_LOT_TABLE_BEGIN), p.u32(G_LOT_TABLE_END))
    if _static.get("key") == key:
        return _static["items"]
    lots = []
    for liid, lc in lot_configurations(p):
        if lc:
            s = lot_summary(p, lc)
            if ZONE_PLOPPED in s["zones"] and s["buildings"]:
                lots.append((liid, s))
    ex = Exemplars(k)
    items = []
    try:
        holders = ex.fetch(sorted({s["buildings"][0] for _, s in lots}))
        wanted = {P_GROUPS, P_PLOP_COST, P_BULLDOZE_COST, P_CONDITIONAL, P_EXCLUSION, P_NAME, P_ITEM_NAME,
                  P_LOT_KEY, P_MONTHLY, P_ORDER}
        for liid, s in lots:
            biid = s["buildings"][0]
            if biid not in holders:
                continue
            props = holder_properties(p, holders[biid], wanted)
            groups = props.get(P_GROUPS) or []
            groups = groups if isinstance(groups, list) else [groups]
            menus = _menus(groups)
            lot_key = props.get(P_LOT_KEY)
            lot_key = lot_key[0] if isinstance(lot_key, list) and lot_key else lot_key
            if not menus or lot_key != liid:
                continue          # not a menu item: the menu lists a building by its own lot key
            monthly = props.get(P_MONTHLY)
            items.append({"lot": liid, "building": biid, "lot_name": s["name"], "menu": menus[0], "menus": menus, "size": s["size"],
                          "cost": props.get(P_PLOP_COST), "props": props,
                          "monthly_cost": monthly[0] if isinstance(monthly, list) and monthly else monthly,
                          "order": props.get(P_ORDER)})
    finally:
        ex.close()
    names = building_names(k, [i["building"] for i in items])
    for i in items:
        i["name"] = names.get(i["building"]) or i["props"].get(P_ITEM_NAME) or i["props"].get(P_NAME)             or i["lot_name"]
    items.sort(key=lambda d: (d["menu"], d["order"] if isinstance(d["order"], int) else 0, d["name"] or ""))
    _static.update(key=key, items=items)
    return items


def ploppables(k, menu: str = "") -> list[dict]:
    """Every lot the player could plop from a build menu now: building, menu, size, cost, monthly cost, and
    whether the menu offers it (False = greyed: a locked reward, an era / population requirement, an exclusion)."""
    items = [i for i in _menu_items(k) if not menu or menu in i["menus"]]
    out = []
    for i, state in zip(items, availability(k, items)):
        if state != "hidden":
            out.append({"lot": "0x%08X" % i["lot"], "building": "0x%08X" % i["building"], "name": i["name"],
                        "menus": i["menus"], "size": i["size"], "cost": i["cost"],
                        "monthly_cost": i["monthly_cost"], "available": state == "available"})
    return out


def find(k, query: str) -> list[dict]:
    """Menu items matching a lot / building id (0x...) or a name (exact, else contained; case-insensitive)."""
    q = query.strip().lower()
    items = _menu_items(k)
    if q.startswith("0x"):
        v = int(q, 16)
        return [i for i in items if v in (i["lot"], i["building"])]
    exact = [i for i in items if (i["name"] or "").lower() == q]
    return exact or [i for i in items if q in (i["name"] or "").lower()]
