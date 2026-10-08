"""FSH textures ("SHPI", type 0x7AB50E44): write 32-bit textures, read the game's (re/agents/formats Q4).

Layout: "SHPI", u32 file size, u32 entry count, 4-char directory id ("G264" for buildings), then per entry a
4-char name and a u32 offset; each bitmap starts with u32 (code in the low byte, 24-bit offset to the next block or
0), u16 width, u16 height, u16 x centre, u16 y centre, u16 x offset, u16 y offset (high nibble = mipmap count),
then the pixels. Codes: 0x7D ARGB8888 (stored B, G, R, A), 0x60 DXT1, 0x61 DXT3. SiMCP writes 0x7D, one level - a
format the game's own building textures use for small images.
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
