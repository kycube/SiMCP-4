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
G_SIMCP_NAMES = 0x5C4D0F01              # SiMCP's LTEXT names (instance = the building)
P_NAME, P_ITEM_NAME, P_ITEM_DESC, P_NAME_KEY, P_DESC_KEY = 0x20, 0x899AFBAD, 0x8A2602A9, 0x8A416A99, 0xCA416AB5
P_PLOP, P_BULLDOZE, P_MONTHLY, P_LOT_KEY, P_GROUPS = 0x49CAC341, 0x099AFACD, 0xEA54D286, 0xEA260589, 0xAA1DD396
LOT_ROW0 = 0x88EDC900


class ContentError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _manifest() -> list[dict]:
    if not os.path.exists(MANIFEST):
        return []
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            raise ValueError("not a list")
        return items
    except (OSError, ValueError) as e:
        raise ContentError("the design list %s cannot be read (%s)" % (MANIFEST, e),
                           "repair or move it aside; the design files themselves are untouched")


def _save_manifest(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, MANIFEST)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:40] or "design"


# text tokens the game replaces in shown texts; any other #...# may reach the game's Lua - refused
SAFE_TOKENS = {"#city#", "#mayor#", "#name#"}


def _check_tokens(text: str, what: str) -> None:
    for tok in re.findall(r"#[^#]*#", text):
        if tok.lower() not in SAFE_TOKENS:
            raise ContentError("the %s may use only the tokens %s (not %r)" % (what, ", ".join(sorted(SAFE_TOKENS)),
                                                                             tok))


def _check_name(name: str) -> None:
    """A design's name: 1-60 printable characters, no game text tokens or Lua long-string brackets."""
    if not name or len(name) > 60 or any(ord(c) < 32 for c in name):
        raise ContentError("give the design a name of 1-60 printable characters")
    if "#" in name or "[[" in name or "]]" in name:
        raise ContentError("a design name may not contain '#', '[[' or ']]'")
    if any(d["name"].lower() == name.lower() and not d.get("disabled") for d in _manifest()):
        raise ContentError("a design named %r exists" % name, "content_designs lists them")


def _design_path(prefix: str, name: str) -> str:
    """The plugin file of a new design; refused when another design already has that file (similar names give the
    same file name)."""
    path = os.path.join(FOLDER, "%s%s.dat" % (prefix, _slug(name)))
    if os.path.exists(path):
        raise ContentError("another design already uses the file %s" % os.path.basename(path),
                           "choose a more different name")
    return path


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
    _check_name(name)
    if any(v is not None and v < 0 for v in (plop_cost, monthly_cost, bulldoze_cost)):
        raise ContentError("costs are 0 or more")
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
    path = _design_path("SiMCP_", name)
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
    hit = [d for d in items if d["name"].lower() == name.lower() and not d.get("disabled")]
    if not hit:
        raise ContentError("no active design named %r" % name, "content_designs lists them")
    d = hit[0]
    os.makedirs(DISABLED, exist_ok=True)
    if os.path.exists(d["file"]):
        dest = os.path.join(DISABLED, os.path.basename(d["file"]))
        if os.path.exists(dest):                 # an older design of the same name was disabled before: keep both
            root, ext = os.path.splitext(dest)
            dest = "%s-%s%s" % (root, time.strftime("%Y%m%d-%H%M%S"), ext)
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


G_ICONS, P_ICON = 0x6A386D26, 0x8A2602B8      # build menu icons (PNG) and the exemplar property naming one


