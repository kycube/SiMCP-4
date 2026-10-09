"""New terrain brushes for god mode: a copy of one of the game's brushes with its own name and reach.

A brush is an exemplar of type 0x27 in group 0x6A01FC2A (god mode lists those with a menu order 0x8A2602B9 and an
icon 0x8A2602B8). It has up to two layers, 0x8A0202xx and 0x8A0203xx: +0 the shape (a heightmap id), +1 a flag,
+2 the radius in metres at each of the 5 zooms, +3 the strength at each zoom, +4 / +5 the mode and operation. A
design scales the radius and strength lists of every layer; shape and operation stay the base brush's.
"""

from __future__ import annotations

import os
import time

from . import content, dbpf

G_BRUSHES = 0x6A01FC2A
LAYERS = (0x8A020200, 0x8A020300)


class BrushError(content.ContentError):
    pass


def design_brush(name: str, base: str = "mountain_default", radius_scale: float = 1.0,
                 strength_scale: float = 1.0) -> dict:
    from . import gamedata, terrain
    content._check_name(name)
    brushes = terrain.god_brushes()
    if base not in brushes:
        raise BrushError("unknown base brush %r" % base, "bases: " + ", ".join(sorted(brushes)))
    if not (0.1 <= radius_scale <= 10 and 0.05 <= strength_scale <= 20):
        raise BrushError("radius_scale is 0.1..10 and strength_scale 0.05..20")
    tpl = dict(gamedata.exemplars(G_BRUSHES))[brushes[base]]
    props = [dbpf.Property(p.id, p.ptype, list(p.values) if isinstance(p.values, list) else p.values, p.multi)
             for p in tpl.props]
    for layer in LAYERS:
        for pid, k in ((layer + 2, radius_scale), (layer + 3, strength_scale)):
            for p in props:
                if p.id == pid:
                    vals = p.values if isinstance(p.values, list) else [p.values]
                    p.values = [float(v) * k for v in vals]
    iid, name_iid = content._new_ids(set(), 2)
    content._set(props, content.P_NAME, dbpf.PT_STRING, "SiMCP" + "".join(w.capitalize() for w in
                                                                        content._slug(name).split("_")) + "Brush")
    content._set(props, content.P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, content.G_SIMCP_NAMES, name_iid], True)
    props = content._drop(props, content.P_DESC_KEY)
    order = [p for p in props if p.id == 0x8A2602B9]
    if order:
        order[0].values = [int((order[0].values[0] if isinstance(order[0].values, list) else order[0].values)) + 1]
    records = [(dbpf.T_EXEMPLAR, G_BRUSHES, iid, dbpf.build_exemplar(props, tpl.parent)),
               (dbpf.T_LTEXT, content.G_SIMCP_NAMES, name_iid, dbpf.build_ltext(name))]
    os.makedirs(content.FOLDER, exist_ok=True)
    path = content._design_path("SiMCP_brush_", name)
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "brush", "file": path, "brush": "0x%08X" % iid, "base": base,
             "radius_scale": radius_scale, "strength_scale": strength_scale,
             "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch; then terraform with "
                            "brush=%r in god mode (before a city is founded)" % brush_key(name))


def brush_key(name: str) -> str:
    return "simcp_" + content._slug(name).lower()


def designed() -> dict[str, int]:
    return {brush_key(d["name"]): int(d["brush"], 16) for d in content._manifest()
            if d.get("kind") == "brush" and not d.get("disabled")}
