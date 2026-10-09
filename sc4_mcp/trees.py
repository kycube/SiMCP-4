"""New tree types for the game's tree menu (Landscape -> trees in mayor mode, the flora brushes in god mode).

A tree is a flora exemplar (type 0x0F, group 0xE83E0437) like the game's five menu trees: SiMCP copies the
properties of the Maxis "decisious1" tree (0x16600000: growth tuning, menu flags) and gives the copy its own name
(LTEXT), price (0x49CAC341), menu icon (PNG 0x6A386D26) and model. The game's menu trees are pre-rendered sprites (one
S3D per zoom and rotation, RKT5); SiMCP's tree is one true 3D model (RKT0 0x27812820, as the game's Burnt Tree):
three vertical quads crossing at the trunk, drawn from both sides, with an RGBA texture whose transparent pixels the
game's default material cuts out (flags 0xA3: alpha test at 0.5, as Maxis trees use). The texture is painted here
(broadleaf, conifer or palm, in the colours asked for) or taken from a picture the agent supplies.
"""

from __future__ import annotations

import io
import math
import os
import random
import time
import zlib

from . import content, dbpf

G_FLORA = 0xE83E0437
G_SIMCP_DESCS = 0x5C4D0F02              # SiMCP's LTEXT descriptions (instance = the item)
TEMPLATE = 0x16600000                   # the game's "decisious1" menu tree
P_RKT5, P_ICON_ID, P_EXEMPLAR_ID = 0x27812825, 0x8A2602BB, 0x21
SHAPES = ("broadleaf", "conifer", "palm")
TEX_W, TEX_H = 128, 256


def _shade(c, k: float) -> tuple[int, int, int, int]:
    return tuple(max(0, min(255, int(v * k))) for v in c) + (255,)


def paint(shape: str, leaf, trunk, seed: int):
    """An RGBA picture (Pillow image, TEX_W x TEX_H) of a tree on a transparent background, trunk at the bottom
    centre. Transparent pixels carry the leaf colour so the edges do not darken when the game filters them."""
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    W, H = TEX_W, TEX_H
    im = Image.new("RGBA", (W, H), tuple(leaf) + (0,))
    d = ImageDraw.Draw(im)
    cx = W / 2
    if shape == "palm":
        bend = rnd.uniform(-10, 10)
        top = (cx + bend, H * 0.22)
        pts = [(cx + bend * (1 - (1 - t) ** 2), H - 1 - t * (H - 1 - top[1])) for t in [i / 20 for i in range(21)]]
        for i in range(20):
            wd = 7 - 3 * i / 20
            d.line([pts[i], pts[i + 1]], fill=_shade(trunk, 0.9 + 0.2 * (i % 2)), width=int(wd))
        for k in range(15):                                      # fronds
            a = math.radians(k * 24 + rnd.uniform(-8, 8))
            length = rnd.uniform(44, 60)
            droop = rnd.uniform(0.6, 1.1)
            prev = top
            for j in range(1, 9):
                t = j / 8
                p = (top[0] + math.cos(a) * length * t, top[1] - math.sin(a) * length * t * 0.45 + droop * 30 * t * t)
                d.line([prev, p], fill=_shade(leaf, rnd.uniform(0.75, 1.1)), width=max(3, int(7 * (1 - t)) + 3))
                for s in (-1, 1):                                # leaflets
                    q = (p[0] + s * 6 * math.sin(a), p[1] + 7)
                    d.line([p, q], fill=_shade(leaf, rnd.uniform(0.65, 1.0)), width=3)
                prev = p
        return im
    if shape == "conifer":
        d.rectangle([cx - 4, H * 0.82, cx + 3, H - 1], fill=_shade(trunk, 1.0))
        d.rectangle([cx, H * 0.82, cx + 3, H - 1], fill=_shade(trunk, 0.75))
        layers = 9
        for i in range(layers):                                  # from the bottom tier up
            t = i / (layers - 1)
            y_base = H * (0.88 - 0.72 * t)
            half = (W * 0.47) * (1 - 0.85 * t) + 4
            apex = y_base - H * 0.2
            pts = [(cx, apex)]
            n = 7
            for j in range(n + 1):                               # a jagged lower edge
                x = cx - half + 2 * half * j / n
                pts.append((x, y_base + rnd.uniform(-4, 4)))
            pts.append((cx, apex))
            d.polygon(pts, fill=_shade(leaf, 0.75 + 0.25 * t))
            d.polygon([(cx, apex), (cx + half, y_base), (cx + half * 0.3, y_base)], fill=_shade(leaf, 0.6 + 0.2 * t))
        d.line([(cx, 2), (cx, 10)], fill=_shade(leaf, 0.9), width=3)
        return im
    # broadleaf
    d.polygon([(cx - 6, H - 1), (cx + 6, H - 1), (cx + 3, H * 0.5), (cx - 3, H * 0.5)], fill=_shade(trunk, 1.0))
    d.polygon([(cx + 1, H - 1), (cx + 6, H - 1), (cx + 3, H * 0.5), (cx + 1, H * 0.5)], fill=_shade(trunk, 0.72))
    for _ in range(5):                                           # branches into the crown
        y = rnd.uniform(H * 0.45, H * 0.6)
        d.line([(cx, y), (cx + rnd.uniform(-30, 30), y - rnd.uniform(20, 40))], fill=_shade(trunk, 0.85), width=3)
    ccx, ccy, rx, ry = cx, H * 0.36, W * 0.44, H * 0.31
    blobs = []
    for _ in range(70):
        a, r = rnd.uniform(0, 2 * math.pi), math.sqrt(rnd.uniform(0, 1))
        x, y = ccx + math.cos(a) * r * (rx - 12), ccy + math.sin(a) * r * (ry - 12)
        blobs.append((y, x, rnd.uniform(9, 17)))
    for y, x, rad in sorted(blobs):                             # back to front, lit from the upper left
        light = 1.12 - 0.35 * ((x - (ccx - rx)) / (2 * rx)) * 0.6 - 0.35 * ((y - (ccy - ry)) / (2 * ry))
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=_shade(leaf, light * rnd.uniform(0.9, 1.05)))
    for _ in range(22):                                          # sunlit leaves, upper left
        a, r = rnd.uniform(math.pi * 0.9, math.pi * 1.6), math.sqrt(rnd.uniform(0.2, 1))
        x, y = ccx + math.cos(a) * r * (rx - 14), ccy + math.sin(a) * r * (ry - 14)
        d.ellipse([x - 1.5, y - 1, x + 1.5, y + 1], fill=_shade(leaf, 1.2))
    return im


