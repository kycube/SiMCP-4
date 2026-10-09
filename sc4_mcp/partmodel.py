"""Buildings from parts (SiMCP 3000's photo-to-building model, carried over): a JSON model of parts and materials
in metres, turned into the game's own 3D model (S3D, one mesh per material) and textures (FSH) by to_s3d.

In SimCity 4 the game draws the model itself (any zoom, any rotation, its own lights and shadows), so a model is
written once; render3d gives a quick preview without the game. Axes: the model's x / y are the lot's (0 .. lot * 16
m), z up; the +y side faces the street (the lot's front), +x is west. Stock props of the Building Architect are not
available: SimCity 4 props go on the lot (design_model_building's objects).

Model (all lengths in metres; the lot is lot * 16 m square, x and y from 0, z up; in the game's default view the +x
side is on the left, +y on the right):

    {"name": "...", "lot": 2, "scale": 1.0 (enlarges the whole model: props read at game size only when made 1.5 -
     2 times life size, as the game's own), "lighting": "game" | "architect",
     "materials": {"siding": {"pattern": "clapboard", "color": "#71806e", "size_m": [1, 1]},
                   "front": {"photo": "haas", "quad": [[x, y], [x, y], [x, y], [x, y]], "fit": true}, ...},
     "parts": [{"type": "box", "x": 6, "y": 4, "z": 0, "w": 15, "d": 18, "h": 11,
                "mat": "siding", "faces": {"+y": "front"}}, ...]}

Part types:
- box: x, y, z, w (along x), d (along y), h; faces of a box: +x, -x, +y, -y, top, bottom.
- beam: from [x, y, z], to [x, y, z], w (thickness), h (depth), offset - a box between two points: bargeboards along
  a gable's rakes, brackets, posts, sloping rails.
- extrude: points [[x, y], ...] (a footprint polygon, counter-clockwise or not), z, h - walls, top, bottom; "faces"
  can name an edge by its index ("0" = from point 0 to point 1).
- prism: cx, cy, z, r, h, sides (6, 8...; 0 or >= 24 = a round cylinder with smooth shading), angle (degrees);
  for a round one, "photo": {"mat": an unwrapped-tower photo material, "toward_deg": the direction the photo looks
  at the tower from (0 = from +x, 90 = from +y)} puts the photo on that side only and "mat" everywhere else.
- cone: cx, cy, z, r, h, sides (0 = round), angle - a cone or pyramid.
- roof: x, y, w, d, z (eave height), style hip | gable_x (ridge along x) | gable_y | pyramid | shed_+x / -x / +y /
  -y | flat; pitch (degrees, default 40), overhang (m, default 0.4); "mat" for the slopes, "gable" for the vertical
  gable ends (default the slopes' material); gable styles take "bargeboard": {"mat", "w", "h"} (carved trim along
  both rakes), "finial": {"mat", "h", "r"} (a turned post at the apex) and "ends": ["+x", ...] (which ends get them);
  any sloped style takes "ridge_cap": {"mat", "w", "h"} (a light line along the ridge and hips).
- panel: from [x, y], to [x, y], z, h - one vertical sheet seen from both sides: fences, open balustrades (a facade
  with "clear" parts is see-through: {"base": {"color": "clear"}} + a railing element).
- ground: the whole lot at z 0 (mat); patch: x, y, w, d, mat (a ground area slightly above it: paths, paving).
- prop: name (a stock Building Architect prop, e.g. "sm decid1"), x, y, z, orientation - drawn from its own views.
Every part takes "mat" (its default material) and "faces" {face: material} overrides.
"lighting": "game" (default) lights like the game's own buildings (soft shaded side); "architect" exactly like the
Building Architect's renders (the shaded side much darker). "shadows": false turns cast shadows off.

Materials (one of):
- {"color": "#rrggbb" | "r,g,b"}
- {"pattern": clapboard | shingle | fishscale | brick | stone | roof_shingle | slate | paving | clapboard_window |
   wall_window, "color": ..., "color2": ... (joints / shadows, or the window frame), "size_m": [w, h] (one repeat;
   for the *_window patterns one window bay, e.g. [2.5, 4] = one window per 2.5 m per storey)}
- {"texture": a Building Architect paint / ground / detail name (e.g. "grass", "brick 03") or a picture file,
   "size_m": [w, h] (one repeat; default: 16 px of the texture = 2 m)}
- {"photo": a photo name (photo_add), "quad": four photo pixels [x, y] at the face's top-left, top-right,
   bottom-right, bottom-left, "fit": true (stretched over the whole face; default) or "size_m": [w, h] to repeat}
   - the photo region is rectified (perspective removed) into a flat texture.
- {"photo": name, "cylinder": {"left": [[x, y_top], [x, y_bottom]], "right": [[x, y_top], [x, y_bottom]],
   "span_deg": 160}} - a ROUND surface (tower, turret, rounded bay) seen from the front: its silhouette edges in the
   photo; the visible half is unrolled at equal angles (a flat quad would stretch the squeezed edges). Use it with a
   round prism's "photo" option.
- {"facade": {...}} - an AUTHORED wall (facade.py): windows, doors, bands, friezes, railings, ornaments and
   shingle fields drawn at measured positions in clean colours; stretched over the whole face. The recommended way
   to use a photo: measure from it, draw the facade (crisp, lit consistently) rather than pasting its pixels.
Options on any material: "glow": true or "#rrggbb" (it shines at night - lamps, lit signs, shop windows; facades
light their windows themselves), "grain": 0.06 (weathering), "tint": "#rrggbb" (multiplies), "brightness": 1.0 (photos of walls in shade usually need
1.2 - 1.5: the renderer lights them again), "remove_color": "#rrggbb" + "tolerance" (photo texels near that colour,
e.g. the sky beside a narrow turret, are filled from the surrounding wall).
"""

from __future__ import annotations

import math
import os
import re

import numpy as np
from PIL import Image



class GameError(Exception):
    """A model the builder cannot follow (the message says what to fix)."""

    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


from . import render3d
from .render3d import Material, Mesh, TILE_M

def _work() -> str:
    from . import launch
    return os.path.join(launch.ROOT, "photos")


WORK = None                                    # photos live in SiMCP's home folder (photos\\)


# ------------------------------------------------------------------------------------------ photos
def photo_path(name: str) -> str:
    return os.path.join(_work(), re.sub(r"[^A-Za-z0-9 _\-]", "_", name) + ".png")


def add_photo(name: str, im: Image.Image) -> dict:
    os.makedirs(os.path.dirname(photo_path(name)), exist_ok=True)
    im.convert("RGB").save(photo_path(name))
    return {"photo": name, "pixels": list(im.size), "file": photo_path(name)}


def load_photo(name: str) -> Image.Image:
    p = photo_path(name)
    if not os.path.exists(p):
        raise GameError(f"no photo {name!r} (photo_add first)")
    return Image.open(p).convert("RGB")


def _homography(src, dst) -> np.ndarray:
    """3x3 matrix mapping dst points to src points (for PIL's perspective transform: output -> input)."""
    A, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    return np.linalg.solve(np.array(A, float), np.array(b, float))


