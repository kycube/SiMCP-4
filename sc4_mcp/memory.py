"""Reading the game's state straight from memory (no calls into the game).

Addresses are SimCity 4 1.1.641 VAs (the exe is never relocated); see re/agents/app-city/REPORT.md and
notes/LIVE_FACTS.md for how each was found and verified.
"""

from __future__ import annotations

from . import win32

G_APP = 0xB43C94          # cISC4App* (= cSC4App + 0xC)
G_SIMULATOR = 0xB43D5C    # cSC4Simulator* of the open city (cached by the game)
G_TERRAIN = 0xB43CF4      # cISTETerrain*
G_SURFACE_WATER = 0xB43CF0
G_LOT_MANAGER = 0xB43D08  # cISC4LotManager* (= the zone developer + 4)
G_CITY = 0xB43CEC         # cSC4City* of the current city (valid only while app state == 2)
APP_VTABLE = 0xA86AF0     # vtable of the cISC4App interface
CITY_VTABLE = 0xA87620    # vtable of cSC4City (cISC4City at +0)

A_STATE = 0x38            # from the cISC4App pointer: 0 none / loading, 1 region view, 2 city
A_CITY = 0x50

APP_STATES = {0: "none", 1: "region", 2: "city"}

C_ESTABLISHED = 0x25
C_DIFFICULTY = 0x28
C_SAVE_PATH = 0x4C        # cRZString: the city's .sc4 file
C_NAME = 0x74             # cRZString {vtable, begin, end, capacity end, refs}
C_MAYOR = 0x9C
C_DESCRIPTION = 0xC4
C_CELLS_X = 0x118
C_CELLS_Z = 0x11C
C_SIMULATOR = 0x158
C_BUDGET = 0x160

SIM_PAUSE = 0x30
SIM_SPEED = 0x3C
SIM_MODE = 0x40
SIM_DAY = 0xEC

DIFFICULTY = {0: "easy", 1: "medium", 2: "hard"}


def jdn_to_date(jdn: int) -> tuple[int, int, int]:
    """(year, month, day) of a Julian Day Number - the simulator's date format (2451545 = 1 January 2000)."""
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def rz_string(p: win32.Process, addr: int, maxlen: int = 512) -> str:
    begin, end = p.u32(addr + 4), p.u32(addr + 8)
    if not begin or end < begin:
        return ""
    return p.read(begin, min(end - begin, maxlen)).decode("latin-1")


def app_state(p: win32.Process) -> int:
    app = p.u32(G_APP)
    return p.u32(app + A_STATE) if app else -1


def city_pointer(p: win32.Process) -> int:
    """The current city, or 0 unless a city is fully loaded (app state 2)."""
    app = p.u32(G_APP)
    if not app or p.u32(app + A_STATE) != 2:
        return 0
    city = p.u32(app + A_CITY)
    return city if city and p.u32(city) == CITY_VTABLE else 0


def city_basics(p: win32.Process) -> dict | None:
    city = city_pointer(p)
    if not city:
        return None
    sim = p.u32(city + C_SIMULATOR)
    out = {
        "name": rz_string(p, city + C_NAME),
        "mayor": rz_string(p, city + C_MAYOR),
        "established": bool(p.u8(city + C_ESTABLISHED)),
        "difficulty": DIFFICULTY.get(p.u32(city + C_DIFFICULTY), p.u32(city + C_DIFFICULTY)),
        "size_cells": [p.u32(city + C_CELLS_X), p.u32(city + C_CELLS_Z)],
    }
    if sim:
        jdn = p.u32(sim + SIM_DAY)
        y, m, d = jdn_to_date(jdn)
        out.update(date="%04d-%02d-%02d" % (y, m, d), day_number=jdn,
                   speed={0: "slow", 1: "medium", 2: "fast"}.get(p.u32(sim + SIM_SPEED), p.u32(sim + SIM_SPEED)),
                   paused=p.i32(sim + SIM_PAUSE) > 0, hidden_paused=p.i32(sim + 0x34) > 0)
    return out
