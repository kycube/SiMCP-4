# SiMCP 4

**A fully featured MCP server for the entirety of SimCity 4 Deluxe: an AI agent can play every part of the game
and develop new buildings, lots and tiles for it.**

SiMCP 4 turns SimCity 4 Deluxe Edition (version 1.1.641, the GOG release, Windows) into a set of
[Model Context Protocol](https://modelcontextprotocol.io) tools that any AI agent can use: Claude, OpenAI and
Gemini agents, local models, or your own code. Everything happens in the real game, through the game's own code,
with the game's own rules and prices. It is the sibling of [SiMCP 3000](https://github.com/kycube/SiMCP-3000)
(SimCity 3000 Unlimited).

> **Status: Phase 0 (groundwork).** No MCP tools yet. So far: the supported build is pinned and checked, the game's
> data files can be read and written (DBPF, QFS compression, exemplars, LTEXT), the game's data is inventoried, and
> the reverse-engineering plan is written. Next: the in-game bridge plugin and the first tools.

> SiMCP 4 is a fan project, not affiliated with or endorsed by Electronic Arts or Maxis. SimCity is a trademark of
> Electronic Arts Inc. You need your own copy of SimCity 4 Deluxe; this repository contains no game files.

## What it will cover

| Area | |
|---|---|
| **Regions and cities** | Regions, city tiles, new cities, load / save, back to the region; neighbour connections and deals |
| **Play** | Zoning, every network (roads to monorail, NAM's), every ploppable building, rewards and landmarks, budgets, taxes, ordinances, loans, time (exact steps and real time) |
| **See everything** | Every data layer per cell, every lot and building, demand, budgets, advisors, news, graphs - read from the game's memory, not from screenshots |
| **The rest of the game** | God mode (terrain, disasters), My Sim, U-Drive-It missions, Lua (advisors, tutorials), cheats as an explicit, tracked tool |
| **Content** | New buildings, lots, props and textures written as the game's own formats (exemplars, S3D, FSH) into a dedicated Plugins folder |
| **Experiments** | Reproducible trials and metrics series, with the plugin set pinned |

## Supported build

SimCity 4 Deluxe Edition 1.1.641 (GOG), `Apps\SimCity 4.exe` TimeDateStamp 0x4C12BFB7, with or without the 4GB
(large address aware) patch. `sc4_mcp/identity.py` refuses every other build. The reference environment uses
[sc4pac](https://memo33.github.io/sc4pac/) with the NAM, CAM, SC4Fix and null-45's DLLs; the exact package list is
in [notes/PHASE0.md](notes/PHASE0.md).

GOG registers a Windows XP compatibility layer for the game that makes Windows ask for administrator rights; SiMCP 4
starts the game through a directory junction instead, unelevated (see PHASE0.md).

## Layout

| Path | What |
|---|---|
| `sc4_mcp/dbpf.py` | DBPF files: read and write, QFS (RefPack) compression, exemplars and cohorts, LTEXT |
| `sc4_mcp/identity.py` | the supported build and the check that refuses others |
| `notes/` | `PHASE0.md` (build, environment, decisions), `DATA_INVENTORY.md`, `RE_BRIEF.md`, `STATIC_PLAN.md`, `LIVE_FACTS.md` |
| `re/` | static reverse-engineering helpers (`pe.py`, `dbpf_inventory.py`) and, later, one report per subsystem |
| `tests/` | offline tests (no game needed); CI runs them on Windows |

## Tests

`python -m pip install -e ".[test]"` then `python -m pytest`.

## License

MIT (see `LICENSE`). SimCity 4 itself is not included and remains Electronic Arts' property.
