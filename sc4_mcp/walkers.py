"""New pedestrians: walkers drawn the way the game's own are - pre-rendered sprites.

A walker is an exemplar of type 0x17 in group 0xC96E6806 (the game's "Ped_male-med01-walk" 0x01600000: name, model
key, occupant groups 0x4000 / 0x4001 / 0x4107 and 0x4149 men or 0x414A women, under cohort 0x05342861) whose model
key [0x29A5D1EC, 0x49A593E7, i] names a 48-byte sprite descriptor: [0x29A5D1EC, FSH type, group, the atlas, 0x09ADCD75,
group, 0, 0, 0, the far zoom's frame table, the close zoom's, the frames per direction (the game's walkers: 11)]. The
atlas is an FSH of 256 x 256 DXT3 pages; a frame table (0x09ADCD75, 100 bytes) has a 32-byte header (type, 8, 1, 1,
zeros), a count (8) and one 8-byte entry per direction - page, log2 of the page size (8: 256 pixels), x, y,
width, height, anchor x, anchor y (the feet, from the frame's top left) - the direction's frames running left to
right from (x, y), wrapping to x = 0, y + height at the page's right edge and to (0, 0) of the next page at its
bottom (LIVE_FACTS, Phase 11 and the 2026-10-09 sprite survey: the game's walker tables start each direction 11
frames after the last).

The game shows pedestrians at its two closest zooms only, both from the close table: 1:1 at zoom 5 and doubled
(smoothed) at zoom 6; the far table is not drawn for them (measured 2026-10-10). Its own walkers' close frames are
drawn at the closest zoom's scale, so on screen pedestrians stand at about twice the city's scale at both zooms.

SiMCP draws the figure as a parts model posed for each of 11 walk-cycle frames (legs and arms swinging), as many as
the game's walkers have, turned to each of 8 headings and rendered with the game's camera and light (batrender) at
the same scales as the game's walkers (the far table at zoom 5's 7 px per metre, the close one at 14); its shadow is
the figure flattened along the game's sun (half length), a translucent dark patch in the sprite.
"""

from __future__ import annotations

import io
import math
import os
import struct
import time

import numpy as np
from PIL import Image

from . import content, dbpf, fsh

