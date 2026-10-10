"""Regions and their cities, read from files (no game needed).

A region is a folder in <user folder>\\Regions with `region.ini` (name, terrain type, water levels) and
`config.bmp`, a bitmap where each pixel is one region grid square (one small city tile = 64x64 cells): a city tile
of size n (1 small, 2 medium, 4 large) is an n x n block whose colour has red (small), green (medium) or blue (large)
at 255. Each established or saved city is a DBPF file `City - <name>.sc4` whose region-view record (type 0xCA027EDB,
group 0xCA027EE1) holds its tile position and size, its names, mode and populations.
"""

from __future__ import annotations

import configparser
import os
import re
import struct

from . import dbpf, identity

T_REGION_VIEW = 0xCA027EDB
G_REGION_VIEW = 0xCA027EE1
SIZE_NAMES = {1: "small", 2: "medium", 4: "large"}
CELLS_PER_GRID = 64

_ltext_cache: dict[int, str] | None = None


def _locale_text(instance: int) -> str | None:
    """A string from the game's English text table by LTEXT instance id (shipped regions name themselves so)."""
    global _ltext_cache
    if _ltext_cache is None:
        _ltext_cache = {}
        path = os.path.join(identity.game_dir(), "English", "SimCityLocale.DAT")
        try:
            d = dbpf.DBPF(path)
            for e in d.find(dbpf.T_LTEXT):
                try:
                    _ltext_cache.setdefault(e.instance, dbpf.parse_ltext(d.read(e)))
                except ValueError:
                    pass
        except OSError:
            pass
    return _ltext_cache.get(instance)


def display_name(raw: str) -> str:
    m = re.fullmatch(r"#(0x[0-9A-Fa-f]{1,8})", raw.strip())
    if m:
        return _locale_text(int(m.group(1), 16)) or raw
    return raw


def read_region_ini(path: str) -> dict:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    with open(path, encoding="latin-1") as f:
        cp.read_string(f.read())
    s = cp["Regional Settings"] if cp.has_section("Regional Settings") else {}
    raw = s.get("Name", "")
    out = {"name_raw": raw, "name": display_name(raw)}
    for key, field in (("Terrain type", "terrain_type"), ("Water Min", "water_min"), ("Water Max", "water_max")):
        try:
            out[field] = int(s.get(key, ""))
        except ValueError:
            out[field] = s.get(key)
    return out


def tile_size_of(rgb: tuple[int, int, int]) -> int | None:
    r, g, b = rgb[:3]
    if b >= 250:
        return 4
    if g >= 250:
        return 2
    if r >= 250:
        return 1
    return None


