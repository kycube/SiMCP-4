"""Per-building funding of civic buildings and power plants, and what it does to their service (LIVE_FACTS:
building funding).

A building's budget items: BudgetSim `[0xB43D64]` slot 51 GetBudgetItemForPurpose(property holder, purpose, item&)
fills {department, line, purpose, full monthly cost int64 +0x10, index +0x18, local funding float +0x1C}; the
department pays full cost x funding. The player's funding slider (0x77BC90, the budget window's building rows) sets
it through the owning simulator, as SiMCP does:
- power plants: PowerSim `[0xB43DA0]` slot 51 SetPowerPlantFundingPercentage(occupant, const float&)
- police stations: PoliceSim `[0xB43D98]` slot 8 SetStationFunding(occupant, const float&)
- fire stations: FireSim `[0xB43D78]` slot 9 SetStationFunding(occupant, const float&)
- schools / hospitals: ResidentialSim `[0xB43DA4]` slot 19 (occupant, const float& staff, const float& coverage,
  bool school); their query data (slot 26 school / 27 hospital, a 0x40-byte object: ctor 0x414210, dtor 0x414250)
  holds +0x14 maximum capacity, +0x18 capacity now, +0x1C maximum staff, +0x20 staff now, +0x24 enrolled,
  +0x2C staff funding, +0x30 staff full cost, +0x34 coverage (bus / ambulance) funding, +0x38 its full cost.
Efficiency getters take a hidden result pointer: PoliceSim slot 25 / FireSim slot 10 / PowerSim slot 45
(efficiency) and 46 (condition) (float* out, occupant). How funding turns into efficiency is a response curve in
the simulators' tuning exemplars (6534284A-E7E2C2DB-...), read live so plugin overrides count.
"""

from __future__ import annotations

import struct

from . import catalog, city, layers, pointer

G_BUDGET, G_POLICE, G_FIRE, G_POWER, G_RES = 0xB43D64, 0xB43D98, 0xB43D78, 0xB43DA0, 0xB43DA4
BUDGET_ITEM_FOR_PURPOSE = 51
QUERY_CTOR, QUERY_DTOR = 0x414210, 0x414250
TUNING_TYPE, TUNING_GROUP = 0x6534284A, 0xE7E2C2DB
T_POLICE, T_FIRE, T_UTILITIES, T_RESIDENTIAL = 0x28DFCF89, 0x68F5524A, 0xC911E35B, 0x69189C84

# item -> purpose, what the funding pays for, (tuning exemplar, funding -> effect curve, effect), (exemplar, max)
ITEMS = {
    "power": (0xCA58E540, "the power plant's upkeep: output capacity follows efficiency",
              (T_UTILITIES, 0x6911E2DF, "efficiency %"), (T_UTILITIES, 0xE911E2D1)),
    "police": (0x0A567BAA, "the station's officers: coverage strength and radius follow efficiency",
               (T_POLICE, 0x68DDAE93, "efficiency %"), (T_POLICE, 0x68DDAE95)),
    "fire": (0xEA567BC3, "the station's firefighters: coverage follows efficiency",
             (T_FIRE, 0x29233E8D, "efficiency %"), (T_FIRE, 0x29233E8F)),
    "school_staff": (0xEA5654B6, "teachers: capacity (students taught) = maximum capacity x efficiency",
                     (T_RESIDENTIAL, 0x691894C6, "efficiency %"), (T_RESIDENTIAL, 0x891894AD)),
    "school_buses": (0x4A5654BA, "school buses: the area the school serves",
                     (T_RESIDENTIAL, 0xEA53B30F, "coverage %"), (T_RESIDENTIAL, 0x891894AD)),
    "hospital_staff": (0xCA565486, "doctors: capacity (patients treated) = maximum capacity x efficiency",
                       (T_RESIDENTIAL, 0x2918949E, "efficiency %"), (T_RESIDENTIAL, 0xA9189479)),
    "ambulances": (0xEA56549E, "ambulances: the area the hospital serves",
                   (T_RESIDENTIAL, 0x0A53B2F9, "coverage %"), (T_RESIDENTIAL, 0xA9189479)),
}
# budget items the player funds only through the department (no per-building slider in the game)
OTHER_PURPOSES = {"water": 0xCA58C9D5, "sanitation": 0xCA58EDC7, "jail": 0xEA56768A, "landmark": 0xAA59670C,
                  "park": 0xCA639989, "business_deal_income": 0x4A5A495E, "toll_booth": 0x0C3BF549}
