"""New cars for the game's traffic (automata, exemplar type 0x16, group 0x096E6739).

The game's commuter cars are small exemplars under three cohorts that set who drives them and where they go:
CheapCarCohort 0xCA47E67E, SoccerMomCohort 0x6A511FE1 (middle) and RichCarCohort 0x2A47E655 (occupant groups 0x4000
automata, 0x4002, 0x420E / 0x420A / 0x420D for the class, 0x420B cars; wealth 0x296E88E9 / 0x696E88DB; 0xC973C9AA).
A car itself names its day model (0x09C80416) and night model (0x09C80417, the lights drawn over it at night),
its query name (0x4B733E12), its automata id (0xEBFC5E5E) and 0xEBFC5FBA (720 for the cheap sedan, 1080 for a
station wagon, 40 for a rich coupe; a design with 6000 was not picked more often in a one-minute sample, so its
meaning is open and a design keeps the sedan's value).

SiMCP copies the Maxis cheap sedan (0x10E40000), takes away what the cohort provides, puts it under the cohort of
the wealth asked for and gives it its own model: a generated body (sedan, van or pickup) with a painted 64 x 64
texture (body, glass, front with headlights, rear with tail lights, tyres) - FSH in 0x1ABE787D as buildings use -
plus the Maxis sedan's undercarriage and blended shadow quads (scaled), and the sedan's night lights. A model is
centred on the origin, wheels on y = 0, +z forward, like the game's (sedan: 2.1 x 1.87 x 5.5 m).
"""

from __future__ import annotations

import io
import os
import struct
import time

from . import content, dbpf

G_AUTOMATA = 0x096E6739
TEMPLATE = 0x10E40000                   # Vehicle_SedanCheap1
NIGHT_MODEL = 0x10E42000                # the sedan's head and tail lights
TEX_UNDERCARRIAGE, TEX_SHADOW = 0xABA645E7, 0x10660002
COHORTS = {"cheap": 0xCA47E67E, "middle": 0x6A511FE1, "rich": 0x2A47E655}
P_MODEL_DAY, P_MODEL_NIGHT, P_QUERY_NAME = 0x09C80416, 0x09C80417, 0x4B733E12
P_AUTOMATA_ID, P_WEIGHT = 0xEBFC5E5E, 0xEBFC5FBA
COHORT_PROPS = (0x296E88E9, 0x696E88DB, 0xAA1DD396, 0xC973C9AA)
KINDS = {   # length, width, height, lower body top, cabin bottom z (rear, front) and top z, as fractions of length
    "sedan": (4.6, 1.85, 1.45, 0.90, (-0.30, 0.18), (-0.20, 0.04)),
    "van": (4.9, 1.95, 2.0, 0.95, (-0.48, 0.26), (-0.48, 0.12)),
    "pickup": (5.2, 1.95, 1.8, 0.95, (0.00, 0.24), (0.03, 0.16)),
}
T = 64
REGIONS = {"body": (0, 0, 32, 32), "glass": (32, 0, 64, 32), "front": (0, 32, 32, 64), "rear": (32, 32, 64, 48),
           "tyre": (32, 48, 64, 64)}


