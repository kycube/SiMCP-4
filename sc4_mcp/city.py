"""The open city's state: budget, demand, lots and buildings, advisors (re/reports/economy, lots, advisors-ui;
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


# developer types (residents or jobs by purpose and wealth); lot slot 53 GetPopulation(type), slot 50
# GetCapacity(type, force) (Windows order; verified on a house 5/5, a factory 4/5 jobs, shops 31/32 jobs)
DEV_TYPES = {0x1010: "R$", 0x1020: "R$$", 0x1030: "R$$$", 0x3110: "CS$", 0x3120: "CS$$", 0x3130: "CS$$$",
             0x3320: "CO$$", 0x3330: "CO$$$", 0x4100: "IR", 0x4200: "ID", 0x4300: "IM", 0x4400: "IHT"}
LOT_POPULATION, LOT_CAPACITY = 53, 50
_ZONE_DEVS = {"residential": (0x1010, 0x1020, 0x1030), "commercial": (0x3110, 0x3120, 0x3130, 0x3320, 0x3330),
              "industrial": (0x4200, 0x4300, 0x4400), "agriculture": (0x4100,)}


def _devs(zone) -> tuple:
    z = str(zone)
    return next((v for k, v in _ZONE_DEVS.items() if z.startswith(k)), ())


def occupancy_many(g, items: list[tuple[int, str]]) -> list[dict]:
    """[(lot pointer, zone name)] -> [{group: {"occupied": n, "capacity": m}}] in batched calls."""
    b = g.bridge
    calls, keys = [], []
    for i, (lot, zone) in enumerate(items):
        for dt in _devs(zone):
            calls.append((LOT_POPULATION, lot, [dt], 1 << 15))
            calls.append((LOT_CAPACITY, lot, [dt, 0], 1 << 15))
            keys.append((i, dt))
    out = [dict() for _ in items]
    for c in range(0, len(calls), 16):          # a call sequence reports 16 results
        r = b.call_sequence(calls[c:c + 16])
        if not r.ok:                              # a fault in the game's code: say which lots are not known
            for j in range(c, len(calls), 2):
                out[keys[j // 2][0]]["unknown"] = True
            break
        for j in range(0, min(16, len(calls) - c), 2):
            i, dt = keys[(c + j) // 2]
            pop, cap = r.ret[j] & 0xFFFF, r.ret[j + 1] & 0xFFFF
            if pop or cap:
                out[i][DEV_TYPES[dt]] = {"occupied": pop, "capacity": cap}
    return out


def lots(g, zone: str | None = None, x0: int = 0, z0: int = 0, x1: int = 1 << 30, z1: int = 1 << 30,
         names: bool = True, limit: int = 2000, occupancy: bool = False) -> dict:
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
            d["_lot"] = lot
            out.append(d)
    if names:
        for d in out:
            if d["_iid"]:
                d["building"] = building_name(g, d["_iid"])
    if occupancy:
        occ = occupancy_many(g, [(d["_lot"], d["zone"]) for d in out])
        for d, o in zip(out, occ):
            if o:
                d["occupancy"] = o
    for d in out:
        d.pop("_iid", None)
        d.pop("_lot", None)
    return {"count": p.u32(LM + 0x64), "listed": len(out), "lots": out}


def lot_info(g, x: int, z: int) -> dict | None:
    lot = layers.lot_at(g.proc, x, z)
    if not lot:
        return None
    d = _lot(g.proc, lot)
    if d["_iid"]:
        d["building"] = building_name(g, d["_iid"])
    d.pop("_iid", None)
    o = occupancy_many(g, [(lot, d["zone"])])[0]
    if o:
        d["occupancy"] = o
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
    if not d["_iid"] or d["state"] not in ("occupied", "abandoned"):
        raise ValueError("the lot has no building yet (%s)" % d["state"])
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


CITY_SET_NAME, CITY_SET_NAME_CHANGED, CITY_SET_MAYOR = 13, 15, 17
FN_RZSTRING_CTOR, RZSTRING_FROM_CHAR, RZSTRING_DELETE = 0x578390, 3, 28


def _check_city_name_free(g, name: str) -> None:
    """Saving names the file "City - <name>.sc4": refuse a name another city file of the region already has, or
    another founded city's name (the save would overwrite it)."""
    import os
    from . import regions
    current = os.path.normcase(os.path.abspath(g.city_file() or ""))
    folder = os.path.dirname(current)
    if not os.path.isdir(folder):
        return
    target = os.path.normcase(os.path.abspath(os.path.join(folder, "City - %s.sc4" % name)))
    if os.path.exists(target) and target != current:
        raise ValueError("another city of this region is saved as %s" % os.path.basename(target))
    for f in os.listdir(folder):
        path = os.path.normcase(os.path.abspath(os.path.join(folder, f)))
        if not f.lower().endswith(".sc4") or path == current:
            continue
        try:
            other = regions.read_city(path)
        except Exception:  # noqa: BLE001 - unreadable: the file name check above covers it
            continue
        if other.get("established") and (other.get("name") or "").lower() == name.lower():
            raise ValueError("%s is already the name of another city of this region (%s)" % (name, f))


def rename(g, name: str = "", mayor: str = "") -> dict:
    """What the city name window in the control panel does: city slot 13 SetCityName (and slot 15 marks the name
    changed, so the next save names the file after it) and slot 17 SetMayorName, each from a cRZString."""
    p, b = g.proc, g.bridge
    c = memory.city_pointer(p)
    if not c:
        raise ValueError("no city is open")
    for label, text in (("city name", name), ("mayor name", mayor)):
        if text and (len(text) > 31 or any(ord(ch) < 32 or ch in r'\/:*?"<>|' for ch in text)):
            raise ValueError(r'the %s is 1-31 characters, without \ / : * ? " < > |' % label)
    if name:
        _check_city_name_free(g, name)
    s = b.scratch(0x1D80)
    for text, slot in ((name, CITY_SET_NAME), (mayor, CITY_SET_MAYOR)):
        if not text:
            continue
        raw = text.encode("latin-1")
        p.write(s + 0x40, raw + b"\0")
        p.write(s, bytes(0x14))
        if not b.call_function(FN_RZSTRING_CTOR, [], this=s).ok:
            raise ValueError("could not make a game string")
        try:
            b.vcall(s, RZSTRING_FROM_CHAR, s + 0x40, len(raw))
            b.vcall(c, slot, s)
            if slot == CITY_SET_NAME:
                b.vcall(c, CITY_SET_NAME_CHANGED, 1)
        finally:
            b.vcall(s, RZSTRING_DELETE, 0)
    basics = memory.city_basics(p) or {}
    return {"name": basics.get("name"), "mayor": basics.get("mayor"),
            "note": "save_city writes the city under its new name"}
