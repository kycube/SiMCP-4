"""(From SiMCP 3000; in SiMCP 4 it gives a quick preview of a parts model without the game - the game draws the
real model itself, with its own camera and lights: check there with snapshot.)

A small software renderer that draws a textured 3D model the way SimCity 3000 draws buildings - the game's
2:1 isometric projection, its four 90-degree rotations, the Building Architect's "Preview" lights (BATConfig.ini) -
so photo-built buildings can be written straight to the game's sprite format (datwriter.py) without the Building
Architect. Pure numpy: z-buffer, perspective-free (orthographic) texture mapping, smooth or flat normals, a shadow
map, and supersampled anti-aliasing.

Units: metres. The lot is a square of `lot` tiles, TILE_M metres each, x and y from 0 to lot * TILE_M, z up.
Projection (rotation 0, the camera looks from +x, +y, above; verified against the Architect's renders: same sprite
sizes and silhouettes within a pixel in all four rotations): a point moves right on screen with y - x and down with
x + y, up with z; one tile is P px wide and P / 2 px high on the ground, one tile of height rises P / 2 px. Depth
(nearer = larger) = x + y + z. Rotation r turns the model r quarter turns counter-clockwise about the lot centre (as
the Architect's Rotate). The lights are fixed to the building (compass directions), as in the Architect's renders.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

TILE_M = 16.0                     # metres per city tile (one Architect cell = 2 m)
# BATConfig.ini [Lights] Preview*: faces turned along x get the warm "north/south" light, along y the blue
# "east/west" light, tops the grey top light; measured on Architect renders: colour = texture * light / 150
LIGHT_X = np.array([190, 174, 164], np.float32)
LIGHT_Y = np.array([71, 71, 91], np.float32)
LIGHT_TOP = np.array([141, 141, 141], np.float32)
LIGHT_DIV = 150.0
# light sets {x-facing, y-facing, top}: "architect" = the Architect's Preview lights (above; Architect-made buildings
# look like this); "game" = matched to the game's own Maxis sprites, whose shaded side is far softer (right walls
# about 0.55 - 0.65 of the left ones in residential sprites, slightly cool) - the default for photo-built buildings
LIGHT_SETS = {
    "architect": (LIGHT_X, LIGHT_Y, LIGHT_TOP),
    "game": (np.array([186, 176, 166], np.float32), np.array([112, 114, 136], np.float32),
             np.array([150, 150, 150], np.float32)),
}
SUN = np.array([0.55, -0.25, 1.0], np.float32)        # shadow-casting direction (towards the light): from +x, above
SHADOW = 0.62                                          # light kept in shadow (warm and top terms)


class Material:
    """A surface: an RGB(A) texture (float 0..1) laid out in metres (tile mode, `size_m` = the texture's size in
    metres) or stretched over the whole face (fit mode), or a plain colour. Alpha < 0.5 = see-through (cut-out)."""

    def __init__(self, name: str, image: Image.Image | None = None, color=None, size_m=(2.0, 2.0),
                 fit: bool = False, cutout: bool = False):
        self.name = name
        self.fit = fit
        self.size_m = (float(size_m[0]), float(size_m[1]))
        if image is None:
            c = np.array(color if color is not None else (180, 180, 180), np.float32) / 255.0
            self.tex = np.ones((2, 2, 4), np.float32)
            self.tex[:, :, :3] = c[:3]
            self.cutout = False
        else:
            self.tex = np.asarray(image.convert("RGBA"), np.float32) / 255.0
            self.cutout = cutout or bool((self.tex[:, :, 3] < 0.5).any())

    def sample(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Bilinear sample at texture coordinates (u right, v down; 1.0 = one texture width / height), repeating."""
        h, w = self.tex.shape[:2]
        x = (u * w - 0.5) % w
        y = (v * h - 0.5) % h
        x0 = np.floor(x).astype(np.int32) % w          # (a float % w can round up to exactly w)
        y0 = np.floor(y).astype(np.int32) % h
        fx = (x - x0)[:, None]
        fy = (y - y0)[:, None]
        x1 = (x0 + 1) % w
        y1 = (y0 + 1) % h
        t = self.tex
        return ((t[y0, x0] * (1 - fx) + t[y0, x1] * fx) * (1 - fy) + (t[y1, x0] * (1 - fx) + t[y1, x1] * fx) * fy)

    def uv(self, um: np.ndarray, vm: np.ndarray, extent=(1.0, 1.0)) -> tuple[np.ndarray, np.ndarray]:
        """Metres on the face (u right, v down from the face's top) -> texture coordinates."""
        if self.fit:
            return um / np.maximum(extent[0], 1e-6), vm / np.maximum(extent[1], 1e-6)
        return um / self.size_m[0], vm / self.size_m[1]


