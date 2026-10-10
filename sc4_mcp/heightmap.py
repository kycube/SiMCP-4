"""Region terrain from a height map, and region tile layouts (re/reports/regions Q1, networks-deals Q5; LIVE_FACTS).

Layout: a region's config.bmp holds one pixel per 1 km grid square: red = a small city tile, green = a medium (2x2
pixels), blue = a large one (4x4). The game reads it when the region loads.

Terrain: the region view's RegionBitmapLoad command (0x7AEDD0) asks for a greyscale bitmap in the game's own file
window (0x79D810, run modally), checks its size - exactly (grid width x 64 + 1) x (grid height x 64 + 1) pixels -
deletes every city of the region, and generates and saves each tile from its part of the image (height = grey x
3 m; sea level is 250 m = grey 83.3). Only 8-bit greyscale BMPs load (a 24-bit one is silently refused). The file
window joins its folder ("Look in", at first "c:\\") and the typed name (component +0xD8, slot 18 gives
{mode, -, path, folder, name}); SiMCP types the name relative to that folder into the File name edit (text-edit
interface slot 49 SetText(char*, length, notify)) and presses OK, as a player would.
"""

from __future__ import annotations

import os
import re
import struct
import time

from . import dialogs, launch, regions

METRES_PER_GREY = 3.0
SEA_LEVEL = 250.0
TILE_COLORS = {"small": (255, 0, 0), "medium": (0, 255, 0), "large": (0, 0, 255)}
TILE_SPAN = {"small": 1, "medium": 2, "large": 4}
EDIT_SET_TEXT, EDIT_GET_TEXT, EDIT_TEXT_LENGTH = 49, 46, 47
FILEWIN_INNER, INNER_EDIT, INNER_GET_SELECTION = 0xD8, 0x100, 18
INNER_VTABLE, EDIT_VTABLE = 0xADD190, 0xADFA68          # the file window's component and its File name edit
HOME = os.path.join(launch.ROOT, "heightmaps")
REGION_NAME = re.compile(r"[A-Za-z0-9 _'-]{1,32}")
S_TEXT, TEXT_MAX = 0x1600, 0x300                          # scratch for the typed file name


class HeightmapError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def region_folder(name: str) -> str:
    """A region folder in SiMCP's own user folder - never anywhere else (names are plain folder names)."""
    if not REGION_NAME.fullmatch(name or ""):
        raise HeightmapError("a region name is 1-32 letters, digits, spaces, - ' _", "list_regions() lists them")
    root = os.path.realpath(os.path.join(launch.USER_DIR, "Regions"))
    folder = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(folder) != root:
        raise HeightmapError("the region must be a folder of SiMCP's own Regions folder")
    if not os.path.isfile(os.path.join(folder, "region.ini")):
        raise HeightmapError("no region folder %r in SiMCP's user folder" % name, "list_regions() lists them")
    return folder


