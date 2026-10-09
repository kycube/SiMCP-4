"""The look of all terrain (global): ground, beach and cliff textures and the table that picks them.

The game draws the ground with textures of group 0x891B0E1A (SimCity_2.dat; instance = zoom << 8 | texture id, zooms
0-4, DXT1 256 x 256, the closest zoom with two variants). Which texture a spot gets comes from the terrain INI
(type 0, group 0x8A5971C5, instance 0xAA597172, read by 0x74DC30): [TropicalTextureMapTable] - 32 rows of
temperature (cold to warm) by 16 columns of moisture (dry to wet) - and [TropicalMiscTextures] (beach 0x39, cliffs
0x43 / 0x44). "Tropical" is the only climate the exe asks for; the desert, temperate and arctic tables in the file
are commented out and their textures were never shipped.

A look is one plugin, SiMCP_terrain_look.dat in SiMCP's plugin folder: recoloured copies of the game's own textures
under the same keys (the game's DXT1 layout), and when asked an INI with the table moved drier or wetter. Plugins
load at start: a new look shows after the game restarts. "default" moves the plugin aside.
"""

from __future__ import annotations

import io
import os
import re
import struct
import time

import numpy as np

from . import content, dbpf, fsh, gamedata

G_TERRAIN_TEX = 0x891B0E1A
INI_TGI = (dbpf.T_INI, 0x8A5971C5, 0xAA597172)
# the table's ground textures from dry to lush: sand, sand + grass, earth + grass, mixed, grass ... dark grass
GROUND = [0x32, 0x33, 0x36, 0x37, 0x38, 0x35, 0x34, 0x31]
BEACH, HIGH_CLIFF, LOW_CLIFF = 0x39, 0x43, 0x44
TEXTURES = GROUND + [BEACH, HIGH_CLIFF, LOW_CLIFF]
ZOOMS = 5
NAME = "Terrain look"
FILE = "SiMCP_terrain_look.dat"
SECTION = "TropicalTextureMapTable"
# preset looks: the table's moisture shift and how the textures are recoloured
LOOKS = {
    "lush": {"moisture_shift": 2, "saturation": 1.12, "brightness": 1.0},
    "arid": {"moisture_shift": -3, "tint_rgb": [196, 160, 104], "tint_strength": 0.45, "saturation": 0.8,
             "brightness": 1.04},
    "arctic": {"moisture_shift": 0, "snow": 0.8, "saturation": 0.6},
    "autumn": {"moisture_shift": 0, "autumn": 0.75, "saturation": 1.0},
}


class TerrainLookError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _tex_dat():
    main = gamedata._main_dat()
    if main is None:
        raise TerrainLookError("the game's data files were not found")
    path = os.path.join(os.path.dirname(main.path), "SimCity_2.dat")
    if not os.path.exists(path):
        raise TerrainLookError("the game's SimCity_2.dat (terrain textures) was not found")
    return dbpf.DBPF(path)


def game_ini() -> str:
    d = gamedata._main_dat()
    e = d.get(*INI_TGI) if d is not None else None
    if e is None:
        raise TerrainLookError("the game's terrain INI (0x8A5971C5 / 0xAA597172) was not found")
    return d.read(e).decode("latin-1")


def table(ini: str) -> list[list[int]]:
    """[TropicalTextureMapTable] as 32 rows (cold to warm) of 16 texture ids (dry to wet)."""
    m = re.search(r"^\[%s\]\s*$(.*?)(?=^\[)" % SECTION, ini, re.M | re.S)
    if not m:
        raise TerrainLookError("the terrain INI has no [%s]" % SECTION)
    rows = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\d\d)=(.*)$", line.strip())
        if mm:
            rows[int(mm.group(1))] = [int(v, 16) for v in mm.group(2).split(",") if v.strip()]
    return [rows[k] for k in sorted(rows)]


def shifted(rows: list[list[int]], shift: int) -> list[list[int]]:
    """Move every ground texture `shift` steps along GROUND (+ wetter / greener, - drier)."""
    out = []
    for r in rows:
        out.append([GROUND[max(0, min(len(GROUND) - 1, GROUND.index(t) + shift))] if t in GROUND else t for t in r])
    return out


def ini_with_table(ini: str, rows: list[list[int]]) -> str:
    body = "".join("%02d=%s,\n" % (k, ",".join("0x%02x" % t for t in r)) for k, r in enumerate(rows))
    new, n = re.subn(r"(^\[%s\]\s*$\n)(.*?)(?=^\[)" % SECTION, lambda m: m.group(1) + body + "\n\n", ini,
                     count=1, flags=re.M | re.S)
    if n != 1:
        raise TerrainLookError("the terrain INI has no [%s]" % SECTION)
    return new


# ---------------------------------------------------------------- textures