DEPARTMENT_CURVES = {"water": (T_UTILITIES, 0x6A410BF2, "efficiency %"),
                     "jail": (T_POLICE, 0x68DDAEA0, "efficiency %"),
                     "power_line_decay": (T_UTILITIES, 0xAA713782, "decay (-) or repair (+) per month"),
                     "pipe_decay": (T_UTILITIES, 0xCA7138C4, "decay (-) or repair (+) per month"),
                     "power_plant_decay": (T_UTILITIES, 0x0911E2E8, "plant decay rate multiplier (x: funding 0-1.2)")}


class ServiceError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise ServiceError("the game's code failed (slot %d): %s" % (slot, r.msg))
    return r.ret[0] & 0xFFFFFFFF


def tuning(g, instances: set[int]) -> dict[int, dict]:
    """{tuning exemplar instance: {property id: value}} as loaded (with plugin overrides)."""
    p, b = g.proc, g.bridge
    rm = p.u32(catalog.G_RESOURCES)
    base = b.scratch(0x1C00)
    out = {}
    for inst in instances:
        p.write(base, struct.pack("<IIII", TUNING_TYPE, TUNING_GROUP, inst, 0))
        _v(g, rm, catalog.RM_GET_RESOURCE, base, catalog.IID_EXEMPLAR, base + 12, 0, 0)
        ex = p.u32(base + 12)
        if not ex:
            continue
        try:
            holder = ex + 0x1C if p.u32(ex + 0x1C) == catalog.HOLDER_VTABLE else _v(g, ex, catalog.EX_HOLDER)
            out[inst] = catalog.holder_properties(p, holder)
        finally:
            _v(g, ex, 2)
    return out


def _curve(tun: dict, inst: int, prop: int) -> list[list[float]] | None:
    v = tun.get(inst, {}).get(prop)
    if not isinstance(v, list) or len(v) < 2:
        return None
    return [[round(v[i], 3), round(v[i + 1], 3)] for i in range(0, len(v) - 1, 2)]