def write_layout(name: str, width: int, height: int, tile: str = "small") -> dict:
    """Write config.bmp: a width x height grid (in 1 km squares) filled with one tile size."""
    if tile not in TILE_SPAN:
        raise HeightmapError("tile is small, medium or large")
    span = TILE_SPAN[tile]
    if not (1 <= width <= 64 and 1 <= height <= 64) or width % span or height % span:
        raise HeightmapError("width and height are 1..64 grid squares, multiples of %d for %s tiles" % (span, tile))
    from PIL import Image
    im = Image.new("RGB", (width, height), TILE_COLORS[tile])
    path = os.path.join(region_folder(name), "config.bmp")
    im.save(path, "BMP")
    return {"region": name, "grid": [width, height], "tile": tile, "cities": (width // span) * (height // span),
            "heightmap_size": [width * 64 + 1, height * 64 + 1]}


def grid_of(name: str) -> tuple[int, int]:
    g = regions.read_config_bmp(os.path.join(region_folder(name), "config.bmp"))
    return g["width"], g["height"]


def make_bitmap(name: str, heights=None, image_path: str = "") -> tuple[str, dict]:
    """An 8-bit greyscale BMP of the size the region needs, from heights in metres (rows, any size; resampled
    bilinearly) or from an image file (any format Pillow reads; grey levels used as they are)."""
    from PIL import Image
    w, h = grid_of(name)
    size = (w * 64 + 1, h * 64 + 1)
    if heights:
        rows = [list(map(float, r)) for r in heights]
        if not rows or any(len(r) != len(rows[0]) for r in rows) or len(rows[0]) < 2 or len(rows) < 2:
            raise HeightmapError("heights must be a rectangle of at least 2 x 2 numbers (metres)")
        flat = [max(0, min(255, round(v / METRES_PER_GREY))) for r in rows for v in r]
        im = Image.new("L", (len(rows[0]), len(rows)))
        im.putdata(flat)
    elif image_path:
        if not os.path.isfile(image_path):
            raise HeightmapError("no image at %s" % image_path)
        im = Image.open(image_path).convert("L")
    else:
        raise HeightmapError("give heights (metres) or an image")
    if im.size != size:
        im = im.resize(size, Image.BILINEAR)
    os.makedirs(HOME, exist_ok=True)
    out = os.path.join(HOME, "%s.bmp" % name)
    im.save(out, "BMP")                       # mode L -> 8 bits with a grey palette
    px = im.tobytes()                         # one byte per pixel (mode L)
    return out, {"size": list(size), "lowest_m": min(px) * METRES_PER_GREY, "highest_m": max(px) * METRES_PER_GREY,
                 "below_sea_level_percent": round(100 * sum(1 for v in px if v * METRES_PER_GREY < SEA_LEVEL) / len(px), 1)}


def _established(name: str) -> list[str]:
    out = []
    folder = region_folder(name)
    for f in os.listdir(folder):
        if f.lower().endswith(".sc4"):
            try:
                c = regions.read_city(os.path.join(folder, f))
            except Exception:  # noqa: BLE001 - an unreadable file counts as a city
                out.append(f)
                continue
            if c.get("established"):
                out.append("%s (%s)" % (c.get("name"), f))
    return out


def _file_window(g, timeout: float = 10.0) -> int:
    """The game's own file window (its component and File name edit checked by their vtables)."""
    p = g.proc
    end = time.time() + timeout
    while time.time() < end:
        for w in dialogs._modal_windows(g):
            inner = p.u32(w + FILEWIN_INNER)
            if inner and p.u32(inner) == INNER_VTABLE and p.u32(p.u32(inner + INNER_EDIT)) == EDIT_VTABLE:
                return w
        time.sleep(0.2)
    raise HeightmapError("the game's file window did not open")


def import_terrain(g, name: str, bmp: str, replace_cities: bool = False, timeout: float = 600.0) -> dict:
    """Run RegionBitmapLoad on the open region with our bitmap (the region view must show `name`)."""
    p, b = g.proc, g.bridge
    shown = g.region_name() or ""
    if shown.lower() != name.lower():
        raise HeightmapError("the region view shows %r, not %r" % (shown, name), "load_region(%r) first" % name)
    cities = _established(name)
    if cities and not replace_cities:
        raise HeightmapError("the import deletes every city of the region, and %d are founded: %s"
                             % (len(cities), ", ".join(cities[:5])), "pass replace_cities=true to replace them")
    folder = region_folder(name)

    def stamps():
        return {f: os.path.getmtime(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".sc4")}
    before = stamps()
    b.command("RegionBitmapLoad", defer=True, timeout_s=0.5)     # the file window keeps the call busy (modal)
    w = _file_window(g)
    try:
        inner = p.u32(w + FILEWIN_INNER)
        edit = p.u32(inner + INNER_EDIT)
        out = b.scratch(0x1E80, 20)
        p.write(out, bytes(20))
        b.vcall(inner, INNER_GET_SELECTION, out)
        d_ptr = struct.unpack_from("<5I", p.read(out, 20))[3]
        cur = p.read(p.u32(d_ptr + 4), 260).split(bytes(1), 1)[0].decode("latin-1") or "c:\\"
        try:
            rel = os.path.relpath(bmp, cur)
        except ValueError:
            raise HeightmapError("the file window is on another drive (%s)" % cur)
        try:
            text = rel.encode("latin-1")
        except UnicodeEncodeError:
            raise HeightmapError("the bitmap's path has characters the game cannot take: %s" % bmp)
        if len(text) >= TEXT_MAX:
            raise HeightmapError("the bitmap's path is too long")
        buf = b.scratch(S_TEXT, len(text) + 1)
        p.write(buf, text + bytes(1))
        b.vcall(edit, EDIT_SET_TEXT, buf, len(text), 1)
    except Exception:
        try:
            dialogs.click(g, "Cancel")                          # never leave the modal window open
        except Exception:  # noqa: BLE001
            pass
        raise
    t0 = time.time()
    dialogs.click(g, "OK")
    other = None
    while time.time() - t0 < timeout and b.deferred_state()["busy"]:
        time.sleep(1.0)
        st = dialogs.status(g)                                  # an error or a question stops the wait
        if st.get("open") and st["dialogs"] and st["dialogs"][0].get("texts") and                 not any("File name" in t for t in st["dialogs"][0]["texts"]):
            other = st["dialogs"][0]
            break
    made = sorted(f for f, t in stamps().items() if before.get(f) != t)
    res = {"region": name, "bitmap": bmp, "seconds": round(time.time() - t0, 1),
           "finished": not b.deferred_state()["busy"], "city_files_written": made}
    st = dialogs.status(g)
    if other or st.get("open"):
        res["dialog"] = other or st["dialogs"][0]
        res["hint"] = "the game asks or reports something: dialog_status / close_dialog"
    elif not res["finished"]:
        res["hint"] = "the game is still generating tiles: game_status shows the region view again when it is done"
    elif not made:
        res["hint"] = "the game generated nothing: check the bitmap size and format"
    return res
