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
centred on the origin, wheels on y = 0, +z forward, like the game's (sedan: 2.1 x 1.87 x 5.5 m). The bodies (sedan,
hatchback, suv, van, pickup) follow real side profiles - hood, raked windscreen, roof, back window, deck - with a
narrower cabin of glass, octagonal wheels with rims, and a 128 px texture: paint lit from above with a shoulder
highlight, door seams, trim, lights, grille and plate. The game lights vehicles by face.
"""

from __future__ import annotations

import io
import math
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
T = 128
REGIONS = {"side": (0, 0, 64, 48), "top": (64, 0, 128, 32), "glass": (64, 32, 128, 64), "front": (0, 64, 64, 96),
        "rear": (0, 96, 64, 128), "wheel": (64, 64, 96, 96), "tread": (96, 64, 128, 80), "dark": (96, 80, 128, 96),
        "bed": (64, 96, 128, 128), "rocker": (0, 48, 64, 64)}
# length, width, height; the lower body's top line (z from front to back, y) and the cabin (windscreen base z,
# roof front z, roof rear z, back base z, belt y); wheelbase; a pickup's bed from z_bed back
KINDS = {
    "sedan": dict(L=4.7, W=1.82, H=1.44, top=[(2.35, 0.80), (2.2, 0.86), (0.95, 0.95), (-1.2, 0.97), (-2.25, 0.93),
                                              (-2.35, 0.86)],
                  cabin=(0.95, 0.15, -0.65, -1.2, 0.95), wb=2.75),
    "hatchback": dict(L=4.15, W=1.78, H=1.48, top=[(2.07, 0.78), (1.95, 0.84), (0.85, 0.93), (-1.95, 0.96),
                                                   (-2.07, 0.92)],
                      cabin=(0.85, 0.12, -1.55, -1.98, 0.93), wb=2.55),
    "suv": dict(L=4.75, W=1.92, H=1.78, top=[(2.37, 0.92), (2.25, 1.0), (1.05, 1.1), (-2.3, 1.12), (-2.37, 1.08)],
                cabin=(1.05, 0.42, -1.95, -2.3, 1.1), wb=2.85),
    "van": dict(L=5.0, W=1.95, H=2.05, top=[(2.5, 0.88), (2.4, 0.95), (1.65, 1.05), (-2.45, 1.08), (-2.5, 1.0)],
                cabin=(1.65, 1.05, -2.45, -2.48, 1.05), wb=3.1),
    "pickup": dict(L=5.35, W=1.95, H=1.85, top=[(2.67, 0.92), (2.55, 1.0), (1.3, 1.1), (-0.5, 1.12), (-2.67, 1.1)],
                   cabin=(1.3, 0.7, -0.35, -0.5, 1.12), wb=3.3, bed=-0.55),
}


def _uv(region, fu, fv):
    x0, y0, x1, y1 = REGIONS[region]
    return ((x0 + 0.5 + (x1 - x0 - 1) * fu) / T, (y0 + 0.5 + (y1 - y0 - 1) * fv) / T)


def paint(body):
    """The 128 x 128 texture: side (paint lit from above, a shoulder highlight, door seams, a trim line), rocker
    panel, top (hood, roof, deck), glass (dark, a sky reflection), front (grille, headlights, bumper), rear (tail
    lights, plate, bumper), wheel (tyre, rim, hub), tread, dark, bed."""
    from PIL import Image, ImageDraw
    body = tuple(int(c) for c in body)

    def sh(k, c=body):
        return tuple(max(0, min(255, int(v * k))) for v in c) + (255,)
    im = Image.new("RGBA", (T, T), sh(1.0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = REGIONS["side"]                      # side: v = 0 at the body's top line, 1 at its bottom
    for y in range(y0, y1):
        f = (y - y0) / (y1 - y0 - 1)
        k = 1.18 - 0.42 * f
        if 0.06 < f < 0.14:
            k = 1.24                                     # the shoulder catching the sky
        d.line([(x0, y), (x1 - 1, y)], fill=sh(k))
    for xs in (22, 40):                                  # door seams
        d.line([(xs, y0 + 6), (xs, y1 - 6)], fill=sh(0.6))
    d.line([(x0 + 4, y0 + 30), (x1 - 5, y0 + 30)], fill=(150, 150, 150, 255))   # side trim
    for x in range(14, 50, 18):                          # door handles
        d.rectangle([x + 3, y0 + 13, x + 6, y0 + 14], fill=sh(0.55))
    x0, y0, x1, y1 = REGIONS["rocker"]
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=sh(0.55))
    x0, y0, x1, y1 = REGIONS["top"]                         # hood / roof: bright, a soft reflection band
    for y in range(y0, y1):
        f = (y - y0) / (y1 - y0 - 1)
        d.line([(x0, y), (x1 - 1, y)], fill=sh(1.12 - 0.08 * abs(f - 0.5) * 2))
    d.line([(x0, y0 + 10), (x1 - 1, y0 + 6)], fill=sh(1.22))
    x0, y0, x1, y1 = REGIONS["glass"]
    for y in range(y0, y1):
        f = (y - y0) / (y1 - y0 - 1)
        d.line([(x0, y), (x1 - 1, y)], fill=(int(70 - 40 * f), int(84 - 44 * f), int(104 - 46 * f), 255))
    for k in range(4):
        d.line([(x0 + 18 + k, y0), (x0 + 6 + k, y1 - 1)], fill=(120, 136, 156, 255))
    d.rectangle([x0, y0, x1 - 1, y0 + 1], fill=sh(0.5))
    x0, y0, x1, y1 = REGIONS["front"]                       # front: body colour, grille, headlights, bumper
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=sh(1.0))
    d.rectangle([x0 + 18, y0 + 12, x0 + 45, y0 + 20], fill=(40, 42, 44, 255))
    for xx in range(x0 + 19, x0 + 45, 3):
        d.line([(xx, y0 + 13), (xx, y0 + 19)], fill=(90, 92, 94, 255))
    for xx in (x0 + 3, x0 + 49):
        d.rectangle([xx, y0 + 10, xx + 11, y0 + 17], fill=(235, 238, 232, 255))
        d.rectangle([xx + 1, y0 + 11, xx + 5, y0 + 16], fill=(255, 250, 220, 255))
    d.rectangle([x0, y0 + 22, x1 - 1, y1 - 1], fill=(55, 56, 58, 255))          # bumper and lower air intake
    d.rectangle([x0 + 22, y0 + 25, x0 + 41, y0 + 28], fill=(225, 225, 215, 255))  # plate
    x0, y0, x1, y1 = REGIONS["rear"]                        # rear: tail lights, plate, bumper
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=sh(0.95))
    for xx in (x0 + 2, x0 + 48):
        d.rectangle([xx, y0 + 8, xx + 13, y0 + 15], fill=(190, 20, 24, 255))
        d.rectangle([xx + 1, y0 + 9, xx + 4, y0 + 11], fill=(250, 210, 200, 255))
    d.rectangle([x0 + 22, y0 + 12, x0 + 41, y0 + 19], fill=(230, 230, 220, 255))
    d.rectangle([x0, y0 + 22, x1 - 1, y1 - 1], fill=(55, 56, 58, 255))
    x0, y0, x1, y1 = REGIONS["wheel"]                       # tyre, rim, hub
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(26, 26, 28, 255))
    cx, cy = (x0 + x1 - 1) / 2, (y0 + y1 - 1) / 2
    d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(150, 152, 156, 255))
    d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(110, 112, 116, 255))
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(170, 172, 176, 255))
    for name in ("tread", "dark"):
        x0, y0, x1, y1 = REGIONS[name]
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(28, 28, 30, 255) if name == "tread" else (36, 37, 40, 255))
    x0, y0, x1, y1 = REGIONS["bed"]
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(48, 48, 50, 255))
    for xx in range(x0 + 4, x1, 8):
        d.line([(xx, y0), (xx, y1 - 1)], fill=(64, 64, 66, 255))
    return im


def body_mesh(kind):
    """Vertices (x, y, z, u, v) and triangles: the car's +z forward, wheels on y = 0, every face once, wound to
    face out (the game lights vehicles by face)."""
    B = KINDS[kind]
    L, W, H = B["L"], B["W"], B["H"]
    w = W / 2
    y0 = 0.32                                              # the body's bottom (the undercarriage's below it)
    verts, tris = [], []
    centre = (0.0, 0.8, 0.0)

    def poly(pts, uvs, ctr=centre):
        a, b, c = pts[0], pts[1], pts[2]
        n = [(b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
             (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])]
        mid = [sum(q[i] for q in pts) / len(pts) for i in range(3)]
        if sum(n[i] * (mid[i] - ctr[i]) for i in range(3)) < 0:
            pts, uvs = pts[::-1], uvs[::-1]
        base = len(verts)
        for p, uv in zip(pts, uvs):
            verts.append((p[0], p[1], p[2]) + tuple(uv))
        for k in range(1, len(pts) - 1):
            tris.append((base, base + k, base + k + 1))
    top = B["top"]
    zf, zr = top[0][0], top[-1][0]
    ytop = max(y for _, y in top)
    # lower body sides: the profile polygon (top line + bottom) on both sides
    prof = [(zf, y0)] + top + [(zr, y0)]
    for sd in (1, -1):
        pts = [(sd * w, y, z) for z, y in prof]
        uvs = [_uv("side", (zf - z) / (zf - zr), min(1.0, (ytop - y) / (ytop - y0))) for z, y in prof]
        poly(pts, uvs)
    # the top line: faces across the width; the first (front panel) and last (rear panel) are the ends
    for i in range(len(top) - 1):
        (za, ya), (zb, yb) = top[i], top[i + 1]
        steep = abs(ya - yb) > abs(za - zb) * 0.8
        region = "front" if (steep and i == 0) else "rear" if (steep and i == len(top) - 2) else "top"
        poly([(-w, ya, za), (w, ya, za), (w, yb, zb), (-w, yb, zb)],
             [_uv(region, 0, 0), _uv(region, 1, 0), _uv(region, 1, 1), _uv(region, 0, 1)])
    yb_f = top[0][1]
    poly([(-w, y0, zf), (w, y0, zf), (w, yb_f, zf), (-w, yb_f, zf)],
         [_uv("front", 0, 1), _uv("front", 1, 1), _uv("front", 1, 0.45), _uv("front", 0, 0.45)])
    yb_r = top[-1][1]
    poly([(-w, y0, zr), (w, y0, zr), (w, yb_r, zr), (-w, yb_r, zr)],
         [_uv("rear", 1, 1), _uv("rear", 0, 1), _uv("rear", 0, 0.4), _uv("rear", 1, 0.4)])
    # the cabin: glass all round, a roof
    zw, zrf, zrr, zb, yb = B["cabin"]
    wb, wt = w * 0.95, w * 0.80
    G = [_uv("glass", 0, 1), _uv("glass", 1, 1), _uv("glass", 1, 0), _uv("glass", 0, 0)]
    cc = (0.0, (yb + H) / 2, (zw + zb) / 2)
    poly([(-wb, yb, zw), (wb, yb, zw), (wt, H, zrf), (-wt, H, zrf)], G, cc)                 # windscreen
    poly([(wb, yb, zb), (-wb, yb, zb), (-wt, H, zrr), (wt, H, zrr)], G, cc)                 # back window
    for sd in (1, -1):
        poly([(sd * wb, yb, zw), (sd * wb, yb, zb), (sd * wt, H, zrr), (sd * wt, H, zrf)],
             [_uv("glass", 0, 1), _uv("glass", 1, 1), _uv("glass", 0.85, 0), _uv("glass", 0.15, 0)], cc)
    poly([(-wt, H, zrf), (wt, H, zrf), (wt, H, zrr), (-wt, H, zrr)],
         [_uv("top", 0, 0), _uv("top", 1, 0), _uv("top", 1, 1), _uv("top", 0, 1)], cc)
    # a pickup's bed: a dark floor sunk into the deck behind the cab
    if "bed" in B:
        zbd = B["bed"]
        yfl = top[-1][1] - 0.45
        poly([(-w * 0.86, yfl + 0.002, zbd), (w * 0.86, yfl + 0.002, zbd), (w * 0.86, yfl + 0.002, zr + 0.08),
              (-w * 0.86, yfl + 0.002, zr + 0.08)],
             [_uv("bed", 0, 0), _uv("bed", 1, 0), _uv("bed", 1, 1), _uv("bed", 0, 1)], (0, yfl - 1, (zbd + zr) / 2))
    # wheels: octagonal, standing slightly out of the body's sides
    r, tw = 0.34, 0.24
    for zc in (B["wb"] / 2, -B["wb"] / 2):
        for sd in (1, -1):
            xo, xi = sd * (w + 0.03), sd * (w + 0.03 - tw)
            ring = [(zc + r * math.cos(2 * math.pi * k / 8 + math.pi / 8), r + r * math.sin(2 * math.pi * k / 8 + math.pi / 8))
                    for k in range(8)]
            wc = ((xo + xi) / 2, r, zc)
            poly([(xo, y, z) for z, y in ring],
                 [_uv("wheel", 0.5 + 0.5 * math.cos(2 * math.pi * k / 8 + math.pi / 8),
                      0.5 - 0.5 * math.sin(2 * math.pi * k / 8 + math.pi / 8)) for k in range(8)], wc)
            for k in range(8):
                (za, ya), (zb_, yb_) = ring[k], ring[(k + 1) % 8]
                if ya < 0.05 and yb_ < 0.05:
                    continue
                poly([(xi, ya, za), (xo, ya, za), (xo, yb_, zb_), (xi, yb_, zb_)],
                     [_uv("tread", 0, 0), _uv("tread", 1, 0), _uv("tread", 1, 1), _uv("tread", 0, 1)], wc)
    return verts, tris


def car_model(kind: str, texture: int):
    """The S3D model: body (opaque), undercarriage (opaque) and shadow (blended), as the Maxis sedan has."""
    from . import s3d
    L, W = KINDS[kind]["L"], KINDS[kind]["W"]
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
    """A small side picture of the car (PNG), as the game keeps for its vehicles (group 0x4C06F888): its side
    profile, cabin and wheels in its paint."""
    from PIL import Image, ImageDraw
    B = KINDS[kind]
    L, H = B["L"], B["H"]
    pic = Image.new("RGBA", (42, 42), (0, 0, 0, 0))
    d = ImageDraw.Draw(pic)
    k = 38 / L
    body = im.getpixel((32, 20))
    gx = lambda z: 21 + z * k                                   # noqa: E731 - front to the right
    gy = lambda y: 30 - y * k                                   # noqa: E731
    zw, zrf, zrr, zb, yb = B["cabin"]
    d.polygon([(gx(zw), gy(yb)), (gx(zrf), gy(H)), (gx(zrr), gy(H)), (gx(zb), gy(yb))], fill=(60, 76, 96, 255))
    top = B["top"]
    d.polygon([(gx(top[0][0]), gy(0.32))] + [(gx(z), gy(y)) for z, y in top] + [(gx(top[-1][0]), gy(0.32))],
              fill=body)
    for z in (B["wb"] / 2, -B["wb"] / 2):
        d.ellipse([gx(z) - 4, gy(0.68), gx(z) + 4, gy(0)], fill=(25, 25, 25, 255))
        d.ellipse([gx(z) - 2, gy(0.5), gx(z) + 2, gy(0.18)], fill=(150, 150, 155, 255))
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