def on_curve(points: list[list[float]], x: float) -> float:
    """Piecewise-linear value of a response curve at x (clamped at its ends)."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / ((x1 - x0) or 1)
    return points[-1][1]


def curves(g) -> dict:
    """The funding response curves the simulators use: [[funding %, effect], ...] per item."""
    tun = tuning(g, {T_POLICE, T_FIRE, T_UTILITIES, T_RESIDENTIAL})
    out = {}
    for name, (_, _, (inst, prop, what), (minst, mprop)) in ITEMS.items():
        mx = tun.get(minst, {}).get(mprop)
        out[name] = {"curve": _curve(tun, inst, prop), "effect": what,
                     "max_funding_percent": round(mx[-1] if isinstance(mx, list) else mx, 1) if mx else None,
                     "initial_funding_percent": round(mx[0], 1) if isinstance(mx, list) and len(mx) > 1 else None}
    for name, (inst, prop, what) in DEPARTMENT_CURVES.items():
        out[name] = {"curve": _curve(tun, inst, prop), "effect": what}
    return out


def _building(g, x: int, z: int) -> tuple[int, dict]:
    occ = pointer.building_at(g, x, z)
    if not occ:
        raise ServiceError("no building on (%d, %d)" % (x, z), "lots() lists the buildings")
    return occ, city.lot_info(g, x, z) or {}


def _items(g, occ: int) -> dict[str, dict]:
    p = g.proc
    holder = _v(g, occ, 6)
    budget = p.u32(G_BUDGET)
    buf = g.bridge.scratch(0x1C40)
    out = {}
    for name, purpose in [(n, v[0]) for n, v in ITEMS.items()] + list(OTHER_PURPOSES.items()):
        p.write(buf, bytes(0x20))
        if _v(g, budget, BUDGET_ITEM_FOR_PURPOSE, holder, purpose, buf) & 0xFF:
            dept, line, _ = struct.unpack("<III", p.read(buf, 12))
            cost, _, pct = struct.unpack("<qif", p.read(buf + 0x10, 16))
            out[name] = {"funding_percent": round(pct * 100, 1), "full_monthly_cost": cost,
                         "monthly_cost": round(cost * pct), "department": "0x%08X" % dept,
                         "per_building": name in ITEMS}
    return out


def _out_float(g, sim: int, slot: int, occ: int) -> float:
    buf = g.bridge.scratch(0x1C80)
    g.proc.write(buf, bytes(4))
    _v(g, sim, slot, buf, occ)
    return round(struct.unpack("<f", g.proc.read(buf, 4))[0] * 100, 1)


def _query(g, occ: int, school: bool) -> dict:
    p, b = g.proc, g.bridge
    res = p.u32(G_RES)
    q = b.scratch(0x1D00)
    b.call_function(QUERY_CTOR, [], this=q)
    try:
        _v(g, res, 26 if school else 27, occ, q)
        raw = p.read(q, 0x40)
    finally:
        b.call_function(QUERY_DTOR, [], this=q)
    i, f = struct.unpack("<16I", raw), struct.unpack("<16f", raw)
    return {"capacity": i[6], "max_capacity": i[5], "staff": i[8], "max_staff": i[7], "enrolled" if school else
            "patients": i[9], "staff_funding": f[11], "coverage_funding": f[13]}


def _effect(g, occ: int, items: dict) -> dict:
    p = g.proc
    eff: dict = {}
    if "power" in items:
        pw = p.u32(G_POWER)
        buf = g.bridge.scratch(0x1C90)
        p.write(buf, bytes(12))
        _v(g, pw, 33, occ, buf, buf + 4)
        _v(g, pw, 34, occ, buf + 8)
        prod, used, mx = struct.unpack("<III", p.read(buf, 12))
        eff["power"] = {"efficiency_percent": _out_float(g, pw, 45, occ),
                        "condition_percent": _out_float(g, pw, 46, occ),
                        "output_capacity_mwh": prod, "used_mwh": used, "max_output_mwh": mx}
    if "police" in items:
        eff["police"] = {"efficiency_percent": _out_float(g, p.u32(G_POLICE), 25, occ)}
    if "fire" in items:
        eff["fire"] = {"efficiency_percent": _out_float(g, p.u32(G_FIRE), 10, occ)}
    for kind, school in (("school", True), ("hospital", False)):
        if kind + "_staff" in items:
            q = _query(g, occ, school)
            q.pop("staff_funding")
            q.pop("coverage_funding")
            eff[kind] = q
    return eff


def building_funding(g, x: int, z: int, with_curves: bool = True) -> dict:
    occ, lot = _building(g, x, z)
    try:
        items = _items(g, occ)
        out = {"building": lot.get("building"), "rect": lot.get("rect"), "items": items,
               "service": _effect(g, occ, items)}
    finally:
        pointer.release(g, occ)
    if with_curves and any(k in ITEMS for k in items):
        cv = curves(g)
        for k, it in items.items():
            if k in ITEMS and cv[k]["curve"]:
                it["effect_now"] = round(on_curve(cv[k]["curve"], it["funding_percent"]), 1)
                it["curve"] = cv[k]["curve"]
                it["effect"] = cv[k]["effect"]
                it["max_funding_percent"] = cv[k]["max_funding_percent"]
                it["pays_for"] = ITEMS[k][1]
    if not items:
        out["note"] = "this building has no budget items (zoned buildings are not funded)"
    return out


def set_building_funding(g, x: int, z: int, item: str, percent: float) -> dict:
    if item not in ITEMS:
        raise ServiceError("item is one of %s" % ", ".join(ITEMS),
                           "water, sanitation, jails, parks and landmarks are funded per department "
                           "(set_department_funding)")
    before = building_funding(g, x, z)
    if item not in before["items"]:
        raise ServiceError("%s has no %s funding" % (before["building"], item),
                           "its items: " + ", ".join(before["items"]) if before["items"] else "")
    mx = before["items"][item].get("max_funding_percent") or 120.0
    pct = max(0.0, min(float(percent), mx)) / 100.0
    p, b = g.proc, g.bridge
    occ, _ = _building(g, x, z)
    val = b.scratch(0x1CC0)
    try:
        if item == "power":
            p.write(val, struct.pack("<f", pct))
            _v(g, p.u32(G_POWER), 51, occ, val)
        elif item == "police":
            p.write(val, struct.pack("<f", pct))
            _v(g, p.u32(G_POLICE), 8, occ, val)
        elif item == "fire":
            p.write(val, struct.pack("<f", pct))
            _v(g, p.u32(G_FIRE), 9, occ, val)
        else:
            school = item.startswith("school")
            q = _query(g, occ, school)
            staff, cover = q["staff_funding"], q["coverage_funding"]
            if item.endswith("staff"):
                staff = pct
            else:
                cover = pct
            p.write(val, struct.pack("<ff", staff, cover))
            _v(g, p.u32(G_RES), 19, occ, val, val + 4, 1 if school else 0)
    finally:
        pointer.release(g, occ)
    after = building_funding(g, x, z)
    return {"building": after["building"], "item": item, "requested_percent": percent,
            "clamped_to_max": percent > mx, "before": before["items"][item], "after": after["items"][item],
            "service_before": before["service"], "service_after": after["service"],
            "note": "capacity and efficiency change at once; coverage maps (map_data police_coverage / "
                    "fire_coverage) follow when the simulators next update (within a month)"}