def paint(body) -> bytes:
    """The 64 x 64 RGBA texture: body, glass, front (headlights, grille), rear (tail lights, plate), tyre."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (T, T), tuple(body) + (255,))
    d = ImageDraw.Draw(im)

    def shade(k):
        return tuple(max(0, min(255, int(c * k))) for c in body) + (255,)
    for y in range(32):                                          # body: lighter on top
        d.line([(0, y), (31, y)], fill=shade(1.12 - 0.3 * y / 31))
    d.rectangle([32, 0, 63, 31], fill=(38, 50, 64, 255))           # glass with a highlight
    for k in range(6):
        d.line([(40 + k, 0), (32 + k, 31)], fill=(90, 110, 130, 255))
    d.rectangle([0, 32, 31, 63], fill=shade(0.95))                 # front
    d.rectangle([10, 46, 21, 52], fill=(30, 30, 30, 255))
    d.rectangle([2, 44, 8, 50], fill=(250, 245, 210, 255))
    d.rectangle([23, 44, 29, 50], fill=(250, 245, 210, 255))
    d.rectangle([32, 32, 63, 47], fill=shade(0.95))                # rear
    d.rectangle([34, 36, 40, 41], fill=(200, 25, 25, 255))
    d.rectangle([55, 36, 61, 41], fill=(200, 25, 25, 255))
    d.rectangle([44, 39, 51, 44], fill=(235, 235, 225, 255))
    d.rectangle([32, 48, 63, 63], fill=(28, 28, 28, 255))          # tyre
    d.rectangle([44, 52, 51, 59], fill=(120, 120, 120, 255))
    return im


def _uv(region):
    x0, y0, x1, y1 = REGIONS[region]
    return ((x0 + 0.5) / T, (y0 + 0.5) / T, (x1 - 0.5) / T, (y1 - 0.5) / T)


def body_mesh(kind: str):
    """Vertices (x, y, z, u, v) and triangles of the car body. Every face is written once, wound so that
    (b - a) x (c - a) points away from its part's centre - as the game's cars are: vehicles are lit by face, and a
    face written both ways round draws its unlit back over its front (the car comes out black)."""
    L, W, H, y1, (cb0, cb1), (ct0, ct1) = KINDS[kind]
    verts, tris = [], []
    body_centre = (0.0, (0.30 + H) / 2, 0.0)

    def quad(pts, region, centre=body_centre):
        u0, v0, u1, v1 = _uv(region)
        uvs = [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]                              # BL, BR, TR, TL
        a, b, c = pts[0], pts[1], pts[2]
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        mid = [sum(q[i] for q in pts) / 4 for i in range(3)]
        if sum(n[i] * (mid[i] - centre[i]) for i in range(3)) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        base = len(verts)
        for p, (u, v) in zip(pts, uvs):
            verts.append((p[0], p[1], p[2], u, v))
        tris.append((base, base + 1, base + 2))
        tris.append((base, base + 2, base + 3))
    w, l, y0 = W / 2, L / 2, 0.30
    # lower body
    quad([(-w, y0, l), (w, y0, l), (w, y1, l), (-w, y1, l)], "front")
    quad([(w, y0, -l), (-w, y0, -l), (-w, y1, -l), (w, y1, -l)], "rear")
    quad([(w, y0, l), (w, y0, -l), (w, y1, -l), (w, y1, l)], "body")
    quad([(-w, y0, -l), (-w, y0, l), (-w, y1, l), (-w, y1, -l)], "body")
    quad([(-w, y1, l), (w, y1, l), (w, y1, -l), (-w, y1, -l)], "body")
    # cabin
    wb, wt = w * 0.96, w * 0.84
    zb0, zb1, zt0, zt1 = cb0 * L, cb1 * L, ct0 * L, ct1 * L
    quad([(-wb, y1, zb1), (wb, y1, zb1), (wt, H, zt1), (-wt, H, zt1)], "glass")          # windscreen
    quad([(wb, y1, zb0), (-wb, y1, zb0), (-wt, H, zt0), (wt, H, zt0)], "glass")          # rear window
    quad([(wb, y1, zb1), (wb, y1, zb0), (wt, H, zt0), (wt, H, zt1)], "glass")            # sides
    quad([(-wb, y1, zb0), (-wb, y1, zb1), (-wt, H, zt1), (-wt, H, zt0)], "glass")
    quad([(-wt, H, zt1), (wt, H, zt1), (wt, H, zt0), (-wt, H, zt0)], "body")             # roof
    # wheels: boxes standing out of the body sides (outer face, front and back)
    r, tw = 0.34, 0.24
    for zc in (L * 0.31, -L * 0.31):
        for sd in (1, -1):
            xo, xi = sd * (w + 0.02), sd * (w + 0.02 - tw)
            centre = ((xo + xi) / 2, r, zc)
            quad([(xo, 0, zc - r), (xo, 0, zc + r), (xo, 2 * r, zc + r), (xo, 2 * r, zc - r)], "tyre", centre)
            for zf in (zc + r, zc - r):
                quad([(xi, 0, zf), (xo, 0, zf), (xo, 2 * r, zf), (xi, 2 * r, zf)], "tyre", centre)
    return verts, tris


def car_model(kind: str, texture: int):
    """The S3D model: body (opaque), undercarriage (opaque) and shadow (blended), as the Maxis sedan has."""
    from . import s3d
    L, W = KINDS[kind][0], KINDS[kind][1]
    bv, bt = body_mesh(kind)
    w, l = W / 2 + 0.05, L / 2 + 0.05
    under = [(w, 0.594, l, 1, 1), (-w, 0.594, l, 1, 0), (-w, 0.594, -l, 0, 0), (w, 0.594, -l, 0, 1)]
    sw, sl = W / 2 * 1.55, L / 2 * 1.2
    shadow = [(-sw, 0.129, sl, 0, 1), (sw, 0.129, sl, 1, 1), (sw, 0.129, -sl, 1, 0), (-sw, 0.129, -sl, 0, 0)]
    quad_tris = [(0, 1, 2), (3, 0, 2)]          # the Maxis order: undercarriage faces down, shadow up
    parts = [(bv, bt, texture, 0xAB, 1, 0, 0x7FFF, b"body"), (under, quad_tris, TEX_UNDERCARRIAGE, 0xAB, 1, 0, 0x7FFF,
                                                               b"undercarriage"),
             (shadow, quad_tris, TEX_SHADOW, 0xBB, 4, 5, 0, b"shadow")]
    m = s3d.Model()
    for k, (verts, tris, tex, flags, src, dst, thr, name) in enumerate(parts):
        m.verts.append(s3d.VertBlock(0, s3d.FMT_XYZ_UV, b"".join(struct.pack("<5f", *v) for v in verts)))
        m.indices.append(s3d.IndexBlock(0, 2, b"".join(struct.pack("<3H", *t) for t in tris)))
        m.prims.append([(0, 0, 3 * len(tris))])
        m.mats.append(s3d.Material(flags=flags, src_blend=src, dst_blend=dst, alpha_threshold=thr,
                                   textures=[s3d.Texture(tex, (3, 3), (1, 1), 0, 0, b"\0")]))
        m.meshes.append(s3d.Mesh(name + b"\0", 0, [(k, k, k, k)]))
    return m


def icon_png(im, kind: str) -> bytes:
    """A small side picture of the car (PNG), as the game keeps for its vehicles (group 0x4C06F888)."""
    from PIL import Image, ImageDraw
    L, W, H, y1, (cb0, cb1), (ct0, ct1) = KINDS[kind]
    pic = Image.new("RGBA", (42, 42), (0, 0, 0, 0))
    d = ImageDraw.Draw(pic)
    k = 38 / L
    body = im.getpixel((16, 16))
    gx = lambda z: 21 + z * k                                   # noqa: E731 - front to the right
    gy = lambda y: 30 - y * k                                   # noqa: E731
    d.rectangle([gx(-L / 2), gy(y1), gx(L / 2), gy(0.3)], fill=body)
    d.polygon([(gx(cb0 * L), gy(y1)), (gx(cb1 * L), gy(y1)), (gx(ct1 * L), gy(H)), (gx(ct0 * L), gy(H))],
              fill=(60, 80, 100, 255))
    for z in (L * 0.31, -L * 0.31):
        d.ellipse([gx(z) - 4, gy(0.68), gx(z) + 4, gy(0)], fill=(25, 25, 25, 255))
    buf = io.BytesIO()
    pic.save(buf, "PNG")
    return buf.getvalue()


def design_car(name: str, kind: str = "sedan", body=(40, 90, 170), wealth: str = "cheap",
               taken: set[int] | None = None) -> dict:
    """Write a new car as a plugin (see the module notes)."""
    from . import fsh, s3d
    content._check_name(name)
    if kind not in KINDS:
        raise content.ContentError("kind is %s" % ", ".join(KINDS))
    if wealth not in COHORTS:
        raise content.ContentError("wealth is cheap, middle or rich")
    if len(body) != 3 or not all(0 <= v <= 255 for v in body):
        raise content.ContentError("colours are [r, g, b] with values 0..255")
    _, tpl = content._find_exemplar(dbpf.T_EXEMPLAR, TEMPLATE, G_AUTOMATA)
    if tpl is None:
        raise content.ContentError("the game's template car (0x10E40000) is not in SimCity_1.dat")
    taken = taken or set()
    car_iid = content._new_ids(taken, 1)[0]
    model_iid = content._free(dbpf.T_S3D, content.G_MODELS, 0xFFFF0000, taken)
    tex_iid = content._free(dbpf.T_FSH, content.G_TEXTURES, 0xFFFFFF00, taken)
    im = paint(tuple(body))
    model = s3d.write(car_model(kind, tex_iid))
    props = content._drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                         p.multi) for p in tpl.props], *COHORT_PROPS, content.P_NAME_KEY)
    content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP_car_" + content._slug(name))
    content._set(props, P_MODEL_DAY, dbpf.PT_UINT32, [dbpf.T_S3D, content.G_MODELS, model_iid], multi=True)
    content._set(props, P_MODEL_NIGHT, dbpf.PT_UINT32, [dbpf.T_S3D, content.G_MODELS, NIGHT_MODEL], multi=True)
    content._set(props, P_QUERY_NAME, dbpf.PT_STRING, name)
    content._set(props, P_AUTOMATA_ID, dbpf.PT_UINT32, [car_iid])
    content._set(props, content.P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, content.G_SIMCP_NAMES, car_iid], multi=True)
    parent = (dbpf.T_COHORT, G_AUTOMATA, COHORTS[wealth])
    records = [(dbpf.T_EXEMPLAR, G_AUTOMATA, car_iid, dbpf.build_exemplar(props, parent)),
               (dbpf.T_S3D, content.G_MODELS, model_iid, model),
               (dbpf.T_FSH, content.G_TEXTURES, tex_iid, fsh.write_argb(T, T, im.tobytes())),
               (dbpf.T_PNG, 0x4C06F888, car_iid, icon_png(im, kind)),
               (dbpf.T_LTEXT, content.G_SIMCP_NAMES, car_iid, dbpf.build_ltext(name))]
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_car_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "car", "body": kind, "file": path, "automata": "0x%08X" % car_iid,
             "model": "0x%08X" % model_iid, "texture": "0x%08X" % tex_iid, "wealth": wealth,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    buf = io.BytesIO()
    im.resize((256, 256)).save(buf, "PNG")
    return dict(entry, texture_png=buf.getvalue(),
                note="the game loads plugins at start-up: quit_game and game_launch; the car then joins the "
                     "traffic of its wealth class")
