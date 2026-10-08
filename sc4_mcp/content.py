"""The content server: new buildings and lots for the game, written as plugin files (re/agents/formats).

New content goes into one folder of SiMCP's own user folder, `<UserDir>\\Plugins\\zzz_SiMCP` (never the player's
Plugins folder), loaded after everything else. Each design is one DBPF file with its exemplars; a manifest in
SiMCP's home lists them. The game reads plugins at start-up, so new content appears after game_launch.

Stage 1 (here): a building made from an existing menu lot of the game - its models, props and textures - under new
ids, with its own name, description, costs and menu: a lot exemplar (group 0xA8FBD372) whose building row names
the new building, and a building exemplar with the same parent cohort. Removing a design moves its file to
`<SiMCP home>\\content-disabled` (nothing is deleted).
"""

from __future__ import annotations

import json
import os
import random
import re
import time

from . import dbpf, gamedata, launch

FOLDER = os.path.join(launch.USER_DIR, "Plugins", "zzz_SiMCP")
DISABLED = os.path.join(launch.ROOT, "content-disabled")
MANIFEST = os.path.join(launch.ROOT, "content.json")
G_LOTS = 0xA8FBD372
G_SIMCP_BUILDINGS = 0x5C4D0F00          # SiMCP's own building exemplar group
P_NAME, P_ITEM_NAME, P_ITEM_DESC, P_NAME_KEY, P_DESC_KEY = 0x20, 0x899AFBAD, 0x8A2602A9, 0x8A416A99, 0xCA416AB5
P_PLOP, P_BULLDOZE, P_MONTHLY, P_LOT_KEY, P_GROUPS = 0x49CAC341, 0x099AFACD, 0xEA54D286, 0xEA260589, 0xAA1DD396
LOT_ROW0 = 0x88EDC900


class ContentError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _manifest() -> list[dict]:
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_manifest(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, MANIFEST)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:40] or "design"


def _find_exemplar(tgi_type: int, instance: int, group: int | None = None, not_group: int | None = None):
    d = gamedata._main_dat()
    if d is None:
        raise ContentError("the game's SimCity_1.dat was not found")
    hits = [e for e in d.find(tgi_type, group, instance) if not_group is None or e.group != not_group]
    if not hits:
        return None, None
    e = hits[0]
    return e, dbpf.parse_exemplar(d.read(e))


def _set(props: list[dbpf.Property], pid: int, ptype: int, values, multi: bool = False) -> None:
    for p in props:
        if p.id == pid:
            p.ptype, p.values, p.multi = ptype, values, multi
            return
    props.append(dbpf.Property(pid, ptype, values, multi))


def _drop(props: list[dbpf.Property], *ids: int) -> list[dbpf.Property]:
    return [p for p in props if p.id not in ids]


_game_ids: set[tuple[int, int, int]] | None = None


def game_ids() -> set[tuple[int, int, int]]:
    """Every (type, group, instance) in the game's own data files (so new models and textures never replace one)."""
    global _game_ids
    if _game_ids is None:
        from . import identity
        ids = set()
        for i in range(1, 6):
            try:
                ids.update(e.tgi for e in dbpf.DBPF(os.path.join(identity.game_dir(), "SimCity_%d.dat" % i)))
            except OSError:
                pass
        _game_ids = ids
    return _game_ids


def _free(tgi_type: int, group: int, mask: int, taken: set[int]) -> int:
    ids = game_ids()
    while True:
        v = (random.getrandbits(32) | 0x10000000) & mask
        if v not in taken and (tgi_type, group, v) not in ids and all(
                (tgi_type, group, (v + k) & 0xFFFFFFFF) not in ids for k in range(0, 0x500, 0x10)):
            return v


def _new_ids(taken: set[int], n: int) -> list[int]:
    out = []
    while len(out) < n:
        v = random.getrandbits(32) | 0x10000000
        if v not in taken and v not in out:
            out.append(v)
    return out


def designs() -> list[dict]:
    return _manifest()