def picture(path: str):
    """An agent-supplied picture of a tree (PNG with a transparent background), scaled to the texture size."""
    from PIL import Image
    if not os.path.isfile(path):
        raise content.ContentError("no picture at %s" % path)
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:  # noqa: BLE001 - any unreadable picture
        raise content.ContentError("the picture cannot be read: %s" % e)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    if im.getextrema()[3][0] == 255:
        raise content.ContentError("the picture needs a transparent background (alpha 0 around the tree)")
    return im.resize((TEX_W, TEX_H), Image.LANCZOS)


def crossed_planes(width: float, height: float, texture: int, planes: int = 3):
    """`planes` vertical quads crossing on the y axis (base at y = 0), each drawn from both sides."""
    from . import s3d
    verts, tris = [], []
    w = width / 2
    for k in range(planes):
        a = math.pi * k / planes
        dx, dz = math.cos(a) * w, math.sin(a) * w
        base = len(verts)
        for (x, y, z, u, v) in ((-dx, 0, -dz, 0, 1), (dx, 0, dz, 1, 1), (dx, height, dz, 1, 0), (-dx, height, -dz, 0, 0)):
            verts.append((x, y, z, u, v))
        for t in ((0, 1, 2), (0, 2, 3)):
            tris.append(tuple(base + i for i in t))
            tris.append(tuple(base + i for i in reversed(t)))
    m = s3d.textured_mesh(verts, tris, texture, name=b"SiMCP_tree\0")
    m.mats[0].textures[0].wrap = (3, 3)        # clamp, as the game's trees: no trunk pixels bleeding over the top
    return m


def icon(im) -> bytes:
    from PIL import Image

    def draw(base, d):
        d.ellipse([10, 37, 34, 42], fill=(70, 110, 50, 255))     # a patch of grass
        t = im.resize((20, 40), Image.LANCZOS)
        base.alpha_composite(t, (12, 2))
    return content.menu_icon(draw)