def read_config_bmp(path: str) -> dict:
    """{width, height, tiles: [{x, y, size}]} in region grid squares, scanned row by row as the game does."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    used = [[False] * w for _ in range(h)]
    tiles = []
    for y in range(h):
        for x in range(w):
            if used[y][x]:
                continue
            n = tile_size_of(px[x, y])
            if not n:
                continue
            if x + n > w or y + n > h:
                n = 1
            for yy in range(y, y + n):
                for xx in range(x, x + n):
                    used[yy][xx] = True
            tiles.append({"x": x, "y": y, "size": SIZE_NAMES.get(n, n), "span": n})
    return {"width": w, "height": h, "tiles": tiles}


def _lstr(b: bytes, o: int) -> tuple[str, int]:
    n = struct.unpack_from("<I", b, o)[0]
    if n > 1024 or o + 4 + n > len(b):
        raise ValueError("bad string length")
    return b[o + 4:o + 4 + n].decode("latin-1"), o + 4 + n


DIFFICULTY = {0: "easy", 1: "medium", 2: "hard"}


def read_city(path: str) -> dict:
    """The region-view record of a saved city (.sc4): cSC4RegionalCity's own serialisation (re/reports/regions Q4).
    v1.13 (cities saved by the game): tile, size, populations, mayor rating (s8 0x24), difficulty (0x25), city
    serial (0x27), founded (0x3F), then length-prefixed strings name, -, mayor, -, utility advisor, description.
    v1.9 / 1.10: the unfounded "New City" tiles shipped with the regions."""
    d = dbpf.DBPF(path)
    e = d.get(T_REGION_VIEW, G_REGION_VIEW, 0)
    if e is None:
        raise ValueError("no region view record")
    b = d.read(e)
    major, minor, tx, ty, sx, sy, res, com, ind = struct.unpack_from("<HH7I", b, 0)
    out = {"file": os.path.basename(path), "version": "%d.%d" % (major, minor), "tile_x": tx, "tile_y": ty,
           "size": SIZE_NAMES.get(sx, sx), "span": sx,
           "population": {"residential": res, "commercial": com, "industrial": ind}}
    if (major, minor) == (1, 13):
        rating, = struct.unpack_from("<b", b, 0x24)
        serial, = struct.unpack_from("<I", b, 0x27)
        founded = bool(b[0x3F])
        strings, o = [], 0x40
        for _ in range(7):
            try:
                t, o = _lstr(b, o)
            except ValueError:
                break
            strings.append(t)
        strings += [""] * (7 - len(strings))
        out.update(name=strings[0], mayor=strings[2] or None, mode="mayor" if founded else "god",
                   established=founded, mayor_rating=rating, difficulty=DIFFICULTY.get(b[0x25], b[0x25]),
                   serial="%08X" % serial, utility_advisor=strings[4] or None, description=strings[5] or None)
    elif (major, minor) in ((1, 9), (1, 10)):
        name_at = 0x3B if minor == 9 else 0x3F
        mode = b[name_at - 1]
        name, _ = _lstr(b, name_at)
        out.update(name=name, mayor=None, mode={0: "god", 1: "mayor"}.get(mode, mode), established=mode == 1)
    else:
        raise ValueError("region view record version %d.%d not known" % (major, minor))
    return out


T_TERRAIN, G_TERRAIN = 0xA9DD6FF4, 0xE98F9525
T_PNG, G_THUMBS = 0x8A2482B9, 0x4A2482BB
THUMBS = {"satellite": 0, "transport": 4}


def read_terrain(path: str) -> dict:
    """The saved altitudes at the cell corners (rows of (cells+1) values) - the city's terrain without the game."""
    d = dbpf.DBPF(path)
    e = d.get(T_TERRAIN, G_TERRAIN, 1)
    if e is None:
        raise ValueError("no terrain record")
    b = d.read(e)
    n = (len(b) - 2) // 4
    side = int(round(n ** 0.5))
    if side * side != n:
        raise ValueError("terrain record is not square")
    vals = struct.unpack_from("<%df" % n, b, 2)
    rows = [[round(v, 2) for v in vals[r * side:(r + 1) * side]] for r in range(side)]
    flat = [v for r in rows for v in r]
    return {"vertices": side, "min": min(flat), "max": max(flat), "altitude": rows}


def read_thumbnail(path: str, view: str = "satellite") -> bytes:
    """The PNG the region view shows for the city (the game renders it when the city is saved)."""
    if view not in THUMBS:
        raise ValueError("view is satellite or transport")
    d = dbpf.DBPF(path)
    e = d.get(T_PNG, G_THUMBS, THUMBS[view])
    if e is None:
        raise ValueError("no %s thumbnail in this file" % view)
    return d.read(e)


def find_city_file(user_dir: str, region: str, city: str) -> str:
    for r in list_regions(user_dir):
        if region.lower() in (r["name"].lower(), r.get("folder", "").lower()):
            for c in r["cities"]:
                if c.get("name", "").lower() == city.lower():
                    return os.path.join(user_dir, "Regions", r["folder"], c["file"])
            raise ValueError("no city %r in region %r" % (city, r["name"]))
    raise ValueError("no region %r" % region)


def list_regions(user_dir: str) -> list[dict]:
    root = os.path.join(user_dir, "Regions")
    out = []
    if not os.path.isdir(root):
        return out
    for folder in sorted(os.listdir(root)):
        rd = os.path.join(root, folder)
        ini = os.path.join(rd, "region.ini")
        if not os.path.isfile(ini):
            continue
        info = {"folder": folder}
        try:
            info.update(read_region_ini(ini))
        except (OSError, configparser.Error) as e:
            info["error"] = "region.ini: %s" % e
        bmp = os.path.join(rd, "config.bmp")
        grid = read_config_bmp(bmp) if os.path.isfile(bmp) else {"width": 0, "height": 0, "tiles": []}
        cities = []
        for f in sorted(os.listdir(rd)):
            if f.lower().endswith(".sc4"):
                try:
                    cities.append(read_city(os.path.join(rd, f)))
                except (OSError, ValueError, struct.error) as e:
                    cities.append({"file": f, "error": str(e)})
        by_tile = {(c.get("tile_x"), c.get("tile_y")): c for c in cities if "tile_x" in c}
        for t in grid["tiles"]:
            c = by_tile.get((t["x"], t["y"]))
            t["city"] = c["name"] if c else None
            t["file"] = c["file"] if c else None
        info.update(grid_width=grid["width"], grid_height=grid["height"], tiles=grid["tiles"], cities=cities)
        out.append(info)
    return out
