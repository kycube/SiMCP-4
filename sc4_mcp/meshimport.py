"""Agent-supplied geometry: Wavefront OBJ models (with their MTL materials and PNG / JPEG textures) as S3D models.

An OBJ's faces become triangles (polygons as fans), grouped by material: one mesh per material, each with its own
FSH texture (the MTL's map_Kd picture, scaled to a power of two up to 512, or its Kd colour). The model is scaled,
centred on x / z and stood on y = 0; OBJ is y-up like the game, and the model's +z side faces the lot's street.
Faces keep the OBJ's winding: counter-clockwise seen from outside, which is what the game's own models use (a face
the game sees from behind draws unlit or not at all, so model both sides of thin parts). A texture with transparent
pixels is cut out by the default material's alpha test.
"""

from __future__ import annotations

import math
import os
import struct

from . import content

MAX_VERTS = 65535
MAX_TEX = 512


class MeshError(content.ContentError):
    pass


def _pow2(n: int) -> int:
    return max(4, min(MAX_TEX, 1 << max(0, math.ceil(math.log2(max(1, n))))))


def _read_mtl(path: str) -> dict:
    mats, cur = {}, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split(None, 1)
            if not parts or parts[0].startswith("#"):
                continue
            key, rest = parts[0], parts[1] if len(parts) > 1 else ""
            if key == "newmtl":
                cur = mats.setdefault(rest.strip(), {"color": (200, 200, 200), "texture": None})
            elif cur is not None and key == "Kd":
                try:
                    cur["color"] = tuple(max(0, min(255, int(float(v) * 255))) for v in rest.split()[:3])
                except ValueError:
                    pass
            elif cur is not None and key == "map_Kd":
                tex = rest.split()[-1] if rest.split() else ""
                cur["texture"] = os.path.join(os.path.dirname(path), tex)
    return mats


def read_obj(path: str) -> dict:
    """{"parts": {material: (vertices [(x, y, z, u, v)], triangles)}, "materials": {...}, "faces": n}."""
    if not os.path.isfile(path):
        raise MeshError("no model at %s" % path)
    if os.path.getsize(path) > 64 * 1024 * 1024:
        raise MeshError("the model file is over 64 MB")
    pos, uv = [], []
    mats = {}
    parts: dict[str, tuple[list, list, dict]] = {}
    cur = "default"
    faces = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts_ = line.split()
            if not parts_ or parts_[0].startswith("#"):
                continue
            k = parts_[0]
            try:
                if k == "v":
                    pos.append(tuple(float(v) for v in parts_[1:4]))
                elif k == "vt":
                    uv.append((float(parts_[1]), float(parts_[2]) if len(parts_) > 2 else 0.0))
                elif k == "mtllib":
                    mtl = os.path.join(os.path.dirname(path), " ".join(parts_[1:]))
                    if os.path.isfile(mtl):
                        mats.update(_read_mtl(mtl))
                elif k == "usemtl":
                    cur = " ".join(parts_[1:]) or "default"
                elif k == "f":
                    corners = []
                    for c in parts_[1:]:
                        idx = c.split("/")
                        vi = int(idx[0])
                        ti = int(idx[1]) if len(idx) > 1 and idx[1] else None
                        vi = vi - 1 if vi > 0 else len(pos) + vi
                        if ti is not None:
                            ti = ti - 1 if ti > 0 else len(uv) + ti
                        corners.append((vi, ti))
                    if len(corners) < 3:
                        continue
                    verts, tris, seen = parts.setdefault(cur, ([], [], {}))
                    ids = []
                    for vi, ti in corners:
                        if (vi, ti) not in seen:
                            x, y, z = pos[vi]
                            u, v = uv[ti] if ti is not None else (0.0, 0.0)
                            seen[(vi, ti)] = len(verts)
                            verts.append((x, y, z, u, 1.0 - v))          # OBJ v runs up; the game's runs down
                        ids.append(seen[(vi, ti)])
                    for i in range(1, len(ids) - 1):
                        tris.append((ids[0], ids[i], ids[i + 1]))
                    faces += 1
            except (ValueError, IndexError) as e:
                raise MeshError("cannot read %s: %r (%s)" % (os.path.basename(path), line.strip()[:60], e))
    if not faces:
        raise MeshError("the model has no faces")
    out = {}
    for name, (verts, tris, _) in parts.items():
        if len(verts) > MAX_VERTS:
            raise MeshError("material %r has %d vertices (at most %d)" % (name, len(verts), MAX_VERTS))
        out[name] = (verts, tris)
    return {"parts": out, "materials": mats, "faces": faces}