def menu_icon(draw, size: int = 44) -> bytes:
    """A build-menu icon as the game's are: one 176 x 44 PNG of four 44 x 44 states - disabled (grey), normal,
    hover (brighter), selected (bright, white frame). `draw(image, draw_context)` paints the 44 x 44 picture."""
    import io
    from PIL import Image, ImageDraw, ImageEnhance, ImageOps
    base = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(base)
    for y in range(size):                                        # a sky like the game's icons
        t = y / (size - 1)
        d.line([(0, y), (size, y)], fill=(int(120 + 80 * t), int(150 + 70 * t), int(200 + 40 * t), 255))
    draw(base, d)
    grey = ImageOps.grayscale(base).convert("RGBA")
    grey = ImageEnhance.Brightness(grey).enhance(0.8)
    hover = ImageEnhance.Brightness(base).enhance(1.15)
    sel = hover.copy()
    ImageDraw.Draw(sel).rectangle([0, 0, size - 1, size - 1], outline=(255, 255, 255, 255), width=2)
    out = Image.new("RGBA", (size * 4, size))
    for i, im in enumerate((grey, base, hover, sel)):
        out.paste(im, (i * size, 0))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def box_icon(width: float, depth: float, height: float, wall, roof) -> bytes:
    """An isometric picture of a box building for its menu icon."""
    import math

    def paint(im, d):
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        pts = {}
        for name, (x, y, z) in {"a": (0, 0, 0), "b": (width, 0, 0), "c": (width, 0, depth), "e": (0, 0, depth),
                                 "a2": (0, height, 0), "b2": (width, height, 0), "c2": (width, height, depth),
                                 "e2": (0, height, depth)}.items():
            pts[name] = ((x - z) * c, (x + z) * s - y)
        xs = [p[0] for p in pts.values()]
        ys = [p[1] for p in pts.values()]
        k = 34.0 / max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        ox = 22 - (max(xs) + min(xs)) / 2 * k
        oy = 23 - (max(ys) + min(ys)) / 2 * k
        P = {n: (ox + px * k, oy + py * k) for n, (px, py) in pts.items()}
        shade = tuple(int(v * 0.72) for v in wall)
        d.polygon([P["e"], P["c"], P["c2"], P["e2"]], fill=tuple(wall) + (255,), outline=(40, 40, 40, 255))
        d.polygon([P["c"], P["b"], P["b2"], P["c2"]], fill=shade + (255,), outline=(40, 40, 40, 255))
        d.polygon([P["a2"], P["b2"], P["c2"], P["e2"]], fill=tuple(roof) + (255,), outline=(40, 40, 40, 255))
    return menu_icon(paint)


