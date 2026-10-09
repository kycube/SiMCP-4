"""New puzzle pieces: SiMCP's own RUL0 rules, merged into the RUL0 the game uses when SiMCP starts the game.

A piece is captured from networks laid in a city: each cell's network tile (piece id, rotation, flip and the edges
of every network on it, read from the occupants) becomes a static cell of a new rule. A rule's static tiles are
drawn as "highway piece" tiles - exemplar type 0x0B in group 0xA8434037 whose RKT3 lists one S3D model per zoom
(group 0xBADB57F1, instances T..T+4), with traffic paths in group 0xA966883F at T - where T = AutoTileBase + x * 0x100
+ z * 0x10, (x, z) counted from the north-west of the rule's static cells (seen live: x east, z south). Ground network tiles are textures (group 0x1ABE787D, T+zoom)
with paths in group 0x69668828, so each captured tile becomes a flat quad (as NAM's flat tiles: y 0.0001, v = 0 at
the north edge) carrying a copy of the texture the game shows, turned to the cell's rotation (one step turns west
to north: the image a quarter turn clockwise, path points (x, z) -> (z, -x), sides k -> k + 1), and a copy of its
paths turned the same way. The copies go only into SiMCP's own plugin folder.

The game reads one RUL0 (type 0x0A5BCF4B, group 0xAA5BCF57, instance 0x10000000): the last plugin's, here NAM's
controller. SiMCP keeps its pieces' sections in its design list and, at game_launch, writes
zzz_SiMCP\\SiMCP_RUL0.dat - the active RUL0 text with SiMCP's sections appended and their rotation rings added to
[Ordering] - loading after every other plugin. Rebuilt at every launch, so it follows NAM updates; without SiMCP
pieces the file is moved aside and the game's RUL0 is untouched. Rules use ids 0x5C4D0000 and up (NAM's end
below 0x06000000).
"""

from __future__ import annotations

import io
import os
import re
import struct
import time

from . import content, dbpf, launch, networks, puzzle

HID_BASE = 0x5C4D0000
RUL0_FILE = "SiMCP_RUL0.dat"
TILE_BASE = 0x5C400000                    # SiMCP's tiles: TILE_BASE + n * 0x10000 per piece
T_PATH, G_PATH_STATIC, G_PATH_ROAD = 0x296678F7, 0xA966883F, 0x69668828
G_TILE, G_MODELS, G_TEX, T_S3D, P_RKT3 = 0xA8434037, 0xBADB57F1, 0x1ABE787D, 0x5AD0E817, 0x27812823
NET_RUL0 = ["road", "rail", "highway", "street", "pipe", "powerline", "avenue", "subway", "lightrail", "monorail",
            "onewayroad", "dirtroad", "groundhighway"]           # RUL0's network names, by network type
LETTERS = [c for c in "abcdefghijklmoqrstuvwxyzABCDEFGHIJKLMNOQRSTUVWYZ"]   # not n, p, X, P (layout codes)
MAX_SIDE = 16


class NetDesignError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _ours() -> str:
    return os.path.join(content.FOLDER, RUL0_FILE)


def _pieces() -> list[dict]:
    return [d for d in content._manifest() if d.get("kind") == "puzzle_piece" and not d.get("disabled")]


def base_rul0() -> tuple[str, str]:
    """The RUL0 the game would use without SiMCP's: (source file, text)."""
    ours = os.path.normcase(os.path.abspath(_ours()))
    files = [f for f in puzzle._rul0_files() if os.path.normcase(os.path.abspath(f)) != ours]
    if files:
        d = dbpf.DBPF(files[-1])
        return files[-1], d.read(d.get(puzzle.RUL_TYPE, puzzle.RUL_GROUP, puzzle.RUL0)).decode("latin-1")
    from . import gamedata
    d = gamedata._main_dat()
    e = d.get(puzzle.RUL_TYPE, puzzle.RUL_GROUP, puzzle.RUL0) if d else None
    if e is None:
        raise NetDesignError("no RUL0 found (the game's data files?)")
    return d.path, d.read(e).decode("latin-1")


