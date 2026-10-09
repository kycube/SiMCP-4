"""Puzzle pieces (interchanges, ramps, NAM's prefab pieces): the RUL0 rules the network tool places whole.

The game parses RUL0 (type 0x0A5BCF4B, group 0xAA5BCF57, instance 0x10000000 - the NAM controller's when NAM is
installed) into a hash map at 0xB452B0 (bucket vector at 0xB452B4 / 0xB452B8; node {next, hid, rule}); 0x625380(hid)
looks a rule up. A rule (cIntRule, 0xFC bytes, layout in the NAM DLL's NetworkStubs.h): +0x00 hid, +0x04 preview
pieces {id, rot, flip, x, z offset}, +0x18 / +0x20 min / max cell, +0x94 handle offset (the cell under the
pointer), +0xC8 AutoTileBase, +0xEC / +0xF0 previous / next in its rotation ring (Home / End), +0xF4 / +0xF8 in
its type ring (Tab).

Placing one is what the game's puzzle-piece input control does (vtable 0xAAAF60): preview (0x661260) - origin =
pointer cell - handle; rule 0x608CD0(x, z, cells x, cells z) checks the map bounds, rule 0x6097E0(x, z, tool)
prepares the tool, cSC4NetworkTool 0x62CD50(x, z, hid, 0) tests the piece and GetCostOfSolution gives its cost;
the UI tries the pointer cell and its four neighbours (0xAAAFCC) and walks the rotation ring until one fits. The
click (0x661010) runs the same with 0x62CD50(..., 1) and charges the cost to the budget (WithdrawFunds).
"""

from __future__ import annotations

import os
import re
import struct

from . import build, launch

G_RULES = 0xB452B0
FN_LOOKUP, FN_FITS_MAP, FN_PREPARE, FN_INSERT = 0x625380, 0x608CD0, 0x6097E0, 0x62CD50
R_PIECES, R_MIN, R_MAX, R_HANDLE, R_AUTOTILE, R_RINGS = 0x04, 0x18, 0x20, 0x94, 0xC8, 0xEC
R_UNNAMED, R_STATIC, R_CHECK = 0x28, 0x4C, 0x58             # cell vectors: '+' cells, static cells, checked cells
SNAP = [(0, 0), (1, 0), (0, -1), (-1, 0), (0, 1)]       # the UI's tries around the pointer cell (0xAAAFCC)
RUL_TYPE, RUL_GROUP, RUL0 = 0x0A5BCF4B, 0xAA5BCF57, 0x10000000
HIGHWAY_TOOL = 2                                         # the UI places every piece with the highway tool
C_CELLS_X, C_CELLS_Z = 93, 94                            # city slots


class PuzzleError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


# ---------------------------------------------------------------- the live rules

def rules(g) -> dict[int, int]:
    """hid -> the rule's address, from the game's own table."""
    p = g.proc
    b0, b1 = p.u32(G_RULES + 4), p.u32(G_RULES + 8)
    n = (b1 - b0) // 4
    if not b0 or not 0 < n < 1 << 20:
        raise PuzzleError("the game's puzzle-piece rules are not loaded", "open a city first")
    out = {}
    for head in struct.unpack("<%dI" % n, p.read(b0, 4 * n)):
        node, guard = head, 0
        while node and guard < 10000:
            out[p.u32(node + 4)] = node + 8
            node, guard = p.u32(node), guard + 1
    return out


def rule_info(g, addr: int) -> dict:
    p = g.proc
    d = p.read(addr, 0xFC)
    hid, pb, pe_ = struct.unpack_from("<III", d, 0)
    mn, mx = struct.unpack_from("<ii", d, R_MIN), struct.unpack_from("<ii", d, R_MAX)
    pieces = []
    if 0 <= pe_ - pb <= 16 * 8:
        for a in range(pb, pe_, 16):
            pid, rot, flip, ox, oz = struct.unpack("<IBB2xff", p.read(a, 16))
            pieces.append({"id": "0x%08X" % pid, "rotation": rot, "flip": bool(flip), "offset_m": [ox, oz]})
    rp, rn, tp, tn = struct.unpack_from("<4I", d, R_RINGS)
    cells = set()
    for off, step in ((R_UNNAMED, 8), (R_STATIC, 8), (R_CHECK, 12)):
        b, e = struct.unpack_from("<II", d, off)
        if b and 0 < e - b <= step * 4096:
            raw = p.read(b, e - b)
            cells.update(struct.unpack_from("<ii", raw, i) for i in range(0, len(raw), step))
    if cells:
        mn = (min(c[0] for c in cells), min(c[1] for c in cells))
        mx = (max(c[0] for c in cells), max(c[1] for c in cells))
    return {"hid": "0x%X" % hid, "cells": {"min": list(mn), "max": list(mx)}, "cell_count": len(cells),
            "size": [mx[0] - mn[0] + 1, mx[1] - mn[1] + 1], "handle": list(struct.unpack_from("<ii", d, R_HANDLE)),
            "preview": pieces, "auto_tile_base": "0x%08X" % struct.unpack_from("<I", d, R_AUTOTILE)[0],
            "rotate_prev": "0x%X" % rp, "rotate_next": "0x%X" % rn, "tab_prev": "0x%X" % tp, "tab_next": "0x%X" % tn}