def fit(obj: dict, scale: float = 1.0, size: tuple[float, float, float] | None = None) -> dict:
    """Scale (a factor, or to fit `size` = width, height, depth in metres keeping proportions), centre on x / z and
    stand on y = 0. Returns the obj with "size_m" [width, height, depth]."""
    pts = [v for verts, _ in obj["parts"].values() for v in verts]
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    w, h, d = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
    if size:
        k = min(size[0] / max(w, 1e-6), size[1] / max(h, 1e-6), size[2] / max(d, 1e-6))
    else:
        k = scale
    if not 0 < k < 1e6:
        raise MeshError("bad scale")
    cx, cz, y0 = (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2, min(ys)
    parts = {n: ([((x - cx) * k, (y - y0) * k, (z - cz) * k, u, v) for x, y, z, u, v in verts], tris)
             for n, (verts, tris) in obj["parts"].items()}
    return dict(obj, parts=parts, size_m=[round(w * k, 3), round(h * k, 3), round(d * k, 3)])


def texture_for(material: dict | None):
    """The RGBA picture of a material: its map_Kd scaled to a power of two (<= 512), or 8 x 8 of its colour."""
    from PIL import Image
    if material and material.get("texture"):
        path = material["texture"]
        if not os.path.isfile(path):
            raise MeshError("the texture %s is missing" % path)
        try:
            im = Image.open(path)
            im.load()
        except Exception as e:  # noqa: BLE001 - any unreadable picture
            raise MeshError("the texture %s cannot be read: %s" % (path, e))
        im = im.convert("RGBA")
        return im.resize((_pow2(im.width), _pow2(im.height)), Image.LANCZOS)
    color = (material or {}).get("color", (200, 200, 200))
    return Image.new("RGBA", (8, 8), tuple(color) + (255,))


def model(obj: dict, first_texture: int):
    """The S3D model (one mesh per material; texture instances first_texture, +1, ...) and the textures as
    [(instance, FSH bytes)]."""
    from . import fsh, s3d
    m = s3d.Model()
    textures = []
    for k, (name, (verts, tris)) in enumerate(sorted(obj["parts"].items())):
        im = texture_for(obj["materials"].get(name))
        tex = first_texture + k
        textures.append((tex, fsh.write_argb(im.width, im.height, im.tobytes())))
        m.verts.append(s3d.VertBlock(0, s3d.FMT_XYZ_UV, b"".join(struct.pack("<5f", *v) for v in verts)))
        m.indices.append(s3d.IndexBlock(0, 2, b"".join(struct.pack("<3H", *t) for t in tris)))
        m.prims.append([(0, 0, 3 * len(tris))])
        m.mats.append(s3d.Material(textures=[s3d.Texture(tex, (1, 1), (1, 1), 0, 0, b"\0")]))
        m.meshes.append(s3d.Mesh(b"part_%d\0" % k, 0, [(k, k, k, k)]))
    if len(textures) > 0xFF:
        raise MeshError("at most 255 materials")
    return m, textures


def load(path: str, scale: float = 1.0, size=None) -> dict:
    return fit(read_obj(path), scale, size)


def preview(obj: dict, size: int = 256, background=(0, 0, 0, 0)):
    """An isometric picture of the model (flat-shaded, each face in its texture's average colour), lit from the
    upper left as the game is - for menu icons and to show the agent what was imported."""
    from PIL import Image, ImageDraw
    yaw, pitch = math.radians(45), math.radians(30)
    light = (-0.4, 0.8, 0.45)
    ln = math.sqrt(sum(c * c for c in light))
    light = tuple(c / ln for c in light)
    faces = []
    for name, (verts, tris) in obj["parts"].items():
        im = texture_for(obj["materials"].get(name)).resize((1, 1), Image.BILINEAR)
        col = im.getpixel((0, 0))[:3]
        for a, b, c in tris:
            P = [verts[a], verts[b], verts[c]]
            e1 = [P[1][i] - P[0][i] for i in range(3)]
            e2 = [P[2][i] - P[0][i] for i in range(3)]
            n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            nl = math.sqrt(sum(x * x for x in n)) or 1.0
            lit = 0.45 + 0.55 * max(0.0, sum(n[i] * light[i] for i in range(3)) / nl)
            proj = []
            for x, y, z, _, _ in P:
                x2 = x * math.cos(yaw) - z * math.sin(yaw)
                z2 = x * math.sin(yaw) + z * math.cos(yaw)
                proj.append((x2, -(y * math.cos(pitch) - z2 * math.sin(pitch)), y * math.sin(pitch) + z2 * math.cos(pitch)))
            faces.append((sum(p[2] for p in proj) / 3, proj, tuple(int(c * lit) for c in col)))
    xs = [p[0] for f in faces for p in f[1]]
    ys = [p[1] for f in faces for p in f[1]]
    k = (size * 0.9) / max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    ox, oy = size / 2 - (max(xs) + min(xs)) / 2 * k, size / 2 - (max(ys) + min(ys)) / 2 * k
    out = Image.new("RGBA", (size, size), background)
    d = ImageDraw.Draw(out)
    for _, proj, col in sorted(faces, key=lambda f: f[0]):
        d.polygon([(ox + p[0] * k, oy + p[1] * k) for p in proj], fill=col + (255,))
    return out


def icon(obj: dict) -> bytes:
    pic = preview(obj, 40)
    return content.menu_icon(lambda im, d: im.alpha_composite(pic, (2, 2)))
