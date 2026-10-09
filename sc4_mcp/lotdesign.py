"""Props and lot layouts for SiMCP's designs (re/agents/formats Q2, LIVE_FACTS Phase 7).

A lot exemplar lists its objects as rows 0x88EDC900.. (numbered without gaps): [type, detail, orientation, x, y, z,
minX, minZ, maxX, maxZ, 0, object id, what...] with positions in 16.16 fixed-point metres from the lot's north-west
corner and the street on the lot's +z edge. Types: 0 the building, 1 a prop (an exemplar of type 0x1E in group
0xC977C536, or a prop family 0xA000xxxx), 2 a ground texture (FSH group 0x0986135E, one row per 16 m cell), 4 a tree
(a flora exemplar). Detail 0x00 shows the object at every lot-detail setting (the game's own decorations often use
0x10 / 0x20, shown only at medium / high detail).

New props are SiMCP's own models: a box, cylinder, cone or sign (a board on a post that can carry a picture), each
face written once and facing out (as the game's own models are - a face written both ways round can draw its
unlit back over its front), on an exemplar copied from the game's stone bench (0x29010000) with RKT0.
"""

from __future__ import annotations

import io
import math
import os
import struct
import time

from . import content, dbpf

G_PROPS = 0xC977C536
PROP_TEMPLATE = 0x29010000                  # APzPark3x1x2_StoneBench
GROUNDS = {"paving": 0x258F2000, "plaza": 0x258E3000, "concrete": 0x258D1000, "asphalt": 0x258C2000,
           "grass": 0x25D60000, "lawn": 0x252B3000, "meadow": 0x25F40000, "gravel": 0x25FB1000,
           "garden": 0x26213000, "sand": 0x25901000, "parking": 0x25A32000}
SHAPES = ("box", "cylinder", "cone", "sign")
ROW_PROP, ROW_TEXTURE, ROW_FLORA, ROW_BUILDING = 1, 2, 4, 0
PT = 128                                     # prop texture size
REG = {"side": (0, 0, 64, 64), "top": (64, 0, 128, 64), "face": (0, 64, 128, 128)}
_props: list[dict] | None = None


class LotError(content.ContentError):
    pass


# ---------------------------------------------------------------- the game's props
def game_props(query: str = "", limit: int = 40) -> list[dict]:
    """The game's props (SimCity_1.dat) and SiMCP's prop designs whose name contains `query`."""
    global _props
    if _props is None:
        from . import gamedata
        d = gamedata._main_dat()
        if d is None:
            raise LotError("the game's SimCity_1.dat was not found")
        _props = []
        for e in d.find(dbpf.T_EXEMPLAR, G_PROPS):
            try:
                ex = dbpf.parse_exemplar(d.read(e))
            except Exception:  # noqa: BLE001 - a record that is not an exemplar
                continue
            if ex.get(0x10) != 0x1E:
                continue
            key = ex.get(content.P_NAME_KEY)
            shown = gamedata.locale_text(key[2], key[1]) if isinstance(key, list) and len(key) == 3 else None
            size = ex.get(content.P_SIZE)
            _props.append({"id": "0x%08X" % e.instance, "exemplar": ex.get(content.P_NAME), "name": shown,
                           "size_m": [round(v, 2) for v in size] if isinstance(size, list) else None})
    q = query.strip().lower()
    mine = [{"id": d["prop"], "exemplar": "SiMCP_prop_" + content._slug(d["name"]), "name": d["name"],
             "size_m": d["size_m"], "design": True}
            for d in content._manifest() if d.get("kind") == "prop" and not d.get("disabled")]
    hits = [p for p in mine + _props if q in (p["exemplar"] or "").lower() or q in (p["name"] or "").lower()]
    return hits[:max(1, limit)]


def _prop(key) -> dict:
    """A prop by id (int or hex) or by name / exemplar name (unique)."""
    if isinstance(key, int) or (isinstance(key, str) and key.lower().startswith("0x")):
        pid = key if isinstance(key, int) else int(key, 16)
        hits = [p for p in game_props("", 100000) if int(p["id"], 16) == pid]
    else:
        q = key.strip().lower()
        hits = [p for p in game_props("", 100000) if q in ((p["exemplar"] or "").lower(), (p["name"] or "").lower())]
    if len(hits) != 1:
        raise LotError("%s prop matches %r" % ("no" if not hits else "more than one", key),
                       "game_props(query) finds props by name; use the id")
    return hits[0]


