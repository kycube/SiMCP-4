# Static-analysis plan

How I split the reverse engineering between static analysis (rules and references: `RE_BRIEF.md`) and live
verification in the running game (results: `LIVE_FACTS.md`). Each topic below has one report
(`re/reports/<topic>/REPORT.md`); every recipe in a report is verified in the running game before a tool relies on
it. Waves are ordered by what the next phase needs; the topics inside a wave are independent of each other.

Starting points that SC3K did not have: the community interface headers (gzcom-dll: method order from the Mac
build), the id catalogue (`sc4-gzids`), the command-system documentation, and a dozen open-source DLLs that call
or patch 1.1.641 at known addresses. So most questions are "confirm and locate", not "discover". If I
approve `sc4-ghidra-symbols` (Maxis' names from the Mac port), it becomes an extra reference for every topic.

## Wave 1 - what the bridge needs (Phase 1)

**framework** - plugin loading and the main loop.
1. The DLL plugin loader (the function using "GZDllGetGZCOMDirector"): which folders it scans (game `Plugins`,
   user `Plugins`, `-UserDir`), subfolders or root only, load order, what happens on a failed load.
2. The director lifecycle as 1.1.641 calls it: `InitializeCOM`, `OnStart`, the framework hooks
   (PreFrameWorkInit ... PostAppShutdown), `AddToTick` / `AddToOnIdle` and on which thread they run.
3. Threads: which thread runs the UI / message pump, the simulation, rendering, the background loader
   (`-backgroundLoader`); what `-CPUCount:1` changes.
4. How code from another thread gets onto the main thread safely (message posting, OnIdle queue).
5. The cheat box / `cIGZCheatCodeManager`: registration and dispatch (also used by commands).

**app-city** - from the app to every simulator and manager.
1. `cISC4App` (GZIID 0x26CE01C0): the implementing class, its vtable, slot check against the header; `GetCity`,
   `GetRegion`, app state (region view / city / loading), `GetDebugFunctionalityEnabled`.
2. `cISC4City`: vtable; getters for every simulator and manager (budget, RCI, demand, traffic, power, water,
   pollution, crime, police, fire, health, education, land value, aura/desirability, ordinances, neighbours,
   disasters, advisors, occupant/lot/zone/network/prop managers, building development); city size, name, mayor,
   established flag, difficulty, date.
3. Where the app and the city live in memory (globals) for the Python side's direct reads.

**commands** - the game's command system and the view's tools.
1. `cIGZCommandServer`: the class, the command registry (id <-> name <-> parameter info), `ListCommands`, how a
   command string is parsed and executed, which thread, how results/output are returned.
2. For PlaceLot, PlaceNetwork, PlaceNetworkIntersection, PlaceZone, Demolish, SetViewTarget, LoadRegion,
   LoadCity, SaveCity, QuitCity: the implementing function, the checks they make (funds, cost charged, terrain,
   availability by city size / reward conditions, zoning rules) compared with the player's tool.
3. View input controls (`cISC4View3DWin`, `cSC4BaseViewInputControl`, `cSC4NetworkTool`): installing a tool and
   feeding it cell coordinates without real mouse input (screen <-> cell picking).
4. Menu buttons: how a UI button id (from the UI layouts) reaches its command (GZWinClickButton path).

**time** - clock, speed and simulation steps.
1. `cISC424HourClock` and the simulation date; pause / speed (SimSpeed* commands), the sim tick and what one
   step advances; messages per day / month / year.
2. A way to advance exactly N days and return (the SC3K AdvanceDay recipe's equivalent), and when the engine has
   finished a step.
3. Randomness: generators, seeding (clock-based?), traffic simulator (NAM) state - for reproducible trials.

## Wave 2 - observation (Phase 2)

**datamaps** - every per-cell layer: terrain altitude (`cISTETerrain`), zones, lots, land value, crime, police /
fire / health / education coverage, air / water / garbage / radiation pollution, traffic volume and congestion,
power, water, desirability per wealth, flammability; grid classes (`cISC4SimGrid`), sizes, value ranges,
how the game's data views read them.

**lots** - lots and buildings: `cISC4LotManager`, `cISC4Lot` (zone, wealth, density, size, facing, capacity,
jobs / residents per wealth, abandoned, historical, construction state), `cISC4OccupantManager` iteration, building
occupants, `cISC4LotConfigurationManager` (the placeable catalogue), building development (growth), RCI demand
and caps, the residential / commercial / industrial simulators.

**economy** - budget, departments, line items, taxes per zone and wealth, loans (bonds), ordinances (incl. the
CAM / custom ordinance host), neighbour deals, monthly and yearly settlement; the Budget window's data.

**advisors-news** - advisors and their messages, the news ticker, city opportunities / petitions (business
deals: casino, army base, missile range, toxic dump...), rewards and landmarks unlocking, My Sim panel,
query dialog contents (incl. what SC4QueryUIHooks adds).

## Wave 3 - the rest of the game (Phases 3-5)

**regions** - `cISC4Region` / `cISC4RegionalCity`: region list, tiles, city sizes, establishment, neighbour
connections and regional demand, region view actions (load city, new city on a tile, delete / reset a city,
region import from bitmap), saving and the `.sc4` save format (a DBPF: which records to read offline).

**god-mode** - terrain tools and brushes before and after establishment, sea level, day/night, flora, the
disaster manager (trigger, follow, end) and dispatch (fire / police / military).

**ui-dialogs** - the window manager (`cIGZWinMgr`): modal detection, reading a dialog's texts and controls, pressing
a button by id, list boxes; every dialog the game can open during play (budget, save prompts, news, advisor
popups, disasters, deals), and the auto-mode policy.

**lua-udi** - the Lua system (`cIGZLuaScriptServer`, `cISCLua`): the C functions the game registers, how advisor /
tutorial / mission scripts run, what LuaExtensions and the Lua sandbox change; **U-Drive-It**: missions (exemplars
type 0x23, Lua), starting a mission, vehicle control input, scoring and rewards.

**cheats** - every registered cheat code (static list; runtime enumeration in the bridge), what each does,
which are debug-only or dangerous (crashes, file writes) and must be refused.

**view-render** - camera (zoom, rotation, centre on a cell), snapshot / album (TakeSnapshot), region thumbnails,
the game's own render-to-image path (for screenshots without the screen), preferences (video, audio, game).

## Wave 4 - content development (content server)

**formats** - exemplar property catalogue (ids, types, meaning; the 0x88EDC900+ LotConfig object rows), building
and prop exemplars' required properties, cohort inheritance, LTEXT names and descriptions, menu icons (PNG),
S3D models (`3DMD`) and FSH textures (`SHPI`, DXT), lot base / overlay textures, plugin load order and instance-id
ranges; what the game needs to show a new building on a new lot in its menus; whether the in-game Lot Editor
(LE) exists in 1.1.641 and how it is opened; network RUL files (read-only first).

## Process

- Each topic starts from `RE_BRIEF.md` and its numbered questions (above, refined with what LIVE_FACTS knows by
  then) and ends in its REPORT.md.
- I verify each recipe live (through the bridge), record it in `LIVE_FACTS.md` with "verified how", mark the
  report item resolved, and keep an open-items list per report until all are closed.
- Dangerous probes stay forbidden (lessons from SC3K): no vtable-call tracing on objects shared between threads,
  no read/write hardware watchpoints; write watchpoints with call chains only on throwaway test cities.