def model_building(name: str, width: float, depth: float, height: float, wall=(205, 195, 170), roof=(90, 90, 95),
                   windows: bool = True, lot_cells: int = 1, description: str = "", plop_cost: int = 500,
                   monthly_cost: int = 20, template_building: int = 0x4A635AD2, taken: set[int] | None = None,
                   ground="plaza", objects: list[dict] | None = None, invisible: bool = False,
                   model_path: str = "", model_scale: float = 1.0, overrides: dict | None = None,
                   kind: str = "", template_group: int | None = None, extra=None) -> dict:
    """A new building with its own model and texture on its own lot (Parks / landmarks properties of the template
    building), written as a plugin into SiMCP's Plugins folder. `ground` covers every cell of the lot (a name from
    lotdesign.GROUNDS or a lot texture id) and `objects` adds props, trees and grounds (lotdesign.rows). invisible:
    the building is a transparent 1 m quad (lotdesign.park). model_path: an OBJ model (meshimport) instead of the
    generated block; its size (after model_scale) replaces width / depth / height."""
    from . import fsh, lotdesign, meshimport, s3d
    mesh = meshimport.load(model_path, model_scale) if model_path else None
    if mesh:
        width, height, depth = mesh["size_m"]
        if not (0.5 <= width <= 16 * lot_cells - 0.5 and 0.5 <= depth <= 16 * lot_cells - 0.5 and height <= 400):
            raise ContentError("the model is %g x %g m (x %g m tall): it must fit a %d-cell lot (%d m) - scale it or "
                               "use a bigger lot" % (width, depth, height, lot_cells, 16 * lot_cells))
    _check_name(name)
    _check_tokens(description, "description")
    if plop_cost < 0 or monthly_cost < 0:
        raise ContentError("costs are 0 or more")
    if not invisible and not mesh and not (2 <= width <= 16 * lot_cells - 1 and 2 <= depth <= 16 * lot_cells - 1
                              and 2 <= height <= 400):
        raise ContentError("the building must fit its lot: width and depth 2..%d m, height 2..400 m"
                           % (16 * lot_cells - 1))
    if not 1 <= lot_cells <= 6:
        raise ContentError("lots are 1 to 6 cells a side here")
    be, bld = _find_exemplar(dbpf.T_EXEMPLAR, template_building, template_group, not_group=G_LOTS)
    if bld is None:
        raise ContentError("the template building is not in the game's own data")
    lot_iid, bld_iid = _new_ids(taken or set(), 2)
    model_iid = _free(dbpf.T_S3D, G_MODELS, 0xFFFF0000, taken or set())
    tex_iid = _free(dbpf.T_FSH, G_TEXTURES, 0xFFFFFF00, taken or set())
    if invisible:              # alpha 0 everywhere: the default material's alpha test drops every pixel
        wall_fsh = roof_fsh = fsh.write_argb(8, 8, bytes(8 * 8 * 4))
        model = s3d.write(s3d.textured_mesh([(-0.5, 0.01, -0.5, 0, 0), (0.5, 0.01, -0.5, 1, 0), (0.5, 0.01, 0.5, 1, 1),
                                             (-0.5, 0.01, 0.5, 0, 1)], [(0, 2, 1), (0, 3, 2)], tex_iid))
        textures = [(tex_iid, wall_fsh)]
        icon_png = lotdesign.park_icon()
    elif mesh:
        mobj, textures = meshimport.model(mesh, tex_iid)
        model = s3d.write(mobj)
        icon_png = meshimport.icon(mesh)
    else:
        wall_fsh = fsh.write_argb(32, 32, wall_tile(tuple(wall), windows))
        roof_fsh = fsh.write_argb(8, 8, solid(tuple(roof)))
        model = s3d.write(box_mesh(width, depth, height, tex_iid, tex_iid + 1))
        textures = [(tex_iid, wall_fsh), (tex_iid + 1, roof_fsh)]
        icon_png = box_icon(width, depth, height, tuple(wall), tuple(roof))
    side = 16.0 * lot_cells
    cx = cz = side / 2
    building_row = [0, 0, 0, _fx(cx), 0, _fx(cz), _fx(cx - width / 2), _fx(cz - depth / 2), _fx(cx + width / 2),
                    _fx(cz + depth / 2), 0, 1, bld_iid]
    rows, placed = lotdesign.rows(lot_cells, building_row, ground, objects)
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
    for pid, value in (overrides or {}).items():       # service numbers (civic designs): keep the template's type
        cur = [p for p in bprops if p.id == pid]
        if not cur:
            raise ContentError("the template building has no property 0x%08X" % pid)
        if isinstance(value, list):
            cur[0].values = list(value)
        else:
            cur[0].values = [type(cur[0].values[0])(value)] if isinstance(cur[0].values, list) else value
    old = [p for p in bprops if p.id == P_MONTHLY]
    _set(bprops, P_MONTHLY, dbpf.PT_SINT64, [int(monthly_cost)], multi=old[0].multi if old else True)
    icon_iid = _free(dbpf.T_PNG, G_ICONS, 0xFFFFFFFF, taken or set())
    _set(bprops, P_ICON, dbpf.PT_UINT32, [icon_iid])
    records = [(dbpf.T_EXEMPLAR, G_SIMCP_BUILDINGS, bld_iid, dbpf.build_exemplar(bprops, bld.parent)),
               (dbpf.T_EXEMPLAR, G_LOTS, lot_iid, dbpf.build_exemplar(lprops, LOT_COHORT)),
               (dbpf.T_S3D, G_MODELS, model_iid, model),
               (dbpf.T_PNG, G_ICONS, icon_iid, icon_png)] + \
              [(dbpf.T_FSH, G_TEXTURES, inst, data) for inst, data in textures]
    extra_entry = {}
    if extra:                                  # more records that need the building's id (a reward's advice)
        more, extra_entry = extra(bld_iid)
        records += more
    os.makedirs(FOLDER, exist_ok=True)
    path = _design_path("SiMCP_park_" if invisible else "SiMCP_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "file": path, "lot": "0x%08X" % lot_iid, "building": "0x%08X" % bld_iid,
             "model": "0x%08X" % model_iid, "texture": "0x%08X" % tex_iid, "size_m": [width, depth, height],
             "lot_cells": lot_cells, "ground": ground, "objects": placed, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    if kind:
        entry["kind"] = kind
        entry["service"] = {"0x%08X" % k: v for k, v in (overrides or {}).items()}
    if invisible:
        entry["kind"] = "park"
    entry.update(extra_entry)
    if mesh:
        entry["model_file"] = os.path.basename(model_path)
        entry["size_m"] = [width, depth, height]
    items = _manifest()
    items.append(entry)
    _save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch, then build_menu")


# ---- growable buildings (stage 3): designs that grow in zones like the game's own houses, shops and factories
PURPOSES = {"residential": 1, "commercial_services": 2, "commercial_office": 3, "tourism": 4, "agriculture": 5,
            "industrial_processing": 6, "industrial_manufacturing": 7, "industrial_high_tech": 8}
P_ZONE_TYPES, P_WEALTH_TYPES, P_PURPOSE_TYPES, P_LOT_SIZE = 0x88EDC793, 0x88EDC795, 0x88EDC796, 0x88EDC790
P_LOT_FAMILY, P_STAGE, P_FAMILY, P_CAPACITY = 0x88EDC791, 0x27812837, 0x27812870, 0x27812834
_growables: list[dict] | None = None


def growable_templates() -> list[dict]:
    """The game's growable lots (SimCity_1.dat) with their zone types, wealth, purpose, size, growth stage and the
    building family they take, plus one building of that family (its exemplar's parent cohort carries the family)."""
    global _growables
    if _growables is not None:
        return _growables
    d = gamedata._main_dat()
    if d is None:
        raise ContentError("the game's SimCity_1.dat was not found")
    cohort_family: dict[int, list] = {}
    members: dict[tuple, list[int]] = {}
    for e in d:
        if e.type == dbpf.T_COHORT:
            for p in dbpf.parse_exemplar(d.read(e)).props:
                if p.id == P_FAMILY:
                    for f in (p.values if isinstance(p.values, list) else [p.values]):
                        cohort_family.setdefault(f, []).append(e.tgi)
        elif e.type == dbpf.T_EXEMPLAR and e.group != G_LOTS:
            ex = dbpf.parse_exemplar(d.read(e))
            members.setdefault(tuple(ex.parent), []).append(e.instance)
    out = []
    for e in d.find(dbpf.T_EXEMPLAR, G_LOTS, None):
        pr = {p.id: p.values for p in dbpf.parse_exemplar(d.read(e)).props}
        zt = pr.get(P_ZONE_TYPES)
        if not zt or zt in ([15], 15) or not pr.get(P_PURPOSE_TYPES) or not pr.get(P_LOT_FAMILY):
            continue
        fam = pr[P_LOT_FAMILY][0] if isinstance(pr[P_LOT_FAMILY], list) else pr[P_LOT_FAMILY]
        blds = [b for c in cohort_family.get(fam, []) for b in members.get(tuple(c), [])]
        if not blds:
            continue
        stage = pr.get(P_STAGE)
        wealth = pr.get(P_WEALTH_TYPES) or [0]
        purpose = pr[P_PURPOSE_TYPES]
        out.append({"lot": e.instance, "zones": zt if isinstance(zt, list) else [zt],
                    "wealth": wealth[0] if isinstance(wealth, list) else wealth,
                    "purpose": purpose[0] if isinstance(purpose, list) else purpose,
                    "size": list(pr.get(P_LOT_SIZE) or [1, 1]),
                    "stage": stage[0] if isinstance(stage, list) else stage, "family": fam, "building": blds[0]})
    _growables = out
    return out


def _capacity_range(templates: list[dict]) -> tuple[int, int]:
    """The smallest and largest capacity of the game's buildings behind these growable lots."""
    caps = []
    for t in templates[:60]:
        _, b = _find_exemplar(dbpf.T_EXEMPLAR, t["building"], not_group=G_LOTS)
        v = next((p.values for p in (b.props if b else []) if p.id == P_CAPACITY), None)
        if isinstance(v, list) and len(v) >= 2:
            caps.append(int(v[1]))
    return (min(caps), max(caps)) if caps else (1, 1)


def growable_building(name: str, purpose: str, wealth: int, width: float, depth: float, height: float,
                      wall=(205, 195, 170), roof=(90, 90, 95), windows: bool = True, lot_size=(1, 1),
                      stage: int = 0, capacity: int = 0, description: str = "", taken: set[int] | None = None) -> dict:
    """A building that grows in zones, with its own model, on its own lot. The lot and building of a game growable
    of the same purpose, wealth and size (closest growth stage) give the zone types, demand, capacity, pollution and
    the rest; the design gets a building family of its own (its lot and building only go with each other) and the
    generated model. Written as a plugin into SiMCP's Plugins folder."""
    from . import fsh, s3d
    if purpose not in PURPOSES:
        raise ContentError("purpose is one of %s" % ", ".join(PURPOSES))
    _check_name(name)
    lw, ld = int(lot_size[0]), int(lot_size[1])
    if not (1 <= lw <= 6 and 1 <= ld <= 6):
        raise ContentError("lots are 1 to 6 cells a side")
    if not (2 <= width <= 16 * lw - 1 and 2 <= depth <= 16 * ld - 1 and 2 <= height <= 400):
        raise ContentError("the building must fit its lot: width 2..%d m, depth 2..%d m, height 2..400 m"
                           % (16 * lw - 1, 16 * ld - 1))
    pid = PURPOSES[purpose]
    cands = [t for t in growable_templates() if t["purpose"] == pid and t["wealth"] == wealth]
    if not cands:
        raise ContentError("the game has no growable %s lots of wealth %d" % (purpose, wealth),
                           "wealth is 1 ($), 2 ($$) or 3 ($$$); agriculture and industry have fewer kinds")
    same = [t for t in cands if t["size"] == [lw, ld]] or \
        sorted(cands, key=lambda t: abs(t["size"][0] - lw) + abs(t["size"][1] - ld))[:20]
    tpl = min(same, key=lambda t: abs((t["stage"] or 1) - (stage or 1)))
    _, lot = _find_exemplar(dbpf.T_EXEMPLAR, tpl["lot"], G_LOTS)
    _, bld = _find_exemplar(dbpf.T_EXEMPLAR, tpl["building"], not_group=G_LOTS)
    if lot is None or bld is None:
        raise ContentError("the template lot or building could not be read")
    lot_iid, bld_iid, family = _new_ids(taken or set(), 3)
    model_iid = _free(dbpf.T_S3D, G_MODELS, 0xFFFF0000, taken or set())
    tex_iid = _free(dbpf.T_FSH, G_TEXTURES, 0xFFFFFF00, taken or set())
    # the lot: the template's settings and its building and texture rows (props and flora are dropped: they could
    # stand inside the new building); the building row names the new family with the new footprint
    rows, kept = [], []
    for p in lot.props:
        if LOT_ROW0 <= p.id <= 0x88EDCDFF and p.multi and p.values:
            rows.append(list(p.values))
        else:
            kept.append(dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                      p.multi))
    same_size = tpl["size"] == [lw, ld]
    side_x, side_z = 16.0 * lw, 16.0 * ld
    new_rows = []
    for r in rows:
        if r[0] == 0:
            cx, cz = (r[3] / 65536.0, r[5] / 65536.0) if same_size else (side_x / 2, side_z / 2)
            cx = min(max(cx, width / 2 + 0.5), side_x - width / 2 - 0.5)
            cz = min(max(cz, depth / 2 + 0.5), side_z - depth / 2 - 0.5)
            new_rows.append(r[:3] + [_fx(cx), r[4], _fx(cz), _fx(cx - width / 2), _fx(cz - depth / 2),
                                     _fx(cx + width / 2), _fx(cz + depth / 2)] + r[10:12] + [family])
        elif r[0] == 2 and same_size:
            new_rows.append(r)
    if not same_size:
        new_rows.append([2, 0, 0, _fx(side_x / 2), 0, _fx(side_z / 2), _fx(0.04), _fx(0.04), _fx(side_x + 0.04),
                         _fx(side_z + 0.04), 0, 2, PAVING])
    if not any(r[0] == 0 for r in new_rows):
        raise ContentError("the template lot has no building row")
    lprops = list(kept)
    _set(lprops, P_NAME, dbpf.PT_STRING, "SiMCP_" + _slug(name))
    _set(lprops, P_LOT_FAMILY, dbpf.PT_UINT32, [family], multi=True)
    _set(lprops, P_LOT_SIZE, dbpf.PT_UINT8, [lw, ld], multi=True)
    if stage:
        _set(lprops, P_STAGE, dbpf.PT_UINT8, [int(stage)])
    for i, r in enumerate(new_rows):
        lprops.append(dbpf.Property(LOT_ROW0 + i, dbpf.PT_UINT32, r, True))
    # the building: the template's own properties (capacity, groups, costs) under its parent cohort, with the new
    # family, name, size and model
    bprops = _drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                  p.multi) for p in bld.props], P_NAME_KEY, P_DESC_KEY, P_RKT1, P_RKT4)
    _set(bprops, P_NAME, dbpf.PT_STRING, name)
    _set(bprops, P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, G_SIMCP_NAMES, bld_iid], multi=True)   # query name
    _set(bprops, P_FAMILY, dbpf.PT_UINT32, [family], multi=True)
    _set(bprops, P_SIZE, dbpf.PT_FLOAT32, [float(width), float(height), float(depth)], multi=True)
    _set(bprops, P_RKT0, dbpf.PT_UINT32, [dbpf.T_S3D, G_MODELS, model_iid], multi=True)
    # building styles (occupant groups 0x2000 Chicago 1890, 0x2001 New York 1940, 0x2002 Houston 1990, 0x2003
    # Euro-contemporary): a city grows only the styles it has switched on, so a design carries all four
    grp = next((p for p in bprops if p.id == P_GROUPS), None)
    if grp is not None and isinstance(grp.values, list):
        grp.values = [g for g in grp.values if not 0x2000 <= g <= 0x2003] + [0x2000, 0x2001, 0x2002, 0x2003]
    cap = next((p for p in bprops if p.id == P_CAPACITY), None)
    if capacity and cap is not None and isinstance(cap.values, list) and len(cap.values) >= 2:
        lo, hi = _capacity_range(same)          # honest play: no more than the game's own buildings of this kind
        if not lo <= int(capacity) <= hi:
            raise ContentError("capacity for this purpose, wealth and lot size is %d-%d (the game's own)" % (lo, hi))
        cap.values = [cap.values[0], int(capacity)] + list(cap.values[2:])
    wall_fsh = fsh.write_argb(32, 32, wall_tile(tuple(wall), windows))
    roof_fsh = fsh.write_argb(8, 8, solid(tuple(roof)))
    model = s3d.write(box_mesh(width, depth, height, tex_iid, tex_iid + 1))
    records = [(dbpf.T_EXEMPLAR, G_SIMCP_BUILDINGS, bld_iid, dbpf.build_exemplar(bprops, bld.parent)),
               (dbpf.T_EXEMPLAR, G_LOTS, lot_iid, dbpf.build_exemplar(lprops, lot.parent)),
               (dbpf.T_S3D, G_MODELS, model_iid, model),
               (dbpf.T_FSH, G_TEXTURES, tex_iid, wall_fsh),
               (dbpf.T_FSH, G_TEXTURES, tex_iid + 1, roof_fsh),
               (dbpf.T_LTEXT, G_SIMCP_NAMES, bld_iid, dbpf.build_ltext(name))]
    os.makedirs(FOLDER, exist_ok=True)
    path = _design_path("SiMCP_", name)
    dbpf.write_dbpf(path, records)
    cap_now = next((p.values for p in bprops if p.id == P_CAPACITY), None)
    entry = {"name": name, "kind": "growable", "file": path, "lot": "0x%08X" % lot_iid,
             "building": "0x%08X" % bld_iid, "family": "0x%08X" % family, "model": "0x%08X" % model_iid,
             "texture": "0x%08X" % tex_iid, "size_m": [width, depth, height], "lot_size": [lw, ld],
             "purpose": purpose, "wealth": wealth, "zones": tpl["zones"],
             "stage": int(stage) or tpl["stage"], "capacity": cap_now, "description": description,
             "template": {"lot": "0x%08X" % tpl["lot"], "building": "0x%08X" % tpl["building"],
                          "size": tpl["size"], "stage": tpl["stage"]},
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = _manifest()
    items.append(entry)
    _save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch; the design then grows on "
                            "zoned land of its zone and wealth when demand calls for it")


