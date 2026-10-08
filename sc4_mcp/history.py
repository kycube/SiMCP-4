"""The city's history: the series behind the game's Graphs window (read from memory, no calls into the game).

The history warehouse (city slot 32, global [0xB43DC0], vtable 0xA8CCB4) keeps an STLport map at +0xC (header
node pointer, count at +0x10) from a series id to an STLport list of samples. A sample node is {next, prev, value
int32 +8, cRZDate +0xC (vtable, Julian day +0x10)}, oldest first. Simulators add samples through RecordHistoryData
(slot 12, posted as message 0x89EFA536), so a value appears a moment after the simulator computes it.

Which series exist and what they are called comes from the game's own data: the Graphs window's graph exemplars
(group 0xCA4AD545: property 0x6A4AEE40 series ids, 0x6A4AEEDC line labels, 0x6A4AEEE2 display scale, 0x8A416A99
title text key), the advisor scripts' `game_trends` constants (Lua), and the budget's daily tax-rate series
(0xAABAAA9F + tax group, rate x 10; re/agents/economy). Verified in LIVE_FACTS (Phase 3).
"""

from __future__ import annotations

import functools
import re

from . import gamedata, memory, win32
from .city import TAX_GROUPS

G_HISTORY = 0xB43DC0
HISTORY_VTABLE = 0xA8CCB4
GROUP_GRAPHS = 0xCA4AD545
G_GRAPH_TEXT = 0x6A231EAA
P_SERIES, P_LABELS, P_SCALE, P_TITLE, P_STYLE = 0x6A4AEE40, 0x6A4AEEDC, 0x6A4AEEE2, 0x8A416A99, 0xAA4C0D1B
LUA_CONSTANTS = 0xFF048A3E     # the advisor system's constants script (defines game_trends)
TAX_RATE_BASE = 0xAABAAA9F


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9$]+", "_", text.lower()).strip("_")


@functools.lru_cache(maxsize=1)
def catalogue() -> dict:
    """{"graphs": [...], "series": {id: {"name", "graph"?, "label"?, "scale"?}}} from the game's data files."""
    series: dict[int, dict] = {}
    for m in re.finditer(r"game_trends\.(\w+)\s*=\s*hex2dec\('([0-9a-fA-F]+)'\)",
                         gamedata.lua_source(LUA_CONSTANTS)):
        name = m.group(1).lower()
        name = re.sub(r"^ga?_", "", name)
        series.setdefault(int(m.group(2), 16), {"name": name})
    for g, group in enumerate(TAX_GROUPS):
        series[TAX_RATE_BASE + g] = {"name": "tax_rate_" + group, "scale": 0.1,
                                     "note": "the tax rate in percent x 10, sampled daily"}
    graphs = []
    for inst, ex in gamedata.exemplars(GROUP_GRAPHS):
        ids = ex.get(P_SERIES) or []
        ids = ids if isinstance(ids, list) else [ids]
        labels = ex.get(P_LABELS) or []
        labels = labels if isinstance(labels, list) else [labels]
        scales = ex.get(P_SCALE) or []
        scales = scales if isinstance(scales, list) else [scales]
        key = ex.get(P_TITLE) or []
        title = gamedata.locale_text(key[2], key[1]) if isinstance(key, list) and len(key) == 3 else None
        title = gamedata.money(title or ex.get(0x20) or "graph %d" % inst)
        lines = []
        for k, sid in enumerate(ids):
            label = gamedata.locale_text(labels[k], G_GRAPH_TEXT) if k < len(labels) else None
            label = gamedata.money(label or "0x%08X" % sid)
            scale = scales[k] if k < len(scales) else (scales[0] if scales else 1.0)
            lines.append({"id": sid, "label": label, "scale": scale})
            entry = series.setdefault(sid, {"name": _slug(title + " " + label) if len(ids) > 1 else _slug(title)})
            entry.update(graph=title, label=label)
            if scale != 1.0:
                entry["scale"] = scale
        graphs.append({"title": title, "style": ex.get(P_STYLE), "lines": lines})
    return {"graphs": graphs, "series": series}