class Mesh:
    """Triangles with per-vertex positions, normals and face coordinates in metres (u, v), a material index and the
    face's extent (for fit-mode materials)."""

    def __init__(self):
        self.p: list = []
        self.n: list = []
        self.uv: list = []
        self.mat: list = []
        self.ext: list = []
        self.billboards: list = []          # (image RGBA, base point (x, y, z), metres per pixel)

    def tri(self, p, n, uv, mat: int, ext=(1.0, 1.0)):
        self.p.append(p)
        self.n.append(n)
        self.uv.append(uv)
        self.mat.append(mat)
        self.ext.append(ext)

    def quad(self, a, b, c, d, n, uva, uvb, uvc, uvd, mat: int, ext=(1.0, 1.0), normals=None):
        na = nb = nc = nd = n
        if normals is not None:
            na, nb, nc, nd = normals
        self.tri((a, b, c), (na, nb, nc), (uva, uvb, uvc), mat, ext)
        self.tri((a, c, d), (na, nc, nd), (uva, uvc, uvd), mat, ext)

    def arrays(self):
        return (np.array(self.p, np.float32).reshape(-1, 3, 3), np.array(self.n, np.float32).reshape(-1, 3, 3),
                np.array(self.uv, np.float32).reshape(-1, 3, 2), np.array(self.mat, np.int32),
                np.array(self.ext, np.float32).reshape(-1, 2))


def _rotate(pts: np.ndarray, r: int, L: float) -> np.ndarray:
    """r quarter turns counter-clockwise about the lot centre: (x, y) -> (L - y, x) per turn."""
    q = pts.copy()
    for _ in range(r % 4):
        x, y = q[..., 0].copy(), q[..., 1].copy()
        q[..., 0], q[..., 1] = L - y, x
    return q


def _rotate_n(n: np.ndarray, r: int) -> np.ndarray:
    q = n.copy()
    for _ in range(r % 4):
        x, y = q[..., 0].copy(), q[..., 1].copy()
        q[..., 0], q[..., 1] = -y, x
    return q