# ---- advice and news (stage 4): the advisors' Lua system, extended the way plugins do it
G_LUA_ADVICE = 0x4A5E8EF6               # the advisor and automata scripts
G_ADVICE_TEXT = 0x6A231EA4              # the advice texts (LTEXT)
ADVISORS = {"utilities": "utilities", "health_education": "hq", "city_planning": "cityplanning",
            "transportation": "transportation", "environment": "environemt", "finances": "finances",
            "safety": "safety", "news": "fluff"}
MOODS = {"alarm": "ALARM", "bad": "BAD_JOB", "neutral": "NEUTRAL", "good": "GREAT_JOB", "fluff": "FLUFF"}
_ALLOWED_TAGS = re.compile(r"</?(b|i|u|br|p)\s*/?>", re.I)


def _advice_text(s: str, what: str, limit: int) -> str:
    if not s or len(s) > limit:
        raise ContentError("the %s is 1-%d characters" % (what, limit))
    if "[[" in s or "]]" in s or s.endswith("]") or "<a" in s.lower():
        raise ContentError("the %s may not contain links, '[[', ']]' or end with ']'" % what)
    _check_tokens(s, what)                    # #link_id#..., #sc4game...#: they run Lua when shown
    if re.sub(_ALLOWED_TAGS, "", s).count("<"):
        raise ContentError("the %s may use only <b>, <i>, <u>, <br> and <p> tags" % what)
    return s