def merged_text(base: str, pieces: list[dict]) -> str:
    """The base RUL0 with each piece's rotation ring added to [Ordering] and its sections appended."""
    rings = "".join("RotationRing = %s\t;SiMCP %s\n" % (", ".join("%X" % h for h in d["ring"]), d["name"])
                    for d in pieces if d.get("ring"))
    m = re.search(r"^\[Ordering\][^\n]*\n", base, re.M | re.I)
    if rings:
        if m:
            base = base[:m.end()] + rings + base[m.end():]
        else:
            base = "[Ordering]\n" + rings + "\n" + base
    tail = "".join("\n\n;### SiMCP: %s ###\n%s\n" % (d["name"], d["rul0"].strip()) for d in pieces)
    return base.rstrip() + "\n" + tail


def merge_rul0() -> dict:
    """Write (or move aside) SiMCP's merged RUL0; called before the game starts."""
    pieces = _pieces()
    path = _ours()
    if not pieces:
        if os.path.exists(path):
            dest_dir = os.path.join(content.DISABLED)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, "SiMCP_RUL0-%s.dat" % time.strftime("%Y%m%d-%H%M%S"))
            os.replace(path, dest)
            return {"rul0": None, "moved_aside": dest}
        return {"rul0": None}
    if os.path.realpath(content.FOLDER) != os.path.abspath(content.FOLDER):
        raise NetDesignError("SiMCP's plugin folder is a link; refusing to write there")
    src, base = base_rul0()
    text = merged_text(base, pieces)
    os.makedirs(content.FOLDER, exist_ok=True)
    dbpf.write_dbpf(path, [(puzzle.RUL_TYPE, puzzle.RUL_GROUP, puzzle.RUL0, text.encode("latin-1"))], compress=False)
    puzzle._scan.clear()
    return {"rul0": path, "base": src, "pieces": len(pieces)}


def new_hids(count: int) -> list[int]:
    used = set()
    for d in content._manifest():
        if d.get("kind") == "puzzle_piece":
            used.update(int(h, 16) for h in d.get("hids", []))
    out, h = [], HID_BASE
    while len(out) < count:
        if h not in used:
            out.append(h)
        h += 1
    return out


# ---------------------------------------------------------------- capturing a laid-out piece

_res: dict = {}


def resources() -> dict:
    """(type, group, instance) -> file for network textures, models, tile exemplars and paths, in load order (the
    game's files, then the plugins as the game loads them; later wins). Built once a session."""
    if _res.get("root") == launch.USER_DIR:
        return _res["index"]
    import glob
    from . import gamedata
    main = gamedata._main_dat()
    files = sorted(glob.glob(os.path.join(os.path.dirname(main.path), "SimCity_*.dat"))) if main else []
    root = os.path.join(launch.USER_DIR, "Plugins")
    plugs = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith((".dat", ".sc4desc", ".sc4lot", ".sc4model")):
                plugs.append(os.path.join(dp, f))
    files += sorted(plugs, key=puzzle._load_order_key)
    keep = {(dbpf.T_FSH, G_TEX), (T_PATH, G_PATH_ROAD), (T_PATH, G_PATH_STATIC), (T_S3D, G_MODELS),
            (dbpf.T_EXEMPLAR, G_TILE)}
    idx = {}
    for f in files:
        try:
            d = dbpf.DBPF(f)
        except (OSError, ValueError):
            continue
        for e in d:
            if (e.type, e.group) in keep:
                idx[(e.type, e.group, e.instance)] = f
    _res.update(root=launch.USER_DIR, index=idx)
    return idx


def _read(key) -> bytes | None:
    f = resources().get(key)
    if not f:
        return None
    d = dbpf.DBPF(f)
    return d.read(d.get(*key))


