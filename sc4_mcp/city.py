"""The open city's state: budget, demand, lots and buildings, advisors (re/agents/economy, lots, advisors-ui;
verified live in LIVE_FACTS). Memory reads where the data is a plain field; the game's own getters through the
bridge where it computes a value (monthly totals, demand objects, building names)."""

from __future__ import annotations

import re
import struct

from . import layers, memory

G_BUDGET = 0xB43D64
G_DEMAND = 0xB43D74
G_RESIDENTIAL = 0xB43DA4
G_BUILDING_DEV = 0xB43D68
G_ADVISORS = 0xB43D34

TAX_GROUPS = ["residential_low", "residential_medium", "residential_high", "commercial_services_low",
              "commercial_services_medium", "commercial_services_high", "commercial_office_medium",
              "commercial_office_high", "industrial_agriculture", "industrial_dirty", "industrial_manufacturing",
              "industrial_high_tech"]
DEMAND_IDS = [(0x1010, "residential_low"), (0x1020, "residential_medium"), (0x1030, "residential_high"),
              (0x3110, "commercial_services_low"), (0x3120, "commercial_services_medium"),
              (0x3130, "commercial_services_high"), (0x3320, "commercial_office_medium"),
              (0x3330, "commercial_office_high"), (0x4100, "industrial_agriculture"), (0x4200, "industrial_dirty"),
              (0x4300, "industrial_manufacturing"), (0x4400, "industrial_high_tech")]
ZONES = {0: "none", 1: "residential_low", 2: "residential_medium", 3: "residential_high", 4: "commercial_low",
         5: "commercial_medium", 6: "commercial_high", 7: "agriculture", 8: "industrial_medium", 9: "industrial_high",
         10: "military", 11: "airport", 12: "seaport", 13: "spaceport", 14: "landfill", 15: "plopped"}
LOT_STATES = {0: "created", 1: "ready", 2: "under_construction", 3: "occupied", 4: "abandoned", 5: "being_destroyed",
              6: "destroyed"}
WEALTH = {0: None, 1: "low", 2: "medium", 3: "high"}
FACING = {0: "north", 1: "east", 2: "south", 3: "west"}
MOODS = {0: "alarm", 1: "bad", 3: "neutral", 5: "good", 7: "fluff"}


def _int64(r) -> int:
    return (r.ret[0] & 0xFFFFFFFF) | (r.ret[1] << 32)


def budget(g) -> dict:
    p, b = g.proc, g.bridge
    B = p.u32(G_BUDGET)
    vt = p.u32(B)

    def call64(slot):
        return _int64(b.call_function(p.u32(vt + 4 * slot), [], this=B))

    funds = struct.unpack("<q", p.read(B + 0x28, 8))[0]
    last_inc, last_exp = struct.unpack("<qq", p.read(B + 0x830, 8) + p.read(B + 0x840, 8))
    return {
        "funds": funds,
        "tax_rates": {name: round(p.f32(B + 0x70 + i * 0x80), 1) for i, name in enumerate(TAX_GROUPS)},
        "monthly": {"income": call64(16), "expense": call64(14)},
        "last_month": {"income": last_inc, "expense": last_exp},
        "year_to_date": {"income": call64(10), "expense": call64(12)},
        "end_of_year_estimate": {"income": call64(11), "expense": call64(13)},
        "loans": {"count": p.u32(B + 0x784), "borrowed": struct.unpack("<q", p.read(B + 0x38, 8))[0]},
        "note": "funds change once a month, when the month's income and expenses are settled",
    }


def demand(g) -> dict:
    p, b = g.proc, g.bridge
    DS = p.u32(G_DEMAND)
    out = {}
    for did, name in DEMAND_IDS:
        d = b.vcall(DS, 6, did, 0x20000).ret[0] & 0xFFFFFFFF   # GetDemand(id, total)
        if not d:
            continue
        out[name] = {"demand": round(p.f32(d + 0x34)), "cap": round(p.f32(d + 0x44), 3),
                     "supply": round(p.f32(d + 0x14)), "wanted": round(p.f32(d + 0x18))}
    return {"demand": out, "residents": p.u32(p.u32(G_RESIDENTIAL) + 0xA4),
            "note": "demand is the game's active demand per group (the demand graph's bars; -10000..54000 here); "
                    "cap is the share of demand blocked by caps (0 = none)"}


_names: dict[int, str] = {}


def building_name(g, iid: int) -> str | None:
    if iid in _names:
        return _names[iid]
    p = g.proc
    s = g.bridge.vcall(p.u32(G_BUILDING_DEV), 38, iid).ret[0] & 0xFFFFFFFF   # GetBuildingName(type)
    name = memory.rz_string(p, s) if s else None
    _names[iid] = name
    return name


