"""Props and lot layouts for SiMCP's designs (re/reports/formats Q2, LIVE_FACTS Phase 7).

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
TIMED_TEMPLATE = 0x2BF20000                 # LM1x1x3_Gnome_BankofAmerica: a date-timed prop (the bench's own
                                            # properties keep a prop always shown: its dates / hours are ignored)
ANIMATED_TEMPLATE = 0x29430000              # ACSign7x7x1_pizza: a 3D prop with animation frames
P_RKT4 = 0x27812824
GROUNDS = {"paving": 0x258F2000, "plaza": 0x258E3000, "concrete": 0x258D1000, "asphalt": 0x258C2000,
           "grass": 0x25D60000, "lawn": 0x252B3000, "meadow": 0x25F40000, "gravel": 0x25FB1000,
           "garden": 0x26213000, "sand": 0x25901000, "parking": 0x25A32000,
           "yard": 0x251C2000}                  # yard: the natural lawn of the game's house lots
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
def rows(lot_cells, building_row: list[int] | None, ground="plaza", objects: list[dict] | None = None,
         first_id: int = 100):
    """The lot's rows: the building (if any), the ground texture on every cell, then the objects - each a dict with
    one of "prop", "tree" or "ground" (a name or id), "x" and "z" in metres from the lot's north-west corner (the
    street is the +z edge), an optional "rotation" 0-3 and, for a prop, an optional "y": metres above the ground (a
    smoke effect at a chimney's top, a prop on a roof - as the game's plant lots raise their smoke to the stacks).
    lot_cells: cells a side, or [across, deep]. Returns (rows, a description of what was placed)."""
    fx = content._fx
    lw, ld = (int(lot_cells[0]), int(lot_cells[1])) if isinstance(lot_cells, (list, tuple)) else (lot_cells, lot_cells)
    side_x, side_z = 16.0 * lw, 16.0 * ld
    out, placed = [], []
    if building_row:
        out.append(building_row)
    cell_ground = {}
    for o in objects or []:
        if "ground" in o:
            cx, cz = int(float(o.get("x", 0)) // 16), int(float(o.get("z", 0)) // 16)
            if not (0 <= cx < lw and 0 <= cz < ld):
                raise LotError("ground at (%s, %s) is outside the lot" % (o.get("x"), o.get("z")))
            cell_ground[(cx, cz)] = _ground(o["ground"])
    base = _ground(ground) if ground else None
    oid = first_id
    for cz in range(ld):
        for cx in range(lw):
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
        try:
            y = float(o.get("y", 0))
        except (TypeError, ValueError):
            raise LotError("y is metres above the ground: %r" % (o,))
        if not 0 <= y <= 400:
            raise LotError("y is 0..400 m above the ground")
        if not (0 <= x <= side_x and 0 <= z <= side_z):
            raise LotError("(%g, %g) is outside the %g x %g m lot" % (x, z, side_x, side_z))
        if "prop" in o:
            p = _prop(o["prop"])
            w, h, d = p["size_m"] or [1.0, 1.0, 1.0]
            if rot % 2:
                w, d = d, w
            if x - w / 2 < -0.5 or z - d / 2 < -0.5 or x + w / 2 > side_x + 0.5 or z + d / 2 > side_z + 0.5:
                raise LotError("%s (%g x %g m) at (%g, %g) sticks out of the lot" % (p["name"] or p["exemplar"], w, d, x, z))
            out.append([ROW_PROP, 0, rot, fx(x), fx(y), fx(z), fx(x - w / 2), fx(z - d / 2), fx(x + w / 2),
                        fx(z + d / 2), 0, oid, int(p["id"], 16)])
            placed.append({"prop": p["name"] or p["exemplar"], "id": p["id"], "at": [x, z], "rotation": rot})
            if y:
                placed[-1]["y"] = y
        elif "seasonal_tree" in o:
            hit = [d for d in content._manifest() if d.get("kind") == "seasonal_tree" and not d.get("disabled")
                   and d["name"].lower() == str(o["seasonal_tree"]).strip().lower()]
            if not hit:
                raise LotError("no seasonal tree %r" % o["seasonal_tree"], "design_seasonal_tree makes one")
            w, h, d_ = hit[0]["size_m"]
            for pid in hit[0]["props"]:                         # four props, each shown in its season
                out.append([ROW_PROP, 0, rot, fx(x), 0, fx(z), fx(x - w / 2), fx(z - d_ / 2), fx(x + w / 2),
                            fx(z + d_ / 2), 0, oid, int(pid, 16)])
                oid += 1
            placed.append({"seasonal_tree": hit[0]["name"], "at": [x, z]})
            continue
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
                model_scale: float = 1.0, animation: str = "", hours: list | None = None,
                dates: dict | None = None, parts_model: dict | None = None, replace: bool = False) -> dict:
    """Write a new prop as a plugin; place it on a lot with design_park / design_model_building objects.
    animation: spin or sway (model frames, as the game's animated props); hours: [from, to] when it shows (the
    game's 24-hour clock, may wrap midnight); dates: {"start": [month, day], "days": n, "every": 365}.
    parts_model: a prop made of parts (partmodel), rendered per view as the game's own props are (batrender, RKT1):
    x 0..width, y 0..depth (its +y side its front: toward the street at rotation 0), z up; its size the model's.
    Its lamps (materials with "glow") light up at night as the game's lamp posts do: a day and a night state (RKT4),
    the night one with the game's light flare at each lamp. replace: rebuild the prop design of that name under
    its own ids (lots that hold it show the new one after a restart)."""
    from . import fsh, meshimport, s3d
    prior = None
    if replace:
        hit = [d for d in content._manifest() if d.get("kind") == "prop" and not d.get("disabled")
               and d["name"].lower() == name.lower()]
        if not hit:
            raise LotError("no prop design named %r to replace" % name)
        prior = hit[0]
    content._check_name(name, existing=prior is not None)
    timing = timing_props(animation, hours, dates)
    mesh = meshimport.load(model_path, model_scale) if model_path else None
    built = None
    if parts_model is not None:
        if animation:
            raise LotError("a parts prop cannot be animated (yet)")
        from . import partmodel
        import math as _m
        try:
            P0 = partmodel.Builder(dict(parts_model, lot=6)).build()[0].arrays()[0]
            if not len(P0):
                raise LotError("parts model: no parts")
            ext = max(float(P0[:, :, 0].max()), float(P0[:, :, 1].max()), 1.0)
            built = partmodel.Builder(dict(parts_model, lot=min(6, max(1, _m.ceil(ext / 16))))).build()
        except partmodel.GameError as e:
            raise LotError("parts model: %s" % e, getattr(e, "hint", ""))
        P = built[0].arrays()[0]
        x0, x1, y0, y1 = (float(P[:, :, 0].min()), float(P[:, :, 0].max()), float(P[:, :, 1].min()),
                          float(P[:, :, 1].max()))
        origin = parts_model.get("origin") or [(x0 + x1) / 2, (y0 + y1) / 2]     # the prop's centre on its lot
        width, depth = x1 - x0, y1 - y0
        height = float(P[:, :, 2].max())
        shape = "parts"
        lights = lamp_points(built[0], built[1], origin)
    if not mesh and not built and shape not in SHAPES:
        raise LotError("shape is %s" % ", ".join(SHAPES))
    if not (0.2 <= width <= 32 and 0.2 <= depth <= 32 and (0.02 if built else 0.2) <= height <= 60):
        raise LotError("a prop is 0.2..32 m wide and deep and 0.2..60 m tall (a parts prop may be flat: 0.02)")
    if len(rgb) != 3 or not all(0 <= v <= 255 for v in rgb):
        raise LotError("colours are [r, g, b] with values 0..255")
    if not mesh and shape == "sign" and depth > 1:
        depth = 0.3
    template = TIMED_TEMPLATE if (hours is not None or dates is not None) else (
        ANIMATED_TEMPLATE if animation else PROP_TEMPLATE)
    _, tpl = content._find_exemplar(dbpf.T_EXEMPLAR, template, G_PROPS)
    if tpl is None:
        raise LotError("the game's template prop (0x%08X) is not in SimCity_1.dat" % template)
    taken = taken or set()
    if prior:
        prop_iid, model_iid = int(prior["prop"], 16), int(prior["model"], 16)
    else:
        prop_iid = content._new_ids(taken, 1)[0]
        model_iid = content._free(dbpf.T_S3D, content.G_MODELS, 0xFFFF0000, taken)
    tex_iid = content._free(dbpf.T_FSH, content.G_TEXTURES, 0xFFFF0000 if built else 0xFFFFFF00, taken)
    baked = None
    if built:                               # a picture per view, as the game's props (batrender)
        from . import batrender
        scene = batrender.Scene(built[0], built[1], 1, origin=tuple(origin))
        baked, textures = batrender.bake(scene, model_iid, tex_iid)
        model = None
        tex = scene.picture(4, 2).convert("RGB")
    elif mesh:
        mobj, textures = meshimport.model(mesh, tex_iid)
        model = s3d.write(mobj)
        tex = meshimport.preview(mesh, 256)
    else:
        image = _picture(image_path) if image_path else None
        tex = prop_texture(tuple(rgb), image)
        mobj = prop_mesh(shape, width, depth, height, tex_iid)
        if animation:
            animate(mobj, animation)
        model = s3d.write(mobj)
        textures = [(tex_iid, fsh.write_argb(PT, PT, tex.tobytes()))]
    if model is not None and not animation:   # one turned copy per view (RKT1): the game draws a prop's model fixed
        # to the camera, so a sign faces its street only with a copy for each view; animated props keep one model,
        # as the game's own do
        baked = [(model_iid + z * 0x100 + r * 0x10, s3d.write(s3d.turned(mobj, r))) for z in range(5) for r in range(4)]
    props = content._drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                         p.multi) for p in tpl.props], content.P_RKT1, P_RKT4, content.P_NAME_KEY,
                          P_DATE_START, P_DATE_DAYS, P_DATE_EVERY, P_HOURS)
    content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP_prop_" + content._slug(name))
    content._set(props, content.P_SIZE, dbpf.PT_FLOAT32, [float(width), float(height), float(depth)], multi=True)
    timed = hours is not None or dates is not None
    lamps = lights if (built and not timed) else []
    for pr in model_key_props(model_iid, timed, views=baked is not None, lights=lamps):
        content._set(props, pr.id, pr.ptype, pr.values, pr.multi)
    content._set(props, content.P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, content.G_SIMCP_NAMES, prop_iid], multi=True)
    for pr in timing:
        content._set(props, pr.id, pr.ptype, pr.values, pr.multi)
    records = [(dbpf.T_EXEMPLAR, G_PROPS, prop_iid, dbpf.build_exemplar(props, tpl.parent)),
               (dbpf.T_LTEXT, content.G_SIMCP_NAMES, prop_iid, dbpf.build_ltext(name))] + \
              [(dbpf.T_FSH, content.G_TEXTURES, inst, data) for inst, data in textures]
    if baked:
        records += [(dbpf.T_S3D, content.G_MODELS, inst, data) for inst, data in baked]
    else:
        records.append((dbpf.T_S3D, content.G_MODELS, model_iid, model))
    os.makedirs(content.FOLDER, exist_ok=True)
    path = prior["file"] if prior else content._design_path("SiMCP_prop_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "prop", "file": path, "prop": "0x%08X" % prop_iid, "model": "0x%08X" % model_iid,
             "texture": "0x%08X" % tex_iid, "shape": shape, "size_m": [width, height, depth],
             "animation": animation or None, "hours": hours, "dates": dates,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    if lamps:
        entry["lights"] = [[round(v, 2) for v in q] for q in lamps]
    items = content._manifest()
    if prior:
        entry["created"] = prior.get("created", entry["created"])
        entry["replaced"] = time.strftime("%Y-%m-%d %H:%M:%S")
        items = [entry if (d.get("kind") == "prop" and d["name"] == prior["name"] and not d.get("disabled")) else d
                 for d in items]
    else:
        items.append(entry)
    content._save_manifest(items)
    buf = io.BytesIO()
    tex.save(buf, "PNG")
    return dict(entry, texture_png=buf.getvalue(),
                note="props stand on lots: place it with design_park or design_model_building (objects); the game "
                     "loads plugins at start-up")


P_ANIMATED, P_HOURS = 0xE83A081D, 0x4A149631
P_DATE_START, P_DATE_DAYS, P_DATE_EVERY = 0xCA7515CC, 0x4A764564, 0x0A751675
ANIMATIONS = ("spin", "sway")
SEASONS = {"spring": ([3, 1], 92), "summer": ([6, 1], 92), "autumn": ([9, 1], 91), "winter": ([12, 1], 90)}


LIGHT_FLARE = 0x29DA0000                    # the game's lamp-post light flare (S3D in group 0xBADB57F1)
P_LIGHT_STATE, P_LIGHT_ON, P_LIGHT_COUNT = 0x49A1E05A, 0x49C9C93C, 0xE9A316EB   # as the game's lamp post 0x1DFC0000


def lamp_points(mesh, mats, origin, join: float = 0.8) -> list:
    """The prop's lamps: the centres of its glowing ("glow") materials' surfaces, joined within `join` metres, in
    the model's frame (X = -(x - origin x), Y up, Z = y - origin y)."""
    import numpy as np
    P, N, UV, M, E = mesh.arrays()
    lamp = [i for i, m in enumerate(mats) if getattr(m, "lamp", False)]
    if not lamp or not len(P):
        return []
    C = P[np.isin(M, lamp)].mean(axis=1)
    groups = []
    for c in C:
        for g in groups:
            if np.linalg.norm(g[0] / g[1] - c) < join:
                g[0] += c
                g[1] += 1
                break
        else:
            groups.append([c.copy(), 1])
    out = []
    for s, n in groups[:8]:
        x, y, z = s / n
        out.append((-(float(x) - origin[0]), float(z), float(y) - origin[1]))
    return out


def _fx16(v: float) -> int:
    return int(round(v * 65536)) & 0xFFFFFFFF


def model_key_props(model_iid: int, timed: bool, views: bool = False, lights=()) -> list:
    """The prop's model key: RKT0 for an ordinary prop (RKT1 for one with a model per view: base + zoom * 0x100 +
    view * 0x10); a timed prop (hours / dates) needs RKT4 with two states as the game's timed props have - state 0
    the model, state 1 an RKT0 with instance 0 (no model): the game hides a timed prop by switching it to state 1,
    so a prop with only RKT0 stays shown. A prop with lights (model frame points) gets the game's lamp-post states:
    state 1 (night) the model and a light flare at each light, state 0 (day) the model alone, and the lamp post's
    light properties. RKT4 entries are [state, x, y, z (16.16 metres), key, type, group, instance]."""
    key = content.P_RKT1 if views else content.P_RKT0
    if lights and not timed:
        vals = [1, 0, 0, 0, key, dbpf.T_S3D, content.G_MODELS, model_iid]
        for X, Y, Z in lights:
            vals += [1, _fx16(X), _fx16(Y), _fx16(Z), content.P_RKT0, dbpf.T_S3D, content.G_MODELS, LIGHT_FLARE]
        vals += [0, 0, 0, 0, key, dbpf.T_S3D, content.G_MODELS, model_iid]
        return [dbpf.Property(P_RKT4, dbpf.PT_UINT32, vals, True),
                dbpf.Property(P_LIGHT_STATE, dbpf.PT_UINT32, [0x49A1E995]),
                dbpf.Property(P_LIGHT_ON, dbpf.PT_UINT32, [1]),
                dbpf.Property(P_LIGHT_COUNT, dbpf.PT_UINT32, [len(lights)])]
    if not timed:
        return [dbpf.Property(key, dbpf.PT_UINT32, [dbpf.T_S3D, content.G_MODELS, model_iid], True)]
    return [dbpf.Property(P_RKT4, dbpf.PT_UINT32,
                          [0, 0, 0, 0, key, dbpf.T_S3D, content.G_MODELS, model_iid,
                           1, 0, 0, 0, content.P_RKT0, dbpf.T_S3D, content.G_MODELS, 0], True)]


def timing_props(animation: str = "", hours=None, dates=None) -> list:
    """The game's prop properties for an animated model (0xE83A081D), hours of the day (0x4A149631 [from, to]) and
    dates (0xCA7515CC [month, day] start, 0x4A764564 days shown, 0x0A751675 repeat every n days)."""
    out = []
    if animation:
        if animation not in ANIMATIONS:
            raise LotError("animation is %s" % ", ".join(ANIMATIONS))
        out.append(dbpf.Property(P_ANIMATED, dbpf.PT_BOOL, [1]))
    if hours is not None:
        if len(hours) != 2 or not all(0 <= float(h) <= 24 for h in hours):
            raise LotError("hours is [from, to] in 0..24")
        out.append(dbpf.Property(P_HOURS, dbpf.PT_FLOAT32, [float(h) for h in hours], True))
    if dates is not None:
        try:
            month, day = (int(v) for v in dates["start"])
            days, every = int(dates.get("days", 30)), int(dates.get("every", 365))
        except (KeyError, TypeError, ValueError):
            raise LotError('dates is {"start": [month, day], "days": n, "every": 365}')
        if not (1 <= month <= 12 and 1 <= day <= 31 and 1 <= days <= every <= 3650):
            raise LotError("dates: month 1-12, day 1-31, 1 <= days <= every <= 3650")
        out += [dbpf.Property(P_DATE_START, dbpf.PT_UINT8, [month, day], True),
                dbpf.Property(P_DATE_DAYS, dbpf.PT_UINT32, [days]),
                dbpf.Property(P_DATE_EVERY, dbpf.PT_UINT32, [every])]
    return out


def animate(m, kind: str, frames: int = 24, fps: int = 12):
    """Give a one-block model `frames` vertex blocks (spin: a full turn about the vertical axis; sway: a gentle rock
    about its base), as the game's animated props have one block per frame."""
    from . import s3d
    vb = m.verts[0]
    verts = [struct.unpack_from("<5f", vb.data, i * 20) for i in range(vb.count)]
    blocks = []
    for k in range(frames):
        t = 2 * math.pi * k / frames
        out = []
        for x, y, z, u, v in verts:
            if kind == "spin":
                x, z = x * math.cos(t) - z * math.sin(t), x * math.sin(t) + z * math.cos(t)
            else:
                a = 0.12 * math.sin(t)
                x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            out.append(struct.pack("<5f", x, y, z, u, v))
        blocks.append(s3d.VertBlock(0, s3d.FMT_XYZ_UV, b"".join(out)))
    m.verts = blocks
    m.frames, m.fps = frames, fps
    m.meshes[0].frames = [(k, 0, 0, 0) for k in range(frames)]
    return m


def design_seasonal_tree(name: str, shape: str = "broadleaf", height: float = 12.0, width: float = 8.0,
                         leaf=None, trunk=None, replace: bool = False) -> dict:
    """A tree that follows the seasons on lots: four props at one spot, each shown in its season (spring blossom
    from 1 March, summer from 1 June, autumn colours from 1 September, bare or snowy from 1 December, every year),
    each rendered per view as the game's own trees are (vegetation, batrender). Planted trees cannot change: the
    game does not run growth or succession for flora in normal play."""
    from . import batrender, partmodel, trees, vegetation
    import zlib
    import math as _m
    prior = None
    if replace:                              # rebuilt under its own prop ids: lots holding it keep it
        hit = [d for d in content._manifest() if d.get("kind") == "seasonal_tree" and not d.get("disabled")
               and d["name"].lower() == name.lower()]
        if not hit:
            raise LotError("no seasonal tree named %r to replace" % name)
        prior = hit[0]
    content._check_name(name, existing=prior is not None)
    if shape not in trees.SHAPES:
        raise LotError("shape is %s" % ", ".join(trees.SHAPES))
    if not (2 <= height <= 40 and 1 <= width <= 16):
        raise LotError("a tree is 2..40 m tall and 1..16 m wide")
    for c in (leaf, trunk):
        if c is not None and (len(c) != 3 or not all(0 <= v <= 255 for v in c)):
            raise LotError("colours are [r, g, b] with values 0..255")
    _, tpl = content._find_exemplar(dbpf.T_EXEMPLAR, TIMED_TEMPLATE, G_PROPS)
    taken: set[int] = set()
    records, prop_ids, pictures = [], [], []
    name_iid = content._new_ids(taken, 1)[0]
    seed = zlib.crc32(name.encode()) & 0xFFFF
    for k_season, (season, (start_day, days)) in enumerate(SEASONS.items()):
        prop_iid = int(prior["props"][k_season], 16) if prior else content._new_ids(taken, 1)[0]
        taken.add(prop_iid)
        model_iid = content._free(dbpf.T_S3D, content.G_MODELS, 0xFFFF0000, taken)
        tex_iid = content._free(dbpf.T_FSH, content.G_TEXTURES, 0xFFFF0000, taken)
        taken |= {model_iid, tex_iid}
        pm = vegetation.model(shape, height, width, leaf, trunk, seed, season)
        pm["lot"] = max(1, min(6, _m.ceil((width * 1.3 + 2) / 16)))
        mesh, mats = partmodel.Builder(pm).build()
        scene = batrender.Scene(mesh, mats, 1, origin=(width / 2, width / 2))
        baked, textures = batrender.bake(scene, model_iid, tex_iid)
        pictures.append(scene.picture(4, 2))
        props = content._drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else
                                             p.values, p.multi) for p in tpl.props], content.P_RKT1, P_RKT4,
                              content.P_NAME_KEY)
        content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP_tree_%s_%s" % (content._slug(name), season))
        content._set(props, content.P_SIZE, dbpf.PT_FLOAT32, [float(width), float(height), float(width)], multi=True)
        for pr in model_key_props(model_iid, True, views=True):
            content._set(props, pr.id, pr.ptype, pr.values, pr.multi)
        content._set(props, content.P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, content.G_SIMCP_NAMES, name_iid], True)
        for pr in timing_props(dates={"start": start_day, "days": days, "every": 365}):
            content._set(props, pr.id, pr.ptype, pr.values, pr.multi)
        records.append((dbpf.T_EXEMPLAR, G_PROPS, prop_iid, dbpf.build_exemplar(props, tpl.parent)))
        records += [(dbpf.T_S3D, content.G_MODELS, i, b) for i, b in baked]
        records += [(dbpf.T_FSH, content.G_TEXTURES, i, b) for i, b in textures]
        prop_ids.append("0x%08X" % prop_iid)
    records.append((dbpf.T_LTEXT, content.G_SIMCP_NAMES, name_iid, dbpf.build_ltext(name)))
    os.makedirs(content.FOLDER, exist_ok=True)
    path = prior["file"] if prior else content._design_path("SiMCP_seasonal_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "seasonal_tree", "file": path, "props": prop_ids, "shape": shape,
             "size_m": [width, height, width], "seasons": {k: v[0] for k, v in SEASONS.items()},
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    if prior:
        entry["created"] = prior.get("created", entry["created"])
        entry["replaced"] = time.strftime("%Y-%m-%d %H:%M:%S")
        items = [entry if (d.get("kind") == "seasonal_tree" and d["name"] == prior["name"] and not d.get("disabled"))
                 else d for d in items]
    else:
        items.append(entry)
    content._save_manifest(items)
    from PIL import Image
    W = sum(im.width for im in pictures) + 8 * 3
    sheet = Image.new("RGBA", (W, max(im.height for im in pictures)), (150, 190, 230, 255))
    x = 0
    for im in pictures:
        sheet.alpha_composite(im, (x, sheet.height - im.height))
        x += im.width + 8
    buf = io.BytesIO()
    sheet.convert("RGB").save(buf, "PNG")
    return dict(entry, texture_png=buf.getvalue(),
                note="place it on lots: {\"seasonal_tree\": name, \"x\": m, \"z\": m} in design_park objects")


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