def clone_lot(template_lot: int, template_building: int | None, name: str, description: str = "",
              plop_cost: int | None = None, monthly_cost: int | None = None, bulldoze_cost: int | None = None,
              taken: set[int] | None = None) -> dict:
    """Write a new design made from a game lot and its building (both from SimCity_1.dat)."""
    if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
        raise ContentError("give the design a name (1-60 characters)")
    if any(d["name"].lower() == name.lower() and not d.get("disabled") for d in _manifest()):
        raise ContentError("a design named %r exists" % name, "content_designs lists them")
    le, lot = _find_exemplar(dbpf.T_EXEMPLAR, template_lot, G_LOTS)
    if lot is not None and template_building is None:      # the building the game's own lot names
        rows = [p.values for p in lot.props if LOT_ROW0 <= p.id <= 0x88EDCDFF and p.multi and p.values
                and p.values[0] == 0 and len(p.values) >= 13]
        template_building = rows[0][12] if rows else 0
    be, bld = _find_exemplar(dbpf.T_EXEMPLAR, template_building, not_group=G_LOTS)
    if lot is None or bld is None:
        raise ContentError("the template lot or building is not in the game's own data",
                           "use a lot and building id from build_menu (Maxis items)")
    lot_iid, bld_iid = _new_ids(taken or set(), 2)
    # the lot: same rows, the building row (type 0) now names the new building
    lprops = [dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values, p.multi)
              for p in lot.props]
    found = False
    for p in lprops:
        if LOT_ROW0 <= p.id <= 0x88EDCDFF and p.multi and p.values and p.values[0] == 0:
            p.values = p.values[:12] + [bld_iid]
            found = True
    if not found:
        raise ContentError("the template lot has no building row")
    _set(lprops, P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name))
    # the building: same properties, new name, description, costs and lot
    bprops = _drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                  p.multi) for p in bld.props], P_NAME_KEY, P_DESC_KEY)
    _set(bprops, P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name))
    _set(bprops, P_ITEM_NAME, dbpf.PT_STRING, name)
    _set(bprops, P_ITEM_DESC, dbpf.PT_STRING, description or name)
    _set(bprops, P_LOT_KEY, dbpf.PT_UINT32, [lot_iid])
    if plop_cost is not None:
        _set(bprops, P_PLOP, dbpf.PT_SINT64, [int(plop_cost)])
    if monthly_cost is not None:
        old = [p for p in bprops if p.id == P_MONTHLY]
        _set(bprops, P_MONTHLY, dbpf.PT_SINT64, [int(monthly_cost)], multi=old[0].multi if old else True)
    if bulldoze_cost is not None:
        _set(bprops, P_BULLDOZE, dbpf.PT_SINT64, [int(bulldoze_cost)])
    records = [(dbpf.T_EXEMPLAR, G_SIMCP_BUILDINGS, bld_iid, dbpf.build_exemplar(bprops, bld.parent)),
               (dbpf.T_EXEMPLAR, G_LOTS, lot_iid, dbpf.build_exemplar(lprops, lot.parent))]
    os.makedirs(FOLDER, exist_ok=True)
    path = os.path.join(FOLDER, "SiMCP_%s.dat" % _slug(name))
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "file": path, "lot": "0x%08X" % lot_iid, "building": "0x%08X" % bld_iid,
             "template_lot": "0x%08X" % template_lot, "template_building": "0x%08X" % template_building,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = _manifest()
    items.append(entry)
    _save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch, then build_menu")


def disable(name: str) -> dict:
    """Take a design out of the game: its file moves to SiMCP's content-disabled folder (not deleted)."""
    items = _manifest()
    hit = [d for d in items if d["name"].lower() == name.lower()]
    if not hit:
        raise ContentError("no design named %r" % name)
    d = hit[0]
    os.makedirs(DISABLED, exist_ok=True)
    if os.path.exists(d["file"]):
        dest = os.path.join(DISABLED, os.path.basename(d["file"]))
        try:
            os.replace(d["file"], dest)             # a rename: all or nothing
        except PermissionError:
            raise ContentError("the game has the design's file open", "quit_game first, then disable_design")
        d["file"] = dest
    d["disabled"] = True
    _save_manifest(items)
    return dict(d, note="restart the game for the change to take effect")


# ------------------------------------------------------------------------------------- stage 2: our own models
G_MODELS, G_TEXTURES, G_LOT_TEXTURES = 0xBADB57F1, 0x1ABE787D, 0x0986135E
LOT_COHORT = (dbpf.T_COHORT, G_LOTS, 0xAA1B5002)
PAVING = 0x258E3000            # a game lot texture (the small plaza's paving)
P_SIZE, P_RKT0, P_RKT1, P_RKT4 = 0x27812810, 0x27812820, 0x27812821, 0x27812824