G_WALKERS = 0xC96E6806
G_SPRITES = 0x49A593E7
T_SPRITE = 0x29A5D1EC
T_FRAMES = 0x09ADCD75
T_COHORT = 0x05342861
TEMPLATE = 0x01600000                       # Ped_male-med01-walk
GROUPS = {"male": [0x4000, 0x4001, 0x4107, 0x4149], "female": [0x4000, 0x4001, 0x4107, 0x414A]}
SCALE = 1.08                                # the game's walkers are about life size (a little over)
FRAMES = 11                                 # frames per direction, as the game's walkers (the descriptor's last value)
TABLE_B = 8                                 # a frame table entry's second byte: log2 of the page size (256)
ZOOMS = (4, 5)                              # the far and close tables' render scales (7 and 14 px/m), as the game's
# direction d walks along (cos 45d, sin 45d) in the game's camera-fixed frame (X, Z): 0 along +X, 2 towards the camera
# (+Z) - found with probe walkers showing their direction (2 and 6 on a north-south street) and the frame widths
# (wide, narrow, narrow, wide... as the game's own); in the parts frame (x = -X, y = Z) that is 90 - 45d degrees
DIR_DEG = [90.0 - 45.0 * d for d in range(8)]
SHADOW_RGB = (26, 22, 40)
SHADOW_A = 0.42


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def figure(kind: str, phase: float, heading_deg: float, colours: dict) -> dict:
    """A walking person as a parts model, life size, its feet at (1, 1), walking towards heading_deg (0 = +y)."""
    c = np.array([1.0, 1.0])
    h = math.radians(heading_deg)
    fwd = np.array([-math.sin(h), math.cos(h)])          # 0 degrees = +y, counter-clockwise from above
    side = np.array([fwd[1], -fwd[0]])

    def at(f, s, z):
        p = c + fwd * f + side * s
        return [float(p[0]), float(p[1]), float(z)]
    swing = math.sin(2 * math.pi * phase)
    lift = max(0.0, math.cos(2 * math.pi * phase))
    female = kind == "female"
    hip, shoulder = 0.97, 1.44
    mats = {"skin": {"color": _hex(colours["skin"]), "grain": 0.04},
            "hair": {"color": _hex(colours["hair"]), "grain": 0.06},
            "shirt": {"color": _hex(colours["shirt"]), "grain": 0.08},
            "legs": {"color": _hex(colours["trousers"]), "grain": 0.08},
            "shoes": {"color": _hex(colours["shoes"]), "grain": 0.04}}
    parts = []
    for sgn in (1, -1):                                   # legs: from the hip to the foot, swinging
        a = 0.42 * swing * sgn
        foot_f = math.sin(a) * hip
        foot_z = 0.06 + (0.07 * lift if sgn * swing < 0 else 0.0)
        parts.append({"type": "beam", "from": at(0.0, 0.09 * sgn, hip), "to": at(foot_f, 0.09 * sgn, foot_z),
                      "w": 0.13, "h": 0.13, "offset": -0.065, "mat": "legs"})
        parts.append({"type": "beam", "from": at(foot_f - 0.05, 0.1 * sgn, 0.04), "to": at(foot_f + 0.17, 0.1 * sgn, 0.04),
                      "w": 0.11, "h": 0.09, "offset": 0.0, "mat": "shoes"})
    # the torso (a skirt for women): a block turned to the heading
    def block(f0, f1, s0, s1, z, hgt, mat):
        pts = [at(f0, s0, 0)[:2], at(f1, s0, 0)[:2], at(f1, s1, 0)[:2], at(f0, s1, 0)[:2]]
        parts.append({"type": "extrude", "points": pts, "z": z, "h": hgt, "mat": mat})
    if female:
        block(-0.14, 0.14, -0.18, 0.18, 0.58, hip - 0.58 + 0.05, "legs")
    block(-0.1, 0.1, -0.17 if not female else -0.15, 0.17 if not female else 0.15, hip - 0.04,
          shoulder - hip + 0.06, "shirt")
    for sgn in (1, -1):                                   # arms swing against the legs
        a = -0.45 * swing * sgn
        hand = at(math.sin(a) * 0.6, 0.22 * sgn, shoulder - math.cos(a) * 0.6)
        parts.append({"type": "beam", "from": at(0.0, 0.22 * sgn, shoulder), "to": hand, "w": 0.09, "h": 0.09,
                      "offset": -0.05, "mat": "shirt"})
        parts.append({"type": "blob", "cx": hand[0], "cy": hand[1], "z": hand[2] - 0.03, "r": 0.06, "jitter": 0,
                      "detail": 1, "mat": "skin"})
    parts.append({"type": "prism", "cx": c[0], "cy": c[1], "z": shoulder, "r": 0.06, "h": 0.08, "sides": 6,
                  "mat": "skin"})
    head = at(0.0, 0.0, shoulder + 0.2)
    parts.append({"type": "blob", "cx": head[0], "cy": head[1], "z": head[2], "rx": 0.1, "ry": 0.1, "rz": 0.12,
                  "jitter": 0, "detail": 1, "mat": "skin"})
    hz = head[2] + (0.03 if not female else 0.01)
    hb = at(-0.03, 0.0, hz)
    parts.append({"type": "blob", "cx": hb[0], "cy": hb[1], "z": hz, "rx": 0.11 if not female else 0.12,
                  "ry": 0.11 if not female else 0.12, "rz": 0.09 if not female else 0.13, "jitter": 0, "detail": 1,
                  "mat": "hair"})
    return {"scale": SCALE, "materials": mats, "parts": parts}


