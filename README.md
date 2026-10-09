# SiMCP 4

**A fully featured MCP server for the entirety of SimCity 4 Deluxe: an AI agent can play every part of the game
and develop new buildings, lots and tiles for it.**

SiMCP 4 turns SimCity 4 Deluxe Edition (version 1.1.641, the GOG release, Windows) into a set of
[Model Context Protocol](https://modelcontextprotocol.io) tools that any AI agent can use: Claude, OpenAI and
Gemini agents, local models, or your own code. Everything happens in the real game, through the game's own code,
with the game's own rules and prices. It is the sibling of [SiMCP 3000](https://github.com/kycube/SiMCP-3000)
(SimCity 3000 Unlimited).

> **Status: Phases 1-9 and part of 10, 104 tools, tested in the running game.** What each test showed, and the known limits, are in
> [notes/LIVE_FACTS.md](notes/LIVE_FACTS.md); every tool's parameters are in [docs/TOOLS.md](docs/TOOLS.md); what is
> left is in [notes/ROADMAP.md](notes/ROADMAP.md). U-Drive-It is left out for now (the existing mission tools stay).

> SiMCP 4 is a fan project, not affiliated with or endorsed by Electronic Arts or Maxis. SimCity is a trademark of
> Electronic Arts Inc. You need your own copy of SimCity 4 Deluxe; this repository contains no game files.

## What it covers

| Area | Tools |
|---|---|
| **The game** | `game_launch` (unelevated, its own user folder, beside your own game), `game_status`, `quit_game`, `dialog_status` / `close_dialog` (any modal dialog), `set_popups` |
| **Regions** | `list_regions`, `load_region`, `open_tile` (any tile, as Play does), `load_city`, `new_region`, `set_region_layout` / `import_region_terrain` (a whole region from a height map, through the game's own import), `found_city`, `rename_city`, `save_city`, `leave_city`, `saved_city` / `city_thumbnail` (saved cities read from their files), `backup_region` / `rename_region` / `remove_city` / `remove_region` (removed files are moved into SiMCP's backups, never deleted) |
| **Time** | `advance_time` (the game plays at its own speed and pauses exactly on the target day; or exact day stepping), `set_speed`, `set_paused`, `day_night` |
| **Seeing the city** | `city_status`, `map_data` / `tile_info` (34 data layers per cell, plus traffic volume), `network_map` / `find_route` (roads, rails, pipes, power lines and their connections), `lots`, `demand`, `get_budget`, `advisors`, `graphs` / `graph_data` (the Graphs window's history), `city_figures` (the advisors' ~190 figures, read-only), `camera` / `set_camera` / `snapshot` (the game's own picture) - read from the game's memory |
| **Building** | `build_network` (roads to monorail, pipes, power lines: the game's path solver and price), `zone`, `build_menu` / `plop` (every menu building with the menus' own availability rules), `bulldoze`, `plant_trees`, `make_historical`, `terrain_brushes` / `terraform` |
| **Running the city** | `set_tax`, `departments` / `set_department_funding`, `building_funding` / `set_building_funding` (per building, with the measured effect on its service), `ordinances` / `set_ordinance`, `loans` / `take_loan`, `neighbor_deals` / `open_neighbor_deals` / `cancel_neighbor_deal`, `game_options` / `set_play_option`, `graphics_options` / `audio_options` (through the game's own dialogs) |
| **The rest of the game** | `start_disaster` / `disaster_status`, `dispatch` (fire and police), `puzzle_pieces` / `place_puzzle_piece` (interchanges and NAM puzzle pieces), `missions` / `start_mission` / `drive` / `stop_driving` (U-Drive-It), `my_sims` / `move_in_sim` / `my_sim_faces` / `design_my_sim_face`, `cheat` (vetted, logged) |
| **New content** | `design_building` (a new menu item from a Maxis one), `design_model_building` (its own generated 3D model and textures, or your OBJ model), `design_growable_building` (houses, shops, offices and factories the city grows by itself), `design_civic_building` (working police, fire, clinic and school buildings with their own coverage and capacity), `design_reward` (rewards with their own unlock condition), `design_ordinance` (new ordinances) and budget departments on designs, `design_brush` (god-mode terrain brushes), `terrain_look` (the look of all terrain: lush, arid, arctic, autumn), `design_puzzle_piece` (new puzzle pieces from networks laid in a city), `bridges` / `design_bridge` (new bridges from the game's), `design_advice` (advisor messages and news as Lua), `design_tree` (new tree types for the tree menu), `design_car` (new cars in the traffic), `design_park` / `design_prop` / `game_props` (lots laid out with props, trees and ground textures; props shown by hours or dates, animated props), `design_seasonal_tree` (trees that follow the seasons), `content_designs`, `disable_design` |

**Honest play.** Every action goes through the code the player's own tools use: the network tool's solver and
price, the zone tool's rules, the plop tool's placement and the build menus' availability (locked rewards stay
locked), the bulldozer's cost, the game's dialogs and buttons. Tools that need a click on the map (disasters,
dispatch, terrain brushes, the My Sim move-in) use a *virtual pointer*: the bridge answers the city view's own
"where is the mouse" question with the chosen cell for a few seconds, so the real mouse never moves. Cheats are a
separate, explicit tool: only vetted ones, every use logged and counted in `city_status`.

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
| `sc4_mcp/server.py` | the MCP server (`python -m sc4_mcp`; `--transport streamable-http` for URL clients) |
| `sc4_mcp/game.py`, `launch.py`, `bridge.py`, `memory.py`, `regions.py` | the running game; starting it unelevated with SiMCP's own user folder; the bridge client; memory reads; regions and cities from files |
| `sc4_mcp/build.py`, `catalog.py`, `pointer.py`, `terrain.py` | building like the player; the build menus; the virtual pointer; terrain brushes |
| `sc4_mcp/city.py`, `layers.py`, `economy.py`, `history.py`, `luaquery.py`, `dialogs.py`, `view.py` | observation and the budget window; graphs; the advisors' figures; dialogs; camera and snapshots |
| `sc4_mcp/networks.py`, `services.py`, `neighbors.py`, `options.py`, `heightmap.py`, `housekeeping.py` | the network map, routes and traffic; per-building funding and its effect; neighbour connections and deals; play options; region layouts and height-map import; region backups, renames and removals |
| `sc4_mcp/disasters.py`, `udi.py`, `mysim.py`, `cheats.py` | disasters and dispatch; U-Drive-It; My Sims; cheats |
| `sc4_mcp/content.py`, `trees.py`, `vehicles.py`, `lotdesign.py`, `meshimport.py`, `orddesign.py`, `brushdesign.py`, `s3d.py`, `fsh.py`, `gamedata.py` | new buildings, trees, cars, props and lot layouts; OBJ import; ordinances and budget departments; S3D models and FSH textures; reading the game's own data files |
| `sc4_mcp/dbpf.py` | DBPF files: read and write, QFS (RefPack) compression, exemplars and cohorts, LTEXT |
| `sc4_mcp/identity.py` | the supported build and the check that refuses others |
| `sc4_mcp/registry.py`, `guide.md` | tool registration (docstrings become JSON schemas and annotations); the agent guide (`guide` tool) |
| `bridge/` | `simcp4.cpp` (the GZCOM plugin the game loads from SiMCP's user Plugins folder), `simcp4bridge.cpp` (the hot-reloadable inner bridge), `build.bat` |
| `docs/TOOLS.md` | every tool with its parameters (generated by `scripts/gen_tool_docs.py`) |
| `notes/` | `PHASE0.md` (build, environment, decisions), `LIVE_FACTS.md` (verified recipes), `DATA_INVENTORY.md`, `RE_BRIEF.md`, `STATIC_PLAN.md` |
| `re/` | static reverse-engineering helpers (`pe.py`, `dbpf_inventory.py`) and one report per subsystem (`agents/*/REPORT.md`) |
| `live/` | tests against the running game (`t1_bridge.py`, `t2_stdio.py`) |
| `tests/` | offline tests (no game needed); CI runs them and builds the DLLs on Windows |

## Quick start

1. Windows, SimCity 4 Deluxe 1.1.641 (GOG), Python 3.10+, Visual Studio (or its Build Tools) with the C++ x86 tools.
2. `python -m pip install -e .` and `bridge\build.bat`.
3. Register `python -m sc4_mcp` as a stdio MCP server with your client; give it a tool timeout of a few minutes.
4. Ask the agent to call `guide`, then `game_launch`.

`game_launch` starts the game through a junction in `%USERPROFILE%\SiMCP-4` (or `SIMCP4_HOME`) with its own user folder there
(`UserDir`: Regions, settings and a Plugins folder that mirrors yours plus the SiMCP plugin); your own
`Documents\SimCity 4` is never written. If your own game is open, SiMCP's runs beside it.

## Tests

`python -m pip install -e ".[test]"` then `python -m pytest`. With the game installed: `python live/t1_bridge.py`
and `python live/t2_stdio.py`.

## License

MIT (see `LICENSE`). SimCity 4 itself is not included and remains Electronic Arts' property.