def _fx(metres: float) -> int:
    """16.16 fixed-point metres, as lot rows store positions."""
    return int(round(metres * 65536)) & 0xFFFFFFFF


def wall_tile(wall: tuple[int, int, int], windows: bool = True, size: int = 32) -> bytes:
    """RGBA of one repeating wall tile (one window per tile; a tile covers 4 m x 4 m of wall)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), wall + (255,))
    if windows:
        d = ImageDraw.Draw(im)
        d.rectangle([size // 4, size // 4, size * 3 // 4 - 1, size * 3 // 4 + 1], fill=(60, 80, 110, 255))
        d.line([size // 4, size * 3 // 4 + 2, size * 3 // 4 - 1, size * 3 // 4 + 2], fill=(235, 235, 230, 255))
    return im.tobytes()


def solid(color: tuple[int, int, int], size: int = 8) -> bytes:
    return bytes(color + (255,)) * (size * size)


def box_mesh(width: float, depth: float, height: float, wall_tex: int, roof_tex: int, tile_m: float = 4.0):
    """A box building: walls (one window tile per tile_m x tile_m of wall, as separate quads - the game clamps
    texture coordinates) and a roof (its own texture), centred on the origin, y up; faces drawn from both sides."""
    import math
    from . import s3d
    w, dp, h = width / 2, depth / 2, height

    def quad(verts, tris, pts, uvs):
        base = len(verts)
        for p, (u, v) in zip(pts, uvs):
            verts.append((p[0], p[1], p[2], u, v))
        for t in ((0, 1, 2), (0, 2, 3)):
            tris.append(tuple(base + i for i in t))
            tris.append(tuple(base + i for i in reversed(t)))
    wv, wt = [], []
    rows = max(1, math.ceil(h / tile_m - 1e-6))
    for (ax, az), (bx, bz) in (((-w, -dp), (w, -dp)), ((w, -dp), (w, dp)), ((w, dp), (-w, dp)), ((-w, dp), (-w, -dp))):
        length = abs(bx - ax) + abs(bz - az)
        cols = max(1, math.ceil(length / tile_m - 1e-6))
        for c in range(cols):
            f0, f1 = c * tile_m / length, min(1.0, (c + 1) * tile_m / length)
            x0, z0 = ax + (bx - ax) * f0, az + (bz - az) * f0
            x1, z1 = ax + (bx - ax) * f1, az + (bz - az) * f1
            u1 = (f1 - f0) * length / tile_m
            for r in range(rows):
                y0, y1 = r * tile_m, min(h, (r + 1) * tile_m)
                v0 = (y1 - y0) / tile_m
                quad(wv, wt, ((x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0)),
                     ((0, v0), (u1, v0), (u1, 0), (0, 0)))
    rv, rt = [], []
    quad(rv, rt, ((-w, h, -dp), (w, h, -dp), (w, h, dp), (-w, h, dp)), ((0, 0), (1, 0), (1, 1), (0, 1)))
    return s3d.multi_mesh([(wv, wt, wall_tex, False), (rv, rt, roof_tex, False)], name=b"SiMCP_box")


def model_building(name: str, width: float, depth: float, height: float, wall=(205, 195, 170), roof=(90, 90, 95),
                   windows: bool = True, lot_cells: int = 1, description: str = "", plop_cost: int = 500,
                   monthly_cost: int = 20, template_building: int = 0x4A635AD2, taken: set[int] | None = None) -> dict:
    """A new building with its own model and texture on its own lot (Parks / landmarks properties of the template
    building), written as a plugin into SiMCP's Plugins folder."""
    from . import fsh, s3d
    if any(d["name"].lower() == name.lower() and not d.get("disabled") for d in _manifest()):
        raise ContentError("a design named %r exists" % name, "content_designs lists them")
    if not (2 <= width <= 16 * lot_cells - 1 and 2 <= depth <= 16 * lot_cells - 1 and 2 <= height <= 400):
        raise ContentError("the building must fit its lot: width and depth 2..%d m, height 2..400 m"
                           % (16 * lot_cells - 1))
    if not 1 <= lot_cells <= 6:
        raise ContentError("lots are 1 to 6 cells a side here")
    be, bld = _find_exemplar(dbpf.T_EXEMPLAR, template_building, not_group=G_LOTS)
    if bld is None:
        raise ContentError("the template building is not in the game's own data")
    lot_iid, bld_iid = _new_ids(taken or set(), 2)
    model_iid = _free(dbpf.T_S3D, G_MODELS, 0xFFFF0000, taken or set())
    tex_iid = _free(dbpf.T_FSH, G_TEXTURES, 0xFFFFFF00, taken or set())
    wall_fsh = fsh.write_argb(32, 32, wall_tile(tuple(wall), windows))
    roof_fsh = fsh.write_argb(8, 8, solid(tuple(roof)))
    model = s3d.write(box_mesh(width, depth, height, tex_iid, tex_iid + 1))
    side = 16.0 * lot_cells
    cx = cz = side / 2
    rows = [
        [0, 0, 0, _fx(cx), 0, _fx(cz), _fx(cx - width / 2), _fx(cz - depth / 2), _fx(cx + width / 2),
         _fx(cz + depth / 2), 0, 1, bld_iid],
        [2, 0, 0, _fx(cx), 0, _fx(cz), _fx(0.04), _fx(0.04), _fx(side + 0.04), _fx(side + 0.04), 0, 2, PAVING],
    ]
    lprops = [dbpf.Property(0x10, dbpf.PT_UINT32, [0x10]), dbpf.Property(P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name)),
              dbpf.Property(0x27812837, dbpf.PT_UINT8, [1], True), dbpf.Property(0x4A4A88F0, dbpf.PT_UINT8, [8], True),
              dbpf.Property(0x88EDC789, dbpf.PT_UINT8, [2], True),
              dbpf.Property(0x88EDC790, dbpf.PT_UINT8, [lot_cells, lot_cells], True),
              dbpf.Property(0x88EDC793, dbpf.PT_UINT8, [15], True), dbpf.Property(0x88EDC795, dbpf.PT_UINT8, [0], True),
              dbpf.Property(0x88EDC796, dbpf.PT_UINT8, [0], True)]
    for i, r in enumerate(rows):
        lprops.append(dbpf.Property(LOT_ROW0 + i, dbpf.PT_UINT32, r, True))
    bprops = _drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                  p.multi) for p in bld.props], P_NAME_KEY, P_DESC_KEY, P_RKT1, P_RKT4)
    _set(bprops, P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name))
    _set(bprops, P_ITEM_NAME, dbpf.PT_STRING, name)
    _set(bprops, P_ITEM_DESC, dbpf.PT_STRING, description or name)
    _set(bprops, P_LOT_KEY, dbpf.PT_UINT32, [lot_iid])
    _set(bprops, P_SIZE, dbpf.PT_FLOAT32, [float(width), float(height), float(depth)], multi=True)
    _set(bprops, P_RKT0, dbpf.PT_UINT32, [dbpf.T_S3D, G_MODELS, model_iid], multi=True)
    _set(bprops, P_PLOP, dbpf.PT_SINT64, [int(plop_cost)])
    old = [p for p in bprops if p.id == P_MONTHLY]
    _set(bprops, P_MONTHLY, dbpf.PT_SINT64, [int(monthly_cost)], multi=old[0].multi if old else True)
    records = [(dbpf.T_EXEMPLAR, G_SIMCP_BUILDINGS, bld_iid, dbpf.build_exemplar(bprops, bld.parent)),
               (dbpf.T_EXEMPLAR, G_LOTS, lot_iid, dbpf.build_exemplar(lprops, LOT_COHORT)),
               (dbpf.T_S3D, G_MODELS, model_iid, model),
               (dbpf.T_FSH, G_TEXTURES, tex_iid, wall_fsh),
               (dbpf.T_FSH, G_TEXTURES, tex_iid + 1, roof_fsh)]
    os.makedirs(FOLDER, exist_ok=True)
    path = os.path.join(FOLDER, "SiMCP_%s.dat" % _slug(name))
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "file": path, "lot": "0x%08X" % lot_iid, "building": "0x%08X" % bld_iid,
             "model": "0x%08X" % model_iid, "texture": "0x%08X" % tex_iid, "size_m": [width, depth, height],
             "lot_cells": lot_cells, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = _manifest()
    items.append(entry)
    _save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch, then build_menu")
