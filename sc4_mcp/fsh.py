"""FSH textures ("SHPI", type 0x7AB50E44): write 32-bit textures, read the game's (re/agents/formats Q4).

Layout: "SHPI", u32 file size, u32 entry count, 4-char directory id ("G264" for buildings), then per entry a
4-char name and a u32 offset; each bitmap starts with u32 (code in the low byte, 24-bit offset to the next block or
0), u16 width, u16 height, u16 x centre, u16 y centre, u16 x offset, u16 y offset (high nibble = mipmap count),
then the pixels. Codes: 0x7D ARGB8888 (stored B, G, R, A), 0x60 DXT1, 0x61 DXT3. SiMCP writes 0x7D, one level - a
format the game's own building textures use for small images - and, for rendered buildings, DXT1 (the picture, 1-bit
alpha) and DXT3 (its night light layer) under "G354" as Maxis' own: at night the game lays a model's night layer
(texture instance + 0x8000) over it - lights come on a few seconds after dusk while the city runs (found live; a
first ARGB8888 layer, checked with the city paused, did not show).
"""

from __future__ import annotations

import struct

CODE_ARGB8888, CODE_DXT1, CODE_DXT3 = 0x7D, 0x60, 0x61


def write_argb(width: int, height: int, rgba: bytes, name: bytes = b"0000", directory: bytes = b"G264") -> bytes:
    """One ARGB8888 bitmap from RGBA bytes (row-major, top row first)."""
    if len(rgba) != width * height * 4:
        raise ValueError("need width * height * 4 bytes of RGBA")
    if width > 1024 or height > 1024 or width < 1 or height < 1:
        raise ValueError("textures are 1..1024 pixels a side")
    bgra = bytearray(rgba)
    bgra[0::4], bgra[2::4] = rgba[2::4], rgba[0::4]
    entry = struct.pack("<I6H", CODE_ARGB8888, width, height, 0, 0, 0, 0) + bytes(bgra)
    off = 16 + 8
    head = b"SHPI" + struct.pack("<II", off + len(entry), 1) + directory + name + struct.pack("<I", off)
    return head + entry


def _rgb565(c: int) -> tuple[int, int, int]:
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _dxt_colors(b: bytes, o: int, dxt1: bool) -> list[tuple[int, int, int, int]]:
    c0, c1 = struct.unpack_from("<HH", b, o)
    p0, p1 = _rgb565(c0), _rgb565(c1)
    if c0 > c1 or not dxt1:
        p2 = tuple((2 * a + b_) // 3 for a, b_ in zip(p0, p1))
        p3 = tuple((a + 2 * b_) // 3 for a, b_ in zip(p0, p1))
        return [p0 + (255,), p1 + (255,), p2 + (255,), p3 + (255,)]
    p2 = tuple((a + b_) // 2 for a, b_ in zip(p0, p1))
    return [p0 + (255,), p1 + (255,), p2 + (255,), (0, 0, 0, 0)]


def read_first(b: bytes) -> tuple[int, int, bytes]:
    """The first bitmap of an FSH as (width, height, RGBA bytes) - for previews."""
    if b[:4] != b"SHPI":
        raise ValueError("not an FSH")
    off, = struct.unpack_from("<I", b, 20)
    rec, w, h = struct.unpack_from("<IHH", b, off)
    code = rec & 0x7F
    px = off + 16
    out = bytearray(w * h * 4)
    if code == CODE_ARGB8888:
        src = b[px:px + w * h * 4]
        out[0::4], out[1::4], out[2::4], out[3::4] = src[2::4], src[1::4], src[0::4], src[3::4]
    elif code in (CODE_DXT1, CODE_DXT3):
        bs = 8 if code == CODE_DXT1 else 16
        o = px
        for by in range(0, h, 4):
            for bx in range(0, w, 4):
                alpha = None
                if code == CODE_DXT3:
                    alpha = struct.unpack_from("<Q", b, o)[0]
                    co = o + 8
                else:
                    co = o
                cols = _dxt_colors(b, co, code == CODE_DXT1)
                bits, = struct.unpack_from("<I", b, co + 4)
                for j in range(16):
                    x, y = bx + (j & 3), by + (j >> 2)
                    if x < w and y < h:
                        r, g, bl, a = cols[(bits >> (2 * j)) & 3]
                        if alpha is not None:
                            a = ((alpha >> (4 * j)) & 15) * 17
                        out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, bl, a))
                o += bs
    else:
        raise ValueError("FSH code 0x%02X not decoded" % code)
    return w, h, bytes(out)


# ---- DXT compression (the game's building textures)


def _to565(c):
    import numpy as np
    c = np.clip(c, 0, 255)
    return ((np.round(c[:, 0] * 31 / 255).astype(np.uint32) << 11) |
            (np.round(c[:, 1] * 63 / 255).astype(np.uint32) << 5) |
            np.round(c[:, 2] * 31 / 255).astype(np.uint32))


def _from565(v):
    import numpy as np
    return np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31],
                    -1).astype(np.float32)


