"""Buildings drawn the way SimCity 4 draws its own: every view (five zooms, four rotations) is rendered with the
game's camera and light, and the picture is laid over the model's triangles that face the camera, in textures of at
most 256 x 256 pixels - as the Building Architect Tool (BAT) makes Maxis' models. Their texture coordinates are
exactly the camera's projection (measured on the game's landmarks: within half a pixel), and the light, the shading
and the shadows are in the picture; the game adds the building's shadow on the ground from the model's shape.

Camera and light, from public references and checked against the game's own models:
- BAT4Blender (github.com/memo33/BAT4Blender, carrying BAT4Max's SFCameraRigHD): an orthographic camera turned
  22.5 degrees, 60 / 55 / 50 / 45 / 45 degrees from the vertical at zooms 1 - 5, a 16 m cell 8 / 16 / 32 / 73 / 146
  pixels wide (the game's models: 0.383 / 0.765 / 1.53 / 3.49 / 6.985 px per metre - the same).
- BAT4Max's sun at (-474, -352, 575) in its scene for the south view, turning with the camera: 44 degrees high, from
  the viewer's left and a little in front.
- Light colours fitted to the game's models (1,118 models: walls facing left and right, tops; the white-walled ones
  for the levels): a warm sun, a blue ambient and a little light from the sky above; a white wall in the sun about
  (225, 210, 200), in the shade about (85, 82, 108).

Frames: the parts model's x (west), y (street), z (up) on the lot become the game's X = -(x - c), Y = z, Z = y - c
(c = the lot's centre); the model for view index r is turned s3d.view_turns(r) quarter turns, as the game expects
of a model per view (RKT1: it draws the model fixed to the camera and picks the index from the lot's facing and the
camera's rotation). In that turned frame the camera and the sun are fixed.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import fsh, s3d
from .render3d import TILE_M, _raster

CELL_PX = (8, 16, 32, 73, 146, 292)        # a 16 m cell's width on screen, zooms 1 - 5 (index 0 - 4); index 5 is
                                            # the game's closest view (UI zoom 6) at full resolution (BAT "HD")
PITCH_DEG = (60.0, 55.0, 50.0, 45.0, 45.0, 45.0)  # the camera from the vertical
YAW_DEG = 22.5
SUN = np.array([-474.0, 575.0, 352.0])      # towards the sun, in the turned model frame (X, Y up, Z)
SUN /= np.linalg.norm(SUN)
# light on a white surface = AMBIENT * sky seen + SKY * up * sky seen + SUN * cos * not shadowed (fitted to the game's
# white-walled models: lit walls facing left about (225, 210, 200), shaded walls facing right about (85, 82, 108))
AMBIENT_RGB = np.array([0.30, 0.30, 0.43], np.float32)
SKY_RGB = np.array([0.10, 0.11, 0.14], np.float32)
SUN_RGB = np.array([1.40, 1.29, 0.87], np.float32)
TEX = 256                                   # the largest texture (as the BAT's)
SS = 4                                      # supersampling per side
# sky directions for the sky's occlusion (elevation, azimuth); a set unchanged by quarter turns
SKY_DIRS = [(el, az) for el in (22.0, 52.0) for az in range(0, 360, 45)] + [(90.0, 0.0)]
SHADOW_RES = 14.0                           # sun shadow map, pixels per metre
SKY_RES = 5.0


def camera(z: int):
    """(right, down, view, pixels per metre) for zoom index z (0 - 4) in the turned model frame."""
    p, y = math.radians(PITCH_DEG[z]), math.radians(YAW_DEG)
    a, b, s, c = math.cos(y), math.sin(y), math.sin(p), math.cos(p)
    right = np.array([a, 0.0, -b])
    down = np.array([b * c, -s, a * c])
    view = np.array([-b * s, -c, -a * s])
    return right, down, view, CELL_PX[z] / (TILE_M * (a + b))


def _turn(v: np.ndarray, k: int) -> np.ndarray:
    """k quarter turns about the vertical axis, (x, z) -> (-z, x) each (negative k turns back)."""
    q = v.copy()
    for _ in range(k % 4):
        x, z = q[..., 0].copy(), q[..., 2].copy()
        q[..., 0], q[..., 2] = -z, x
    return q


def _vnoise(p: np.ndarray, scale: float, seed: float = 0.0) -> np.ndarray:
    """Smooth value noise in -1..1 at points p (n x 3, metres) with features about `scale` metres across."""
    q = p / scale + seed
    i = np.floor(q)
    f = q - i
    f = f * f * (3 - 2 * f)

    def h(o):
        c = i + o
        v = np.sin(c @ np.array([12.9898, 78.233, 37.719])) * 43758.5453
        return v - np.floor(v)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * h(np.array([dx, dy, dz], float))
    return out * 2 - 1


def weathering(pos0: np.ndarray, nrm0: np.ndarray, grain: np.ndarray) -> np.ndarray:
    """A brightness factor per point: blotches (0.4 and 1.6 m) and a little grime low on walls - in the unturned
    model frame, so every view shows the same weathering and nothing repeats like a tiled texture."""
    n = 0.55 * _vnoise(pos0, 0.4, 3.1) + 0.45 * _vnoise(pos0, 1.6, 7.7)
    wall = np.clip(1 - np.abs(nrm0[:, 1]) * 1.5, 0, 1)
    grime = 1 - 0.10 * wall * np.clip(1 - pos0[:, 1] / 0.9, 0, 1)
    return (1 + grain * n) * grime


def _pow2(v: int, lo: int = 8) -> int:
    p = lo
    while p < v:
        p *= 2
    return p


class Scene:
    """A built parts model (partmodel.Builder) ready to render: triangles in the game's model frame."""

    def __init__(self, mesh, mats, lot, night: bool = False, origin=None):
        """lot: cells a side, or [across the street, deep]: the model's origin is the lot's centre - or origin
        (x, y in the model's metres; a prop's centre)."""
        P, N, UV, M, E = mesh.arrays()
        if not len(P):
            raise ValueError("the model has no faces")
        lw, ld = (lot[0], lot[1]) if isinstance(lot, (list, tuple)) else (lot, lot)
        cx, cy = (float(origin[0]), float(origin[1])) if origin is not None else (lw * TILE_M / 2.0,
                                                                                  ld * TILE_M / 2.0)
        self.P0 = np.stack([-(P[..., 0] - cx), P[..., 2], P[..., 1] - cy], -1).astype(np.float64)
        self.N0 = np.stack([-N[..., 0], N[..., 2], N[..., 1]], -1).astype(np.float64)
        self.UV, self.M, self.E, self.mats = UV, M, E, mats
        self.lot = lot
        self.cutmats = {i for i, m in enumerate(mats) if m.cutout}
        self._sky = None
        self._sun: dict[int, object] = {}

    # ------------------------------------------------------------ helpers
    def _cut(self):
        if not self.cutmats:
            return None
        UV, M, E, mats, cutmats = self.UV, self.M, self.E, self.mats, self.cutmats

        def cut(t, b0, b1, b2):
            mi = int(M[t])
            if mi not in cutmats:
                return np.ones(b0.shape, bool)
            um = b0 * UV[t, 0, 0] + b1 * UV[t, 1, 0] + b2 * UV[t, 2, 0]
            vm = b0 * UV[t, 0, 1] + b1 * UV[t, 1, 1] + b2 * UV[t, 2, 1]
            u, v = mats[mi].uv(um.ravel(), vm.ravel(), E[t])
            return (mats[mi].sample(u, v)[:, 3] >= 0.5).reshape(b0.shape)
        return cut

    def _depth_map(self, P: np.ndarray, d: np.ndarray, res: float):
        """Visibility towards direction d: a function of points -> 0..1 (3 x 3 filtered)."""
        d = d / np.linalg.norm(d)
        a = np.cross(d, [0.0, 1.0, 0.0])
        a = a / np.linalg.norm(a) if np.linalg.norm(a) > 1e-6 else np.array([1.0, 0, 0])
        b = np.cross(d, a)
        pu, pv, pd = P @ a, P @ b, P @ d
        u0, v0 = pu.min() - 1, pv.min() - 1
        W = int((pu.max() - u0) * res) + 3
        H = int((pv.max() - v0) * res) + 3
        _t, zb, _b = _raster((pu - u0) * res, (pv - v0) * res, pd, W, H, cut=self._cut())
        bias = 1.5 / res

        def vis(points: np.ndarray) -> np.ndarray:
            u = (points @ a - u0) * res
            v = (points @ b - v0) * res
            dd = points @ d
            acc = np.zeros(len(points), np.float32)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    xi = np.clip((u + dx).astype(np.int32), 0, W - 1)
                    yi = np.clip((v + dy).astype(np.int32), 0, H - 1)
                    acc += (dd >= zb[yi, xi] - bias).astype(np.float32)
            return acc / 9.0
        return vis

    def sky_occlusion(self, points: np.ndarray, normals: np.ndarray) -> np.ndarray:
        """How much of the sky a point sees (1 = all of it), cosine-weighted over SKY_DIRS (unturned frame)."""
        if self._sky is None:
            dirs = []
            for el, az in SKY_DIRS:
                e, z = math.radians(el), math.radians(az)
                dirs.append(np.array([math.cos(e) * math.sin(z), math.sin(e), math.cos(e) * math.cos(z)]))
            self._sky = [(d, self._depth_map(self.P0, d, SKY_RES)) for d in dirs]
        num = np.zeros(len(points), np.float32)
        den = np.zeros(len(points), np.float32)
        for d, vis in self._sky:
            w = np.maximum(0.0, normals @ d).astype(np.float32)
            sel = w > 0
            if sel.any():
                v = np.zeros(len(points), np.float32)
                v[sel] = vis(points[sel])
                num += w * v
                den += w
        return np.where(den > 0, num / np.maximum(den, 1e-6), 1.0)

    # ------------------------------------------------------------ one view
    def render(self, z: int, r: int, ss: int = SS, light: bool = True):
        """The view as the game shows it: (RGBA image, its origin in pixels (x, y) in the camera's plane, the
        turned triangles, the ids of the triangles seen); self.night_img is then the view's night light layer (RGBA,
        transparent where nothing shines) or None."""
        P = _turn(self.P0, s3d.view_turns(r))
        N = _turn(self.N0, s3d.view_turns(r))
        right, down, view, k = camera(z)
        px, py = P @ right * k, P @ down * k
        ox, oy = math.floor(px.min()) - 2, math.floor(py.min()) - 2
        W, H = math.ceil(px.max()) - ox + 2, math.ceil(py.max()) - oy + 2
        tid, _zb, bc = _raster((px - ox) * ss, (py - oy) * ss, -(P @ view), W * ss, H * ss, cut=self._cut())
        cov = tid >= 0
        rgb = np.zeros((H * ss, W * ss, 3), np.float32)
        glow = None
        ys, xs = np.nonzero(cov)
        if len(ys):
            t = tid[ys, xs]
            b = bc[ys, xs]
            pos = b[:, 0:1] * P[t, 0] + b[:, 1:2] * P[t, 1] + b[:, 2:3] * P[t, 2]
            nrm = b[:, 0:1] * N[t, 0] + b[:, 1:2] * N[t, 1] + b[:, 2:3] * N[t, 2]
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
            back = (nrm @ view) > 0                       # a sheet seen from behind: light its other side
            nrm[back] *= -1
            um = b[:, 0] * self.UV[t, 0, 0] + b[:, 1] * self.UV[t, 1, 0] + b[:, 2] * self.UV[t, 2, 0]
            vm = b[:, 0] * self.UV[t, 0, 1] + b[:, 1] * self.UV[t, 1, 1] + b[:, 2] * self.UV[t, 2, 1]
            base = np.zeros((len(t), 3), np.float32)
            mi = self.M[t]
            for m in np.unique(mi):
                sel = mi == m
                mat = self.mats[int(m)]
                ext = self.E[t[sel]]
                u, v = mat.uv(um[sel], vm[sel], (ext[:, 0], ext[:, 1]))
                base[sel] = mat.sample(u, v)[:, :3]
                gm = getattr(mat, "glow", None)
                if gm is not None:
                    if glow is None:
                        glow = np.zeros((H * ss, W * ss, 4), np.float32)
                    gl = gm.sample(u, v)
                    glow[ys[sel], xs[sel]] = np.concatenate([gl[:, :3] * gl[:, 3:4], gl[:, 3:4]], -1)
            pos0 = b[:, 0:1] * self.P0[t, 0] + b[:, 1:2] * self.P0[t, 1] + b[:, 2:3] * self.P0[t, 2]
            n0 = _turn(nrm, -s3d.view_turns(r))
            grain = np.array([getattr(self.mats[int(m)], "grain", 0.0) for m in range(len(self.mats))],
                             np.float32)[mi]
            base = np.clip(base * weathering(pos0, n0, grain)[:, None], 0, 1)
            if light:
                if r not in self._sun:
                    self._sun[r] = self._depth_map(P, SUN, SHADOW_RES)
                cosl = (nrm @ SUN).astype(np.float32)
                wrap = np.array([getattr(self.mats[int(m)], "wrap", 0.0) for m in range(len(self.mats))],
                                np.float32)[mi]
                sun = np.clip((cosl + wrap) / (1 + wrap), 0, 1)     # wrap: light through leaves
                lit = sun > 0
                if lit.any():
                    sun[lit] *= self._sun[r](pos[lit] + nrm[lit] * 0.04)
                ao = self.sky_occlusion(pos0 + n0 * 0.05, n0)
                up = np.maximum(nrm[:, 1], 0).astype(np.float32)
                amb = AMBIENT_RGB[None, :] * ao[:, None] + SKY_RGB[None, :] * (ao * up)[:, None]
                col = base * (amb + SUN_RGB[None, :] * sun[:, None])
            else:
                col = base
            rgb[ys, xs] = np.clip(col, 0, 1)
        # box filter to the game's pixels (premultiplied), then un-premultiply
        a = cov.astype(np.float32).reshape(H, ss, W, ss).mean(axis=(1, 3))
        c = (rgb * cov[..., None]).reshape(H, ss, W, ss, 3).mean(axis=(1, 3))
        c = np.where(a[..., None] > 0, c / np.maximum(a[..., None], 1e-6), 0)
        img = np.concatenate([c, a[..., None]], -1)
        self.night_img = None
        if glow is not None:                    # premultiplied light, filtered like the picture
            g = glow.reshape(H, ss, W, ss, 4).mean(axis=(1, 3))
            ga = g[..., 3:4]
            self.night_img = np.concatenate([np.where(ga > 0, g[..., :3] / np.maximum(ga, 1e-6), 0), ga], -1)
        seen = np.unique(tid[tid >= 0])
        return img, (ox, oy), P, seen

    def picture(self, z: int = 4, r: int = 0) -> Image.Image:
        """A view as an RGBA picture (what the game shows, on a transparent background)."""
        img, _o, _P, _s = self.render(z, r)
        return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------------------------------ the game's model