def capture(g, x0: int, z0: int, x1: int, z1: int) -> dict:
    """{(x, z): {piece, rotation, flip, networks: [(type, edges)]}} for the network tiles in the rectangle."""
    p = g.proc
    out: dict = {}
    with networks.occupants(g, networks.T_NETWORK, x0, z0, x1, z1) as items:
        for o in items:
            raw = p.read(o - 4, 0x140)
            x = int(struct.unpack_from("<f", raw, 0x9C)[0] // 16)
            z = int(struct.unpack_from("<f", raw, 0xA4)[0] // 16)
            if not (x0 <= x <= x1 and z0 <= z <= z1):
                continue
            nets = [(raw[0x10C], struct.unpack_from("<I", raw, 0x110)[0])]
            cnt, extra = raw[0x108], struct.unpack_from("<I", raw, 0x114)[0]
            if cnt and extra:
                ab = p.read(extra, 8 * cnt)
                nets += [(t & 0xFF, e) for t, e in (struct.unpack_from("<II", ab, 8 * k) for k in range(cnt))]
            cell = {"piece": struct.unpack_from("<I", raw, 0xFC)[0], "rotation": raw[0x104] & 3,
                    "flip": raw[0x104] >> 7, "networks": nets}
            if (x, z) in out:
                raise NetDesignError("cell (%d, %d) holds two network pieces (e.g. a bridge or an elevated "
                                     "network over another)" % (x, z), "capture ground networks only")
            out[(x, z)] = cell
    return out


def tile_id(base: int, dx: int, dz: int) -> int:
    """A rule's static tile: x (east) in the 0x100s, z (south) in the 0x10s, the zoom in the units."""
    return base + dx * 0x100 + dz * 0x10


def turn_side(k: int, rot: int, flip: int) -> int:
    if not 0 <= k <= 3:
        return k
    if flip:
        k = {0: 2, 2: 0}.get(k, k)
    return (k + rot) % 4


def turn_point(x: float, z: float, rot: int, flip: int) -> tuple[float, float]:
    if flip:
        x = -x
    for _ in range(rot % 4):
        x, z = z, -x
    return x, z


def turn_path(text: str, rot: int, flip: int) -> str:
    """An SC4PATHS text (1.0, 1.1 or 1.2) turned like the tile: every point and entry / exit side. Header: version,
    paths, stop paths (1.1 / 1.2: one more line). A path: "-- name", its numbers (type, class, entry, exit,
    [1.2: one more], point count), the points "x,z,height"; a stop path: "-- name", (US / UK, type, class, entry,
    exit 255), one point."""
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    if not lines or lines[0] != "SC4PATHS":
        raise NetDesignError("not an SC4PATHS text path")
    ver, n_paths, n_stops = lines[1], int(lines[2]), int(lines[3])
    i = 4 if ver == "1.0" else 5
    out = lines[:i]

    def point(ln):
        vals = [float(v) for v in ln.split(",")]
        vals[0], vals[1] = turn_point(vals[0], vals[1], rot, flip)
        return ",".join("%g" % v for v in vals)

    for k in range(n_paths + n_stops):
        out.append(lines[i])
        i += 1
        nums = []
        while i < len(lines) and lines[i] and "," not in lines[i] and not lines[i].startswith("--"):
            nums.append(int(lines[i]))
            i += 1
        stop = k >= n_paths
        e_at, x_at = (3, 4) if stop else (2, 3)
        if len(nums) > x_at:
            nums[e_at], nums[x_at] = turn_side(nums[e_at], rot, flip), turn_side(nums[x_at], rot, flip)
        count = 1 if stop else (nums[-1] if nums else 0)
        out += [str(v) for v in nums] + [point(ln) for ln in lines[i:i + count]]
        i += count
    return "\r\n".join(out) + "\r\n"


def turn_image(im, rot: int, flip: int):
    from PIL import Image
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    for _ in range(rot % 4):
        im = im.transpose(Image.ROTATE_270)          # a quarter turn clockwise: west (left) to north (top)
    return im


def flat_tile_model(tex_instance: int):
    from . import s3d
    verts = [(-8.0, 0.0001, 8.0, 0.0, 1.0), (8.0, 0.0001, 8.0, 1.0, 1.0), (8.0, 0.0001, -8.0, 1.0, 0.0),
             (-8.0, 0.0001, -8.0, 0.0, 0.0)]
    m = s3d.textured_mesh(verts, [(0, 1, 2), (2, 3, 0)], tex_instance)
    m.mats[0].flags = 0x2B                # NAM's flat tiles (0x2A) + alpha test: the road's own transparency
    m.mats[0].textures[0].wrap = (3, 3)
    m.mats[0].textures[0].filters = (1, 1)
    return m


def tile_records(t_id: int, cell: dict, name: str) -> list:
    """Records for SiMCP tile t_id copying the cell's ground tile (textures, a flat model per zoom, the tile
    exemplar, the paths), turned to the cell's rotation."""
    from PIL import Image
    from . import fsh, s3d
    src, rot, flip = cell["piece"], cell["rotation"], cell["flip"]
    recs = []
    for z in range(5):
        raw = _read((dbpf.T_FSH, G_TEX, src + z))
        if raw is None:
            raise NetDesignError("tile 0x%08X has no ground texture for zoom %d (a 3D tile: bridges, elevated "
                                 "pieces and NAM's model tiles cannot be captured yet)" % (src, z + 1))
        w, h, px = fsh.read_first(raw)
        im = turn_image(Image.frombytes("RGBA", (w, h), px), rot, flip)     # keep alpha: the ground shows through
        recs.append((dbpf.T_FSH, G_TEX, t_id + z, fsh.write_argb(w, h, im.tobytes())))
        recs.append((T_S3D, G_MODELS, t_id + z, s3d.write(flat_tile_model(t_id + z))))
    props = [dbpf.Property(0x10, dbpf.PT_UINT32, [0x0B]),
             dbpf.Property(0x20, dbpf.PT_STRING, "SiMCP_tile_%s_%08X" % (content._slug(name), t_id)),
             dbpf.Property(P_RKT3, dbpf.PT_UINT32, [T_S3D, G_MODELS] + [t_id + z for z in range(5)], True)]
    recs.append((dbpf.T_EXEMPLAR, G_TILE, t_id, dbpf.build_exemplar(props)))
    path = _read((T_PATH, G_PATH_ROAD, src)) or _read((T_PATH, G_PATH_STATIC, src))
    if path is not None and path[:8] == b"SC4PATHS":
        recs.append((T_PATH, G_PATH_STATIC, t_id,
                     turn_path(path.decode("latin-1"), rot, flip).encode("latin-1")))
    return recs


def stub_cells(cells: dict, x0: int, z0: int, x1: int, z1: int) -> set:
    """Cells whose networks lead out of the rectangle: the piece's ends, where other networks join it."""
    out = set()
    for (x, z), c in cells.items():
        for _, e in c["networks"]:
            for k, (dx, dz) in enumerate(((-1, 0), (0, -1), (1, 0), (0, 1))):
                if (e >> (8 * k)) & 0xFF and not (x0 <= x + dx <= x1 and z0 <= z + dz <= z1):
                    out.add((x, z))
    return out


def rul0_section(hid: int, name: str, cells: dict, x0: int, z0: int, w: int, h: int, tile_base: int,
                 cost: int, stubs: set = frozenset()) -> tuple[str, dict]:
    """The rule's RUL0 text (origin and handle at the rectangle's north-west cell): static cells drawn with
    SiMCP's tiles; stub cells as "check" cells, which the tool lays as ordinary network tiles from their edges (the
    way NAM's FLEX pieces are laid), so networks can be dragged into them."""
    letters, types, k = {}, {}, 0
    for (x, z) in sorted(cells, key=lambda c: (c[1], c[0])):
        letters[(x, z)] = LETTERS[k]
        types[LETTERS[k]] = (tuple(cells[(x, z)]["networks"]), (x, z) in stubs)
        k += 1
    rows, cons = [], []
    for z in range(z0, z0 + h):
        row = "".join(letters.get((x, z), ".") for x in range(x0, x0 + w))
        rows.append("CellLayout = %s%s" % (row, "<" if z == z0 else "."))
        cons.append("ConsLayout = %s%s" % ("." * w, "<" if z == z0 else "."))
    rows.append("CellLayout = ^" + "." * w)
    cons.append("ConsLayout = ^" + "." * w)
    checks = []
    for ch, (nets, stub) in types.items():
        if stub:
            checks.append("CheckType = %s - %s" % (ch, " ".join("%s: 0x%08X,0xFFFFFFFF check" % (NET_RUL0[t], e)
                                                               for t, e in nets)))
        else:
            checks.append("CheckType = %s - %s" % (ch, " ".join("%s: 0x%08X" % (NET_RUL0[t], e) for t, e in nets)))
    static = [c for c in cells if c not in stubs]
    lines = [";### next file: SiMCP.txt ###", ";%s" % name, "[HighwayIntersectionInfo_0x%08X]" % hid]
    if static:
        first = min(static, key=lambda c: (c[1], c[0]))
        sx0, sz0 = min(c[0] for c in static), min(c[1] for c in static)
        lines.append("Piece = 0.0, 0.0, 0, 0, 0x%08X" % tile_id(tile_base, first[0] - sx0, first[1] - sz0))
    lines += [""] + rows + [""] + checks + [""] + cons + [""]
    if static:
        lines.append("AutoTileBase = 0x%08X" % tile_base)
    lines += ["ReplacementIntersection = 0, 0", "Costs = %d" % cost, ""]
    text = "\n".join(lines)
    for r in (1, 2, 3):
        text += "\n[HighwayIntersectionInfo_0x%08X]\nCopyFrom = 0x%X\nRotate = %d\n" % (hid + r, hid, r)
    return text, letters


def _tile_base(taken_bases: set[int]) -> int:
    idx = resources()
    n = 0
    while True:
        b = TILE_BASE + n * 0x10000
        if b not in taken_bases and not any((dbpf.T_EXEMPLAR, G_TILE, b + o) in idx for o in (0, 0x10, 0x100)):
            return b
        n += 1


def design_piece(g, name: str, x0: int, z0: int, x1: int, z1: int, cost: int | None = None,
                 open_ends: bool = True) -> dict:
    """A new puzzle piece from the ground networks laid in a rectangle of the open city. open_ends: the cells
    whose networks lead out of the rectangle are laid as ordinary network (others can join them there); the rest
    keep the tiles they show now."""
    content._check_name(name)
    x0, x1, z0, z1 = min(x0, x1), max(x0, x1), min(z0, z1), max(z0, z1)
    w, h = x1 - x0 + 1, z1 - z0 + 1
    if w > MAX_SIDE or h > MAX_SIDE:
        raise NetDesignError("a piece is at most %d x %d cells" % (MAX_SIDE, MAX_SIDE))
    cells = capture(g, x0, z0, x1, z1)
    if not cells:
        raise NetDesignError("no networks in that rectangle", "lay them with build_network first")
    if len(cells) > len(LETTERS):
        raise NetDesignError("at most %d network cells in a piece" % len(LETTERS))
    for (x, z), c in cells.items():
        for t, _ in c["networks"]:
            if t >= len(NET_RUL0) or NET_RUL0[t] in ("pipe", "powerline", "subway"):
                raise NetDesignError("cell (%d, %d): %s cannot be in a puzzle piece" % (x, z, NET_RUL0[t]
                                     if t < len(NET_RUL0) else t))
    items = content._manifest()
    if any(d.get("kind") == "puzzle_piece" and not d.get("disabled") and d["name"].lower() == name.lower()
           for d in items):
        raise NetDesignError("a puzzle piece is already called %r" % name, "disable_design it or choose another")
    bases = {int(d["tile_base"], 16) for d in items if d.get("kind") == "puzzle_piece" and d.get("tile_base")}
    tile_base = _tile_base(bases)
    hids = new_hids(4)
    if hids != list(range(hids[0], hids[0] + 4)):
        hids = list(range(max(hids), max(hids) + 4))
    stubs = stub_cells(cells, x0, z0, x1, z1) if open_ends else set()
    static = {k: v for k, v in cells.items() if k not in stubs}
    records = []
    if static:
        sx0, sz0 = min(c[0] for c in static), min(c[1] for c in static)
        for (x, z), c in static.items():
            records += tile_records(tile_id(tile_base, x - sx0, z - sz0), c, name)
    if cost is None:
        cost = 10 * len(cells)
    text, letters = rul0_section(hids[0], name, cells, x0, z0, w, h, tile_base, int(cost), stubs)
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_piece_", name)
    if records:
        dbpf.write_dbpf(path, records, compress=False)
    else:                                    # only open ends: ordinary network, no tiles of its own
        path = ""
    entry = {"name": name, "kind": "puzzle_piece", "file": path, "hids": ["0x%X" % x for x in hids],
             "ring": hids, "tile_base": "0x%08X" % tile_base, "size": [w, h], "cells": len(cells),
             "open_ends": sorted([x - x0, z - z0] for x, z in stubs),
             "cost": int(cost), "from": [x0, z0, x1, z1], "rul0": text,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items.append(entry)
    content._save_manifest(items)
    return dict(entry, note="the piece joins the game's RUL0 when SiMCP next starts the game (quit_game, "
                            "game_launch); then place_puzzle_piece(\"0x%X\", x, z) puts its north-west cell on "
                            "(x, z), its rotations are 0x%X..0x%X" % (hids[0], hids[1], hids[3]))
