"""Content formats written by SiMCP: S3D models, FSH textures, generated buildings (no game needed)."""
import struct

from sc4_mcp import content, fsh, s3d


def test_textured_mesh_round_trip():
    verts = [(0, 0, 0, 0, 1), (1, 0, 0, 1, 1), (1, 1, 0, 1, 0), (0, 1, 0, 0, 0)]
    m = s3d.textured_mesh(verts, [(0, 1, 2), (0, 2, 3)], 0x12345600)
    b = s3d.write(m)
    assert b[:4] == b"3DMD" and struct.unpack_from("<I", b, 4)[0] == len(b)
    back = s3d.parse(b)
    assert back == m
    assert back.verts[0].count == 4 and s3d.stride_of(back.verts[0].fmt) == 20
    assert back.mats[0].textures[0].instance == 0x12345600


def test_chunk_sizes_are_exact():
    b = s3d.write(content.box_mesh(10, 8, 20, 0x100, 0x101))
    o, tags = 8, []
    while o < len(b):
        tag, size = b[o:o + 4], struct.unpack_from("<I", b, o + 4)[0]
        tags.append(tag)
        o += size
    assert o == len(b)
    assert tags == [b"HEAD", b"VERT", b"INDX", b"PRIM", b"MATS", b"ANIM", b"PROP", b"REGP"]


def test_box_mesh_parts_and_tiling():
    m = content.box_mesh(14, 10, 28, 0x200, 0x201)
    assert len(m.meshes) == 2 and [mt.textures[0].instance for mt in m.mats] == [0x200, 0x201]
    walls = m.verts[0]
    pts = [struct.unpack_from("<5f", walls.data, 20 * i) for i in range(walls.count)]
    assert all(0 <= u <= 1.0001 and 0 <= v <= 1.0001 for *_, u, v in pts)        # the game clamps UVs
    xs, ys, zs = zip(*[(x, y, z) for x, y, z, _, _ in pts])
    assert (min(xs), max(xs), min(zs), max(zs), min(ys), max(ys)) == (-7, 7, -5, 5, 0, 28)
    # 4 walls of 14 / 10 m in 4 m columns, 7 rows of 4 m: (4 + 3 + 4 + 3) * 7 quads, both faces
    assert len(m.indices[0].data) // 6 == 14 * 7 * 4


def test_fsh_argb_round_trip():
    rgba = bytes([10, 20, 30, 255, 200, 100, 50, 128] * 8)
    b = fsh.write_argb(4, 4, rgba)
    assert b[:4] == b"SHPI" and b[12:16] == b"G264"
    w, h, back = fsh.read_first(b)
    assert (w, h, back) == (4, 4, rgba)


def test_wall_tile_and_fixed_point():
    assert len(content.wall_tile((200, 100, 50))) == 32 * 32 * 4
    assert content._fx(16.0) == 1048576 and content._fx(0.04) == 2621
