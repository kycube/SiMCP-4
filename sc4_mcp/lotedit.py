"""Editing lots as the Lot Editor does: read any of the game's lots (or SiMCP's designs) object by object, and
write a copy with objects removed, moved or added.

A lot is an exemplar in group 0xA8FBD372: its size (0x88EDC790, cells x by z), and one row per object from
0x88EDC900: [type, ?, rotation 0-3, x, y, z, min x, min z, max x, max z, ?, object id, what...] - positions in
metres as 16.16 fixed point from the lot's north-west corner (the street on the +z edge). Types: 0 building,
1 prop, 2 ground texture, 4 flora (tree), 5 / 6 water and land constraints, 7 network tile (what = network type,
?, edges). An edited lot is a new design (its own building copy, as design_building makes).
"""

from __future__ import annotations

import os
import time

from . import content, dbpf

TYPES = {0: "building", 1: "prop", 2: "ground", 3: "fence", 4: "tree", 5: "water", 6: "land", 7: "network"}
NETWORKS = ["road", "rail", "elevated_highway", "street", "pipe", "power_line", "avenue", "subway", "light_rail",
            "monorail", "one_way_road", "dirt_road", "ground_highway"]
P_SIZE = 0x88EDC790
ROW0, ROW_LAST = content.LOT_ROW0, content.LOT_ROW0 + 0x4FF


class LotEditError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _ex_from_designs(iid: int):
    for d in content._manifest():
        if d.get("lot") and int(d["lot"], 16) == iid and not d.get("disabled") and os.path.exists(d.get("file", "")):
            f = dbpf.DBPF(d["file"])
            e = f.get(dbpf.T_EXEMPLAR, content.G_LOTS, iid)
            if e:
                return dbpf.parse_exemplar(f.read(e)), d
    return None, None


def find_lot(key: str):
    """A lot by id (hex) or by its menu item name (the game's or SiMCP's): (lot id, exemplar, source)."""
    k = str(key).strip()
    iid = None
    if k.lower().startswith("0x"):
        iid = int(k, 16)
    else:
        hits = [d for d in content._manifest() if d.get("lot") and d["name"].lower() == k.lower()
                and not d.get("disabled")]
        if hits:
            iid = int(hits[0]["lot"], 16)
    if iid is None:
        raise LotEditError("no lot %r" % key, "use a lot id from build_menu ('lot': '0x...') or a design's name")
    ex, design = _ex_from_designs(iid)
    if ex is not None:
        return iid, ex, "design:" + design["name"]
    _, ex = content._find_exemplar(dbpf.T_EXEMPLAR, iid, content.G_LOTS)
    if ex is None:
        raise LotEditError("lot 0x%08X is not in the game's data or SiMCP's designs" % iid,
                           "lots from other plugins cannot be read yet")
    return iid, ex, "game"


def _names() -> dict:
    """id -> name for props, trees and buildings (cached by lotdesign / build)."""
    from . import build, lotdesign
    out = {}
    for p in lotdesign.game_props("", 100000):
        out[("prop", int(p["id"], 16))] = p["name"] or p["exemplar"]
    try:
        for t in build.tree_types():
            out[("tree", int(t["id"], 16))] = t["name"] or t["exemplar"]
    except Exception:  # noqa: BLE001 - names are only a convenience
        pass
    return out


def _s(v: int) -> int:
    return v - (1 << 32) if v >= 1 << 31 else v


def layout(key: str) -> dict:
    iid, ex, source = find_lot(key)
    props = {p.id: p for p in ex.props}
    size = props[P_SIZE].values if P_SIZE in props else [1, 1]
    names = _names()
    rows = []
    for pid in sorted(k for k in props if ROW0 <= k <= ROW_LAST):
        r = props[pid].values
        m = [_s(v) / 65536.0 for v in r[3:10]]      # x, y, z, min x, min z, max x, max z (signed 16.16)
        t = TYPES.get(r[0], str(r[0]))
        d = {"index": pid - ROW0, "type": t, "x": round(m[0], 2), "z": round(m[2], 2), "rotation": r[2],
             "size_m": [round(m[5] - m[3], 2), round(m[6] - m[4], 2)]}
        if t == "network" and len(r) >= 15:
            d.update(network=NETWORKS[r[12]] if r[12] < len(NETWORKS) else r[12], edges="0x%08X" % r[14])
        elif len(r) >= 13:
            ids = r[12:]
            d["id"] = "0x%08X" % ids[0] if len(ids) == 1 else ["0x%08X" % v for v in ids]
            if t in ("prop", "tree") and len(ids) == 1:
                d["name"] = names.get((t, ids[0]))
            elif t == "building":
                d["name"] = _building_name(ids[0])
        rows.append(d)
    return {"lot": "0x%08X" % iid, "exemplar": props[0x20].values if 0x20 in props else None, "source": source,
            "size_cells": list(size), "rows": rows}


