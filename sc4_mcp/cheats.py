"""Cheats: an explicit, logged, vetted tool - not part of honest play (re/agents/cheats, LIVE_FACTS Phase 3).

A cheat runs exactly as typed in the game's cheat box: the cheat code manager [0xB43CAC] slot 22
DoDefaultCheatCodeProcessing(cIGZString line, &id) matches the line (case-insensitive prefix), notifies the
cheat's owner and records it in the game's own cheat history. Only the allow-list below runs (player cheats with
validated arguments); developer and dangerous cheats (CreateException, FPS, Recorder, HeapCheck, debug-gated
ones...) are refused, and free text never reaches the game's command line.

Every use is appended to <SiMCP home>\\cheats.jsonl (time, city, region, game date, cheat), and city_status reports
how many cheats were used in the open city.
"""

from __future__ import annotations

import json
import os
import re
import time

from . import launch, memory

G_CHEAT_MANAGER = 0xB43CAC
FN_RZSTRING_CTOR = 0x578390
STR_FROM_CHAR_LEN, STR_DELETE = 3, 28
CM_PROCESS = 22
LOG = os.path.join(launch.ROOT, "cheats.jsonl")

WORD = re.compile(r"^[A-Za-z0-9_'-]{1,32}$")

# name -> (argument rule, what it does)
ALLOWED = {
    "weaknesspays": (None, "adds 1,000 to the city's funds"),
    "riskymoney": (None, "adds 10,000 to the city's funds; each use raises the chance that it starts a riot "
                         "(mayor mode)"),
    "howdryiam": (None, "every building counts as watered until the city is reloaded"),
    "fightthepower": (None, "every building counts as powered until the city is reloaded"),
    "barstuck": (None, "toggles the game's CheatCoffeeBar growth flag (effect undocumented)"),
    "whattimeizit": ("hour", "sets the time of day of the day/night cycle (0-23), not the simulation date"),
    "stopwatch": ("stopwatch", "the day/night clock: pause, resume, or magnify <1-100> its speed"),
    "showtime": (None, "toggles the small clock panel"),
    "whererufrom": ("word", "renames the city (one word)"),
    "hellomynameis": ("word", "renames the mayor (one word)"),
    "dollyllama": (None, "toggles the llama models"),
    "casper": ("onoff", "automata 'ghost' mode on, or off with 'off'"),
    "gp": ("onoff", "pause when the game window loses focus: on / off"),
}
REFUSED = {"createexception": "raises an exception that ends the game", "fps": "can divide by zero and crash",
           "recorder": "writes files", "heapcheck": "a developer tool", "moolah": "debug only",
           "simdate": "debug only", "plopalllots": "debug only", "plopallbuildings": "debug only",
           "lotplop": "debug only", "buildingplop": "debug only"}


class CheatError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _line(name: str, arg: str) -> str:
    name = name.strip().lower()
    if name in REFUSED:
        raise CheatError("the %s cheat is refused: %s" % (name, REFUSED[name]))
    if name not in ALLOWED:
        raise CheatError("unknown or unvetted cheat %r" % name, "cheats: " + ", ".join(ALLOWED))
    rule = ALLOWED[name][0]
    arg = (arg or "").strip()
    if rule is None:
        if arg:
            raise CheatError("%s takes no argument" % name)
        return name
    if rule == "hour":
        if not arg.isdigit() or not 0 <= int(arg) <= 23:
            raise CheatError("whattimeizit takes an hour 0-23")
        return "%s %d" % (name, int(arg))
    if rule == "word":
        if not WORD.match(arg):
            raise CheatError("%s takes one word (letters, digits, - ' _; up to 32)" % name)
        return "%s %s" % (name, arg)
    if rule == "onoff":
        if arg not in ("", "on", "off"):
            raise CheatError("%s takes 'on', 'off' or nothing" % name)
        return ("%s %s" % (name, arg)).strip()
    if rule == "stopwatch":
        parts = arg.split()
        if parts in (["pause"], ["resume"]):
            return "%s %s" % (name, parts[0])
        if len(parts) == 2 and parts[0] == "magnify" and parts[1].isdigit() and 1 <= int(parts[1]) <= 100:
            return "%s magnify %d" % (name, int(parts[1]))
        raise CheatError("stopwatch takes 'pause', 'resume' or 'magnify <1-100>'")
    raise CheatError("bad rule")


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise CheatError("the game's code failed (slot %d, status %d)" % (slot, r.status))
    return r.ret[0] & 0xFFFFFFFF


def run(g, name: str, arg: str = "") -> dict:
    line = _line(name, arg)
    p, b = g.proc, g.bridge
    basics = memory.city_basics(p)
    if not basics:
        raise CheatError("no city is open", "cheats work in a city")
    b.attach()
    s = b.scratch(0x800)
    text, strobj, idout = s, s + 0x80, s + 0xA0
    p.write(text, line.encode("ascii") + b"\0")
    p.write(strobj, bytes(0x20))
    p.write(idout, bytes(4))
    if not b.call_function(FN_RZSTRING_CTOR, [], this=strobj).ok:
        raise CheatError("could not make the cheat line")
    try:
        _v(g, strobj, STR_FROM_CHAR_LEN, text, len(line))
        _v(g, p.u32(G_CHEAT_MANAGER), CM_PROCESS, strobj, idout)
    finally:
        _v(g, strobj, STR_DELETE, 0)
    cid = p.u32(idout)
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "city": basics["name"], "region": g.region_name(),
             "game_date": basics.get("date"), "cheat": line, "matched": bool(cid)}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"cheat": line, "ran": bool(cid), "effect": ALLOWED[line.split()[0]][1], "logged": LOG,
            "note": "cheats are outside honest play; this use is recorded"}


def used(city: str, region: str | None) -> list[dict]:
    """The logged cheat uses for a city (by name and region)."""
    if not os.path.exists(LOG):
        return []
    out = []
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("city") == city and (region is None or e.get("region") == region):
                out.append(e)
    return out
