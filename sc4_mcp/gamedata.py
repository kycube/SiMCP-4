"""Reading the game's own data files (read-only; nothing from them is stored in this repository).

Texts come from `English\\SimCityLocale.DAT` (LTEXT records), exemplars and Lua scripts from `SimCity_1.dat`. Each
table is read once per process and cached.
"""

from __future__ import annotations

import functools
import os

from . import dbpf, identity

T_EXEMPLAR = 0x6534284A
T_LUA = 0xCA63E2A3
G_LUA_SYSTEM = 0x4A5E8EF6


@functools.lru_cache(maxsize=1)
def _locale() -> dict[tuple[int, int], str]:
    out: dict[tuple[int, int], str] = {}
    path = os.path.join(identity.game_dir(), "English", "SimCityLocale.DAT")
    try:
        d = dbpf.DBPF(path)
    except OSError:
        return out
    for e in d.find(dbpf.T_LTEXT):
        try:
            out.setdefault((e.group, e.instance), dbpf.parse_ltext(d.read(e)))
        except ValueError:
            pass
    return out


@functools.lru_cache(maxsize=1)
def _locale_by_instance() -> dict[int, str]:
    out: dict[int, str] = {}
    for (_, i), text in _locale().items():
        out.setdefault(i, text)
    return out


def locale_text(instance: int, group: int | None = None) -> str | None:
    """An English string by LTEXT instance (and group, when known)."""
    if group is not None:
        t = _locale().get((group, instance))
        if t is not None:
            return t
    return _locale_by_instance().get(instance)


def money(text: str) -> str:
    """The game's font draws its currency sign as the section sign; return plain $ for readers."""
    return text.replace("§", "$")


@functools.lru_cache(maxsize=1)
def _main_dat() -> dbpf.DBPF | None:
    try:
        return dbpf.DBPF(os.path.join(identity.game_dir(), "SimCity_1.dat"))
    except OSError:
        return None


def exemplars(group: int) -> list[tuple[int, dbpf.Exemplar]]:
    """[(instance, exemplar)] of one exemplar group in SimCity_1.dat."""
    d = _main_dat()
    if d is None:
        return []
    out = []
    for e in d.find(T_EXEMPLAR, group):
        try:
            out.append((e.instance, dbpf.parse_exemplar(d.read(e))))
        except ValueError:
            pass
    return sorted(out, key=lambda x: x[0])


def lua_source(instance: int, group: int = G_LUA_SYSTEM) -> str:
    d = _main_dat()
    e = d.get(T_LUA, group, instance) if d else None
    return d.read(e).decode("latin-1") if e else ""
