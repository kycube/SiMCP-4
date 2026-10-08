"""Inventory of SimCity 4's data: every DBPF file of the game (and optionally a Plugins folder).

    python re/dbpf_inventory.py OUT_DIR [--plugins PATH] [--game PATH]

Writes into OUT_DIR (keep it outside the repository; it holds game content):
  files.json        per file: header, record counts by type, compressed counts, bytes
  types.json        per record type: count, files, groups (top), first bytes seen (signature histogram)
  exemplars.jsonl   every exemplar / cohort: file, TGI, parent, exemplar type (0x10), name (0x20), properties
  ltext.jsonl       every LTEXT record: file, TGI, text
  lua/              every Lua record as a .lua file (<file>_<group>_<instance>.lua)
  type0/            type-0 records (UI layouts, INI text...) dumped raw, one file each
  summary.txt       a readable summary
Read-only: never writes next to the game or the plugins.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sc4_mcp import dbpf  # noqa: E402

GAME = os.environ.get("SC4_GAME_DIR") or r"C:\Program Files\GOG Galaxy\Games\SimCity 4 Deluxe Edition"
DBPF_EXT = (".dat", ".sc4", ".sc4lot", ".sc4desc", ".sc4model")


def game_files(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel.split(os.sep)[0] in ("Regions", "__support", "userdocs"):
            continue
        for f in files:
            if f.lower().endswith(DBPF_EXT):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def plugin_files(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(DBPF_EXT):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def sig(data: bytes) -> str:
    head = data[:8]
    if all(32 <= b < 127 for b in head[:4]):
        return head[:4].decode("ascii")
    return head[:4].hex()


def jsonable(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, list):
        return [jsonable(x) for x in v]
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--game", default=GAME)
    ap.add_argument("--plugins")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "lua"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "type0"), exist_ok=True)
    files = [("game", p) for p in game_files(a.game)]
    if a.plugins:
        files += [("plugins", p) for p in plugin_files(a.plugins)]
    finfo = {}
    types = collections.defaultdict(lambda: {"count": 0, "files": collections.Counter(), "groups": collections.Counter(),
                                             "sigs": collections.Counter(), "bytes": 0})
    ex_types = collections.Counter()
    ex_type_by_src = collections.defaultdict(collections.Counter)
    prop_ids = collections.Counter()
    lua_count = ltext_count = ex_count = 0
    errors = []
    with open(os.path.join(a.out, "exemplars.jsonl"), "w", encoding="utf-8") as fex, \
            open(os.path.join(a.out, "ltext.jsonl"), "w", encoding="utf-8") as flt:
        for src, path in files:
            label = os.path.relpath(path, a.game if src == "game" else a.plugins)
            try:
                d = dbpf.DBPF(path)
            except Exception as e:  # noqa: BLE001
                errors.append((label, str(e)))
                continue
            c = collections.Counter(e.type for e in d)
            finfo[src + ":" + label] = {
                "bytes": os.path.getsize(path), "records": len(d), "compressed": sum(e.compressed for e in d),
                "version": "%d.%d idx %d.%d" % (d.header.major, d.header.minor, d.header.index_major, d.header.index_minor),
                "types": {"%08X" % t: n for t, n in c.most_common()},
            }
            short = os.path.basename(path).replace(" ", "_")
            for e in d:
                ty = types["%08X" % e.type]
                ty["count"] += 1; ty["files"][src + ":" + label] += 1; ty["groups"]["%08X" % e.group] += 1
                ty["bytes"] += e.usize or e.size
                want = e.type in (dbpf.T_EXEMPLAR, dbpf.T_COHORT, dbpf.T_LTEXT, dbpf.T_LUA, 0) or ty["count"] <= 50
                if not want:
                    continue
                try:
                    data = d.read(e)
                except Exception as ex:  # noqa: BLE001
                    errors.append((label, "%08X-%08X-%08X: %s" % (e.type, e.group, e.instance, ex)))
                    continue
                ty["sigs"][sig(data)] += 1
                tgi = "%08X-%08X-%08X" % e.tgi
                if e.type in (dbpf.T_EXEMPLAR, dbpf.T_COHORT) and dbpf.is_exemplar(data):
                    try:
                        x = dbpf.parse_exemplar(data)
                    except Exception as ex:  # noqa: BLE001
                        errors.append((label, tgi + " exemplar: %s" % ex))
                        continue
                    ex_count += 1
                    et = x.get(0x10)
                    if isinstance(et, list):    # some plugins store the type as a 1-element list
                        et = et[0] if len(et) == 1 else tuple(et)
                    ex_types[(e.type, et)] += 1
                    ex_type_by_src[src][et] += 1
                    for p in x.props:
                        prop_ids["%08X" % p.id] += 1
                    fex.write(json.dumps({
                        "src": src, "file": label, "tgi": tgi, "kind": x.kind,
                        "parent": "%08X-%08X-%08X" % x.parent, "exemplar_type": et, "name": x.get(0x20),
                        "props": [["%08X" % p.id, dbpf.PT_NAMES.get(p.ptype, hex(p.ptype)), jsonable(p.value)]
                                  for p in x.props]}) + "\n")
                elif e.type == dbpf.T_LTEXT:
                    try:
                        txt = dbpf.parse_ltext(data)
                    except Exception as ex:  # noqa: BLE001
                        errors.append((label, tgi + " ltext: %s" % ex))
                        continue
                    ltext_count += 1
                    flt.write(json.dumps({"src": src, "file": label, "tgi": tgi, "text": txt}, ensure_ascii=False) + "\n")
                elif e.type == dbpf.T_LUA:
                    lua_count += 1
                    with open(os.path.join(a.out, "lua", "%s_%08X_%08X.lua" % (short, e.group, e.instance)), "wb") as f:
                        f.write(data)
                elif e.type == 0:
                    with open(os.path.join(a.out, "type0", "%s_%08X_%08X.bin" % (short, e.group, e.instance)), "wb") as f:
                        f.write(data)
    with open(os.path.join(a.out, "files.json"), "w") as f:
        json.dump(finfo, f, indent=1)
    tout = {k: {"count": v["count"], "bytes": v["bytes"], "files": dict(v["files"].most_common(8)),
                "n_files": len(v["files"]), "groups_top": dict(v["groups"].most_common(10)),
                "n_groups": len(v["groups"]), "sigs": dict(v["sigs"].most_common(8))}
            for k, v in sorted(types.items(), key=lambda kv: -kv[1]["count"])}
    with open(os.path.join(a.out, "types.json"), "w") as f:
        json.dump(tout, f, indent=1)
    with open(os.path.join(a.out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("files %d (game %d, plugins %d), errors %d\n" % (
            len(files), sum(1 for s, _ in files if s == "game"), sum(1 for s, _ in files if s == "plugins"), len(errors)))
        f.write("exemplars+cohorts parsed %d, LTEXT %d, Lua %d\n\n" % (ex_count, ltext_count, lua_count))
        f.write("record types:\n")
        for k, v in tout.items():
            f.write("  %s %-10s %8d records %6d files %6d groups  %12d bytes  sigs %s\n" % (
                k, dbpf.TYPE_NAMES.get(int(k, 16), ""), v["count"], v["n_files"], v["n_groups"], v["bytes"],
                v["sigs"]))
        f.write("\nexemplar type (property 0x10) by source:\n")
        for src, cnt in ex_type_by_src.items():
            f.write("  %s: %s\n" % (src, sorted(((k if k is not None else -1), n) for k, n in cnt.items())))
        f.write("\nmost common property ids:\n")
        for k, n in prop_ids.most_common(80):
            f.write("  %s %d\n" % (k, n))
        f.write("\nerrors:\n")
        for e in errors[:200]:
            f.write("  %s: %s\n" % e)
    print(open(os.path.join(a.out, "summary.txt"), encoding="utf-8").read()[:6000])


if __name__ == "__main__":
    main()