def _building_name(iid: int) -> str | None:
    _, b = content._find_exemplar(dbpf.T_EXEMPLAR, iid, None, not_group=content.G_LOTS)
    if b is None:
        for d in content._manifest():
            if d.get("building") and int(d["building"], 16) == iid:
                return d["name"]
        return None
    v = {p.id: p.values for p in b.props}
    return v.get(content.P_ITEM_NAME) or v.get(0x20)


def edit(name: str, key: str, remove: list[int] | None = None, move: list[dict] | None = None,
         add: list[dict] | None = None, description: str = "", plop_cost: int | None = None,
         monthly_cost: int | None = None) -> dict:
    """A copy of a lot (and its building) with rows removed (by index), moved ({index, x, z, rotation}) or added
    (lotdesign objects: {"prop" / "tree" / "ground": ..., "x", "z", "rotation"})."""
    from . import lotdesign
    content._check_name(name)
    iid, ex, source = find_lot(key)
    props = {p.id: p for p in ex.props}
    size = props[P_SIZE].values if P_SIZE in props else [1, 1]
    rows = {pid - ROW0: list(props[pid].values) for pid in props if ROW0 <= pid <= ROW_LAST}
    for i in remove or []:
        if i not in rows:
            raise LotEditError("the lot has no row %d" % i, "lot_layout lists the rows")
        if rows[i][0] == 0:
            raise LotEditError("row %d is the building: it stays" % i)
        del rows[i]
    fx = content._fx
    for m in move or []:
        i = int(m.get("index", -1))
        if i not in rows:
            raise LotEditError("the lot has no row %d" % i, "lot_layout lists the rows")
        r = rows[i]
        x = float(m.get("x", _s(r[3]) / 65536.0))
        z = float(m.get("z", _s(r[5]) / 65536.0))
        if not (0 <= x <= 16 * size[0] and 0 <= z <= 16 * size[1]):
            raise LotEditError("(%g, %g) is outside the %d x %d-cell lot" % (x, z, size[0], size[1]))
        w, d = (_s(r[8]) - _s(r[6])) / 65536.0, (_s(r[9]) - _s(r[7])) / 65536.0
        rot = int(m.get("rotation", r[2]))
        if not 0 <= rot <= 3:
            raise LotEditError("rotation is 0..3")
        if (rot - r[2]) % 2:
            w, d = d, w
        r[2], r[3], r[5] = rot, fx(x), fx(z)
        r[6:10] = [fx(x - w / 2), fx(z - d / 2), fx(x + w / 2), fx(z + d / 2)]
    added, placed = [], []
    if add:
        side = max(size)
        objs = [dict(o) for o in add]
        for o in objs:
            if not (0 <= float(o.get("x", -1)) <= 16 * size[0] and 0 <= float(o.get("z", -1)) <= 16 * size[1]):
                raise LotEditError("(%s, %s) is outside the %d x %d-cell lot" % (o.get("x"), o.get("z"), *size))
        added, placed = lotdesign.rows(side, None, None, objs)
        oid = max([r[11] for r in rows.values() if len(r) > 11] + [100]) + 1
        for r in added:
            r[11] = oid
            oid += 1
    out_rows = [rows[i] for i in sorted(rows)] + added
    if len(out_rows) > 0x500:
        raise LotEditError("too many objects for one lot")
    building_rows = [r for r in out_rows if r[0] == 0]
    if not building_rows:
        raise LotEditError("the lot has no building row")
    template_building = building_rows[0][12]
    # the clone: same lot and building as design_building makes, then these rows
    entry = content.clone_lot(iid, template_building, name, description, plop_cost, monthly_cost) \
        if source == "game" else None
    if entry is None:
        raise LotEditError("SiMCP's own designs are edited by designing them again",
                           "edit a game lot (lot ids from build_menu)")
    f = dbpf.DBPF(entry["file"])
    recs = [(e.type, e.group, e.instance, f.read(e)) for e in f]
    new_lot = int(entry["lot"], 16)
    new_bld = int(entry["building"], 16)
    out = []
    for t, g, i, data in recs:
        if t == dbpf.T_EXEMPLAR and g == content.G_LOTS and i == new_lot:
            lot = dbpf.parse_exemplar(data)
            lp = [p for p in lot.props if not (ROW0 <= p.id <= ROW_LAST)]
            for k, r in enumerate(out_rows):
                r = list(r)
                if r[0] == 0:
                    r = r[:12] + [new_bld]
                lp.append(dbpf.Property(ROW0 + k, dbpf.PT_UINT32, r, True))
            data = dbpf.build_exemplar(lp, lot.parent)
        out.append((t, g, i, data))
    dbpf.write_dbpf(entry["file"], out)
    items = content._manifest()
    for d in items:
        if d.get("file") == entry["file"]:
            d.update(kind="edited_lot", removed=sorted(remove or []), moved=len(move or []), added=placed)
    content._save_manifest(items)
    return dict(entry, removed=sorted(remove or []), moved=len(move or []), added=placed,
                created=time.strftime("%Y-%m-%d %H:%M:%S"))