def _blocks(img):
    import numpy as np
    h, w = img.shape[:2]
    return img.reshape(h // 4, 4, w // 4, 4, img.shape[2]).transpose(0, 2, 1, 3, 4).reshape(-1, 16, img.shape[2])


def _ends(rgb, weight):
    """Endpoints along the main axis of each block's colours (weighted: transparent texels do not count)."""
    import numpy as np
    wsum = weight.sum(1, keepdims=True) + 1e-6
    mean = (rgb * weight[..., None]).sum(1) / wsum
    d = (rgb - mean[:, None, :]) * weight[..., None]
    cov = np.einsum("nki,nkj->nij", d, d)
    v = np.ones_like(mean)
    for _ in range(6):
        v = np.einsum("nij,nj->ni", cov, v)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    proj = np.einsum("nki,ni->nk", rgb - mean[:, None, :], v)
    big = np.where(weight > 0, proj, -1e9).max(1)
    small = np.where(weight > 0, proj, 1e9).min(1)
    big = np.where(np.isfinite(big) & (big > -1e8), big, 0)
    small = np.where(np.isfinite(small) & (small < 1e8), small, 0)
    return mean + v * big[:, None], mean + v * small[:, None]


def dxt1(rgba):
    """DXT1: four-colour blocks; a block with transparent texels uses the three-colour mode (index 3 = clear)."""
    import numpy as np
    blk = _blocks(rgba.astype(np.float32))
    rgb, a = blk[..., :3], blk[..., 3]
    clear = a < 128
    hi, lo = _ends(rgb, (~clear).astype(np.float32))
    c0, c1 = _to565(hi), _to565(lo)
    has_clear = clear.any(1)
    # four-colour mode needs c0 > c1, three-colour mode c0 <= c1
    swap4 = (~has_clear) & (c0 < c1)
    swap3 = has_clear & (c0 > c1)
    sw = swap4 | swap3
    c0, c1 = np.where(sw, c1, c0), np.where(sw, c0, c1)
    p0, p1 = _from565(c0), _from565(c1)
    pal4 = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    pal3 = np.stack([p0, p1, (p0 + p1) / 2, np.full_like(p0, 1e6)], 1)
    pal = np.where(has_clear[:, None, None], pal3, pal4)
    idx = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1).argmin(2).astype(np.uint32)
    idx = np.where(clear, 3, idx)
    same4 = (~has_clear) & (c0 == c1)
    idx[same4] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    rec = np.zeros(len(c0), dtype=[("c0", "<u2"), ("c1", "<u2"), ("bits", "<u4")])
    rec["c0"], rec["c1"], rec["bits"] = c0, c1, bits
    return rec.tobytes()


def dxt3(rgba):
    """DXT3: 4-bit alpha per texel, then a four-colour block."""
    import numpy as np
    blk = _blocks(rgba.astype(np.float32))
    rgb, a = blk[..., :3], blk[..., 3]
    a4 = np.clip(np.round(a / 17), 0, 15).astype(np.uint64)
    abits = (a4 << (4 * np.arange(16, dtype=np.uint64))).sum(1).astype(np.uint64)
    hi, lo = _ends(rgb, (a > 0).astype(np.float32) + 1e-3)
    c0, c1 = _to565(hi), _to565(lo)
    sw = c0 < c1
    c0, c1 = np.where(sw, c1, c0), np.where(sw, c0, c1)
    p0, p1 = _from565(c0), _from565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    idx = ((rgb[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1).argmin(2).astype(np.uint32)
    idx[c0 == c1] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    rec = np.zeros(len(c0), dtype=[("a", "<u8"), ("c0", "<u2"), ("c1", "<u2"), ("bits", "<u4")])
    rec["a"], rec["c0"], rec["c1"], rec["bits"] = abits, c0, c1, bits
    return rec.tobytes()


def write_dxt(rgba, code: int = CODE_DXT1, directory: bytes = b"G354") -> bytes:
    """One DXT1 (1-bit alpha) or DXT3 bitmap from an RGBA array (height x width x 4, sides multiples of 4)."""
    import numpy as np
    rgba = np.asarray(rgba)
    h, w = rgba.shape[:2]
    if w % 4 or h % 4 or not (4 <= w <= 1024 and 4 <= h <= 1024):
        raise ValueError("DXT textures are 4..1024 pixels a side, multiples of 4")
    if code not in (CODE_DXT1, CODE_DXT3):
        raise ValueError("code: CODE_DXT1 or CODE_DXT3")
    data = dxt1(rgba) if code == CODE_DXT1 else dxt3(rgba)
    entry = struct.pack("<I6H", code, w, h, 0, 0, 0, 0) + data
    off = 16 + 8
    return b"SHPI" + struct.pack("<II", off + len(entry), 1) + directory + b"0000" + struct.pack("<I", off) + entry