def _clip(poly: list, x0: float, y0: float, x1: float, y1: float) -> list:
    """Sutherland-Hodgman: a convex polygon of (sx, sy, X, Y, Z) clipped to a screen rectangle."""
    for axis, lim, keep_ge in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        out = []
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            ina = a[axis] >= lim if keep_ge else a[axis] <= lim
            inb = b[axis] >= lim if keep_ge else b[axis] <= lim
            if ina:
                out.append(a)
            if ina != inb:
                t = (lim - a[axis]) / (b[axis] - a[axis])
                out.append(tuple(a[j] + t * (b[j] - a[j]) for j in range(5)))
        poly = out
        if len(poly) < 3:
            return []
    return poly


def _bleed(rgba: np.ndarray, steps: int = 4) -> np.ndarray:
    """Spread colours into the transparent texels around them (alpha stays 0) so filtering never pulls in black."""
    out = rgba.copy()
    filled = out[..., 3] > 0
    for _ in range(steps):
        if filled.all():
            break
        acc = np.zeros(out.shape[:2] + (3,), np.float32)
        cnt = np.zeros(out.shape[:2], np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(np.roll(out[..., :3], dy, 0), dx, 1)
            ok = np.roll(np.roll(filled, dy, 0), dx, 1)
            acc += src * ok[..., None]
            cnt += ok
        grow = (~filled) & (cnt > 0)
        out[grow, :3] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
    return out


NIGHT = 0x8000                              # a texture's night light layer: its instance + 0x8000 (the game's own)


def tex_instance(base: int, z: int, r: int, n: int) -> int:
    """Texture n of the view (zoom z, rotation r): base + (n // 16) * 0x1000 + z * 0x100 + r * 0x10 + n % 16
    (+ NIGHT for its night light layer)."""
    if n >= 128:
        raise ValueError("more than 128 textures in one view")
    return base + (n >> 4) * 0x1000 + z * 0x100 + r * 0x10 + (n & 15)


SHELL_TRIANGLES = 900                       # more seen triangles than this: the picture goes on a shell


def _octagon(pts2: np.ndarray, margin: float) -> np.ndarray:
    """The octagon (8 x 2) around points in the horizontal plane: the tightest one with sides at 45 degrees."""
    angs = np.radians(np.arange(8) * 45.0)
    dirs = np.stack([np.cos(angs), np.sin(angs)], 1)
    h = (pts2 @ dirs.T).max(0) + margin
    out = []
    for i in range(8):
        j = (i + 1) % 8
        A = np.array([dirs[i], dirs[j]])
        out.append(np.linalg.solve(A, [h[i], h[j]]))
    return np.array(out)


def shell(P: np.ndarray, bands: int = 5, margin: float = 0.15) -> np.ndarray:
    """A low-poly shell around a dense model (the Building Architect's LOD): stacked octagonal bands that follow its
    silhouette, as triangles (n x 3 x 3) in the model's frame (y up). The picture is projected onto it, so any shape
    covering every seen pixel draws the same; the game also casts the model's shadow from it."""
    V = P.reshape(-1, 3)
    y0, y1 = float(V[:, 1].min()), float(V[:, 1].max())
    edges = np.linspace(y0, y1, bands + 1)
    step = (y1 - y0) / bands
    tris = []
    for b in range(bands):                       # a prism per band: the octagon around the points in it
        sel = V[(V[:, 1] >= edges[b] - step * 0.5) & (V[:, 1] <= edges[b + 1] + step * 0.5)]
        o = _octagon((sel if len(sel) else V)[:, [0, 2]], margin)
        lo_y = edges[b] - (margin if b == 0 else 0)
        hi_y = edges[b + 1] + (margin if b == bands - 1 else 0)
        lo = [np.array([x, lo_y, zz]) for x, zz in o]
        hi = [np.array([x, hi_y, zz]) for x, zz in o]
        centre = np.array([o[:, 0].mean(), (lo_y + hi_y) / 2, o[:, 1].mean()])
        band = []
        for i in range(8):
            j = (i + 1) % 8
            band += [(lo[i], lo[j], hi[j]), (lo[i], hi[j], hi[i])]
        for i in range(1, 7):                    # its top (a ledge where the band above is narrower)
            band.append((hi[0], hi[i], hi[i + 1]))
        for a, b_, c in band:                    # every triangle wound to face outwards
            n = np.cross(b_ - a, c - a)
            tris.append((a, b_, c) if np.dot(n, (a + b_ + c) / 3 - centre) >= 0 else (a, c, b_))
    return np.array(tris)


def bake_view(scene: Scene, z: int, r: int, tex_base: int, name: bytes = b"SiMCP", lod: str = "auto"):
    """One view's model and textures: (S3D bytes, [(FSH instance, FSH bytes)]). lod: "mesh" lays the picture on
    the model's own triangles that are seen, "shell" on a low-poly shell around it (trees, dense props: the game
    does not draw flora models with thousands of vertices), "auto" a shell above SHELL_TRIANGLES seen triangles."""
    img, (ox, oy), P, seen = scene.render(z, r)
    shelled = lod == "shell" or (lod == "auto" and len(seen) > SHELL_TRIANGLES)
    if shelled:
        P = shell(P)
        seen = np.arange(len(P))
    night = scene.night_img
    H, W = img.shape[:2]
    right, down, view, k = camera(z)
    alpha = img[..., 3] > 0.04                  # partly covered pixels count: the triangles draw the outline
    rgba = np.concatenate([img[..., :3], alpha[..., None].astype(np.float32)], -1)
    # tiles of the picture
    tiles = []
    for ty in range(0, H, TEX):
        for tx in range(0, W, TEX):
            tw, th = min(TEX, W - tx), min(TEX, H - ty)
            if alpha[ty:ty + th, tx:tx + tw].any():
                tiles.append((tx, ty, tw, th))
    meshes = {i: ([], []) for i in range(len(tiles))}
    for t in seen:
        tri = P[t]
        a_, b_, c_ = tri
        nrm = np.cross(b_ - a_, c_ - a_)
        if np.dot(nrm, -view) < 0:              # wound to face the camera (the game culls the other side)
            if shelled:
                continue                         # a shell's back faces are hidden behind its front
            tri = tri[[0, 2, 1]]
        poly0 = [(float(q @ right * k - ox), float(q @ down * k - oy), float(q[0]), float(q[1]), float(q[2]))
                 for q in tri]
        xs_ = [q[0] for q in poly0]
        ys_ = [q[1] for q in poly0]
        for i, (tx, ty, tw, th) in enumerate(tiles):
            if max(xs_) < tx or min(xs_) > tx + tw or max(ys_) < ty or min(ys_) > ty + th:
                continue
            poly = _clip(poly0, tx, ty, tx + tw, ty + th)
            if len(poly) < 3:
                continue
            TW, TH = _pow2(tw), _pow2(th)
            verts, idx = meshes[i]
            base = len(verts)
            for q in poly:
                verts.append((q[2], q[3], q[4], (q[0] - tx) / TW, (q[1] - ty) / TH))
            for j in range(1, len(poly) - 1):
                idx.append((base, base + j, base + j + 1))
    m = s3d.Model()
    textures = []
    n = 0
    for i, (tx, ty, tw, th) in enumerate(tiles):
        verts, idx = meshes[i]
        if not idx:
            continue
        if len(verts) > 65535:
            raise ValueError("too many vertices in one texture tile")
        TW, TH = _pow2(tw), _pow2(th)
        tile = np.zeros((TH, TW, 4), np.float32)
        tile[:th, :tw] = rgba[ty:ty + th, tx:tx + tw]
        tile = _bleed(tile)
        iid = tex_instance(tex_base, z, r, n)
        data = (np.clip(tile, 0, 1) * 255 + 0.5).astype(np.uint8)
        textures.append((iid, fsh.write_dxt(data, fsh.CODE_DXT1)))
        if night is not None and (night[ty:ty + th, tx:tx + tw, 3] > 0.02).any():
            nt = np.zeros((TH, TW, 4), np.float32)
            nt[:th, :tw] = night[ty:ty + th, tx:tx + tw]
            nd = (np.clip(nt, 0, 1) * 255 + 0.5).astype(np.uint8)
            textures.append((iid + NIGHT, fsh.write_dxt(nd, fsh.CODE_DXT3)))
        k_ = len(m.verts)
        m.verts.append(s3d.VertBlock(0, s3d.FMT_XYZ_UV, b"".join(
            np.array(v, np.float32).tobytes() for v in verts)))
        m.indices.append(s3d.IndexBlock(0, 2, np.array(idx, np.uint16).tobytes()))
        m.prims.append([(0, 0, 3 * len(idx))])
        m.mats.append(s3d.Material(flags=0xAB, alpha_func=4, depth_func=3, src_blend=1, dst_blend=0,
                                   alpha_threshold=0x7FFF,
                                   textures=[s3d.Texture(iid, (3, 3), (0, 0), 0, 0, b"\0")]))
        m.meshes.append(s3d.Mesh(name + b"_Z%dR%d_%d\0" % (z + 1, r, n), 0, [(k_, k_, k_, k_)]))
        n += 1
    if not m.meshes:
        raise ValueError("nothing of the model is seen in zoom %d, rotation %d" % (z + 1, r))
    return s3d.write(m), textures


def bake(scene: Scene, model_base: int, tex_base: int, name: bytes = b"SiMCP", lod: str = "auto"):
    """Every view: ([(model instance, S3D bytes)] for RKT1 at model_base + z * 0x100 + r * 0x10,
    [(FSH instance, FSH bytes)])."""
    models, textures = [], []
    for z in range(5):
        for r in range(4):
            mb, tx = bake_view(scene, z, r, tex_base, name, lod)
            models.append((model_base + z * 0x100 + r * 0x10, mb))
            textures += tx
    return models, textures


def views_picture(scene: Scene, z: int = 4, bg=(98, 128, 72)) -> Image.Image:
    """The four rotations side by side at zoom z (index; 4 = the closest), on a lawn-coloured ground."""
    ims = [scene.picture(z, r) for r in range(4)]
    w = sum(im.width for im in ims) + 10 * 3
    h = max(im.height for im in ims)
    out = Image.new("RGBA", (w, h), bg + (255,))
    x = 0
    for im in ims:
        out.alpha_composite(im, (x, h - im.height))
        x += im.width + 10
    return out


def icon(scene: Scene) -> bytes:
    """A 44 x 44 menu icon from the closest view."""
    import io
    im = scene.picture(4, 0)
    box = im.getbbox() or (0, 0, im.width, im.height)
    im = im.crop(box)
    k = 42.0 / max(im.width, im.height)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
    out.alpha_composite(im, ((44 - im.width) // 2, (44 - im.height) // 2))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