def advice_design(name: str, advisor: str, title: str, message: str, trigger: str = "1", mood: str = "neutral",
                  priority: int = 50, once: bool = True, news_only: bool = False, timeout_days: int = 30,
                  frequency_days: int = 0) -> dict:
    """A new piece of advice (or news) for the advisors, written as a Lua plugin like the game's own: it appears
    when its trigger - a read-only expression of the city's values (game.g_*, game.trend_value...) - is true."""
    from . import luaquery
    if advisor not in ADVISORS:
        raise ContentError("advisor is one of %s" % ", ".join(ADVISORS))
    if mood not in MOODS:
        raise ContentError("mood is one of %s" % ", ".join(MOODS))
    _check_name(name)
    if "\r" in trigger or "\n" in trigger:
        raise ContentError("the trigger is one line")
    try:
        luaquery.check(trigger)
    except luaquery.LuaError as e:
        raise ContentError("trigger: %s" % e, getattr(e, "hint", ""))
    if '"' in trigger or "\\" in trigger:
        raise ContentError("the trigger may not contain quotes or backslashes")
    title = _advice_text(title, "title", 120)
    message = _advice_text(message, "message", 2000)
    guid = "%08x" % random.getrandbits(32)
    # The game runs "package" scripts - Lua records whose first line is "--#-package:<hex>#" - in number order
    # (0x2000 the advice system, 0x3000 the advisors, 0x4000 the tutorial, 0x01001000 Rush Hour; scripts without
    # the header run only when a package dofile()s them by name). Each design is a package of its own, numbered
    # after the game's.
    package = 0x5C4D0000 | random.getrandbits(16)
    # texts are LTEXT records ("text@<instance> fallback", group 0x6A231EA4 like the game's advice); plain text
    # shows with a "NOT_IN_TEXT_DATABASE" mark
    title_iid, message_iid = _new_ids(set(), 2)
    lua = "\n".join([
        "--#-package:%08X# -- package signature" % package,
        "-- SiMCP advice design: %s" % re.sub(r"[\r\n]", " ", name),
        'dofile("_adv_sys.lua")', 'dofile("_adv_advice.lua")', 'dofile("adv_game_data.lua")',
        'dofile("adv_fluffnews.lua")', "",
        "a = create_advice_%s('%s')" % (ADVISORS[advisor], guid),
        'a.trigger  = "%s"' % trigger,
        "a.title    = [[text@%08x %s]]" % (title_iid, title),
        "a.message  = [[text@%08x %s]]" % (message_iid, message),
        "a.mood     = advice_moods.%s" % MOODS[mood],
        "a.priority = %d" % max(0, min(int(priority), 100)),
        "a.timeout  = %d" % max(1, int(timeout_days)),
    ] + (["a.frequency = %d" % int(frequency_days)] if frequency_days else []) + (["a.once = 1"] if once else []) +
        (["a.news_only = 1", "a.persist = 1"] if news_only else []) + [
        "", "if (_sys.config_run == 0)", "then", "   advices : run_triggers()", "end", ""])
    taken = {e.instance for e in (gamedata._main_dat() or [])} if gamedata._main_dat() else set()
    inst = 0xFF000000 | random.getrandbits(24)
    while inst in taken:
        inst = 0xFF000000 | random.getrandbits(24)
    os.makedirs(FOLDER, exist_ok=True)
    path = _design_path("SiMCP_advice_", name)
    dbpf.write_dbpf(path, [(dbpf.T_LUA, G_LUA_ADVICE, inst, lua.encode("latin-1", "replace")),
                           (dbpf.T_LTEXT, G_ADVICE_TEXT, title_iid, dbpf.build_ltext(title)),
                           (dbpf.T_LTEXT, G_ADVICE_TEXT, message_iid, dbpf.build_ltext(message))], compress=False)
    entry = {"name": name, "kind": "advice", "file": path, "advisor": advisor, "guid": guid,
             "package": "0x%08X" % package,
             "lua": "0x%08X" % inst, "trigger": trigger, "title": title, "mood": mood, "once": once,
             "news_only": news_only, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = _manifest()
    items.append(entry)
    _save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch; advisors() then shows "
                            "the advice once its trigger is true (the advisors check every few days)")