def _render_frame(model: dict, zoom: int):
    """(RGBA float image with the shadow under the figure, anchor (x, y) of the feet in it)."""
    from . import batrender, partmodel
    pm = dict(model)
    pm["lot"] = 1
    mesh, mats = partmodel.Builder(pm).build()
    origin = (1.0 * SCALE, 1.0 * SCALE)
    fig = batrender.Scene(mesh, mats, 1, origin=origin)
    img, (ox, oy), _P, _s = fig.render(zoom, 2)
    # the shadow: the figure flattened onto the ground along the sun, drawn as one dark translucent patch
    from .render3d import Material, Mesh
    P, N, UV, M, E = mesh.arrays()
    sun = batrender.SUN                                   # in the game's model frame (X, Y up, Z)
    # parts frame: x = -X, y = Z (view 2 is unturned); half the true length, as the game's walkers' shadows
    dx, dy = 0.5 * sun[0] / sun[1], -0.5 * sun[2] / sun[1]
    sm = Mesh()
    for t in range(len(P)):
        pts = [(float(p[0] + dx * p[2]), float(p[1] + dy * p[2]), 0.005) for p in P[t]]
        sm.tri(tuple(pts), ((0, 0, 1.0),) * 3, ((0, 0), (1, 0), (0, 1)), 0)
    sh = batrender.Scene(sm, [Material("shadow", color=(0, 0, 0))], 1, origin=origin)
    simg, (sx, sy), _P2, _s2 = sh.render(zoom, 2, light=False)
    x0, y0 = min(ox, sx), min(oy, sy)
    W = max(ox + img.shape[1], sx + simg.shape[1]) - x0
    H = max(oy + img.shape[0], sy + simg.shape[0]) - y0
    out = np.zeros((H, W, 4), np.float32)
    a = simg[..., 3:4] * SHADOW_A
    out[sy - y0:sy - y0 + simg.shape[0], sx - x0:sx - x0 + simg.shape[1]] = np.concatenate(
        [np.broadcast_to(np.array(SHADOW_RGB, np.float32) / 255, simg.shape[:2] + (3,)), a], -1)
    fa = img[..., 3:4]
    region = out[oy - y0:oy - y0 + img.shape[0], ox - x0:ox - x0 + img.shape[1]]
    region[..., :3] = img[..., :3] * fa + region[..., :3] * (1 - fa)
    region[..., 3:4] = fa + region[..., 3:4] * (1 - fa)
    return out, (-x0, -y0)


