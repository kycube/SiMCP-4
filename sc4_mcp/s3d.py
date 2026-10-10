"""S3D models ("3DMD", type 0x5AD0E817): read and write (re/reports/formats Q3, loader 0x806FA0).

A model is "3DMD" + total size, then the chunks HEAD (u16 major 1, u16 minor 5), VERT (vertex blocks), INDX (index
blocks), PRIM (primitive lists: triangle lists by block), MATS (materials, each naming FSH textures by instance),
ANIM (frames: for each mesh, which vert / index / prim / material block to draw), PROP and REGP (usually empty).
The game parses the chunks in this order and does not rely on their sizes; we write correct sizes anyway.

Vertex format 0x80004001 = position (3 floats) + one UV set (2 floats), 20 bytes - what Maxis buildings use.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

LEGACY = {1: 16, 2: 20, 3: 28, 10: 24, 11: 32, 32: 12, 33: 24, 34: 28, 35: 32, 36: 40, 37: 36, 38: 44}
FMT_XYZ_UV = 0x80004001


def stride_of(fmt: int) -> int:
    """Bytes per vertex for a vertex format (port of 0x8D0370)."""
    if fmt in LEGACY:
        return LEGACY[fmt]
    f = fmt & 0x7FFFFFFF
    n = ((f >> 10) & 0xF) + 2 * ((f >> 14) & 0xF) + ((f >> 8) & 3) + 3 * (f & 3)
    if f & 0xF:
        n += 3 * (((f >> 18) & 0xF) + ((f >> 6) & 1)) + 4 * ((f >> 22) & 0xF) + ((f >> 2) & 7) + \
             ((f >> 7) & 1) + ((f >> 5) & 1)
    return 4 * n


@dataclass
class VertBlock:
    flags: int
    fmt: int
    data: bytes                   # count * stride bytes

    @property
    def count(self) -> int:
        return len(self.data) // stride_of(self.fmt)


@dataclass
class IndexBlock:
    flags: int
    stride: int
    data: bytes


@dataclass
class Texture:
    instance: int
    wrap: tuple[int, int] = (1, 1)
    filters: tuple[int, int] = (2, 2)
    anim_rate: int = 0
    anim_mode: int = 0
    name: bytes = b"\0"           # stored with its terminating NUL


@dataclass
class Material:
    flags: int = 0xA3
    alpha_func: int = 4
    depth_func: int = 3
    src_blend: int = 1
    dst_blend: int = 0
    alpha_threshold: int = 0x7FFF
    material_class: int = 0
    reserved: int = 0
    textures: list[Texture] = field(default_factory=list)


@dataclass
class Mesh:
    name: bytes
    flags: int
    frames: list[tuple[int, int, int, int]]    # (vert, index, prim, material) block numbers per frame


@dataclass
class Model:
    version: tuple[int, int] = (1, 5)
    verts: list[VertBlock] = field(default_factory=list)
    indices: list[IndexBlock] = field(default_factory=list)
    prims: list[list[tuple[int, int, int]]] = field(default_factory=list)
    mats: list[Material] = field(default_factory=list)
    frames: int = 1
    fps: int = 0
    anim_mode: int = 3
    anim_flags: int = 0
    displacement: float = 0.0
    meshes: list[Mesh] = field(default_factory=list)
    prop: bytes = b"\0\0\0\0"
    regp: bytes = b"\0\0\0\0"


def parse(b: bytes) -> Model:
    if b[:4] != b"3DMD":
        raise ValueError("not an S3D model")
    m = Model()
    o = 8
    while o + 8 <= len(b):
        tag = b[o:o + 4]
        size, = struct.unpack_from("<I", b, o + 4)
        p = o + 8
        if tag == b"HEAD":
            m.version = struct.unpack_from("<HH", b, p)
            p += 4
        elif tag == b"VERT":
            n, = struct.unpack_from("<I", b, p)
            p += 4
            for _ in range(n):
                flags, cnt, fmt = struct.unpack_from("<HHI", b, p)
                p += 8
                ln = cnt * stride_of(fmt)
                m.verts.append(VertBlock(flags, fmt, b[p:p + ln]))
                p += ln
        elif tag == b"INDX":
            n, = struct.unpack_from("<I", b, p)
            p += 4
            for _ in range(n):
                flags, stride, cnt = struct.unpack_from("<HHH", b, p)
                p += 6
                m.indices.append(IndexBlock(flags, stride, b[p:p + cnt * stride]))
                p += cnt * stride
        elif tag == b"PRIM":
            n, = struct.unpack_from("<I", b, p)
            p += 4
            for _ in range(n):
                k, = struct.unpack_from("<H", b, p)
                p += 2
                m.prims.append([struct.unpack_from("<III", b, p + 12 * i) for i in range(k)])
                p += 12 * k
        elif tag == b"MATS":
            n, = struct.unpack_from("<I", b, p)
            p += 4
            for _ in range(n):
                flags, af, df, sb, db, athr, mclass, res, ntex = struct.unpack_from("<IBBBBHIBB", b, p)
                p += 16
                mat = Material(flags, af, df, sb, db, athr, mclass, res)
                for _ in range(ntex):
                    tid, wu, wv = struct.unpack_from("<IBB", b, p)
                    p += 6
                    filt = (0, 0)
                    if m.version[1] >= 5:
                        filt = struct.unpack_from("<BB", b, p)
                        p += 2
                    rate, mode, nl = struct.unpack_from("<HHB", b, p)
                    p += 5
                    mat.textures.append(Texture(tid, (wu, wv), filt, rate, mode, b[p:p + nl]))
                    p += nl
                m.mats.append(mat)
        elif tag == b"ANIM":
            m.frames, m.fps, m.anim_mode, m.anim_flags, m.displacement, nmesh = struct.unpack_from("<HHHIfH", b, p)
            p += 16
            for _ in range(nmesh):
                nl, mfl = struct.unpack_from("<BB", b, p)
                p += 2
                name = b[p:p + nl]
                p += nl
                frames = [struct.unpack_from("<4H", b, p + 8 * k) for k in range(m.frames)]
                p += 8 * m.frames
                m.meshes.append(Mesh(name, mfl, frames))
        elif tag == b"PROP":          # effect-point records: kept as they are, up to the REGP chunk
            end = b.find(b"REGP", p)
            end = end if end >= 0 else len(b)
            m.prop = b[p:end]
            p = end
        elif tag == b"REGP":          # the last chunk: the rest of the model
            m.regp = b[p:]
            p = len(b)
        else:
            raise ValueError("unknown chunk %r" % tag)
        o = p          # the game reads sequentially; sizes are not trusted
    return m


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + struct.pack("<I", 8 + len(body)) + body


def write(m: Model) -> bytes:
    head = struct.pack("<HH", *m.version)
    vert = struct.pack("<I", len(m.verts)) + b"".join(
        struct.pack("<HHI", v.flags, v.count, v.fmt) + v.data for v in m.verts)
    indx = struct.pack("<I", len(m.indices)) + b"".join(
        struct.pack("<HHH", i.flags, i.stride, len(i.data) // i.stride) + i.data for i in m.indices)
    prim = struct.pack("<I", len(m.prims)) + b"".join(
        struct.pack("<H", len(pl)) + b"".join(struct.pack("<III", *q) for q in pl) for pl in m.prims)
    mats = struct.pack("<I", len(m.mats))
    for mt in m.mats:
        mats += struct.pack("<IBBBBHIBB", mt.flags, mt.alpha_func, mt.depth_func, mt.src_blend, mt.dst_blend,
                            mt.alpha_threshold, mt.material_class, mt.reserved, len(mt.textures))
        for t in mt.textures:
            mats += struct.pack("<IBB", t.instance, *t.wrap)
            if m.version[1] >= 5:
                mats += struct.pack("<BB", *t.filters)
            mats += struct.pack("<HHB", t.anim_rate, t.anim_mode, len(t.name)) + t.name
    anim = struct.pack("<HHHIfH", m.frames, m.fps, m.anim_mode, m.anim_flags, m.displacement, len(m.meshes))
    for me in m.meshes:
        anim += struct.pack("<BB", len(me.name), me.flags) + me.name
        anim += b"".join(struct.pack("<4H", *f) for f in me.frames)
    body = (_chunk(b"HEAD", head) + _chunk(b"VERT", vert) + _chunk(b"INDX", indx) + _chunk(b"PRIM", prim) +
            _chunk(b"MATS", mats) + _chunk(b"ANIM", anim) + _chunk(b"PROP", m.prop) + _chunk(b"REGP", m.regp))
    return b"3DMD" + struct.pack("<I", 8 + len(body)) + body


def textured_mesh(vertices: list[tuple[float, float, float, float, float]], triangles: list[tuple[int, int, int]],
                  texture: int, name: bytes = b"SiMCP\0", alpha: bool = False) -> Model:
    """One textured triangle mesh (positions in metres, UVs 0..1) as a single-frame model."""
    if len(vertices) > 65535:
        raise ValueError("too many vertices")
    vdata = b"".join(struct.pack("<5f", *v) for v in vertices)
    idata = b"".join(struct.pack("<3H", *t) for t in triangles)
    mat = Material(flags=0xAB if alpha else 0xA3, src_blend=4 if alpha else 1, dst_blend=5 if alpha else 0,
                   textures=[Texture(texture, (1, 1), (2, 2), 0, 0, b"\0")])
    return Model(verts=[VertBlock(0, FMT_XYZ_UV, vdata)], indices=[IndexBlock(0, 2, idata)],
                 prims=[[(0, 0, 3 * len(triangles))]], mats=[mat], meshes=[Mesh(name, 0, [(0, 0, 0, 0)])])


def multi_mesh(parts: list[tuple[list, list, int, bool]], name: bytes = b"SiMCP") -> Model:
    """Several textured meshes in one model: parts = [(vertices (x, y, z, u, v), triangles, FSH instance, alpha)].
    Each part gets its own vertex / index / primitive / material blocks and mesh (as multi-material models do).
    Textures repeat (wrap 1) so UVs beyond 0..1 tile them."""
    m = Model()
    for k, (verts, tris, texture, alpha) in enumerate(parts):
        m.verts.append(VertBlock(0, FMT_XYZ_UV, b"".join(struct.pack("<5f", *v) for v in verts)))
        m.indices.append(IndexBlock(0, 2, b"".join(struct.pack("<3H", *t) for t in tris)))
        m.prims.append([(0, 0, 3 * len(tris))])
        m.mats.append(Material(flags=0xAB if alpha else 0xA3, src_blend=4 if alpha else 1, dst_blend=5 if alpha else 0,
                               textures=[Texture(texture, (1, 1), (1, 1), 0, 0, b"\0")]))
        m.meshes.append(Mesh(name + b"_%d\0" % k, 0, [(k, k, k, k)]))
    return m


def view_turns(r: int) -> int:
    """Quarter turns ((x, z) -> (-z, x) each) that make a model's +Z side (its street front) right for the game's
    view index r. The game draws a building's model fixed to the camera (+Z toward the lower left, +X toward the
    lower right) and picks index r = (lot facing - camera rotation) mod 4, facing north 0, east 1, south 2, west 3
    (found live with a probe showing its index on the roof, lots facing four ways, four camera rotations)."""
    return (r + 2) % 4


def turned(m: Model, r: int) -> Model:
    """A copy of a model turned for the game's view index r (view_turns): building models are drawn fixed to the
    camera, so each view needs its own turned copy (RKT1: base + zoom * 0x100 + r * 0x10)."""
    import copy
    out = copy.deepcopy(m)
    k = view_turns(r)
    if not k:
        return out
    for vb in out.verts:
        st = stride_of(vb.fmt)
        data = bytearray(vb.data)
        for i in range(0, len(data), st):
            x, y, z = struct.unpack_from("<3f", data, i)
            for _ in range(k):
                x, z = -z, x
            struct.pack_into("<3f", data, i, x, y, z)
        vb.data = bytes(data)
    return out