# ---- working civic designs: a Maxis civic building's service with SiMCP's model, name, costs and numbers
CIVIC = {   # kind -> (Maxis building (group 0x07BDDF1C), lot cells, {knob: (property, what)})
    "police": (0x03880000, 1, {"radius_m": (0x48D71ED2, "coverage radius in metres (the kiosk: 192 = 12 cells)"),
                               "strength": (0x48D71ED0, "coverage strength (the kiosk: 100)")}),
    "fire": (0x03100000, 1, {"radius_m": (0x08F55DC2, "coverage radius in metres (the small station: 384)"),
                             "strength": (0x08F55DC0, "coverage strength (the small station: 200)")}),
    "clinic": (0x03110000, 1, {"radius_m": (0x091B42A2, "coverage radius in metres (the clinic: 384)"),
                               "capacity": (0x69220415, "patients at full funding (the clinic: 500)")}),
    "school": (0x03140000, 2, {"radius_m": (0x691B42B3, "coverage radius in metres (the K-8 school: 384)"),
                               "capacity": (0x8922041B, "students at full funding (the K-8 school: 500)")}),
}


def civic_building(name: str, kind: str, width: float = 10.0, depth: float = 10.0, height: float = 8.0,
                   wall=(200, 200, 205), roof=(70, 70, 80), lot_cells: int = 0, description: str = "",
                   plop_cost: int | None = None, monthly_cost: int | None = None, ground: str = "concrete",
                   objects: list[dict] | None = None, model_path: str = "", model_scale: float = 1.0,
                   **numbers) -> dict:
    """A police, fire, clinic or school building that works as the game's own (its service copied from a Maxis
    building) with SiMCP's model, name, costs and service numbers (radius_m, strength, capacity - see CIVIC)."""
    if kind not in CIVIC:
        raise ContentError("kind is %s" % ", ".join(CIVIC))
    template, cells, knobs = CIVIC[kind]
    overrides = {}
    for k, v in numbers.items():
        if v is None:
            continue
        if k not in knobs:
            raise ContentError("a %s building takes %s" % (kind, ", ".join(knobs)))
        if not 0 < float(v) <= (4096 if k == "radius_m" else 100000):
            raise ContentError("%s is out of range" % k)
        overrides[knobs[k][0]] = v
    _, tpl = _find_exemplar(dbpf.T_EXEMPLAR, template, 0x07BDDF1C)
    if tpl is None:
        raise ContentError("the game's %s building (0x%08X) is not in SimCity_1.dat" % (kind, template))
    costs = {p.id: p.values for p in tpl.props}
    plop = plop_cost if plop_cost is not None else costs.get(P_PLOP, [500])[0]
    monthly = monthly_cost if monthly_cost is not None else (costs.get(P_MONTHLY) or [20])[0]
    return model_building(name, width, depth, height, wall, roof, True, lot_cells or cells, description, int(plop),
                          int(monthly), template_building=template, ground=ground, objects=objects,
                          model_path=model_path, model_scale=model_scale, overrides=overrides, kind=kind,
                          template_group=0x07BDDF1C)