def read_entries(b: bytes) -> list[np.ndarray]:
    """Every bitmap of a terrain FSH as an RGB array."""
    n, = struct.unpack_from("<I", b, 8)
    out = []
    for k in range(n):
        off, = struct.unpack_from("<I", b, 20 + 8 * k)
        w, h, px = fsh.read_first(b[:20] + struct.pack("<I", off) + b[24:])     # offsets are absolute
        out.append(np.frombuffer(px, np.uint8).reshape(h, w, 4)[:, :, :3].copy())
    return out


def _to565(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0, 255)
    r = np.round(c[:, 0] * 31 / 255).astype(np.uint32)
    g = np.round(c[:, 1] * 63 / 255).astype(np.uint32)
    b = np.round(c[:, 2] * 31 / 255).astype(np.uint32)
    return (r << 11) | (g << 5) | b


def _from565(v: np.ndarray) -> np.ndarray:
    return np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31],
                    -1).astype(np.float32)


def dxt1(img: np.ndarray) -> bytes:
    """DXT1 blocks for an RGB image (sides multiples of 4): per 4 x 4 block the two ends of its colours along their
    main axis, four-colour mode."""
    h, w = img.shape[:2]
    blk = img.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3).astype(np.float32)
    mean = blk.mean(1)
    d = blk - mean[:, None, :]
    cov = np.einsum("nki,nkj->nij", d, d)
    v = np.ones_like(mean)
    for _ in range(6):
        v = np.einsum("nij,nj->ni", cov, v)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    proj = np.einsum("nki,ni->nk", d, v)
    hi = mean + v * proj.max(1)[:, None]
    lo = mean + v * proj.min(1)[:, None]
    c0, c1 = _to565(hi), _to565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0, p1 = _from565(c0), _from565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)
    idx = ((blk[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1).argmin(2).astype(np.uint32)
    idx[c0 == c1] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    rec = np.zeros(len(c0), dtype=[("c0", "<u2"), ("c1", "<u2"), ("bits", "<u4")])
    rec["c0"], rec["c1"], rec["bits"] = c0, c1, bits
    return rec.tobytes()


def write_fsh(images: list[np.ndarray], name: bytes = b"0000") -> bytes:
    """A terrain FSH as the game's: "G264", one DXT1 bitmap per image, entries at 16-byte boundaries."""
    head = 16 + 8 * len(images)
    pos = (head + 15) & ~15
    offs, blobs = [], []
    for im in images:
        h, w = im.shape[:2]
        blob = struct.pack("<I6H", fsh.CODE_DXT1, w, h, 0, 0, 0, 0) + dxt1(im)
        blob += bytes((-len(blob)) % 16)
        offs.append(pos)
        blobs.append(blob)
        pos += len(blob)
    out = bytearray(b"SHPI" + struct.pack("<II", pos, len(images)) + b"G264")
    for o in offs:
        out += name + struct.pack("<I", o)
    out += bytes(offs[0] - len(out))
    for b_ in blobs:
        out += b_
    return bytes(out)


def recolour(img: np.ndarray, saturation: float = 1.0, brightness: float = 1.0, tint_rgb=None,
             tint_strength: float = 0.0, snow: float = 0.0, autumn: float = 0.0) -> np.ndarray:
    """Recolour a texture keeping its detail: saturation and brightness; a tint moves its average colour towards
    tint_rgb (a per-channel gain, so the pattern stays); autumn turns green parts orange-brown; snow lays white
    over it with the texture's light and shade showing through."""
    c = img.astype(np.float32) / 255.0
    lum = (c @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    if autumn:
        r, g, b = c[..., 0:1], c[..., 1:2], c[..., 2:3]
        green = np.clip((g - 0.9 * r) / 0.05, 0, 1) * np.clip((g - b) / 0.08, 0, 1) * autumn   # olive too
        fall = lum / max(float(lum.mean()), 1e-3) * np.array([0.56, 0.38, 0.19], np.float32)
        c = c * (1 - green) + fall * green
    c = lum + (c - lum) * saturation
    if tint_rgb is not None and tint_strength:
        gain = (np.array(tint_rgb, np.float32) / 255.0) / np.maximum(c.reshape(-1, 3).mean(0), 1e-3)
        c = c * (1 - tint_strength) + c * gain * tint_strength
    c = c * brightness
    if snow:
        lum = (c @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
        white = np.array([0.90, 0.93, 0.97], np.float32) * (0.88 + 0.5 * (lum - float(lum.mean())))
        c = c * (1 - snow) + white * snow
    return np.clip(c * 255.0 + 0.5, 0, 255).astype(np.uint8)


def _settings(look: str, **kw) -> dict:
    if look != "custom" and look not in LOOKS:
        raise TerrainLookError("look is default, %s or custom" % ", ".join(LOOKS))
    s = {"moisture_shift": 0, "saturation": 1.0, "brightness": 1.0, "tint_rgb": None, "tint_strength": 0.0,
         "snow": 0.0, "autumn": 0.0}
    if look != "custom":
        s.update(LOOKS[look])
    s.update({k: v for k, v in kw.items() if v is not None})
    if not -7 <= int(s["moisture_shift"]) <= 7:
        raise TerrainLookError("moisture_shift is -7..7")
    for k, lo, hi in (("saturation", 0.0, 2.0), ("brightness", 0.5, 1.5), ("tint_strength", 0.0, 1.0),
                      ("snow", 0.0, 1.0), ("autumn", 0.0, 1.0)):
        if not lo <= float(s[k]) <= hi:
            raise TerrainLookError("%s is %g..%g" % (k, lo, hi))
    if s["tint_rgb"] is not None and (len(s["tint_rgb"]) != 3 or not all(0 <= v <= 255 for v in s["tint_rgb"])):
        raise TerrainLookError("tint_rgb is [r, g, b] in 0..255")
    return s


def _for_texture(s: dict, tid: int) -> dict:
    """Beach and cliffs take half the colour change and less snow (rock shows through)."""
    k = 1.0 if tid in GROUND else 0.5
    return {"saturation": 1 + (s["saturation"] - 1) * k, "brightness": 1 + (s["brightness"] - 1) * k,
            "tint_rgb": s["tint_rgb"], "tint_strength": s["tint_strength"] * k,
            "snow": s["snow"] * (1.0 if tid in GROUND else 0.75 if tid == BEACH else 0.45),
            "autumn": s["autumn"] * (1.0 if tid in GROUND else 0.0)}


def _path() -> str:
    return os.path.join(content.FOLDER, FILE)


def _own_folder() -> None:
    f = content.FOLDER
    if os.path.realpath(f) != os.path.abspath(f):
        raise TerrainLookError("SiMCP's plugin folder is a link; refusing to write there")


def current() -> dict:
    hit = [d for d in content._manifest() if d.get("kind") == "terrain_look" and not d.get("disabled")]
    if hit and os.path.exists(hit[0]["file"]):
        return dict(hit[0], active=True)
    return {"look": "default", "active": False}


def _reset_entry() -> None:
    items = content._manifest()
    if any(d.get("kind") == "terrain_look" and not d.get("disabled") for d in items):
        try:
            content.disable(NAME)
        except content.ContentError as e:
            raise TerrainLookError("the running game has the terrain look open",
                                   "quit_game, change the look, then game_launch") from e


def design(look: str, moisture_shift: int | None = None, saturation: float | None = None,
           brightness: float | None = None, tint_rgb=None, tint_strength: float | None = None,
           snow: float | None = None, autumn: float | None = None) -> dict:
    """Write the terrain look plugin (replacing the last one), or with "default" move it aside."""
    _own_folder()
    if look == "default":
        before = current()
        _reset_entry()
        return {"look": "default", "was": before.get("look"),
                "note": "the game's own terrain from the next game start"}
    s = _settings(look, moisture_shift=moisture_shift, saturation=saturation, brightness=brightness,
                  tint_rgb=tint_rgb, tint_strength=tint_strength, snow=snow, autumn=autumn)
    src = _tex_dat()
    records, before, after = [], [], []
    for tid in TEXTURES:
        p = _for_texture(s, tid)
        for z in range(ZOOMS):
            e = src.get(dbpf.T_FSH, G_TERRAIN_TEX, (z << 8) | tid)
            if e is None:
                continue
            ims = read_entries(src.read(e))
            new = [recolour(im, **p) for im in ims]
            records.append((dbpf.T_FSH, G_TERRAIN_TEX, (z << 8) | tid, write_fsh(new)))
            if z == ZOOMS - 1:
                before.append(ims[0])
                after.append(new[0])
    if not records:
        raise TerrainLookError("no terrain textures were read")
    if s["moisture_shift"]:
        ini = game_ini()
        records.append(INI_TGI + (ini_with_table(ini, shifted(table(ini), int(s["moisture_shift"]))).encode(
            "latin-1"),))
    _reset_entry()
    os.makedirs(content.FOLDER, exist_ok=True)
    path = _path()
    dbpf.write_dbpf(path, records, compress=False)      # the game's terrain textures are stored uncompressed
    entry = {"name": NAME, "kind": "terrain_look", "look": look, "file": path, "settings": s,
             "textures": ["0x%02X" % t for t in TEXTURES], "table_changed": bool(s["moisture_shift"]),
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = [d for d in content._manifest() if not (d.get("kind") == "terrain_look" and not d.get("disabled"))]
    items.append(entry)
    content._save_manifest(items)
    return dict(entry, png=_sheet(before, after),
                note="plugins load at start: quit and launch the game to see it (saved cities take it too)")


def _sheet(before: list[np.ndarray], after: list[np.ndarray]) -> bytes:
    from PIL import Image
    t = 96
    sheet = Image.new("RGB", (len(before) * (t + 4) + 4, 2 * (t + 4) + 4), (40, 40, 40))
    for k, (a, b) in enumerate(zip(before, after)):
        sheet.paste(Image.fromarray(a).resize((t, t)), (4 + k * (t + 4), 4))
        sheet.paste(Image.fromarray(b).resize((t, t)), (4 + k * (t + 4), t + 8))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue()