def _samples_index(p: win32.Process) -> dict[int, int]:
    """{series id: list sentinel} from the warehouse's map."""
    hw = p.u32(G_HISTORY)
    if not hw or p.u32(hw) != HISTORY_VTABLE:
        return {}
    hdr = p.u32(hw + 0xC)
    count = p.u32(hw + 0x10)
    out: dict[int, int] = {}
    stack, seen = [p.u32(hdr + 4)], 0
    while stack and seen <= count + 1:
        n = stack.pop()
        if not n or n == hdr:
            continue
        seen += 1
        out[p.u32(n + 0x10)] = p.u32(n + 0x14)
        stack.append(p.u32(n + 8))
        stack.append(p.u32(n + 0xC))
    return out


def _samples(p: win32.Process, sentinel: int, limit: int = 5000) -> list[tuple[int, int]]:
    out, node = [], p.u32(sentinel)
    while node and node != sentinel and len(out) < limit:
        out.append((p.u32(node + 0x10), p.i32(node + 8)))
        node = p.u32(node)
    return out


def _date(jdn: int) -> str:
    return "%04d-%02d-%02d" % memory.jdn_to_date(jdn)


def graphs(p: win32.Process) -> list[dict]:
    """The Graphs window: each graph with its lines' latest values (display units: value x scale)."""
    idx = _samples_index(p)
    out = []
    for gr in catalogue()["graphs"]:
        lines = []
        for ln in gr["lines"]:
            s = _samples(p, idx[ln["id"]]) if ln["id"] in idx else []
            d = {"series": "0x%08X" % ln["id"], "label": ln["label"], "samples": len(s)}
            if s:
                d.update(latest=round(s[-1][1] * ln["scale"], 4), date=_date(s[-1][0]))
            lines.append(d)
        out.append({"graph": gr["title"], "lines": lines})
    return out


def find_series(query: str) -> list[int]:
    """Series ids matching an id (0x...), a series name, a graph title or 'graph: label'."""
    cat = catalogue()["series"]
    q = query.strip().lower()
    if re.fullmatch(r"0x[0-9a-f]{1,8}", q):
        return [int(q, 16)]
    exact = [sid for sid, s in cat.items() if q in (s["name"], (s.get("graph") or "").lower(),
                                                     "%s: %s" % ((s.get("graph") or "").lower(),
                                                                 (s.get("label") or "").lower()))]
    if exact:
        return exact
    return [sid for sid, s in cat.items() if q in s["name"] or q in (s.get("graph") or "").lower()]


def series_data(p: win32.Process, query: str, last: int = 24) -> dict:
    ids = find_series(query)
    if not ids:
        return {"error": "no series matches %r" % query,
                "hint": "graph_data lists the graphs and series; ids look like 0x4A5BA3D0"}
    idx = _samples_index(p)
    cat = catalogue()["series"]
    out = []
    for sid in ids[:16]:
        info = cat.get(sid, {"name": "0x%08X" % sid})
        s = _samples(p, idx[sid]) if sid in idx else []
        scale = info.get("scale", 1.0)
        pts = s[-last:] if last > 0 else s
        d = {"series": "0x%08X" % sid, "name": info["name"], "samples_kept": len(s),
             "points": [[_date(j), round(v * scale, 4)] for j, v in pts]}
        for k in ("graph", "label", "note"):
            if k in info:
                d[k] = info[k]
        if scale != 1.0:
            d["scale"] = scale
        out.append(d)
    return {"series": out}


def all_series(p: win32.Process) -> list[dict]:
    """Every series the city keeps (also ones no graph shows), with its name when the game's data names it."""
    cat = catalogue()["series"]
    out = []
    for sid, sent in sorted(_samples_index(p).items()):
        s = _samples(p, sent)
        info = cat.get(sid, {})
        d = {"series": "0x%08X" % sid, "name": info.get("name"), "samples": len(s)}
        if s:
            d.update(first=_date(s[0][0]), last=_date(s[-1][0]), latest=s[-1][1])
        out.append(d)
    return out