def design_tree(name: str, shape: str = "broadleaf", height: float = 12.0, width: float = 8.0,
                leaf=(70, 125, 55), trunk=(95, 70, 45), cost: int = 3, description: str = "",
                image_path: str = "", taken: set[int] | None = None) -> dict:
    """Write a new tree type as a plugin (see the module notes)."""
    from . import fsh, s3d
    content._check_name(name)
    content._check_tokens(description, "description")
    if shape not in SHAPES and not image_path:
        raise content.ContentError("shape is broadleaf, conifer or palm (or give image_path)")
    if not (2 <= height <= 40 and 1 <= width <= 16):
        raise content.ContentError("a tree is 2..40 m tall and 1..16 m wide (a cell is 16 m)")
    if not 0 <= cost <= 10000:
        raise content.ContentError("the price per tree is 0..10000")
    for c in (leaf, trunk):
        if len(c) != 3 or not all(0 <= v <= 255 for v in c):
            raise content.ContentError("colours are [r, g, b] with values 0..255")
    _, tpl = content._find_exemplar(dbpf.T_EXEMPLAR, TEMPLATE, G_FLORA)
    if tpl is None:
        raise content.ContentError("the game's template tree (0x16600000) is not in SimCity_1.dat")
    taken = taken or set()
    flora_iid = content._new_ids(taken, 1)[0]
    model_iid = content._free(dbpf.T_S3D, content.G_MODELS, 0xFFFF0000, taken)
    tex_iid = content._free(dbpf.T_FSH, content.G_TEXTURES, 0xFFFFFF00, taken)
    icon_iid = content._free(dbpf.T_PNG, content.G_ICONS, 0xFFFFFFFF, taken)
    im = picture(image_path) if image_path else paint(shape, tuple(leaf), tuple(trunk), zlib.crc32(name.encode()))
    texture = fsh.write_argb(TEX_W, TEX_H, im.tobytes())
    model = s3d.write(crossed_planes(width, height, tex_iid))
    props = content._drop([dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values,
                                         p.multi) for p in tpl.props],
                          P_RKT5, content.P_NAME_KEY, content.P_DESC_KEY)
    content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP_tree_" + content._slug(name))
    content._set(props, P_EXEMPLAR_ID, dbpf.PT_UINT32, [flora_iid])
    content._set(props, content.P_RKT0, dbpf.PT_UINT32, [dbpf.T_S3D, content.G_MODELS, model_iid], multi=True)
    content._set(props, content.P_ICON, dbpf.PT_UINT32, [icon_iid])
    content._set(props, P_ICON_ID, dbpf.PT_UINT32, [flora_iid])
    old = [p for p in tpl.props if p.id == content.P_PLOP]
    content._set(props, content.P_PLOP, old[0].ptype if old else dbpf.PT_SINT64, [int(cost)])
    content._set(props, content.P_ITEM_NAME, dbpf.PT_STRING, name)
    content._set(props, content.P_ITEM_DESC, dbpf.PT_STRING, description or name)
    content._set(props, content.P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, content.G_SIMCP_NAMES, flora_iid], multi=True)
    content._set(props, content.P_DESC_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, G_SIMCP_DESCS, flora_iid], multi=True)
    records = [(dbpf.T_EXEMPLAR, G_FLORA, flora_iid, dbpf.build_exemplar(props, tpl.parent)),
               (dbpf.T_S3D, content.G_MODELS, model_iid, model),
               (dbpf.T_FSH, content.G_TEXTURES, tex_iid, texture),
               (dbpf.T_PNG, content.G_ICONS, icon_iid, icon(im)),
               (dbpf.T_LTEXT, content.G_SIMCP_NAMES, flora_iid, dbpf.build_ltext(name)),
               (dbpf.T_LTEXT, G_SIMCP_DESCS, flora_iid, dbpf.build_ltext(description or name))]
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_tree_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "tree", "file": path, "flora": "0x%08X" % flora_iid,
             "model": "0x%08X" % model_iid, "texture": "0x%08X" % tex_iid, "shape": "picture" if image_path else shape,
             "size_m": [width, height], "cost": cost, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return dict(entry, texture_png=buf.getvalue(),
                note="the game loads plugins at start-up: quit_game and game_launch, then plant_trees with its name")


def designed() -> list[dict]:
    """SiMCP's own active tree designs, as tree_types lists trees."""
    return [{"id": d["flora"], "name": d["name"], "exemplar": "SiMCP_tree_" + content._slug(d["name"]),
             "design": True}
            for d in content._manifest() if d.get("kind") == "tree" and not d.get("disabled")]