def _tree(key) -> dict:
    from . import build
    q = str(key).strip().lower()
    hits = [t for t in build.tree_types() if q in (t["id"].lower(), (t["name"] or "").lower(),
                                                    (t["exemplar"] or "").lower())]
    if len(hits) != 1:
        raise LotError("%s tree matches %r" % ("no" if not hits else "more than one", key),
                       "build_menu(menu='trees') lists the trees")
    return hits[0]


def _ground(key) -> int:
    if isinstance(key, int):
        return key
    k = str(key).strip().lower()
    if k in GROUNDS:
        return GROUNDS[k]
    if k.startswith("0x"):
        return int(k, 16)
    raise LotError("unknown ground %r" % key, "grounds: " + ", ".join(GROUNDS))


# ---------------------------------------------------------------- lot rows
def rows(lot_cells: int, building_row: list[int] | None, ground="plaza", objects: list[dict] | None = None):
    """The lot's rows: the building (if any), the ground texture on every cell, then the objects - each a dict with
    one of "prop", "tree" or "ground" (a name or id), "x" and "z" in metres from the lot's north-west corner (the
    street is the +z edge) and an optional "rotation" 0-3. Returns (rows, a description of what was placed)."""
    fx = content._fx
    side = 16.0 * lot_cells
    out, placed = [], []
    if building_row:
        out.append(building_row)
    cell_ground = {}
    for o in objects or []:
        if "ground" in o:
            cx, cz = int(float(o.get("x", 0)) // 16), int(float(o.get("z", 0)) // 16)
            if not (0 <= cx < lot_cells and 0 <= cz < lot_cells):
                raise LotError("ground at (%s, %s) is outside the lot" % (o.get("x"), o.get("z")))
            cell_ground[(cx, cz)] = _ground(o["ground"])
    base = _ground(ground) if ground else None
    oid = 100
    for cz in range(lot_cells):
        for cx in range(lot_cells):
            tex = cell_ground.get((cx, cz), base)
            if tex is None:
                continue
            x0, z0 = cx * 16.0, cz * 16.0
            out.append([ROW_TEXTURE, 0, 0, fx(x0 + 8), 0, fx(z0 + 8), fx(x0 + 0.04), fx(z0 + 0.04), fx(x0 + 16.04),
                        fx(z0 + 16.04), 0, oid, tex])
            oid += 1
    for o in objects or []:
        if "ground" in o:
            continue
        try:
            x, z = float(o["x"]), float(o["z"])
        except (KeyError, TypeError, ValueError):
            raise LotError("every object needs x and z in metres: %r" % (o,))
        rot = int(o.get("rotation", 0))
        if not 0 <= rot <= 3:
            raise LotError("rotation is 0..3")
        if not (0 <= x <= side and 0 <= z <= side):
            raise LotError("(%g, %g) is outside the %g m lot" % (x, z, side))
        if "prop" in o:
            p = _prop(o["prop"])
            w, h, d = p["size_m"] or [1.0, 1.0, 1.0]
            if rot % 2:
                w, d = d, w
            if x - w / 2 < -0.5 or z - d / 2 < -0.5 or x + w / 2 > side + 0.5 or z + d / 2 > side + 0.5:
                raise LotError("%s (%g x %g m) at (%g, %g) sticks out of the lot" % (p["name"] or p["exemplar"], w, d, x, z))
            out.append([ROW_PROP, 0, rot, fx(x), 0, fx(z), fx(x - w / 2), fx(z - d / 2), fx(x + w / 2), fx(z + d / 2),
                        0, oid, int(p["id"], 16)])
            placed.append({"prop": p["name"] or p["exemplar"], "id": p["id"], "at": [x, z], "rotation": rot})
        elif "tree" in o:
            t = _tree(o["tree"])
            out.append([ROW_FLORA, 0, rot, fx(x), 0, fx(z), fx(x - 1), fx(z - 1), fx(x + 1), fx(z + 1), 0, oid,
                        int(t["id"], 16)])
            placed.append({"tree": t["name"], "id": t["id"], "at": [x, z]})
        else:
            raise LotError("an object is a prop, a tree or a ground: %r" % (o,))
        oid += 1
    if len(out) > 0x4FF:
        raise LotError("too many objects for one lot")
    return out, placed


# ---------------------------------------------------------------- new props
def _picture(path: str):
    """An agent-supplied picture (any format Pillow reads)."""
    from PIL import Image
    if not os.path.isfile(path):
        raise LotError("no picture at %s" % path)
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:  # noqa: BLE001 - any unreadable picture
        raise LotError("the picture cannot be read: %s" % e)
    return im


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c) + (255,)