def ring(g, table: dict[int, int], hid: int, off: int) -> list[int]:
    """The ring a rule belongs to, following the link at `off` (+0xF0 rotation, +0xF8 type) from hid."""
    out, cur = [hid], hid
    for _ in range(256):
        a = table.get(cur)
        nxt = g.proc.u32(a + off) if a else 0
        if not nxt or nxt == hid or nxt not in table:
            break
        out.append(nxt)
        cur = nxt
    return out


# ---------------------------------------------------------------- names from the RUL0 text

def _load_order_key(path: str):
    # the game loads a folder's files before its subfolders, each alphabetically (case-insensitive)
    parts = os.path.relpath(path, launch.USER_DIR).lower().split(os.sep)
    return [(1, x) for x in parts[:-1]] + [(0, parts[-1])]


_scan: dict = {}


def _rul0_files() -> list[str]:
    """Plugins holding a RUL0, in load order (scanned once a session: plugins load only at game start)."""
    from . import dbpf
    root = os.path.join(launch.USER_DIR, "Plugins")
    if _scan.get("root") == root:
        return _scan["files"]
    found = []
    for dp, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".dat", ".sc4desc", ".sc4lot", ".sc4model")) or "." not in f:
                path = os.path.join(dp, f)
                try:
                    d = dbpf.DBPF(path)
                except (OSError, ValueError):
                    continue
                if d.get(RUL_TYPE, RUL_GROUP, RUL0):
                    found.append(path)
    _scan.update(root=root, files=sorted(found, key=_load_order_key))
    return _scan["files"]


def active_rul0() -> tuple[str, bytes] | None:
    """The RUL0 text the game uses: the last plugin that has one, else the game's own."""
    from . import dbpf, gamedata
    found = _rul0_files()
    if found:
        path = found[-1]
        d = dbpf.DBPF(path)
        return path, d.read(d.get(RUL_TYPE, RUL_GROUP, RUL0))
    d = gamedata._main_dat()
    e = d.get(RUL_TYPE, RUL_GROUP, RUL0) if d else None
    return (d.path, d.read(e)) if e else None


_SKIP = re.compile(r"^(added|edited|modified|created|updated|fixed|changed|by |last modified|next file|-+$|=+$|#)",
                   re.I)


