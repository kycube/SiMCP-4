# Phase 0 (2026-10-08): the build, the environment, the data, the plan

## Decisions

- Project and repository name: **SiMCP 4** (`SiMCP-4`), MIT licence, public on GitHub from the first commit.
  Commits as `kycube <18388061+kycube@users.noreply.github.com>`. Local-only material (scans, dumps, screenshots,
  throwaway scripts, community sources) lives in a workbench folder next to the repository, never in it.
- The game is launched **outside GOG and without elevation** (my call, see "Launching").
- Still to settle before Phase 1: the questions at the end of this file.

## The build (re-verified 2026-10-08)

| | |
|---|---|
| Game | SimCity 4 Deluxe Edition, GOG (product 1207664593, build 51802744985586183, registry `ver` "1.1.641 hotfix") |
| Executable | `Apps\SimCity 4.exe`: FileVersion 1.1.641.0, TimeDateStamp 0x4C12BFB7, ImageBase 0x400000, SizeOfImage 0x7C8000, entry 0x9F15DC, 7,524,352 bytes; built with MSVC 7.x + STLport (PDB path `...\SC4000Projects\Ep1\out\ReleaseSRT\`), RTTI only for ~60 exception/STL classes |
| 4GB patch | applied: SHA-1 `ec64f671e227dc1640e85e3f303b28b0437a5792`, LARGE_ADDRESS_AWARE set. Original kept as `SimCity 4.exe.Backup`, SHA-1 `c5607c745c727630af57b614fdbb71de044ed849`. Exactly 4 bytes differ (0x156 Characteristics 0x10F -> 0x12F, 0x198-0x19A checksum 0 -> 0x73B9B4); clearing the bit and the checksum gives back the original's hash. |
| Identity check | `sc4_mcp/identity.py check_exe()` accepts both files (and any other tool's LAA patch whose normalised hash is the original's) and refuses every other build. |
| Data files (SHA-1) | `SimCity_1.dat` c7d9c1eb..., `_2` b73f7bb1..., `_3` 6b305295..., `_4` 606c4c7f..., `_5` fe9fe872..., `EP1.dat` 0834a17d..., `Sound.dat` 1e6fb9e1..., `Intro.dat` 78e2eb33... (full hashes in the workbench's `phase0/build.json`) |
| Registry | `HKLM\SOFTWARE\WOW6432Node\Maxis\SimCity 4` (`Install Dir`, `IsDeluxe` 1, `Language` English US); GOG key `...\GOG.com\Games\1207664593` (`savegamefolder` = the user folder) |
| User folder | `Documents\SimCity 4` (inside OneDrive): `Plugins`, `Regions`, `HTTPCache`, `SimCity 4.cfg` (a DBPF; last region Timbuktu) |
| Regions | Berlin, Downloads, Fairview, London, New York, San Francisco, Timbuktu. The game folder's own `Regions\` holds the shipped originals (same names); the user-folder copies are what the game plays. Both are protected: never overwritten by tools. |

## Launching

**GOG's compatibility layer forces elevation.** GOG registers `WINXPSP3 HIGHDPIAWARE` for the exe's path (HKCU
and HKLM `AppCompatFlags\Layers`). On this Windows 11 build the WINXPSP3 (and WINXPSP2) layer makes
`CreateProcess` fail with error 740 (elevation required) - so GOG-launched games run as administrator after a
UAC prompt. An elevated game cannot be read or messaged by a normal-user MCP server (integrity levels, UIPI).

Tested with suspended processes (killed before running any game code):
- copies of the exe elsewhere, with no layer or with `HIGHDPIAWARE` or `WIN7RTM`: start unelevated;
- the same copies with `__COMPAT_LAYER=WINXPSP3` (or `WINXPSP2`): error 740; adding `RunAsInvoker` does not help;
- the installed path with any `__COMPAT_LAYER` value (including `RunAsInvoker`): error 740 - the registry entry
  for the path is always merged in.

**Recipe (no change to the game folder or the registry):** a directory junction outside OneDrive,
`%USERPROFILE%\SiMCP-4\game` -> the GOG game folder (first made under `%LOCALAPPDATA%`; moved because a packaged
client sees AppData through a private virtualized copy - see LIVE_FACTS), and the game started through it:
`<junction>\Apps\SimCity 4.exe -CPUCount:1 -w -intro:off -CustomResolution:enabled -r1024x768x32` with working
directory `<junction>\Apps` and `__COMPAT_LAYER=HIGHDPIAWARE` (our shell's own `DetectorsAppHealth` would otherwise
be inherited). The path no longer matches GOG's entry, so the game runs unelevated without the XP layer. The
junction must never be inside OneDrive (it would try to sync the 900 MB game folder). Removing it (`rmdir`, not a
recursive delete) removes only the link.

Command-line switches present in the exe (strings near the parser): `-w`/`-f`, `-r<W>x<H>x<bpp>`,
`-CustomResolution:enabled`, `-intro:off`, `-CPUCount:`, `-CPUPriority:`, `-UserDir:`, `-audio/-music/-sound/-radio`,
`-d:directx|dx|soft|opengl`, `-IgnoreMissingModelDataBugs`, `-ExceptionHandling`, `-writeLog`, `-backgroundLoader`,
`-LuaScript:"<path>"` and `-NetCommandGenerator:enabled` (see "The game's own command system").

## The windowed run (2026-10-08 14:10, verified)

- Started through the junction as above: came up unelevated (our normal-user process could open it for reading).
- Window: class `GDriverClass--DirectX`, title **"SC4Fix r7"** (SC4Fix renames it), client area exactly 1024x768;
  the region view of **Timbuktu** (the last region in the .cfg) with its tutorial cities, ~20 s after launch,
  18 threads, ~187 MB private memory at that point.
- All 12 plugin DLLs loaded from the user Plugins folder (in this address order): CustomBudgetDepartments,
  memo.lua-sandbox, memo.transparent-texture-fix, NAM, SC4CustomOrdinanceHost, SC4DBPFLoading, SC4Fix,
  SC4LegalizeGamblingUpgrade, SC4LuaExtensions, SC4QueryUIHooks, SC4ResourceLoadingHooks, AdvancedWaterManagement.
- **`NAM.log` now says "The 4GB patch is installed."** (the 13:51 run before the patch said it was not).
- DLL logs of this run (what each one hooks):

| DLL | Log |
|---|---|
| NAM DLL 1.3.1 | 4GB patch installed; no NAM.ini (defaults); patches: Draggable Diagonal Streets, Disable auto-connect for RHW and Streets, Tunnels for RHW/Street/Lightrail, Ferry Bridge Height, RUL2 Engine, Network Slopes, FLEX Puzzle Piece RUL0, Eternal Commute Loop; skipped DirtRoad/RHW Access |
| SC4DBPFLoading 2.1.0 | disabled the built-in DBPF loading debug code; patched the DBPF Open header check; hex missing-plugin message; cRZFile hooks; `.SC4*` plugin scan patch |
| SC4LuaExtensions 1.5.0 | replaced the Maxis Lua print overrides; Lua package script name patch; cGZLuaScriptServer hooks; LuaScriptServer `print` and `hex2dec` |
| SC4ResourceLoadingHooks 2.0.1 | exemplar factory proxy; 30 exemplar patches for 30 exemplars |
| SC4CustomOrdinanceHost 1.0.1 | 1 ordinance exemplar found in `Plugins\140-ordinances\` |
| SC4QueryUIHooks 2.7.1 | query UI hooks |
| AdvancedWaterManagement 1.0.0 | water building query UI hook |
| memo Lua Sandbox 1.0.0 | no ini (defaults); Lua sandbox patch |
| memo Transparent Texture Fix 1.0.0 | patch installed |
| SC4CustomBudgetDepartments 1.1.0, SC4LegalizeGamblingUpgrade 1.0.0 | version line only |
| SC4Fix 1.0.7 | no log (window title "SC4Fix r7") |

- I closed the game from its own menu; no `*_stkdmp.txt`, nothing new in the game folder apart from the
  game's own `<computer>-config-log.txt` (it holds the Windows user and computer names: never commit it).

## Environment pin: plugins (sc4pac lock file, 2026-10-08)

Profile 1 of sc4pac (memo33's package manager; channels memo33.github.io/sc4pac, sc4pac.simtropolis.com,
sc4evermore). The profile's `sc4pac-profiles.json` holds a sign-in token and is never read or copied. Explicitly
selected: `cam:colossus-addon-mod`, `nam:network-addon-mod`, `null-45:startup-performance-optimization-dll`,
`simmaster07:sc4fix`. Global variants: CAM yes (current), drive side right, road style US, night mode standard,
NAM current, traffic simulator capacity **low**, Maxis highway style default, airport capacity medium, canals CAL,
automata controller standard-persistent, one-way arrows single, universal commercial cap standard, edition
Windows-digital. Installed (44):

| Package | Version | Variant |
|---|---|---|
| cam:colossus-addon-mod | 3.1.1 | CAM yes, current |
| cam:colossus-addon-mod-core | 4.0.1 | |
| cam:sc4-system-integration-module | 4.0.1 | |
| cam:ordinances | 3.3.0-2 | |
| cam:universal-commercial-cap-fix | 2.0.0-1 | cap standard |
| config:sc4-edition | 1 | Windows-digital |
| config:sc4-edition-windows-digital | 1.1.641 | |
| cyclone-boom:save-warning | 1.0 | |
| heinbloed4711:hi-tech-missing-high-wealth-jobs | 1.11-1 | CAM yes |
| memo:i-r-fix | 1.0.0-2 | |
| memo:lua-sandbox-dll | 1.0.0 | |
| memo:transparent-texture-fix-dll | 1.0.0-2 | |
| nam:network-addon-mod | 50,49 | current |
| nam:network-addon-mod-core | 50,49 | current |
| nam:controller | 50,49 | current, right |
| nam:dll | 1.3.1 | |
| nam:traffic-simulator | 50,49 | current, capacity low |
| nam:textures | 50,49 | right, default highway, current, standard night, US |
| nam:automata-controller | 50,49 | current, standard-persistent |
| nam:bridges, data-views, ground-light-rail, high-speed-rail, hybrid-railway, real-expressway, real-highway, real-railway, network-widening-mod, street-addon-mod | 50,49 | current |
| nam:canals | 50,49 | current, CAL |
| nam:maxis-highway | 50,49 | current, default |
| nam:maxis-transit-lots | 50,49 | current, airport medium |
| nam:one-way-arrows | 50,49 | current, single |
| null-45:startup-performance-optimization-dll (SC4DBPFLoading) | 2.1-2 | |
| null-45:query-tool-ui-extensions-dll | 2.7.1 | |
| null-45:sc4-resource-loading-hooks | 2.0.1-1 | |
| null-45:lua-extensions-dll | 1.5 | |
| null-45:custom-budget-departments-dll | 1.1 | |
| null-45:custom-ordinance-exemplar-host-dll | 1.0.1-2 | |
| null-45:advanced-water-management-dll | 1.0 | |
| null-45:legalize-gambling-ordinance-upgrade-dll | 1.0.0-1 | |
| scoty:zoning-mod-maxis | 2.0.0 | |
| simmaster07:sc4fix | 1.0.7-2 | |
| t-wrecks:maxis-prop-names-and-query-fix | 2.0 | |

Plugins layout: numbered category folders `050-load-first`, `060-config`, `140-ordinances`, `150-mods`,
`770-network-addon-mod`; the DLLs sit in the Plugins root as symbolic links into their package folders and each
writes a `.log` next to itself. Experiments will record this pin (read from the lock file at run time) in their
metadata.

## The game's own command system (static, 2026-10-08; to verify live in Phase 1)

SC4 1.1.641 contains Maxis' test-automation command server (`cIGZCommandServer`): named commands with parameters,
reachable from Lua test scripts (`-LuaScript:`), from a TCP listener (`-NetCommandGenerator:enabled`,
`cRZNetCommandGenerator/1.0`, port 50020 according to the community documentation; it accepts connections from
other machines, so SiMCP 4 will not use it) and from the cheat box. Strings confirmed in the exe:
`kCommandID_LoadRegion`, `LoadRegion`, `PlaceLot`, `PlaceLotTool`, `ListCommands`, `-LuaScript:`,
`NetCommandGenerator`. The community documents 192 commands (56 app, 122 city, 14 region): app (ExecuteCheat, GamePause, TakeSnapshot,
GetAppState, GZWin* window commands: click a button by id, wait for a window, select a list item...), tools
(PlaceLot, PlaceNetwork, PlaceNetworkIntersection, PlaceZone, Demolish, SetViewTarget), city (every tool, zoom,
rotate, speed, SaveCity, QuitCity, city name/mayor/established, query tools, dialogs) and region (LoadRegion,
LoadCity, QuitGame). The bridge can run these in-process through the command server - the game's own entry points
for most actions - and must vet each one for honest play (e.g. whether `PlaceLot` charges and respects
availability like the menus do; if not, it is a cheat-class tool).

## Community sources (read-only reference, in the workbench)

Shallow clones, 44 MB: nsgomez/gzcom-dll (LGPL-2.1; 291 headers incl. 202 cISC4*/cIGZ* interfaces, vtables
"taken from the Mac vtable"), nsgomez/sc4fix (MIT), 0xC0000054 (null-45): sc4-gzids (Apache-2.0: class, interface,
message and type ids), sc4-game-command-documentation (GPL-3.0), sc4-network-game-command (GPL-3.0),
sc4-lua-test-scripts (GPL-3.0), sc4-dll-utilities (LGPL-2.1), sc4-gzcom-dll-template (MIT, vendors an MIT-era
gzcom-dll), and the sources of every installed DLL: sc4-dbpf-loading (LGPL-2.1), sc4-query-ui-hooks,
sc4-resource-loading-hooks, sc4-lua-extensions, sc4-custom-budget-departments, sc4-custom-ordinance-host
(LGPL-3.0), sc4-advanced-water-management, sc4-legalize-gambling-ordinance-upgrade (MIT); NAMTeam/nam-dll
(LGPL-3.0); memo33 transparent-texture-fix-dll and sc4-lua-sandbox-dll (LGPL-3.0).

Licence rule for this MIT repository: facts (interface layouts, ids, addresses, command names) are restated in our
own words and code; no LGPL/GPL source is copied in. MIT/Apache-2.0 material may be included with its notice.
How the bridge DLL uses gzcom-dll (submodule vs our own minimal declarations) is decided in Phase 1.

Not fetched (large; waiting for my OK): 0xC0000054/sc4-ghidra-symbols (187 MB, Apache-2.0) - symbol information
extracted from the Mac PowerPC port, i.e. Maxis' own function and class names.

## Phase 0 deliverables

- `sc4_mcp/dbpf.py` (DBPF read/write, QFS, exemplars/cohorts, LTEXT; round-trip tests), `sc4_mcp/identity.py`.
- `notes/DATA_INVENTORY.md` (the game's data), `notes/RE_BRIEF.md` (rules for static-analysis agents),
  `notes/STATIC_PLAN.md` (the static-analysis plan), `re/pe.py` + `re/dbpf_inventory.py`.
- Offline tests (`python -m pytest`) and CI on windows-latest.

## Decisions taken before Phase 1 (2026-10-08)

1. **Bridge location: SiMCP's own user folder.** The game is started with
   `-UserDir:%USERPROFILE%\SiMCP-4\UserDir\`; its `Plugins` mirrors the player's Plugins root (a junction per
   category folder, a symbolic link per DLL, a copy per INI - rebuilt at each launch by `sc4_mcp/launch.py`) plus
   `simcp4.dll`; it has its own `Regions`, `SimCity 4.cfg` and DLL logs. The player's Documents\SimCity 4 is never
   written. (sc4pac's handling of unknown files in Plugins therefore does not matter.)
2. **sc4-ghidra-symbols: approved** and fetched (shallow, 12 MB). Its `SimCity4.gdt` was decoded offline into
   the workbench (`ghidra\vftables.txt`, `classes.txt`, `types.json`): 357 vtables named slot by slot, 449 class
   layouts from the Mac build. See RE_BRIEF.md for the ABI caveats.
3. **Fixture: a new region "MCP Test"** in SiMCP's user folder (my choice, because of CAM/NAM):
   `region.ini` + an 8x4 `config.bmp` (one large, two medium, eight small tiles; flat new land). Experiments
   record the plugin pin.
4. **I also play unelevated**: desktop shortcuts "SimCity 4 (no admin)" (full screen) and "(no admin,
   windowed)" start the game through the junction with the player's normal user folder. sc4pac does not need the
   game elevated (it only writes the Documents Plugins folder).

The C++ toolchain is already there: Visual Studio Community 2022 (17.13) with the x86 toolset that built
SiMCP 3000's bridge, plus Build Tools 2019.