def prop_texture(rgb, image=None):
    """128 x 128 RGBA: side (top left), top (top right), and the face (bottom half: a picture or the colour)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (PT, PT), tuple(rgb) + (255,))
    d = ImageDraw.Draw(im)
    for y in range(64):
        d.line([(0, y), (63, y)], fill=_shade(rgb, 1.08 - 0.25 * y / 63))
    d.rectangle([64, 0, 127, 63], fill=_shade(rgb, 1.15))
    if image is not None:
        im.paste(image.convert("RGBA").resize((PT, 64)), (0, 64))
    else:
        d.rectangle([0, 64, 127, 127], fill=_shade(rgb, 1.0))
    return im


def _uv(region):
    x0, y0, x1, y1 = REG[region]
    return ((x0 + 0.5) / PT, (y0 + 0.5) / PT, (x1 - 0.5) / PT, (y1 - 0.5) / PT)


def prop_mesh(shape: str, w: float, d: float, h: float, texture: int):
    """The prop's model, centred on the origin, standing on y = 0, every face facing out (single-sided)."""
    from . import s3d
    verts, tris = [], []

    def face(pts, region, centre, uvs=None):
        u0, v0, u1, v1 = _uv(region)
        uvs = uvs or [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
        a, b, c = pts[0], pts[1], pts[2]
        e1, e2 = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        mid = [sum(q[i] for q in pts) / len(pts) for i in range(3)]
        if sum(n[i] * (mid[i] - centre[i]) for i in range(3)) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        base = len(verts)
        for p, (u, v) in zip(pts, uvs):
            verts.append((p[0], p[1], p[2], u, v))
        for k in range(1, len(pts) - 1):
            tris.append((base, base + k, base + k + 1))

    def box(x0, x1, y0, y1, z0, z1, front="side"):
        c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], front, c)      # +z: the street side
        face([(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)], "side", c)
        face([(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)], "side", c)
        face([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], "side", c)
        face([(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], "top", c)
    if shape == "box":
        box(-w / 2, w / 2, 0, h, -d / 2, d / 2)
    elif shape in ("cylinder", "cone"):
        n, rx, rz = 16, w / 2, d / 2
        top = 0.0 if shape == "cone" else 1.0
        c = (0.0, h / 2, 0.0)
        u0, v0, u1, v1 = _uv("side")
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            p0, p1 = (rx * math.cos(a0), rz * math.sin(a0)), (rx * math.cos(a1), rz * math.sin(a1))
            pts = [(p0[0], 0, p0[1]), (p1[0], 0, p1[1]), (p1[0] * top, h, p1[1] * top), (p0[0] * top, h, p0[1] * top)]
            fu0, fu1 = u0 + (u1 - u0) * k / n, u0 + (u1 - u0) * (k + 1) / n
            uvs = [(fu0, v1), (fu1, v1), (fu1, v0), (fu0, v0)]
            if shape == "cone":                             # a triangle: the apex once
                pts, uvs = pts[:3], uvs[:3]
            face(pts, "side", c, uvs)
        if shape == "cylinder":
            tu0, tv0, tu1, tv1 = _uv("top")
            ring = [(rx * math.cos(2 * math.pi * k / n), h, rz * math.sin(2 * math.pi * k / n)) for k in range(n)]
            uvs = [(tu0 + (tu1 - tu0) * (0.5 + 0.5 * math.cos(2 * math.pi * k / n)),
                    tv0 + (tv1 - tv0) * (0.5 + 0.5 * math.sin(2 * math.pi * k / n))) for k in range(n)]
            face(ring, "top", (0.0, 0.0, 0.0), uvs)
    elif shape == "sign":
        post = min(0.25, w / 6)
        board_h = h * 0.55
        box(-post / 2, post / 2, 0, h - board_h, -post / 2, post / 2)
        box(-w / 2, w / 2, h - board_h, h, -d / 2, d / 2, front="face")
    else:
        raise LotError("shape is %s" % ", ".join(SHAPES))
    m = s3d.textured_mesh(verts, tris, texture, name=b"SiMCP_prop\0")
    m.mats[0].textures[0].wrap = (3, 3)
    return m


def design_prop(name: str, shape: str = "box", width: float = 2.0, depth: float = 2.0, height: float = 2.0,
                rgb=(150, 150, 150), image_path: str = "", taken: set[int] | None = None, model_path: str = "",
                model_scale: float = 1.0) -> dict:
    """Write a new prop as a plugin; place it on a lot with design_park / design_model_building objects."""
    from . import fsh, meshimport, s3d
    content._check_name(name)
    mesh = meshimport.load(model_path, model_scale) if model_path else None
    if mesh:
        width, height, depth = mesh["size_m"]
        shape = "model"
    if not mesh and shape not in SHAPES:
        raise LotError("shape is %s" % ", ".join(SHAPES))
    if not (0.2 <= width <= 32 and 0.2 <= depth <= 32 and 0.2 <= height <= 60):
        raise LotError("a prop is 0.2..32 m wide and deep and 0.2..60 m tall")
    if len(rgb) != 3 or not all(0 <= v <= 255 for v in rgb):
        raise LotError("colours are [r, g, b] with values 0..255")
    if not mesh and shape == "sign" and depth > 1:
        depth = 0.3
    _, tpl = content._find_exemplar(dbpf.T_EXEMPLAR, PROP_TEMPLATE, G_PROPS)
    if tpl is None:
        raise LotError("the game's template prop (0x29010000) is not in SimCity_1.dat")
    taken = taken or set()
    prop_iid = content._new_ids(taken, 1)[0]
    model_iid = content._free(dbpf.T_S3D, content.G_MODELS, 0xFFFF0000, taken)
    tex_iid = content._free(dbpf.T_FSH, content.G_TEXTURES, 0xFFFFFF00, taken)
    if mesh:
        mobj, textures = meshimport.model(mesh, tex_iid)
        model = s3d.write(mobj)
        tex = meshimport.preview(mesh, 256)
    else:
        image = _picture(image_path) if image_path else None
        tex = prop_texture(tuple(rgb), image)
        model = s3d.write(prop_mesh(shape, width, depth, height, tex_iid))
        textures = [(tex_iid, fsh.write_argb(PT, PT, tex.tobytes()))]
    props = content._drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                         p.multi) for p in tpl.props], content.P_RKT1, content.P_NAME_KEY)
    content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP_prop_" + content._slug(name))
    content._set(props, content.P_SIZE, dbpf.PT_FLOAT32, [float(width), float(height), float(depth)], multi=True)
    content._set(props, content.P_RKT0, dbpf.PT_UINT32, [dbpf.T_S3D, content.G_MODELS, model_iid], multi=True)
    content._set(props, content.P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, content.G_SIMCP_NAMES, prop_iid], multi=True)
    records = [(dbpf.T_EXEMPLAR, G_PROPS, prop_iid, dbpf.build_exemplar(props, tpl.parent)),
               (dbpf.T_S3D, content.G_MODELS, model_iid, model),
               (dbpf.T_LTEXT, content.G_SIMCP_NAMES, prop_iid, dbpf.build_ltext(name))] + \
              [(dbpf.T_FSH, content.G_TEXTURES, inst, data) for inst, data in textures]
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_prop_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "prop", "file": path, "prop": "0x%08X" % prop_iid, "model": "0x%08X" % model_iid,
             "texture": "0x%08X" % tex_iid, "shape": shape, "size_m": [width, height, depth],
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    buf = io.BytesIO()
    tex.save(buf, "PNG")
    return dict(entry, texture_png=buf.getvalue(),
                note="props stand on lots: place it with design_park or design_model_building (objects); the game "
                     "loads plugins at start-up")