def _lot(p, lot: int) -> dict:
    raw = p.read(lot, 0x8C)
    biid = struct.unpack_from("<I", raw, 0x3C)[0]
    flags = raw[0x79]
    return {"x": raw[0x7A], "z": raw[0x7B], "size": [raw[0x7C], raw[0x7D]], "rect": list(raw[0x20:0x24]),
            "facing": FACING.get(raw[0x7E], raw[0x7E]), "zone": ZONES.get(raw[0x81], raw[0x81]),
            "wealth": WEALTH.get(raw[0x82], raw[0x82]), "state": LOT_STATES.get(raw[0x7F], raw[0x7F]),
            "historical": bool(flags & 0x20), "needs_power": bool(flags & 0x08), "powered": bool(flags & 0x10),
            "building_id": "0x%08X" % biid if biid else None, "_iid": biid}


def lots(g, zone: str | None = None, x0: int = 0, z0: int = 0, x1: int = 1 << 30, z1: int = 1 << 30,
         names: bool = True, limit: int = 2000) -> dict:
    p = g.proc
    LM = p.u32(memory.G_LOT_MANAGER)
    sent = p.u32(LM + 0x5C)
    node, out, n = p.u32(sent), [], 0
    while node and node != sent and n < 100000:
        n += 1
        lot = p.u32(node + 8)
        node = p.u32(node)
        d = _lot(p, lot)
        if zone and d["zone"] != zone:
            continue
        if d["rect"][2] < x0 or d["rect"][0] > x1 or d["rect"][3] < z0 or d["rect"][1] > z1:
            continue
        if len(out) < limit:
            out.append(d)
    if names:
        for d in out:
            if d["_iid"]:
                d["building"] = building_name(g, d["_iid"])
    for d in out:
        d.pop("_iid", None)
    return {"count": p.u32(LM + 0x64), "listed": len(out), "lots": out}


def lot_info(g, x: int, z: int) -> dict | None:
    lot = layers.lot_at(g.proc, x, z)
    if not lot:
        return None
    d = _lot(g.proc, lot)
    if d["_iid"]:
        d["building"] = building_name(g, d["_iid"])
    d.pop("_iid", None)
    return d


LOT_SET_HISTORICAL = 44
GROWABLE_ZONES = {"residential_low", "residential_medium", "residential_high", "commercial_low",
                  "commercial_medium", "commercial_high", "agriculture", "industrial_medium", "industrial_high"}


def set_historical(g, x: int, z: int, on: bool = True) -> dict:
    """The query window's "Make Historical" button (R / C / I query windows, button 0x107A): lot slot 44
    SetHistorical sets bit 0x20 of lot +0x79. A historical building is kept as it is - not redeveloped - and the
    game charges nothing. Only zoned (growable) buildings have the button."""
    lot = layers.lot_at(g.proc, x, z)
    if not lot:
        raise ValueError("no lot on (%d, %d)" % (x, z))
    d = _lot(g.proc, lot)
    if d["zone"] not in GROWABLE_ZONES:
        raise ValueError("only zoned buildings can be made historical (this lot is %s)" % d["zone"])
    g.bridge.vcall(lot, LOT_SET_HISTORICAL, 1 if on else 0)
    return lot_info(g, x, z)


def _text(html: str) -> str:
    import html as htmlmod
    t = re.sub(r"<[^>]+>", " ", html)
    t = htmlmod.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def advisors(g, include_fluff: bool = False) -> dict:
    p = g.proc
    sys_ = p.u32(G_ADVISORS)
    hdr = p.u32(sys_ + 0x4C)
    nodes, stack, cur = [], [], p.u32(hdr + 4)
    while (cur and cur != hdr) or stack:               # in-order walk of the STLport map (ids ascending)
        while cur and cur != hdr:
            stack.append(cur)
            cur = p.u32(cur + 8)
        cur = stack.pop()
        nodes.append(cur)
        cur = p.u32(cur + 0xC)
    out = []
    for nd in nodes:
        aid, I = p.u32(nd + 0x10), p.u32(nd + 0x14)
        if aid < 21 or (aid == 28 and not include_fluff) or aid == 30:
            continue                                     # 1-5 / 30 are My Sim panels; 28 the fluff news
        vb, ve = p.u32(I + 0x7C), p.u32(I + 0x80)
        active = []
        for i in range((ve - vb) // 16):
            adv = p.u32(vb + 16 * i)
            if not adv or not p.u32(adv + 0x70) & 2:
                continue
            mood = p.u32(adv + 0x84)
            active.append({"title": memory.rz_string(p, adv + 0x30), "mood": MOODS.get(mood, mood),
                           "priority": p.u32(adv + 0x78),
                           "message": _text(memory.rz_string(p, adv + 0x50, 4000))})
        active.sort(key=lambda a: -a["priority"])
        moods = [a["mood"] for a in active]
        worst = next((m for m in ("alarm", "bad", "neutral", "good") if m in moods), None)
        out.append({"advisor": memory.rz_string(p, I + 0x10), "id": aid, "mood": worst, "messages": active})
    return {"advisors": out}