def rectify(photo: Image.Image, quad, out_w: int, out_h: int) -> Image.Image:
    """The photo region inside quad (top-left, top-right, bottom-right, bottom-left) as a flat out_w x out_h image."""
    if len(quad) != 4:
        raise GameError("quad: four [x, y] photo pixels: top-left, top-right, bottom-right, bottom-left")
    dst = [(0, 0), (out_w, 0), (out_w, out_h), (0, out_h)]
    coeffs = _homography([tuple(map(float, p)) for p in quad], dst)
    return photo.transform((out_w, out_h), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)


# ------------------------------------------------------------------------------------------ materials
def parse_color(v) -> tuple:
    if isinstance(v, (list, tuple)):
        return tuple(int(c) for c in v[:3])
    s = str(v).strip()
    if s.startswith("#") and len(s) == 7:
        return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
    parts = [p for p in re.split(r"[ ,]+", s) if p]
    if len(parts) == 3:
        return tuple(int(p) for p in parts)
    raise GameError(f"colour {v!r}: '#rrggbb' or 'r,g,b'")


def _shade(c, k):
    return tuple(max(0, min(255, int(x * k))) for x in c)


def pattern_image(kind: str, color, color2=None, px: int = 64) -> Image.Image:
    if kind in ("clapboard_window", "wall_window"):
        px = 128
    """A small repeating texture (px x px for one repeat)."""
    from PIL import ImageDraw
    c = parse_color(color)
    c2 = parse_color(color2) if color2 else _shade(c, 0.72)
    hi = _shade(c, 1.12)
    im = Image.new("RGB", (px, px), c)
    d = ImageDraw.Draw(im)
    if kind == "clapboard":                     # 4 boards per repeat: highlight, body, shadow line
        for k in range(4):
            y0 = k * px // 4
            d.line([(0, y0), (px, y0)], fill=hi, width=max(1, px // 64))
            d.rectangle([0, y0 + px // 4 - max(2, px // 24), px, y0 + px // 4 - 1], fill=c2)
    elif kind in ("shingle", "roof_shingle", "slate"):
        rows = 4
        for k in range(rows):
            y0 = k * px // rows
            d.rectangle([0, y0 + px // rows - max(2, px // 32), px, y0 + px // rows - 1], fill=c2)
            off = (px // 8) if k % 2 else 0
            for x in range(off, px + px // 4, px // 4):
                d.line([(x, y0), (x, y0 + px // rows - 1)], fill=c2, width=max(1, px // 64))
    elif kind == "fishscale":
        rows, cols = 4, 4
        sw, sh = px // cols, px // rows
        for k in range(rows + 1):
            off = sw // 2 if k % 2 else 0
            for j in range(-1, cols + 1):
                x0, y0 = j * sw + off, k * sh - sh
                d.arc([x0, y0, x0 + sw, y0 + 2 * sh], 0, 180, fill=c2, width=max(1, px // 40))
    elif kind == "brick":
        rows = 8
        for k in range(rows):
            y0 = k * px // rows
            d.line([(0, y0), (px, y0)], fill=c2, width=max(1, px // 64))
            off = px // 8 if k % 2 else 0
            for x in range(off, px + px // 4, px // 4):
                d.line([(x, y0), (x, y0 + px // rows)], fill=c2, width=max(1, px // 64))
    elif kind in ("clapboard_window", "wall_window"):
        # a wall repeat with one window in it (for the sides a photo does not show): clapboard or plain wall,
        # a light frame (color2) and dark glass with a sash bar
        if kind == "clapboard_window":
            for k in range(8):
                y0 = k * px // 8
                d.line([(0, y0), (px, y0)], fill=hi, width=max(1, px // 64))
                d.rectangle([0, y0 + px // 8 - max(2, px // 40), px, y0 + px // 8 - 1], fill=_shade(c, 0.78))
        frame = parse_color(color2) if color2 else (214, 210, 196)
        glass = (44, 52, 64)
        x0, x1 = int(px * 0.32), int(px * 0.68)
        y0, y1 = int(px * 0.22), int(px * 0.82)
        f = max(2, px // 24)
        d.rectangle([x0 - f, y0 - f, x1 + f, y1 + f], fill=frame)
        d.rectangle([x0, y0, x1, y1], fill=glass)
        d.rectangle([x0, (y0 + y1) // 2 - f // 2, x1, (y0 + y1) // 2 + f // 2], fill=frame)
        d.rectangle([x0, y0, x1, y0 + (y1 - y0) // 6], fill=(70, 78, 90))
        d.rectangle([x0 - 2 * f, y1 + f, x1 + 2 * f, y1 + 2 * f], fill=frame)        # sill
    elif kind in ("stone", "paving"):
        rows = 4 if kind == "stone" else 4
        for k in range(rows):
            y0 = k * px // rows
            d.line([(0, y0), (px, y0)], fill=c2, width=max(1, px // 32))
            off = px // 4 if k % 2 else 0
            for x in range(off, px + px // 2, px // 2):
                d.line([(x, y0), (x, y0 + px // rows)], fill=c2, width=max(1, px // 32))
    else:
        raise GameError("pattern: clapboard, clapboard_window, wall_window, shingle, fishscale, brick, stone, "
                        "roof_shingle, slate or paving")
    return im


def foliage_image(kind: str, color, color2=None, density: float = 0.75, seed: int = 1, px: int = 96):
    """A see-through foliage texture (RGBA): leaves (small broad leaves at random angles), needles (short strokes)
    or fronds (a feather of leaflets along a midrib, for palm fronds); colours vary around color, a share of darker
    color2. Transparent texels are cut away by the renderer (and in its shadows)."""
    from PIL import ImageDraw
    rnd = np.random.default_rng(seed)
    c = np.array(parse_color(color), float)
    c2 = np.array(parse_color(color2), float) if color2 else c * 0.62
    im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def col():
        k = rnd.uniform(0.78, 1.18)
        base = c2 if rnd.random() < 0.3 else c
        jit = rnd.normal(0, 8, 3)
        return tuple(int(v) for v in np.clip(base * k + jit, 0, 255)) + (255,)
    if kind == "fronds":
        mid = px // 2
        d.line([(mid, 0), (mid, px)], fill=col(), width=max(2, px // 32))
        for y in range(-px // 8, px, max(2, px // 32)):
            L = px * 0.47
            for s in (-1, 1):
                d.line([(mid, y), (mid + s * L, y + px * 0.16)], fill=col(), width=max(2, px // 24))
        return im
    n = int(px * px * density / (14 if kind == "leaves" else 9))
    for _ in range(n):
        x, y = rnd.uniform(-4, px + 4, 2)
        a = rnd.uniform(0, np.pi)
        if kind == "needles":
            L = rnd.uniform(3, 6)
            for dx in (-px, 0, px):
                for dy in (-px, 0, px):
                    d.line([(x + dx - L * np.cos(a), y + dy - L * np.sin(a)),
                            (x + dx + L * np.cos(a), y + dy + L * np.sin(a))], fill=col(), width=2)
            continue
        L, W = rnd.uniform(2.5, 5.0), rnd.uniform(1.6, 3.0)
        pts = [(L * np.cos(t) * np.cos(a) - W * np.sin(t) * np.sin(a),
                L * np.cos(t) * np.sin(a) + W * np.sin(t) * np.cos(a)) for t in np.linspace(0, 2 * np.pi, 8)]
        f = col()
        for dx in (-px, 0, px):                      # wrap around: the texture repeats
            for dy in (-px, 0, px):
                d.polygon([(x + dx + u, y + dy + v) for u, v in pts], fill=f)
    return im


def library_texture(name: str) -> Image.Image | None:
    """A picture file used as a texture (SimCity 4 has no Building Architect paint library)."""
    for cand in (name, name + ".png", name + ".tga", name + ".bmp"):
        p = cand if os.path.exists(cand) else None
        if p:
            im = Image.open(p).convert("RGBA")
            if p.lower().endswith(".bmp"):
                im.putdata([(0, 0, 0, 0) if c[:3] == (255, 0, 255) else c for c in im.getdata()])
            return im
    return None


def unwrap_cylinder(photo: Image.Image, cyl: dict) -> tuple[Image.Image, float]:
    """Unroll a round tower seen from the front: for every photo row between the top and bottom of the given
    silhouette edges ("left" / "right": [[x, y_top], [x, y_bottom]] each), the tower's centre is midway between the
    edges and its radius half their distance, and a point at angle a (0 = facing the camera) appears at
    x = centre + radius * sin(a). Columns of the result are equal steps of angle across span_deg (default 160: the
    last degrees at the silhouette are too squeezed in the photo to use), so the texture is a true unrolled strip."""
    try:
        (lx0, ly0), (lx1, ly1) = cyl["left"]
        (rx0, ry0), (rx1, ry1) = cyl["right"]
    except (KeyError, TypeError, ValueError):
        raise GameError('cylinder: {"left": [[x, y_top], [x, y_bottom]], "right": [[x, y_top], [x, y_bottom]], '
                        '"span_deg": 160}')
    span = float(cyl.get("span_deg", 160))
    if not 30 <= span <= 180:
        raise GameError("cylinder span_deg: 30..180")
    top, bot = (ly0 + ry0) / 2, (ly1 + ry1) / 2
    H = int(max(16, min(2048, bot - top)))
    rad = abs(rx0 - lx0) / 2
    W = int(max(16, min(2048, rad * math.radians(span))))
    t = (np.arange(H) + 0.5) / H
    xl, xr = lx0 + (lx1 - lx0) * t, rx0 + (rx1 - rx0) * t
    yy = top + (bot - top) * t
    ang = np.radians(-span / 2 + span * (np.arange(W) + 0.5) / W)
    c, R = (xl + xr) / 2, (xr - xl) / 2
    X = c[:, None] + R[:, None] * np.sin(ang)[None, :]
    Y = np.repeat(yy[:, None], W, axis=1)
    src = np.asarray(photo, np.float32)
    x0 = np.clip(np.floor(X).astype(int), 0, src.shape[1] - 2)
    y0 = np.clip(np.floor(Y).astype(int), 0, src.shape[0] - 2)
    fx, fy = (X - x0)[..., None], (Y - y0)[..., None]
    out = (src[y0, x0] * (1 - fx) + src[y0, x0 + 1] * fx) * (1 - fy) +           (src[y0 + 1, x0] * (1 - fx) + src[y0 + 1, x0 + 1] * fx) * fy
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"), span


def _remove_color(mat: Material, color, tol: float) -> None:
    """Replace texels close to a colour (e.g. sky showing beside a narrow tower in the photo) with the colours
    around them: repeated averaging of the valid neighbours grows the wall into the removed area."""
    t = mat.tex
    rgb = t[:, :, :3] * 255.0
    bad = np.linalg.norm(rgb - np.array(color, np.float32), axis=2) < tol
    if not bad.any() or bad.all():
        return
    good = ~bad
    col = np.where(good[..., None], t[:, :, :3], 0).astype(np.float32)
    w = good.astype(np.float32)
    for _ in range(max(t.shape[:2])):
        if good.all():
            break
        pc = np.pad(col, ((1, 1), (1, 1), (0, 0)))
        pw = np.pad(w, 1)
        s_ = pc[:-2, 1:-1] + pc[2:, 1:-1] + pc[1:-1, :-2] + pc[1:-1, 2:]
        n_ = pw[:-2, 1:-1] + pw[2:, 1:-1] + pw[1:-1, :-2] + pw[1:-1, 2:]
        grow = (~good) & (n_ > 0)
        col[grow] = s_[grow] / n_[grow][:, None]
        w[grow] = 1.0
        good = good | grow
    t[:, :, :3] = col


GRAIN = 0.06                 # default weathering: the renderer's noise in model space (batrender)


def make_material(name: str, spec: dict, rect_px_per_m: float = 48.0) -> Material:
    if not isinstance(spec, dict):
        raise GameError(f"material {name!r}: an object such as {{\"color\": \"#8a8a8a\"}}")
    mat = _make_material(name, spec, rect_px_per_m)
    if spec.get("glow"):                     # it shines at night: a lamp globe, a lit sign, a shop window
        g = spec["glow"]
        c = parse_color("#ffd38a" if g is True else g)
        im = Image.new("RGBA", (4, 4), tuple(c[:3]) + (int(255 * float(spec.get("glow_alpha", 0.95))),))
        mat.glow = Material(name + " light", im, fit=True)
    try:
        mat.wrap = float(spec.get("wrap", 0.0))         # foliage: light wraps past the shaded side (0..1)
        mat.grain = float(spec.get("grain", GRAIN))
    except (TypeError, ValueError):
        raise GameError(f"material {name!r}: grain is a number (0 = clean, 0.06 default, 0.2 strong)")
    if not 0 <= mat.grain <= 0.5:
        raise GameError(f"material {name!r}: grain 0..0.5")
    return mat


def _make_material(name: str, spec: dict, rect_px_per_m: float = 48.0) -> Material:
    tint = parse_color(spec["tint"]) if spec.get("tint") else None
    bright = float(spec.get("brightness", 1.0))
    size = spec.get("size_m")
    if "facade" in spec:                     # an authored wall: drawn element by element (facade.py)
        from . import facade
        im, glow = facade.draw_with_light(spec["facade"])
        mat = Material(name, im, fit=True)
        if glow is not None:                 # what shines at night (batrender's night layer)
            mat.glow = Material(name + " light", glow, fit=True)
        if bright != 1.0 or tint:
            t = np.array(tint or (255, 255, 255), np.float32) / 255.0 * bright
            mat.tex[:, :, :3] = np.clip(mat.tex[:, :, :3] * t, 0, 1)
        return mat
    if "color" in spec and "pattern" not in spec:
        c = _shade(parse_color(spec["color"]), bright)
        return Material(name, color=c)
    if spec.get("pattern") in ("leaves", "fronds", "needles"):     # foliage: see-through, cut out by alpha
        im = foliage_image(spec["pattern"], spec.get("color", "#5f7a3a"), spec.get("color2"),
                           float(spec.get("density", 0.75)), int(spec.get("seed", 1)))
        mat = Material(name, im, size_m=size or (1.4, 1.4))
    elif "pattern" in spec:
        im = pattern_image(spec["pattern"], spec.get("color", "#9a9a9a"), spec.get("color2"))
        mat = Material(name, im, size_m=size or (1.0, 1.0))
    elif "texture" in spec:
        im = library_texture(str(spec["texture"]))
        if im is None:
            raise GameError(f"material {name!r}: no picture file {spec['texture']!r}")
        mat = Material(name, im, size_m=size or (im.width / 8.0, im.height / 8.0))
    elif "photo" in spec and spec.get("cylinder"):
        im, span = unwrap_cylinder(load_photo(str(spec["photo"])), spec["cylinder"])
        mat = Material(name, im, fit=True)
        mat.span_deg = span
    elif "photo" in spec:
        photo = load_photo(str(spec["photo"]))
        quad = spec.get("quad")
        if not quad:
            raise GameError(f"material {name!r}: a photo material needs quad (4 photo pixels)")
        wq = max(math.dist(quad[0], quad[1]), math.dist(quad[3], quad[2]))
        hq = max(math.dist(quad[0], quad[3]), math.dist(quad[1], quad[2]))
        w = int(min(2048, max(16, wq)))
        h = int(min(2048, max(16, hq)))
        im = rectify(photo, quad, w, h)
        fit = spec.get("fit", size is None)
        mat = Material(name, im, size_m=size or (1.0, 1.0), fit=fit)
    else:
        raise GameError(f"material {name!r}: give color, pattern, texture or photo")
    if spec.get("remove_color"):
        _remove_color(mat, parse_color(spec["remove_color"]), float(spec.get("tolerance", 60)))
    if tint or bright != 1.0:
        t = np.array(tint or (255, 255, 255), np.float32) / 255.0 * bright
        mat.tex[:, :, :3] = np.clip(mat.tex[:, :, :3] * t, 0, 1)
    return mat


# ------------------------------------------------------------------------------------------ geometry
UP = np.array([0, 0, 1.0])


class Builder:
    def __init__(self, model: dict):
        self.model = model
        lot = model.get("lot", 1)
        self.lot_w, self.lot_d = (int(lot[0]), int(lot[1])) if isinstance(lot, (list, tuple)) else (int(lot), int(lot))
        if not (1 <= self.lot_w <= 6 and 1 <= self.lot_d <= 6):
            raise GameError("lot: 1..6 cells a side (a number, or [across the street, deep])")
        self.lot = max(self.lot_w, self.lot_d)
        self.L = self.lot * TILE_M
        self.LX, self.LY = self.lot_w * TILE_M, self.lot_d * TILE_M
        self.mesh = Mesh()
        self.mats: list[Material] = []
        self.mat_index: dict[str, int] = {}
        specs = model.get("materials", {})
        for k, v in specs.items():
            self.mat_index[k] = len(self.mats)
            self.mats.append(make_material(k, v))
        self.default = self._mat("_default", {"color": "#b4b4b4"})

    def _mat(self, name, spec=None) -> int:
        if name in self.mat_index:
            return self.mat_index[name]
        if spec is None:
            raise GameError(f"no material {name!r} (define it under materials)")
        self.mat_index[name] = len(self.mats)
        self.mats.append(make_material(name, spec))
        return self.mat_index[name]

    def face_mat(self, part, face: str) -> int:
        f = part.get("faces", {})
        name = f.get(face) or (f.get("sides") if face not in ("top", "bottom") else None) or part.get("mat")
        return self._mat(name) if name else self.default

    # a planar polygon face (convex, triangle fan from its first vertex) with face coordinates in metres:
    # u to the right seen from outside, v downwards (walls: from the top; slopes: downhill; flat: along x)
    def face(self, pts, normal, mat: int, smooth=None):
        pts = [np.array(p, float) for p in pts]
        n = np.array(normal, float)
        n /= np.linalg.norm(n)
        if abs(n[2]) > 0.999:
            right = np.array([0, 1.0, 0]) if n[2] > 0 else np.array([0, -1.0, 0])
            down = np.array([1.0, 0, 0])
        else:
            right = np.cross(UP, n)
            right /= np.linalg.norm(right)
            down = -UP + n * n[2]                    # steepest descent within the plane (straight down on a wall)
            down /= np.linalg.norm(down)
        us = [float(np.dot(q, right)) for q in pts]
        vs = [float(np.dot(q, down)) for q in pts]
        u0, v0 = min(us), min(vs)
        ext = (max(us) - u0, max(vs) - v0)
        uv = [(u - u0, v - v0) for u, v in zip(us, vs)]
        nn = smooth or [n] * len(pts)
        for i in range(1, len(pts) - 1):
            self.mesh.tri((pts[0], pts[i], pts[i + 1]), (nn[0], nn[i], nn[i + 1]), (uv[0], uv[i], uv[i + 1]), mat, ext)

    # ---------------------------------------------------------------- parts
    def box(self, p):
        x, y, z = float(p["x"]), float(p["y"]), float(p.get("z", 0))
        w, d, h = float(p["w"]), float(p["d"]), float(p["h"])
        X, Y, Z = x + w, y + d, z + h
        self.face([(X, y, Z), (X, Y, Z), (X, Y, z), (X, y, z)], (1, 0, 0), self.face_mat(p, "+x"))
        self.face([(x, Y, Z), (x, y, Z), (x, y, z), (x, Y, z)], (-1, 0, 0), self.face_mat(p, "-x"))
        self.face([(X, Y, Z), (x, Y, Z), (x, Y, z), (X, Y, z)], (0, 1, 0), self.face_mat(p, "+y"))
        self.face([(x, y, Z), (X, y, Z), (X, y, z), (x, y, z)], (0, -1, 0), self.face_mat(p, "-y"))
        self.face([(x, y, Z), (x, Y, Z), (X, Y, Z), (X, y, Z)], (0, 0, 1), self.face_mat(p, "top"))

    def panel(self, p):
        """One vertical sheet from "from" [x, y] to "to" [x, y], z .. z + h: fences, open balustrades, signs (a
        facade with "clear" parts is see-through; the sheet shows from both sides)."""
        (x0, y0), (x1, y1) = (tuple(map(float, q)) for q in (p["from"], p["to"]))
        z, h = float(p.get("z", 0)), float(p["h"])
        nx, ny = (y1 - y0), -(x1 - x0)
        if abs(nx) + abs(ny) < 1e-9:
            raise GameError("panel: from and to are the same point")
        self.face([(x1, y1, z + h), (x0, y0, z + h), (x0, y0, z), (x1, y1, z)], (nx, ny, 0), self.face_mat(p, "sides"))

    def extrude(self, p):
        pts = [tuple(map(float, q)) for q in p["points"]]
        if len(pts) < 3:
            raise GameError("extrude: at least 3 points")
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
        if area < 0:
            pts = pts[::-1]
        z, h = float(p.get("z", 0)), float(p["h"])
        n_pts = len(pts)
        for i in range(n_pts):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n_pts]
            nx, ny = (y1 - y0), -(x1 - x0)                     # outward for counter-clockwise polygons
            if abs(nx) + abs(ny) < 1e-9:
                continue
            self.face([(x1, y1, z + h), (x0, y0, z + h), (x0, y0, z), (x1, y1, z)], (nx, ny, 0),
                      self.face_mat(p, str(i)))
        self.face([(px, py, z + h) for px, py in pts], (0, 0, 1), self.face_mat(p, "top"))

    def _ring(self, cx, cy, r, sides, angle):
        n = sides if sides and sides < 24 else 32
        a0 = math.radians(angle)
        return [(cx + r * math.cos(a0 + 2 * math.pi * k / n), cy + r * math.sin(a0 + 2 * math.pi * k / n))
                for k in range(n)], (not sides or sides >= 24)

    def prism(self, p):
        cx, cy, z, r, h = (float(p[k]) for k in ("cx", "cy", "z", "r", "h")) if "z" in p else \
            (float(p["cx"]), float(p["cy"]), 0.0, float(p["r"]), float(p["h"]))
        ring, round_ = self._ring(cx, cy, r, int(p.get("sides", 0)), float(p.get("angle", 0)))
        n = len(ring)
        mat = self.face_mat(p, "sides")
        circ = 2 * math.pi * r
        ph = p.get("photo")                # {"mat": unwrapped photo material, "toward_deg": 0 = facing +x}
        if ph:
            pmat = self._mat(ph["mat"])
            pspan = float(getattr(self.mats[pmat], "span_deg", ph.get("span_deg", 160)))
            toward = math.radians(float(ph.get("toward_deg", 0)))
            if not round_:
                raise GameError("photo on a prism needs a round one (sides 0)")
            # an exact ring for the photo span: segment boundaries at the span's edges
            a0 = toward - math.radians(pspan) / 2
            k = max(8, int(round(32 * pspan / 360)))
            angs = [a0 + math.radians(pspan) * j / k for j in range(k + 1)]
            rest = 360 - pspan
            k2 = max(4, int(round(32 * rest / 360)))
            angs += [a0 + math.radians(pspan) + math.radians(rest) * j / k2 for j in range(1, k2)]
            ring = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angs]
            n = len(ring)
            arc = r * math.radians(pspan)
            for i in range(n):
                (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % n]
                n0 = np.array((x0 - cx, y0 - cy, 0.0)) / r
                n1 = np.array((x1 - cx, y1 - cy, 0.0)) / r
                a_, b_, c_, d_ = (x1, y1, z + h), (x0, y0, z + h), (x0, y0, z), (x1, y1, z)
                if i < k:                  # in the photo span: u across the span (fit to the unrolled strip)
                    u0, u1 = arc * i / k, arc * (i + 1) / k
                    self.mesh.quad(a_, b_, c_, d_, n1, (u1, 0), (u0, 0), (u0, h), (u1, h), pmat, (arc, h),
                                   normals=[n1, n0, n0, n1])
                else:
                    u0, u1 = r * angs[i], r * (angs[(i + 1) % n] if i + 1 < n else angs[0] + 2 * math.pi)
                    self.mesh.quad(a_, b_, c_, d_, n1, (u1, 0), (u0, 0), (u0, h), (u1, h), mat, (circ, h),
                                   normals=[n1, n0, n0, n1])
            self.face([(x, y, z + h) for x, y in ring], (0, 0, 1), self.face_mat(p, "top"))
            return
        for i in range(n):
            (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % n]
            mx, my = (x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy
            if round_:
                n0 = (x0 - cx, y0 - cy, 0)
                n1 = (x1 - cx, y1 - cy, 0)
                u0, u1 = circ * i / n, circ * (i + 1) / n
                a, b, c, d = (x1, y1, z + h), (x0, y0, z + h), (x0, y0, z), (x1, y1, z)
                nn = [np.array(v, float) / np.linalg.norm(v) for v in (n1, n0, n0, n1)]
                self.mesh.quad(a, b, c, d, nn[0], (u1, 0), (u0, 0), (u0, h), (u1, h), mat, (circ, h), normals=nn)
            else:
                self.face([(x1, y1, z + h), (x0, y0, z + h), (x0, y0, z), (x1, y1, z)], (mx, my, 0), mat)
        self.face([(x, y, z + h) for x, y in ring], (0, 0, 1), self.face_mat(p, "top"))

    def cone(self, p):
        cx, cy, z, r, h = float(p["cx"]), float(p["cy"]), float(p.get("z", 0)), float(p["r"]), float(p["h"])
        ring, round_ = self._ring(cx, cy, r, int(p.get("sides", 0)), float(p.get("angle", 0)))
        n = len(ring)
        mat = self.face_mat(p, "sides")
        apex = (cx, cy, z + h)
        slant = math.hypot(r, h)
        for i in range(n):
            (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % n]
            if round_:
                def nrm(x, y):
                    v = np.array([(x - cx) * h / r, (y - cy) * h / r, r], float)
                    return v / np.linalg.norm(v)
                n0, n1 = nrm(x0, y0), nrm(x1, y1)
                na = (n0 + n1) / np.linalg.norm(n0 + n1)
                u0, u1 = 2 * math.pi * r * i / n, 2 * math.pi * r * (i + 1) / n
                self.mesh.tri(((x1, y1, z), apex, (x0, y0, z)), (n1, na, n0), ((u1, slant), ((u0 + u1) / 2, 0),
                              (u0, slant)), mat, (2 * math.pi * r, slant))
            else:
                e = np.array([x1 - x0, y1 - y0, 0.0])
                f = np.array(apex) - np.array([x0, y0, z])
                nn = np.cross(e, f)
                if nn[2] < 0:
                    nn = -nn
                self.face([(x0, y0, z), (x1, y1, z), apex], nn, mat)

    def roof(self, p):
        x, y, w, d, z = (float(p[k]) for k in ("x", "y", "w", "d", "z"))
        style = p.get("style", "hip")
        t = math.tan(math.radians(float(p.get("pitch", 40))))
        o = float(p.get("overhang", 0.4))
        smat = self._mat(p["mat"]) if p.get("mat") else self.default
        gmat = self._mat(p["gable"]) if p.get("gable") else smat
        # eave rectangle with the overhang, lowered so the slope still meets the wall top
        X0, Y0, X1, Y1, ze = x - o, y - o, x + w + o, y + d + o, z - o * t
        if style == "flat":
            self.face([(X0, Y0, z), (X0, Y1, z), (X1, Y1, z), (X1, Y0, z)], (0, 0, 1), smat)
            return
        if style in ("hip", "pyramid"):
            W, D = X1 - X0, Y1 - Y0
            if style == "pyramid" or abs(W - D) < 1e-6:
                hgt = min(W, D) / 2 * t
                ap = ((X0 + X1) / 2, (Y0 + Y1) / 2, ze + hgt)
                for a, b, nrm in (((X1, Y0), (X1, Y1), (1, 0)), ((X1, Y1), (X0, Y1), (0, 1)),
                                  ((X0, Y1), (X0, Y0), (-1, 0)), ((X0, Y0), (X1, Y0), (0, -1))):
                    self.face([(a[0], a[1], ze), (b[0], b[1], ze), ap], (nrm[0] * t, nrm[1] * t, 1), smat)
                self._ridge_caps(p, [((X0, Y0, ze), ap), ((X1, Y0, ze), ap), ((X1, Y1, ze), ap), ((X0, Y1, ze), ap)])
                return
            hgt = min(W, D) / 2 * t
            zr = ze + hgt
            if W >= D:
                ym = (Y0 + Y1) / 2
                ra, rb = (X0 + D / 2, ym, zr), (X1 - D / 2, ym, zr)
                self.face([(X0, Y1, ze), (X1, Y1, ze), rb, ra], (0, t, 1), smat)
                self.face([(X1, Y0, ze), (X0, Y0, ze), ra, rb], (0, -t, 1), smat)
                self.face([(X1, Y0, ze), rb, (X1, Y1, ze)], (t, 0, 1), smat)
                self.face([(X0, Y1, ze), ra, (X0, Y0, ze)], (-t, 0, 1), smat)
                self._ridge_caps(p, [(ra, rb), ((X0, Y0, ze), ra), ((X0, Y1, ze), ra), ((X1, Y0, ze), rb),
                                     ((X1, Y1, ze), rb)])
            else:
                xm = (X0 + X1) / 2
                ra, rb = (xm, Y0 + W / 2, zr), (xm, Y1 - W / 2, zr)
                self.face([(X1, Y0, ze), (X1, Y1, ze), rb, ra], (t, 0, 1), smat)
                self.face([(X0, Y1, ze), (X0, Y0, ze), ra, rb], (-t, 0, 1), smat)
                self.face([(X1, Y1, ze), (X0, Y1, ze), rb], (0, t, 1), smat)
                self.face([(X0, Y0, ze), (X1, Y0, ze), ra], (0, -t, 1), smat)
                self._ridge_caps(p, [(ra, rb), ((X0, Y0, ze), ra), ((X1, Y0, ze), ra), ((X0, Y1, ze), rb),
                                     ((X1, Y1, ze), rb)])
            return
        if style == "gable_y":                      # ridge along y; gable ends at y = y and y + d (no overhang)
            xm, hgt = (X0 + X1) / 2, (X1 - X0) / 2 * t
            zr = ze + hgt
            for ya, yb in ((Y0, Y1),):
                self.face([(X1, ya, ze), (X1, yb, ze), (xm, yb, zr), (xm, ya, zr)], (t, 0, 1), smat)
                self.face([(X0, yb, ze), (X0, ya, ze), (xm, ya, zr), (xm, yb, zr)], (-t, 0, 1), smat)
            gz = z                                   # gable walls stand on the wall top, up to the ridge
            gh = (w / 2) * t
            self.face([(x + w, Y1, gz), (x, Y1, gz), (x + w / 2, Y1, gz + gh)], (0, 1, 0), gmat)
            self.face([(x, Y0, gz), (x + w, Y0, gz), (x + w / 2, Y0, gz + gh)], (0, -1, 0), gmat)
            self._ridge_caps(p, [((xm, Y0, zr), (xm, Y1, zr))])
            self._gable_trim(p, {"+y": ([(X0, Y1, ze), (X1, Y1, ze)], (xm, Y1, zr), (0, 1, 0)),
                                 "-y": ([(X0, Y0, ze), (X1, Y0, ze)], (xm, Y0, zr), (0, -1, 0))})
            return
        if style == "gable_x":                      # ridge along x; gable ends at x = x and x + w
            ym, hgt = (Y0 + Y1) / 2, (Y1 - Y0) / 2 * t
            zr = ze + hgt
            self.face([(X1, Y1, ze), (X0, Y1, ze), (X0, ym, zr), (X1, ym, zr)], (0, t, 1), smat)
            self.face([(X0, Y0, ze), (X1, Y0, ze), (X1, ym, zr), (X0, ym, zr)], (0, -t, 1), smat)
            gh = (d / 2) * t                         # the ridge: ze + (d / 2 + o) t = z + (d / 2) t
            self.face([(X1, y, z), (X1, y + d, z), (X1, y + d / 2, z + gh)], (1, 0, 0), gmat)
            self.face([(X0, y + d, z), (X0, y, z), (X0, y + d / 2, z + gh)], (-1, 0, 0), gmat)
            self._ridge_caps(p, [((X0, ym, zr), (X1, ym, zr))])
            self._gable_trim(p, {"+x": ([(X1, Y0, ze), (X1, Y1, ze)], (X1, ym, zr), (1, 0, 0)),
                                 "-x": ([(X0, Y0, ze), (X0, Y1, ze)], (X0, ym, zr), (-1, 0, 0))})
            return
        if style.startswith("shed_"):
            hi = style[5:]
            if hi in ("+x", "-x"):
                hgt = (X1 - X0) * t
                xa, xb = (X0, X1) if hi == "+x" else (X1, X0)
                s = -1 if hi == "+x" else 1
                self.face([(xa, Y0, ze), (xa, Y1, ze), (xb, Y1, ze + hgt), (xb, Y0, ze + hgt)], (s * t, 0, 1), smat)
                self.face([(xb, Y0, ze), (xb, Y1, ze), (xb, Y1, ze + hgt), (xb, Y0, ze + hgt)], (-s, 0, 0), gmat)
                for yy, sy in ((Y0, -1), (Y1, 1)):
                    self.face([(xa, yy, ze), (xb, yy, ze), (xb, yy, ze + hgt)], (0, sy, 0), gmat)
            else:
                hgt = (Y1 - Y0) * t
                ya, yb = (Y0, Y1) if hi == "+y" else (Y1, Y0)
                s = -1 if hi == "+y" else 1
                self.face([(X0, ya, ze), (X1, ya, ze), (X1, yb, ze + hgt), (X0, yb, ze + hgt)], (0, s * t, 1), smat)
                self.face([(X0, yb, ze), (X1, yb, ze), (X1, yb, ze + hgt), (X0, yb, ze + hgt)], (0, -s, 0), gmat)
                for xx, sx in ((X0, -1), (X1, 1)):
                    self.face([(xx, ya, ze), (xx, yb, ze), (xx, yb, ze + hgt)], (sx, 0, 0), gmat)
            return
        raise GameError(f"roof style: hip, pyramid, gable_x, gable_y, shed_+x/-x/+y/-y or flat")

    def _ridge_caps(self, p, lines):
        """Capping along the ridge and the hips ("ridge_cap": {"mat", "w", "h"}): a light line that draws the roof's
        shape at game size, as the ridge tiles or flashing of a real roof do."""
        rc = p.get("ridge_cap")
        if not rc:
            return
        w, h = float(rc.get("w", 0.22)), float(rc.get("h", 0.12))
        for a, b in lines:
            self.beam({"from": list(a), "to": list(b), "w": w, "h": h, "offset": -h * 0.4,
                       "mat": rc.get("mat") or p.get("mat")})

    def _gable_trim(self, p, ends):
        """Bargeboards along both rakes and a finial post at the apex of each gable end.
        ends = {key: ([eave corner, eave corner], apex, outward direction)}."""
        bb, fin = p.get("bargeboard"), p.get("finial")
        if not bb and not fin:
            return
        keys = p.get("ends") or list(ends)
        for key in keys:
            if key not in ends:
                raise GameError(f"roof ends: {sorted(ends)} for this style, not {key!r}")
            corners, apex, out = ends[key]
            out = np.array(out, float)
            if bb:
                w, h = float(bb.get("w", 0.16)), float(bb.get("h", 0.35))
                for c in corners:
                    self.beam({"from": list(np.array(c) + out * w / 2), "to": list(np.array(apex) + out * w / 2),
                               "w": w, "h": h, "offset": -h * 0.85, "mat": bb.get("mat") or p.get("mat")})
            if fin:
                fh, fr = float(fin.get("h", 1.0)), float(fin.get("r", 0.09))
                ax, ay, az = np.array(apex) + out * 0.06
                fm = fin.get("mat") or p.get("mat")
                self.prism({"cx": ax, "cy": ay, "z": az - 0.15, "r": fr, "h": fh * 0.7, "sides": 6, "mat": fm})
                self.prism({"cx": ax, "cy": ay, "z": az - 0.15 + fh * 0.45, "r": fr * 1.8, "h": fh * 0.12,
                            "sides": 6, "mat": fm})
                self.cone({"cx": ax, "cy": ay, "z": az - 0.15 + fh * 0.7, "r": fr * 0.9, "h": fh * 0.3,
                           "sides": 6, "mat": fm})

    def beam(self, p):
        """A box between two points (bargeboards along a gable rake, brackets, posts, rails): "from" and "to"
        [x, y, z]; w = thickness across (horizontal, at right angles to it), h = depth (perpendicular to both);
        "offset" moves it along its depth axis (negative = downwards / inwards)."""
        a = np.array(p["from"], float)
        b = np.array(p["to"], float)
        d = b - a
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            raise GameError("beam: from and to are the same point")
        d /= L
        side = np.cross(d, UP)
        side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array([1.0, 0, 0])
        up = np.cross(side, d)
        if up[2] < 0:
            up = -up
        w, h = float(p.get("w", 0.15)), float(p.get("h", 0.3))
        off = float(p.get("offset", -h / 2))
        o = up * off
        cs = [side * (-w / 2) + o, side * (w / 2) + o, side * (w / 2) + up * h + o, side * (-w / 2) + up * h + o]
        A = [a + c for c in cs]
        B = [b + c for c in cs]
        mat = self.face_mat(p, "sides")
        for i in range(4):
            j = (i + 1) % 4
            n = np.cross(B[i] - A[i], A[j] - A[i])
            if np.dot(n, (A[i] + A[j]) / 2 - (a + o + up * h / 2)) < 0:
                n = -n
            self.face([A[i], A[j], B[j], B[i]], n, mat)
        self.face([A[0], A[1], A[2], A[3]], -d, mat)
        self.face([B[0], B[1], B[2], B[3]], d, mat)

    def ground(self, p):
        LX, LY = self.LX, self.LY
        self.face([(0, 0, 0), (0, LY, 0), (LX, LY, 0), (LX, 0, 0)], (0, 0, 1), self.face_mat(p, "top"))

    def blob(self, p):
        """A leaf clump or any rounded mass: an ellipsoid at cx, cy, z (its centre) with radii rx, ry, rz (or r),
        its surface roughened by "jitter" (0..0.4), normals pointing out from the centre (soft, round shading)."""
        cx, cy, cz = float(p["cx"]), float(p["cy"]), float(p.get("z", 0))
        r = float(p.get("r", 1.0))
        rx, ry, rz = float(p.get("rx", r)), float(p.get("ry", r)), float(p.get("rz", r))
        jitter = float(p.get("jitter", 0.15))
        level = int(p.get("detail", 2))
        seed = int(p.get("seed", 0))
        mat = self.face_mat(p, "sides")
        verts = [np.array(v, float) for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
        tris = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
        for _ in range(max(0, min(3, level))):
            cache, new = {}, []

            def mid(a, b):
                k = (min(a, b), max(a, b))
                if k not in cache:
                    m = verts[a] + verts[b]
                    verts.append(m / np.linalg.norm(m))
                    cache[k] = len(verts) - 1
                return cache[k]
            for a, b, c in tris:
                ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
                new += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
            tris = new
        V = np.array(verts)
        h = np.sin(V @ np.array([12.9898, 78.233, 37.719]) * 7.13 + seed * 1.618) * 43758.5453
        k = 1 + jitter * ((h - np.floor(h)) * 2 - 1)
        P = np.stack([cx + V[:, 0] * rx * k, cy + V[:, 1] * ry * k, cz + V[:, 2] * rz * k], 1)
        Nrm = np.stack([V[:, 0] / rx, V[:, 1] / ry, V[:, 2] / rz], 1)
        Nrm /= np.linalg.norm(Nrm, axis=1, keepdims=True)
        crown = p.get("crown")              # shade as part of a larger mass (a tree's crown): its normals mixed in
        if crown:
            cc = np.array(crown["c"], float)
            cr = np.array(crown["r"], float)
            mix = float(crown.get("mix", 0.7))
            Cn = (P - cc) / (cr * cr)
            Cn /= np.maximum(np.linalg.norm(Cn, axis=1, keepdims=True), 1e-9)
            Nrm = (1 - mix) * Nrm + mix * Cn
            Nrm /= np.maximum(np.linalg.norm(Nrm, axis=1, keepdims=True), 1e-9)
        for a, b, c in tris:
            pa, pb, pc = P[a], P[b], P[c]
            fn = np.cross(pb - pa, pc - pa)
            if np.linalg.norm(fn) < 1e-12:
                continue
            if np.dot(fn, Nrm[a] + Nrm[b] + Nrm[c]) < 0:
                pb, pc, b, c = pc, pb, c, b
                fn = -fn
            n = fn / np.linalg.norm(fn)
            right = np.cross(UP, n)
            right = right / np.linalg.norm(right) if np.linalg.norm(right) > 1e-6 else np.array([0, 1.0, 0])
            down = np.cross(n, right)
            uv = [(float(np.dot(q, right)), float(np.dot(q, down))) for q in (pa, pb, pc)]
            self.mesh.tri((tuple(pa), tuple(pb), tuple(pc)), (Nrm[a], Nrm[b], Nrm[c]), uv, mat, (1.0, 1.0))

    def quad(self, p):
        """A free sheet through four points [[x, y, z] x 4] in order (palm fronds, awnings, signs at an angle),
        seen from both sides."""
        pts = [np.array(q, float) for q in p["points"]]
        if len(pts) != 4:
            raise GameError("quad: four points [[x, y, z], ...]")
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        if np.linalg.norm(n) < 1e-9:
            raise GameError("quad: the points are on a line")
        mat = self.face_mat(p, "sides")
        w = float(np.linalg.norm(pts[1] - pts[0]))
        h = float(np.linalg.norm(pts[3] - pts[0]))
        uv = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
        n = n / np.linalg.norm(n)
        self.mesh.tri(tuple(map(tuple, (pts[0], pts[1], pts[2]))), (n, n, n), (uv[0], uv[1], uv[2]), mat, (w, h))
        self.mesh.tri(tuple(map(tuple, (pts[0], pts[2], pts[3]))), (n, n, n), (uv[0], uv[2], uv[3]), mat, (w, h))

    def patch(self, p):
        x, y, w, d = float(p["x"]), float(p["y"]), float(p["w"]), float(p["d"])
        z = float(p.get("z", 0.02))
        self.face([(x, y, z), (x, y + d, z), (x + w, y + d, z), (x + w, y, z)], (0, 0, 1), self.face_mat(p, "top"))

    def prop(self, p):
        raise GameError("SimCity 4 props go on the lot, not into the model",
                        "design_model_building(..., objects=[{\"prop\": ..., \"x\": m, \"z\": m}])")

    def build(self) -> tuple[Mesh, list[Material]]:
        kinds = {"box": self.box, "beam": self.beam, "panel": self.panel, "extrude": self.extrude, "prism": self.prism, "cylinder": self.prism,
                 "cone": self.cone, "pyramid": self.cone, "roof": self.roof, "ground": self.ground,
                 "patch": self.patch, "prop": self.prop, "blob": self.blob, "quad": self.quad}
        for i, part in enumerate(self.model.get("parts", [])):
            k = part.get("type")
            if k not in kinds:
                raise GameError(f"part {i}: type one of {sorted(kinds)}")
            try:
                kinds[k](part)
            except KeyError as e:
                raise GameError(f"part {i} ({k}): missing {e.args[0]!r}")
        sc = self.model.get("scale", 1.0)
        try:
            sc = float(sc)
        except (TypeError, ValueError):
            raise GameError("scale: a number (e.g. 1.6 to enlarge a prop as the game's own are)")
        if not 0.1 <= sc <= 10:
            raise GameError("scale: 0.1 .. 10")
        if sc != 1.0:                        # the whole model, textures with it (they are laid in metres)
            m = self.mesh
            m.p = [tuple(tuple(c * sc for c in v) for v in t) for t in m.p]
            m.uv = [tuple(tuple(c * sc for c in v) for v in t) for t in m.uv]
            m.ext = [tuple(c * sc for c in e) for e in m.ext]
        return self.mesh, self.mats


# ------------------------------------------------------------------------------------------ SimCity 4 model
# The game draws building models with the lighting baked into their textures (Maxis models are positions and UVs
# only), so each material's triangles are grouped by the light their face gets and each group gets a copy of the
# texture lit for it. The light is fixed to the building (as in SiMCP 3000's photo buildings).
LIGHT_SUN = np.array([-0.45, 0.62, 0.65])              # towards the light, in model axes (x west, y street, z up)
LIGHT_SUN = LIGHT_SUN / np.linalg.norm(LIGHT_SUN)
LIGHT_COLOR = np.array([1.00, 0.97, 0.92])             # the sunlit share, warm
LIGHT_AMBIENT = np.array([0.50, 0.52, 0.58])           # the sky's share, cool
LIGHT_STEPS = 12


def light_level(n) -> int:
    """0..LIGHT_STEPS: how much sun a face with normal n gets."""
    n = np.asarray(n, float)
    n = n / max(np.linalg.norm(n), 1e-9)
    return int(round(max(0.0, float(np.dot(n, LIGHT_SUN))) * LIGHT_STEPS))


def light_rgb(level: int, up: float = 0.0) -> np.ndarray:
    k = level / LIGHT_STEPS
    return np.clip(LIGHT_AMBIENT * (0.85 + 0.15 * up) + LIGHT_COLOR * k * 0.62, 0, 1.25)


def _pow2(v: int, lo: int = 8, hi: int = 512) -> int:
    p = lo
    while p < v and p < hi:
        p *= 2
    return p


def to_s3d(mesh: Mesh, mats: list[Material], lot: int, tex_iid0: int, lit: bool = True):
    """The game's model for a built mesh: (S3D bytes, [(FSH instance, FSH bytes)], (width, height, depth) in metres).
    Model axes: X = -(x - centre), Y = z, Z = y - centre (the lot centre at the origin, the +y side to the street);
    every triangle wound so its outward side is (b - a) x (c - a)."""
    from . import fsh, s3d
    P, N, UV, M, E = mesh.arrays()
    if not len(P):
        raise GameError("the model has no faces")
    c = lot * TILE_M / 2.0
    groups: dict = {}
    for t in range(len(P)):
        n = N[t].mean(axis=0)
        key = (int(M[t]), light_level(n) if lit else LIGHT_STEPS, round(float(n[2]) / max(np.linalg.norm(n), 1e-9), 1)
               if lit else 0.0)
        groups.setdefault(key, []).append(t)
    parts, textures = [], []
    for k, ((mi, level, up), tris) in enumerate(sorted(groups.items())):
        mat = mats[mi]
        tex = mat.tex.copy()
        if lit:
            tex[:, :, :3] = np.clip(tex[:, :, :3] * light_rgb(level, max(up, 0.0)), 0, 1)
        h, w = tex.shape[:2]
        img = Image.fromarray((tex * 255 + 0.5).astype(np.uint8), "RGBA")
        W, H = _pow2(w), _pow2(h)
        if (W, H) != (w, h):
            img = img.resize((W, H), Image.LANCZOS if (W < w or H < h) else Image.BILINEAR)
        iid = tex_iid0 + k
        textures.append((iid, fsh.write_argb(W, H, img.tobytes())))
        verts, idx = [], []
        for t in tris:
            u, v = mat.uv(UV[t][:, 0], UV[t][:, 1], tuple(E[t]))
            pts = [(-(float(p[0]) - c), float(p[2]), float(p[1]) - c) for p in P[t]]
            nn = N[t].mean(axis=0)
            want = np.array([-nn[0], nn[2], nn[1]])
            a, b, cc = (np.array(q) for q in pts)
            order = (0, 1, 2) if float(np.dot(np.cross(b - a, cc - a), want)) >= 0 else (0, 2, 1)
            base = len(verts)
            for j in order:
                verts.append(pts[j] + (float(u[j]), float(v[j])))
            idx.append((base, base + 1, base + 2))
        if len(verts) > 65535:
            raise GameError("too many triangles in one material (more than 21,845)")
        parts.append((verts, idx, iid, False))
    model = s3d.write(s3d.multi_mesh(parts))
    xs, ys, zs = P[:, :, 0], P[:, :, 1], P[:, :, 2]
    size = (float(xs.max() - xs.min()), float(zs.max() - max(zs.min(), 0.0)), float(ys.max() - ys.min()))
    return model, textures, size


def preview(mesh: Mesh, mats: list[Material], lot: int, rotation: int = 0, px_per_tile: int = 128) -> Image.Image:
    """A quick picture of the model (SiMCP 3000's isometric renderer; the game draws it with its own camera)."""
    return render3d.Renderer(mesh, mats, lot).render(rotation, px_per_tile, ss=2)


def icon(mesh: Mesh, mats: list[Material], lot: int) -> bytes:
    """A 44 x 44 menu icon from the preview."""
    import io
    im = preview(mesh, mats, lot, 0, 64)
    box = im.getbbox() or (0, 0, im.width, im.height)
    im = im.crop(box)
    k = 40.0 / max(im.width, im.height)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
    out.alpha_composite(im, ((44 - im.width) // 2, (44 - im.height) // 2))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