# ---------------------------------------------------------------- parks: a lot of objects
def park_icon(ground_rgb=(95, 150, 70)) -> bytes:
    def draw(im, d):
        d.polygon([(4, 30), (22, 21), (40, 30), (22, 39)], fill=tuple(ground_rgb) + (255,), outline=(50, 80, 40, 255))
        for x, y in ((15, 26), (27, 25), (22, 31)):
            d.line([(x, y), (x, y - 5)], fill=(90, 65, 40, 255), width=2)
            d.ellipse([x - 5, y - 15, x + 5, y - 4], fill=(45, 110, 45, 255))
    return content.menu_icon(draw)


def park(name: str, lot_cells: int = 1, ground: str = "grass", objects: list[dict] | None = None,
         description: str = "", plop_cost: int = 200, monthly_cost: int = 10) -> dict:
    """A park for the Parks menu: a lot of props, trees and ground textures around an invisible building (a lot needs
    one building row; this one is a 1 m quad whose texture is fully transparent)."""
    if not objects:
        raise LotError("a park needs objects: props, trees or grounds")
    return content.model_building(name, 1.0, 1.0, 1.0, lot_cells=lot_cells, description=description,
                                  plop_cost=plop_cost, monthly_cost=monthly_cost, ground=ground, objects=objects,
                                  invisible=True)