# ---- rewards: a reward building with its own unlock condition (a reward advice, as adv_rewards.lua writes them)
REWARDS = {"statue": 0x03730000, "mayors_house": 0x031F0000}    # templates in group 0x8A3858D8: effects kept
G_REWARDS = 0x8A3858D8
P_CONDITIONAL, P_EXCLUSION = 0xEA3209F8, 0xEA2E078B
MENU_REWARDS = 0x150B


def reward_building(name: str, condition: str, requirement: str = "", title: str = "", message: str = "",
                    template: str = "statue", width: float = 6.0, depth: float = 6.0, height: float = 10.0,
                    wall=(220, 210, 190), roof=(150, 120, 60), lot_cells: int = 1, description: str = "",
                    plop_cost: int = 2000, monthly_cost: int = 0, ground: str = "plaza",
                    objects: list[dict] | None = None, model_path: str = "", model_scale: float = 1.0) -> dict:
    """A reward for the Rewards menu that unlocks when `condition` (a read-only expression of the city's values,
    like an advice trigger) is true: the building is conditional (0xEA3209F8) and a reward advice named after it
    (create_reward_cityplanning) returns its requirement text until then, reward_state.AVAILABLE after - the
    game's own mechanism. Effects (mayor rating and so on) come from the template reward."""
    from . import luaquery
    if template not in REWARDS:
        raise ContentError("template is %s" % ", ".join(REWARDS))
    if "\r" in condition or "\n" in condition or '"' in condition or "\\" in condition or "]]" in condition:
        raise ContentError("the condition is one line without quotes, backslashes or ']]'")
    try:
        luaquery.check(condition)
    except luaquery.LuaError as e:
        raise ContentError("condition: %s" % e, getattr(e, "hint", ""))
    requirement = _advice_text(requirement or "Unlocks when the city is ready", "requirement", 200)
    title = _advice_text(title or "%s is now available" % name, "title", 120)
    message = _advice_text(message or "Mayor, #city# has earned a %s. Find it in the Rewards menu." % name,
                           "message", 1000)
    exclusion = random.getrandbits(32) | 0x10000000

    def extra(bld_iid):
        req_iid, title_iid, msg_iid = _new_ids({bld_iid}, 3)
        package = 0x5C4D0000 | random.getrandbits(16)
        lua = "\n".join([
            "--#-package:%08X# -- package signature" % package,
            "-- SiMCP reward design: %s" % re.sub(r"[\r\n]", " ", name),
            'dofile("_adv_sys.lua")', 'dofile("_adv_advice.lua")', 'dofile("adv_game_data.lua")', "",
            "a = create_reward_cityplanning('%08x')" % bld_iid,
            "function a.condition()",
            "   if (%s) then" % condition,
            "      return reward_state.AVAILABLE",
            "   end",
            "   return [[text@%08x %s]]" % (req_iid, requirement),
            "end",
            "a.once = 1", "a.persist = 1", "a.timeout = 60", "a.priority = 80",
            "a.title   = [[text@%08x %s]]" % (title_iid, title),
            "a.message = [[text@%08x %s]]" % (msg_iid, message),
            "a.mood = advice_moods.GREAT_JOB",
            "", "if (_sys.config_run == 0)", "then", "   advices : run_triggers()", "end", ""])
        inst = 0xFF000000 | random.getrandbits(24)
        records = [(dbpf.T_LUA, G_LUA_ADVICE, inst, lua.encode("latin-1", "replace")),
                   (dbpf.T_LTEXT, G_ADVICE_TEXT, req_iid, dbpf.build_ltext(requirement)),
                   (dbpf.T_LTEXT, G_ADVICE_TEXT, title_iid, dbpf.build_ltext(title)),
                   (dbpf.T_LTEXT, G_ADVICE_TEXT, msg_iid, dbpf.build_ltext(message))]
        return records, {"condition": condition, "requirement": requirement, "lua": "0x%08X" % inst,
                         "package": "0x%08X" % package}

    return model_building(name, width, depth, height, wall, roof, True, lot_cells, description, plop_cost,
                          monthly_cost, template_building=REWARDS[template], template_group=G_REWARDS,
                          ground=ground, objects=objects, model_path=model_path, model_scale=model_scale,
                          overrides={P_GROUPS: [MENU_REWARDS], P_EXCLUSION: exclusion, P_CONDITIONAL: 1},
                          kind="reward", extra=extra)