def _probe_frame(d: int, zoom: int, f: int = 0):
    """A probe frame: a bright card with the direction's digit (to find which direction is which heading) and,
    along its foot, a bar filled to frame f's place in the cycle (to see the game play every frame, and only the
    direction's own)."""
    from PIL import ImageDraw, ImageFont
    w, h = (14, 22) if zoom == 4 else (24, 36)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, w - 1, h - 6], fill=(255, 225, 40, 255), outline=(0, 0, 0, 255))
    bar = h - 9 if zoom != 4 else h - 8
    dr.rectangle([1, bar, 1 + round((w - 3) * (f + 1) / FRAMES), h - 7], fill=(200, 30, 30, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", h - 10)
    except OSError:
        font = ImageFont.load_default()
    dr.text((w / 2, (h - 6) / 2), str(d), fill=(0, 0, 0, 255), font=font, anchor="mm")
    dr.line([(w / 2, h - 6), (w / 2, h - 1)], fill=(0, 0, 0, 255), width=2)
    return np.asarray(im, np.float32) / 255.0, (w // 2, h - 1)


def frames(kind: str, colours: dict, zoom: int, probe: bool = False):
    """[(direction's frames [RGBA float], anchor)] for 8 directions, all frames of a direction on one canvas size."""
    out = []
    for d in range(8):
        imgs = []
        for f in range(FRAMES):
            if probe:
                imgs.append(_probe_frame(d, zoom, f))
            else:
                imgs.append(_render_frame(figure(kind, f / FRAMES, DIR_DEG[d], colours), zoom))
        # a common canvas: the union of every frame's box around the shared anchor
        left = max(a[0] for _, a in imgs)
        top = max(a[1] for _, a in imgs)
        right = max(im.shape[1] - a[0] for im, a in imgs)
        bottom = max(im.shape[0] - a[1] for im, a in imgs)
        W, H = left + right, top + bottom
        canv = []
        for im, (ax, ay) in imgs:
            c = np.zeros((H, W, 4), np.float32)
            c[top - ay:top - ay + im.shape[0], left - ax:left - ax + im.shape[1]] = im
            canv.append(c)
        out.append((canv, (left, top)))
    return out


def pack(zoom_sets):
    """Pages (256 x 256 float RGBA) and per zoom 8 entries (page, 8, x, y, w, h, ax, ay), the frames placed by the
    game's rule: left to right from (x, y), wrapping to x = 0, y + h. Every direction of a zoom uses the zoom's
    tallest frame height so rows never overlap, its frames sitting at the bottom of their cells so the feet (the
    anchor) stay where the game puts the walker's ground point; a direction whose frames would pass a page's bottom
    starts on a new page. Every direction must have the same number of frames (the descriptor's)."""
    pages = [np.zeros((256, 256, 4), np.float32)]
    page, x, y = 0, 0, 0
    tables = []
    for dirs in zoom_sets:
        H = max(c[0].shape[0] for c, _ in dirs)
        entries = []
        if x:                                            # a new zoom starts on a fresh row
            x, y = 0, y + row_h
        row_h = H
        for canv, (ax, ay) in dirs:
            w = canv[0].shape[1]
            n = len(canv)
            if x + w > 256:                              # a direction starts where its first frame fits
                x, y = 0, y + H
            # where would the frames end? start on a new page if they would not fit
            X, Y = x, y
            for _ in range(n):
                if X + w > 256:
                    X, Y = 0, Y + H
                X += w
            if Y + H > 256:
                pages.append(np.zeros((256, 256, 4), np.float32))
                page, x, y = len(pages) - 1, 0, 0
            entries.append((page, TABLE_B, x, y, w, H, ax, ay + (H - canv[0].shape[0])))
            for im in canv:
                if x + w > 256:
                    x, y = 0, y + H
                pages[page][y + H - im.shape[0]:y + H, x:x + w] = im    # bottom of the cell, as the anchor says
                x += w
        tables.append(entries)
    return pages, tables


def frame_table(entries) -> bytes:
    b = struct.pack("<4I", T_FRAMES, 8, 1, 1) + bytes(16) + struct.pack("<I", len(entries))
    for e in entries:
        if not all(0 <= v <= 255 for v in e):
            raise content.ContentError("a walker frame does not fit the table (%r)" % (e,))
        b += bytes(e)
    return b


def descriptor(atlas: int, t0: int, t1: int, frames: int = FRAMES) -> bytes:
    """The sprite descriptor: the atlas, the far and close frame tables, and the frames per direction (the game
    plays that many from each direction's start)."""
    return struct.pack("<12I", T_SPRITE, 0x7AB50E44, G_SPRITES, atlas, T_FRAMES, G_SPRITES, 0, 0, 0, t0, t1, frames)


def write_pages(pages) -> bytes:
    """An FSH of DXT3 pages ("TB2 ", "TB3 "...), as the game's walker atlases."""
    blobs = []
    for i, p in enumerate(pages):
        data = (np.clip(p, 0, 1) * 255 + 0.5).astype(np.uint8)
        one = fsh.write_dxt(data, fsh.CODE_DXT3)
        blobs.append(one[24:])                           # the entry (header + pixels) of a one-entry FSH
    head = 16 + 8 * len(blobs)
    out = bytearray(b"SHPI" + struct.pack("<II", 0, len(blobs)) + b"G264")
    off = head
    for i, bl in enumerate(blobs):
        out += (b"TB%d " % (2 + min(i, 7)))[:4] + struct.pack("<I", off)
        off += len(bl)
    for bl in blobs:
        out += bl
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)


DEFAULT_COLOURS = {"male": {"skin": (198, 152, 120), "hair": (60, 44, 34), "shirt": (70, 96, 140),
                            "trousers": (52, 54, 60), "shoes": (34, 30, 28)},
                   "female": {"skin": (206, 162, 132), "hair": (98, 64, 40), "shirt": (168, 62, 70),
                              "trousers": (58, 58, 66), "shoes": (40, 34, 32)}}


def design_walker(name: str, kind: str = "male", colours: dict | None = None, probe: bool = False,
                  taken: set[int] | None = None, replace: bool = False) -> dict:
    """Write a new walker as a plugin: it joins the city's pedestrians of its kind (men or women). replace:
    rebuild the walker design of that name (walkers are not kept in saved cities, so its ids may change)."""
    if replace:
        hit = [d for d in content._manifest() if d.get("kind") == "walker" and not d.get("disabled")
               and d["name"].lower() == name.lower()]
        if not hit:
            raise content.ContentError("no walker design named %r to replace" % name)
        content.disable(hit[0]["name"])
    content._check_name(name)
    if kind not in GROUPS:
        raise content.ContentError("kind is male or female")
    cols = dict(DEFAULT_COLOURS[kind])
    for k, v in (colours or {}).items():
        if k not in cols:
            raise content.ContentError("colours: %s" % ", ".join(cols))
        if len(v) != 3 or not all(0 <= x <= 255 for x in v):
            raise content.ContentError("colours are [r, g, b] with values 0..255")
        cols[k] = tuple(v)
    _, tpl = content._find_exemplar(dbpf.T_EXEMPLAR, TEMPLATE, G_WALKERS)
    if tpl is None:
        raise content.ContentError("the game's template walker (0x01600000) is not in SimCity_1.dat")
    taken = taken or set()
    while True:
        base = content._new_ids(taken, 1)[0] & 0xFFFFFF00
        ids = content.game_ids()
        if not any((t, G_SPRITES, base + k) in ids for t in (T_SPRITE, T_FRAMES, 0x7AB50E44) for k in range(2)):
            break
    walker_iid = content._new_ids(taken, 1)[0]
    sets = [frames(kind, cols, z, probe) for z in ZOOMS]
    pages, tables = pack(sets)
    props = [dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values, p.multi)
             for p in tpl.props]
    content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP_walker_" + content._slug(name))
    content._set(props, 0x09C80416, dbpf.PT_UINT32, [T_SPRITE, G_SPRITES, base], multi=True)
    content._set(props, 0xAA1DD396, dbpf.PT_UINT32, GROUPS[kind], multi=True)
    records = [(dbpf.T_EXEMPLAR, G_WALKERS, walker_iid, dbpf.build_exemplar(props, (T_COHORT, G_WALKERS, 1))),
               (T_SPRITE, G_SPRITES, base, descriptor(base, base, base + 1)),
               (T_FRAMES, G_SPRITES, base, frame_table(tables[0])),
               (T_FRAMES, G_SPRITES, base + 1, frame_table(tables[1])),
               (0x7AB50E44, G_SPRITES, base, write_pages(pages))]
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_walker_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "walker", "file": path, "walker": "0x%08X" % walker_iid,
             "sprites": "0x%08X" % base, "who": kind, "probe": probe, "pages": len(pages), "frames": FRAMES,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    sheet = Image.fromarray((np.clip(pages[0], 0, 1) * 255).astype(np.uint8), "RGBA")
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return dict(entry, atlas_png=buf.getvalue(),
                note="the game loads plugins at start-up: quit_game and game_launch; the walker then joins the "
                     "city's pedestrians")