def parse_names(text: str) -> dict[int, dict]:
    """hid -> {name, group, cost, copy_from} from the RUL0 text: the comment just above each rule (NAM writes the
    piece's name there), the "next file" part it sits in; a rotated copy takes its source's name."""
    out: dict[int, dict] = {}
    group, comments, cur = "", [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(";"):
            c = line.lstrip(";").strip()
            m = re.match(r"#+\s*next file:\s*(.+?)\s*#+", c, re.I)
            if m:
                group = re.sub(r"^[0-9A-Fa-f]{4}_|\.txt$", "", m.group(1)).replace("_", " ")
                comments = []
            elif c and "=" not in c and not _SKIP.match(c):
                comments.append(c)
            continue
        m = re.match(r"^\[HighwayIntersectionInfo_0x([0-9A-Fa-f]+)\]", line)
        if m:
            cur = int(m.group(1), 16)
            out[cur] = {"name": comments[-1] if comments else "", "group": group}
            comments = []
            continue
        if cur is not None and "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip().lower(), val.split(";")[0].strip()
            try:
                if key == "copyfrom":
                    out[cur]["copy_from"] = int(val, 16)
                elif key == "costs":
                    out[cur]["cost"] = int(float(val))
                elif key in ("rotate", "transpose"):
                    out[cur][key] = int(val)
            except ValueError:
                pass
        elif line.startswith("["):
            cur = None
    for hid, d in out.items():                       # rotated / mirrored copies: their source's name
        seen, src = {hid}, d
        while not src.get("name") and src.get("copy_from") in out and src["copy_from"] not in seen:
            seen.add(src["copy_from"])
            src = out[src["copy_from"]]
        if not d["name"] and src.get("name"):
            d["name"] = src["name"]
    return out


_names_cache: dict = {}


def names() -> tuple[str, dict[int, dict]]:
    a = active_rul0()
    if a is None:
        return "", {}
    path, data = a
    key = (path, os.path.getmtime(path) if os.path.exists(path) else 0, len(data))
    if _names_cache.get("key") != key:
        _names_cache.update(key=key, names=parse_names(data.decode("latin-1")))
    return path, _names_cache["names"]


def search(g, query: str = "", group: str = "", limit: int = 40) -> dict:
    table = rules(g)
    path, nm = names()
    q, gq = query.strip().lower(), group.strip().lower()
    hits = []
    for hid in sorted(table):
        d = nm.get(hid, {})
        if q and q not in d.get("name", "").lower() and q != "0x%x" % hid:
            continue
        if gq and gq not in d.get("group", "").lower():
            continue
        hits.append(hid)
    out = []
    for hid in hits[:max(1, min(int(limit), 500))]:
        d = nm.get(hid, {})
        info = rule_info(g, table[hid])
        out.append({"hid": info["hid"], "name": d.get("name", ""), "group": d.get("group", ""),
                    "size": info["size"], "cost": d.get("cost"), "rotations": len(ring(g, table, hid, 0xF0)),
                    "variant": ("rotated %d" % d["rotate"]) if d.get("rotate") else
                    ("mirrored" if d.get("transpose") else "")})
    groups = sorted({d.get("group", "") for d in nm.values() if d.get("group")})
    return {"rules": len(table), "matches": len(hits), "pieces": out, "rul0": path,
            "groups": groups if not (q or gq) else None}


# ---------------------------------------------------------------- placing

def _try(k, t, rule: int, hid: int, ox: int, oz: int, nx: int, nz: int) -> tuple[bool, int]:
    if not k.b.call_function(FN_FITS_MAP, [ox & 0xFFFFFFFF, oz & 0xFFFFFFFF, nx, nz], this=rule).ret[0] & 0xFF:
        return False, 0
    k.v(t, build.NT_RESET)
    k.b.call_function(FN_PREPARE, [ox & 0xFFFFFFFF, oz & 0xFFFFFFFF, t], this=rule)
    ok = k.b.call_function(FN_INSERT, [ox & 0xFFFFFFFF, oz & 0xFFFFFFFF, hid, 0], this=t).ret[0] & 0xFF
    return bool(ok), k.v(t, build.NT_COST) if ok else 0


def place(g, hid: int, x: int, z: int, build_it: bool = True, auto_fit: bool = False) -> dict:
    """Place puzzle piece `hid` with its handle on cell (x, z), as the game's puzzle-piece tool does; auto_fit also
    tries the four neighbouring cells and the piece's other rotations, as the tool does under the pointer."""
    table = rules(g)
    if hid not in table:
        raise PuzzleError("no puzzle piece 0x%X" % hid, "puzzle_pieces lists them")
    city = build._city(g)
    k = build._Caller(g)
    p = k.p
    nx, nz = k.v(city, C_CELLS_X), k.v(city, C_CELLS_Z)
    if not (0 <= x < nx and 0 <= z < nz):
        raise PuzzleError("cell (%d, %d) is outside the city (0..%d, 0..%d)" % (x, z, nx - 1, nz - 1))
    tries = []
    for dx, dz in (SNAP if auto_fit else [(0, 0)]):
        for h in (ring(g, table, hid, 0xF0) if auto_fit else [hid]):
            tries.append((h, dx, dz))
    t = k.v(p.u32(city + build.C_NETWORK_MANAGER), build.NM_GET_TOOL, HIGHWAY_TOOL, 1)
    if not t:
        raise PuzzleError("the game has no highway tool")
    k.v(t, build.NT_ADDREF)
    k.v(t, build.NT_INIT)
    funds0 = k.funds()
    try:
        found = None
        for h, dx, dz in tries:
            rule = table[h]
            hx, hz = struct.unpack("<ii", p.read(rule + R_HANDLE, 8))
            ox, oz = x + dx - hx, z + dz - hz
            ok, cost = _try(k, t, rule, h, ox, oz, nx, nz)
            if ok:
                found = (h, rule, ox, oz, cost)
                break
        if not found:
            return {"placed": False, "hid": "0x%X" % hid, "reason": "the piece does not fit there: something is in "
                    "the way, the ground is too steep or outside the city, or the networks it needs are missing",
                    "tried": len(tries)}
        h, rule, ox, oz, cost = found
        info = rule_info(g, rule)
        out = {"hid": "0x%X" % h, "origin": [ox, oz], "cost": cost,
               "cells": [[ox + info["cells"]["min"][0], oz + info["cells"]["min"][1]],
                         [ox + info["cells"]["max"][0], oz + info["cells"]["max"][1]]]}
        if h != hid:
            out["rotated_to"] = out["hid"]
        if not build_it:
            out.update(possible=True)
            return out
        if funds0 < cost:
            out.update(placed=False, reason="the city cannot pay %d (funds %d)" % (cost, funds0))
            return out
        k.v(t, build.NT_RESET)
        k.b.call_function(FN_PREPARE, [ox & 0xFFFFFFFF, oz & 0xFFFFFFFF, t], this=rule)
        r = k.b.call_function(FN_INSERT, [ox & 0xFFFFFFFF, oz & 0xFFFFFFFF, h, 1], this=t)
        placed = bool(r.ok and r.ret[0] & 0xFF)
        if placed:                                       # the tool's click charges after placing (0x6610A0)
            k.withdraw(cost)
        out.update(placed=placed, charged=funds0 - k.funds())
        return out
    finally:
        try:
            k.v(t, build.NT_RESET)
            k.v(t, build.NT_SHUTDOWN)
        finally:
            k.v(t, build.NT_RELEASE)