def _raster(sx, sy, depth, W, H, attrs=None, cut=None):
    """Z-buffer rasterisation of triangles given in pixel coordinates (pixel centres at +0.5). Returns the
    triangle-id buffer, the depth buffer and the barycentric buffers. cut(t, b0, b1, b2) -> keep mask per pixel
    (cut-out materials)."""
    zb = np.full((H, W), -np.inf, np.float32)
    tid = np.full((H, W), -1, np.int32)
    bc = np.zeros((H, W, 3), np.float32)
    for t in range(sx.shape[0]):
        x0, x1, x2 = sx[t]
        y0, y1, y2 = sy[t]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        xmin = max(int(math.floor(min(x0, x1, x2))), 0)
        xmax = min(int(math.ceil(max(x0, x1, x2))), W - 1)
        ymin = max(int(math.floor(min(y0, y1, y2))), 0)
        ymax = min(int(math.ceil(max(y0, y1, y2))), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        gx, gy = np.meshgrid(np.arange(xmin, xmax + 1, dtype=np.float32) + 0.5,
                             np.arange(ymin, ymax + 1, dtype=np.float32) + 0.5)
        w0 = ((x1 - gx) * (y2 - gy) - (x2 - gx) * (y1 - gy)) / area
        w1 = ((x2 - gx) * (y0 - gy) - (x0 - gx) * (y2 - gy)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        d = w0 * depth[t, 0] + w1 * depth[t, 1] + w2 * depth[t, 2]
        sub = zb[ymin:ymax + 1, xmin:xmax + 1]
        m = inside & (d > sub)
        if cut is not None and m.any():
            m &= cut(t, w0, w1, w2)
        if not m.any():
            continue
        sub[m] = d[m]
        tid[ymin:ymax + 1, xmin:xmax + 1][m] = t
        b = bc[ymin:ymax + 1, xmin:xmax + 1]
        b[..., 0][m] = w0[m]
        b[..., 1][m] = w1[m]
        b[..., 2][m] = w2[m]
    return tid, zb, bc


class Renderer:
    def __init__(self, mesh: Mesh, materials: list[Material], lot: int, shadows: bool = True,
                 lights: str = "game"):
        if lights not in LIGHT_SETS:
            raise ValueError(f"lights: one of {list(LIGHT_SETS)}")
        self.lights = LIGHT_SETS[lights]
        self.mesh = mesh
        self.mats = materials
        self.lot = lot
        self.L = lot * TILE_M
        self.shadows = shadows
        self.P, self.N, self.UV, self.M, self.EXT = mesh.arrays()

    # ---------------------------------------------------------------- projection
    def project(self, pts: np.ndarray, px_per_tile: float):
        k = px_per_tile / TILE_M
        sx = (pts[..., 1] - pts[..., 0]) * k / 2 + self.L * k / 2
        sy = (pts[..., 0] + pts[..., 1]) * k / 4 - pts[..., 2] * k / 2
        return sx, sy

    def _cut(self, uvw):
        """Cut-out test for triangles whose material has see-through texels."""
        cutmats = {i for i, m in enumerate(self.mats) if m.cutout}
        if not cutmats:
            return None
        UV, M, EXT = self.UV, self.M, self.EXT

        def cut(t, b0, b1, b2):
            mi = int(M[t])
            if mi not in cutmats:
                return np.ones(b0.shape, bool)
            mat = self.mats[mi]
            um = b0 * UV[t, 0, 0] + b1 * UV[t, 1, 0] + b2 * UV[t, 2, 0]
            vm = b0 * UV[t, 0, 1] + b1 * UV[t, 1, 1] + b2 * UV[t, 2, 1]
            u, v = mat.uv(um.ravel(), vm.ravel(), EXT[t])
            return (mat.sample(u, v)[:, 3] >= 0.5).reshape(b0.shape)
        return cut

    # ---------------------------------------------------------------- shadow map
    def _shadow_fn(self, P: np.ndarray):
        s = SUN / np.linalg.norm(SUN)
        a = np.cross(s, [0, 0, 1.0])
        a /= np.linalg.norm(a)
        b = np.cross(s, a)
        res = 12.0                                    # shadow-map pixels per metre
        pu, pv, pd = P @ a, P @ b, P @ s
        umin, vmin = pu.min() - 1, pv.min() - 1
        W = int((pu.max() - umin) * res) + 3
        H = int((pv.max() - vmin) * res) + 3
        sxs, sys_ = (pu - umin) * res, (pv - vmin) * res
        _tid, zb, _bc = _raster(sxs, sys_, pd, W, H, cut=self._cut(None))

        def lit(points: np.ndarray) -> np.ndarray:
            u = (points @ a - umin) * res
            v = (points @ b - vmin) * res
            d = points @ s
            acc = np.zeros(len(points), np.float32)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    xi = np.clip((u + dx).astype(np.int32), 0, W - 1)
                    yi = np.clip((v + dy).astype(np.int32), 0, H - 1)
                    occ = zb[yi, xi]
                    acc += (d >= occ - 0.25).astype(np.float32)
            return acc / 9.0
        return lit

    # ---------------------------------------------------------------- render one rotation
    def render(self, rotation: int, px_per_tile: float, ss: int = 4) -> Image.Image:
        """The building at one rotation as an RGBA image `lot * px_per_tile` wide whose bottom row is the lot's
        bottom corner (the sprite layout the game expects), anti-aliased by `ss` x `ss` supersampling."""
        P = _rotate(self.P, rotation, self.L)
        N = _rotate_n(self.N, rotation)
        Pss = px_per_tile * ss
        sx, sy = self.project(P, Pss)
        bottom = self.L * Pss / TILE_M / 2               # y of the lot's bottom corner
        top = min(float(sy.min()), 0.0)
        bscale = Pss / 256.0                             # prop bitmaps: 32 px per 2 m cell = 256 px per tile
        for bb in self.mesh.billboards:
            c = _rotate(np.array(bb["center"], np.float32), rotation, self.L)
            _bx, by = self.project(c, Pss)
            img = bb["views"][rotation % len(bb["views"])]
            top = min(top, float(by) - img.height * bscale / 2)
        H = int(math.ceil(bottom - top))
        W = int(round(self.lot * Pss))
        sy = sy - top
        depth = P[..., 0] + P[..., 1] + P[..., 2]
        tid, zb, bc = _raster(sx, sy, depth, W, H, cut=self._cut(None))
        rgb = np.zeros((H, W, 3), np.float32)
        cov = tid >= 0
        ys, xs = np.nonzero(cov)
        if len(ys):
            t = tid[ys, xs]
            b = bc[ys, xs]
            # light and shadows are fixed to the building (the Architect's lights are compass directions: they
            # turn with the model), so shading uses the unrotated positions and normals
            P0, N0 = self.P, self.N
            pos = (b[:, 0:1] * P0[t, 0] + b[:, 1:2] * P0[t, 1] + b[:, 2:3] * P0[t, 2])
            nrm = (b[:, 0:1] * N0[t, 0] + b[:, 1:2] * N0[t, 1] + b[:, 2:3] * N0[t, 2])
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-6)
            um = b[:, 0] * self.UV[t, 0, 0] + b[:, 1] * self.UV[t, 1, 0] + b[:, 2] * self.UV[t, 2, 0]
            vm = b[:, 0] * self.UV[t, 0, 1] + b[:, 1] * self.UV[t, 1, 1] + b[:, 2] * self.UV[t, 2, 1]
            base = np.zeros((len(t), 3), np.float32)
            mi = self.M[t]
            for k in np.unique(mi):
                sel = mi == k
                mat = self.mats[int(k)]
                ext = self.EXT[t[sel]]
                u, v = mat.uv(um[sel], vm[sel], (ext[:, 0], ext[:, 1]))
                base[sel] = mat.sample(u, v)[:, :3]
            # Lambert from lights along +-x (warm), +-y (blue) and the top (measured against Architect renders)
            lx, ly, lt = self.lights
            nx, ny, nz = np.abs(nrm[:, 0]), np.abs(nrm[:, 1]), nrm[:, 2]
            warm = nx[:, None] * lx + np.maximum(nz, 0)[:, None] * lt
            cool = ny[:, None] * ly
            if self.shadows:
                if getattr(self, "_lit", None) is None:
                    self._lit = self._shadow_fn(self.P)          # same for every rotation (lights turn with the model)
                lit = self._lit(pos + nrm * 0.05)
                warm = warm * (SHADOW + (1 - SHADOW) * lit)[:, None]
            col = base * (warm + cool) / LIGHT_DIV
            rgb[ys, xs] = np.clip(col, 0, 1)
        # billboards (stock props): their bitmap centre at the projected centre point; depth of a camera-facing
        # plane through that point, rising with height
        kk = Pss / TILE_M
        for bb in self.mesh.billboards:
            c = _rotate(np.array(bb["center"], np.float32), rotation, self.L)
            bx, by = self.project(c, Pss)
            by -= top
            img = bb["views"][rotation % len(bb["views"])]
            im = img.resize((max(1, int(round(img.width * bscale))), max(1, int(round(img.height * bscale)))),
                            Image.NEAREST)
            a = np.asarray(im, np.float32) / 255.0
            ox, oy = int(round(bx - im.width / 2)), int(round(by - im.height / 2))
            for yy in range(im.height):
                Y = oy + yy
                if not 0 <= Y < H:
                    continue
                zrow = float(c[0] + c[1] + c[2]) + (by - (Y + 0.5)) / (kk / 2)
                xs_ = np.arange(im.width) + ox
                ok = (xs_ >= 0) & (xs_ < W) & (a[yy, :, 3] >= 0.5)
                xs_ = xs_[ok]
                if not len(xs_):
                    continue
                nearer = zrow > zb[Y, xs_]
                xs_ = xs_[nearer]
                rgb[Y, xs_] = a[yy, ok][nearer, :3]
                zb[Y, xs_] = zrow
                cov[Y, xs_] = True
        rgba = np.concatenate([rgb * cov[..., None], cov[..., None].astype(np.float32)], axis=2)
        out = Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA")
        return out


def downsample(img: Image.Image, factor: int) -> Image.Image:
    """Box-filter a premultiplied RGBA image by an integer factor, keeping the bottom row aligned, and
    un-premultiply. Height is padded at the top to a multiple of the factor."""
    w, h = img.size
    H = int(math.ceil(h / factor) * factor)
    pad = Image.new("RGBA", (w, H), (0, 0, 0, 0))
    pad.paste(img, (0, H - h))
    a = np.asarray(pad, np.float32).reshape(H // factor, factor, w // factor, factor, 4).mean(axis=(1, 3))
    alpha = a[..., 3:4]
    rgb = np.where(alpha > 0, a[..., :3] / np.maximum(alpha, 1e-6) * 255.0, 0)
    out = np.concatenate([rgb, alpha], axis=2)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def crop_top(img: Image.Image) -> Image.Image:
    """Drop empty rows at the top (the bottom row stays the lot's bottom corner)."""
    a = np.asarray(img)[..., 3]
    rows = np.flatnonzero((a >= 128).any(axis=1))
    return img.crop((0, int(rows[0]), img.width, img.height)) if len(rows) else img.crop((0, img.height - 1, img.width, img.height))


def sprite_set(renderer: Renderer, ss: int = 4, native_zoom5: bool = True) -> dict[tuple[int, int], Image.Image]:
    """All game frames {(zoom, rotation): image}: zoom z is 8 * 2^(z-1) px per tile (zoom 5 = 128). Rendered once per
    rotation at zoom 5 x ss and box-filtered down to every zoom."""
    out = {}
    for r in range(4):
        big = renderer.render(r, 128, ss)
        for z in range(1, 6):
            if z == 5 and not native_zoom5:
                continue
            f = ss * 2 ** (5 - z)
            out[(z, r)] = crop_top(downsample(big, f))
    return out
