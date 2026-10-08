# Facts measured in the running game

Heap addresses change per run; code addresses do not (the exe is never relocated). Each entry says how it was
verified. Where a static report disagrees with this file, this file wins.

## Session 2026-10-08 (Phase 0: one windowed run, no bridge)

- **Unelevated launch through a junction** works: `%LOCALAPPDATA%\SiMCP-4\game` (later moved to
  `%USERPROFILE%\SiMCP-4`, see "AppData is virtualized" below) -> the GOG folder, game started
  as `<junction>\Apps\SimCity 4.exe -CPUCount:1 -w -intro:off -CustomResolution:enabled -r1024x768x32`, cwd
  `<junction>\Apps`, `__COMPAT_LAYER=HIGHDPIAWARE`. Verified: no error 740, the process opened for reading by a
  normal-user process, region view shown. (Through the real path every launch fails with error 740 because of
  GOG's WINXPSP3 layer; see PHASE0.md.)
- Main window: class `GDriverClass--DirectX`, title `SC4Fix r7`, client 1024x768 (Win32 client rect). Other windows
  of the process: `Win32ClipboardSupportClass` (hidden), IME windows.
- Start-up to the region view (Timbuktu, from the .cfg) in under 20 s with `-intro:off`.
- Plugin DLLs are loaded from the user Plugins root (all 12 seen as modules); `NAM.log` reports the 4GB patch.
- Quitting from the game's own menu leaves no stack dump.
- Without GOG's XP layer the game's config log reports `osVersion = Windows NT 6.2` and `memory = 4096` (with the
  layer: NT 5.1 and 1024), so its graphics rules pick "high memory" (texture quality / building variety high).

## Session 2026-10-08 (Phase 1 start)

- **`-UserDir:<path>\` works** (`-UserDir:C:\Users\<u>\AppData\Local\SiMCP-4\UserDir\`, no quotes, trailing
  backslash): on first start the game created `HTTPCache` and copied the seven shipped regions from the install's
  `Regions` folder into `<path>\Regions`, and it loads plugin DLLs from `<path>\Plugins` only - nothing in
  Documents\SimCity 4 was touched (checked with file times).
- **A relative symbolic link whose target crosses a junction does not resolve**: the mirror first copied sc4pac's
  relative DLL links (`150-mods\...\X.dll`) next to a junction `150-mods` -> the real folder; every link was
  dangling, no DLL loaded (window title "SimCity 4" instead of "SC4Fix r7", no DLL logs). Links to the absolute
  file path work: all 12 DLLs loaded from the mirror and logged into it.
- **Only one instance**: a second `SimCity 4.exe` started while one runs exits within seconds, before loading
  plugins. Cause (re/agents/framework): the named mutex "SimCity 4 Mutex"; Maxis' own `-AllowMultipleInstances`
  switch skips the check - verified: SiMCP's instance ran beside the player's elevated one for an hour.
- **Explorer applies GOG's compatibility layer through the junction**: a desktop shortcut whose target is
  `<junction>\Apps\SimCity 4.exe` started the game elevated (a normal-user `taskkill` got "Access is denied"),
  while `CreateProcess` on the same path from our launcher does not elevate. The shortcuts were changed to run
  `cmd.exe /c ""<junction>\Apps\SimCity 4.exe" -CPUCount:1 -f"` (minimised console) - NOT YET TESTED.
- **Region files** (`sc4_mcp/regions.py`): every one of the 416 city files in the seven shipped regions parses.
  Region-view record (type 0xCA027EDB, group 0xCA027EE1) versions: 1.13 (cities saved by the game: name at 0x40,
  mode byte 0x3F, mayor rating / stars / tutorial at 0x24..0x26, GUID 0x27), 1.10 (name at 0x3F) and 1.9 (name
  at 0x3B) for the unfounded "New City" tiles; tile x/y at 0x04/0x08, size at 0x0C/0x10, R/C/I populations at
  0x14..0x1C. Shipped region names are LTEXT tokens (`Name = #0x8c3a9773`) resolved from English\SimCityLocale.DAT.
  Matches the game: Timbuktu's founded cities are the four tutorials, Berlin's Konradshohe / Spandau / Tegel.

## Session 2026-10-08 (Phase 1: the bridge and the first tools)

All in SiMCP's own instance (`-UserDir`, beside the player's open elevated instance via `-AllowMultipleInstances`).
Scripts: `live/t1_bridge.py`, `live/t2_stdio.py`.

- **Plugin lifecycle** (simcp4.log): InitializeCOM, OnStart, AddHook, then the hooks PreFrameWorkInit / PreAppInit /
  PostAppInit, all on the main thread (one thread id). In PostAppInit: framework->Application() + QI 0x26CE01C0
  gave cISC4App 0x02CE0020 = cSC4App+0xC (cIGZApp 0x02CE0040 = +0x2C), equal to the global `[0xB43C94]`, vtable
  0xA86AF0 (re/agents/app-city confirmed); message server 2 and command server from GetSystemService.
- **Inner bridge**: loaded by the plugin with LoadLibraryW on the main thread. x86 `__stdcall` exports are
  decorated (`_SimcpBridgeAttach@4`): GetProcAddress needs `/EXPORT:` aliases. Ping answers on the main thread;
  calling address 0x10 returns status -100 (0xC0000005 caught) and the game keeps running; unload + load (hot
  reload, new content-addressed copy) works.
- **cISC4App::GetAppState** (slot 25) = `[[0xB43C94]+0x38]`: 1 in the region view, 2 in a city.
- **The game's command server** (slot 19 ExecuteCommand(string, len, out), slot 24 output -> text through a
  cRZString made with the game's ctor 0x578390 and destroyed with its slot 28): output is "<values> <status>",
  e.g. `GetAppState` -> "1 0", `GetDateAndTime` -> "\"10/8/2026 15:18:09\" 0", `GetFrameRate` -> "1451.4 0" (region
  view, busy loop), `GetCitySize` -> "64 64 0"; an unknown command returns status 2. `ListCommands` prints nothing
  into the output (status 0, text "0").
- **LoadRegion "<folder>"** (run deferred) switches regions in 0.2-1.9 s; the region object (cISC4App slot 35)
  slots 3 / 5 (GetName / GetDirectoryName) return cRZStrings: "MCP Test" - the game accepted SiMCP's region files.
- **LoadCity** (region handler 0x7AF4B0, verified in code and live): an empty name loads the first *unfounded*
  tile of the size (founded cities are skipped); a name loads the *founded* city of that name. `LoadCity "" small
  empty` opened a 64x64 "New City" in MCP Test (15 s the first time, 1.7 s after); `LoadCity "Making Money
  Tutorial" any full` the founded tutorial (128x128, mayor Defacto, 2008-11-03) in 1.9 s; Konradshohe (Berlin,
  mayor Knut, hard, 2026-01-27) in 1.9 s.
- **QuitCity 1** goes back to the region view without the dialog (0.2-2.3 s).
- **City fields from memory** match the game's own commands: name `[city+0x74]` cRZString = GetCityName, cell
  count +0x118/+0x11C = GetCitySize (64 64), established byte +0x25 = GetCityEstablished (0 for a "New City").
- **Simulator** `[0xB43D5C]`, vtable 0xAB2FB8; ms per day [2000, 1000, 50] (the "Main Simulator" exemplar); the
  date is a Julian Day Number at +0xEC (a new tile starts at 2451545 = 2000-01-01); in Konradshohe right after
  loading the agent lists hold 9 one-shot, 34 day, 1 week, 26 month, 2 year and 23 idle agents. Time also runs in
  god mode (an unfounded tile's date moved on).
- **Exact day stepping** (bridge OP_STEP_DAYS, `advance_time`): HiddenPause (sim slot 10) for the duration; each
  step = AdvanceTime 0x702A80, restart the agent budget timer S+0x198 (cRZTimer::Restart 0x89058F) with S+0x78 = 50,
  RunAgents 0x7038B0; ms-per-day S+0x80 = 0 while stepping (restored). One step per day. Konradshohe: 30 days right
  after loading in 0.45 s, 365 days in 4.5 s (80 days/s), date exactly +365 (2026-01-27 -> 2027-02-26).
  Learned on the way: writing the granularity S+0x7C = 0 does not lift the day throttle; without restarting the
  budget timer RunAgents handles one agent per call (~2000 steps per day); right after a load some day agent stays
  unfinished for a few seconds whatever the number of steps (it waits for work outside the simulator), so stepping
  must yield to the game's loop instead of spinning.
- **quit_game** (cISC4App slot 10 RequestQuit(0, 0)): the game exits in 2.0 s with no dialog, writes its .cfg into
  SiMCP's user folder, no stack dump.
- **Open: SiMCP's window shows black** while the player's (minimised, elevated) instance runs: the game renders
  (GetFrameRate 26 in a city, frame count rising) and its window is on top, but the screen shows black with a white
  box top-left; the pause-on-focus-loss flag (cSC4App+0x5D1) was 0. To retest with a single instance; screenshots
  will use the game's own snapshot path anyway.

## Session 2026-10-08 (Phase 2: observation, in Konradshohe)

- **Display**: SiMCP's window renders normally when it is the only instance; started as a second instance
  (`-AllowMultipleInstances`) beside another running copy it stays black (it still simulates and answers; frame rate
  26) - also after the other copy exits. Screenshot of the city view and the region view taken when alone.
- **Date vs the game's UI**: memory 2026-02-08 vs the UI's 2/9/26 a second later (slow speed: 2 s per day);
  `advance_time(30)` from 2026-02-11 -> 2026-03-13 in 0.51 s, the UI then shows 3/13/26.
- **Data layers** (`sc4_mcp/layers.py`, re/agents/datamaps): all 34 grids read (type = low 12 bits of the CLSID at
  +0x10: 0x49B9E603 -> s8). Konradshohe (128x128): zones u8.. tract 1 (values 0, 2, 3, 5, 9, 14, 15), land value u8
  tract 2, slope f32 tract 8, crime / police / fire tract 2, flammability tract 1, air / water pollution s16 tract 2,
  radiation all 0, power u8 tract 1 with only 0 / 1 / 2 (3443 powered, 62 wired-unpowered cells), water u8 values 0,
  1, 3, 9, 11, 15 (bits), mayor rating s8 tract 4, residential population / EQ / HQ tract 4. Terrain 129x129 vertices,
  sea level 250.0, altitudes 192-283.
  Open: the "garbage" grid (pollution type 2) reads 15450 at the coal plant and -32768 minimum - meaning to verify.
- **Budget** (re/agents/economy): funds int64 `[B+0x28]` = 206 = GetTotalFunds (slot 6); tax rates floats
  `[B+0x70+g*0x80]` (8.9 / 7.0 / 9.0...); monthly income 3327 / expense 3987 (slots 16 / 14, int64 in edx:eax),
  last month 3329 / 3957, end-of-year estimate 39926 / 47814; no loans.
- **Demand**: DemandSim slot 6 (id, 0x20000) returns cSC4Demand objects (vtable 0xAA2758) for all 12 groups; active
  demand +0x34 (R$ 15951), cap +0x44, max 54000 / min -10000. Residents `[[0xB43DA4]+0xA4]` = 15025.
- **Lots** (re/agents/lots): the lot list `[LM+0x5C]` walks 741 lots = the count `[LM+0x64]`, every one vtable
  0xAB19B0; states 730 occupied, 6 under construction, 4 ready, 1 abandoned; the first is the 4x4 plopped coal plant
  at (0..3, 32..35), building type 0x1F4D0000, and BuildingDevelopmentSim slot 38 names it "Coal Power Plant" (slot
  37: "Up64x64_CoalPowerPlant_1F4D"); the cell table `[LM+0x50]` gives the same lot at (1, 33).
- **Advisors** (re/agents/advisors-ui): the advisor map `[sys+0x4C]` holds ids 1-5 (MySim), 21-30; each advisor's
  record vector I+0x7C..+0x80 lists all its advices (Utilities 116, Fluffy News 266...); active ones have flag 2.
  Titles and messages come out detokenized ("Good gravy Mayor Knut ... in Konradshohe"); moods 0 / 1 / 3 / 5 / 7.
  The current-advice list node layout guessed by the report (advice at node+0xC) is wrong - the record vector is used.
- **AppData is virtualized for this development session**: everything the session's processes wrote under
  `%LOCALAPPDATA%\SiMCP-4` (the junction, SiMCP's user folder) physically lives in
  `AppData\Local\Packages\Claude_<id>\LocalCache\Local\SiMCP-4` (MSIX file-system virtualization of the client app's
  process tree), so Explorer, the player's shortcuts and any MCP client started outside that app did not see it (a
  diagnostic .cmd started from Explorer: `cd` to the junction failed, errorlevel 3). SiMCP's home moved to the profile
  root `%USERPROFILE%\SiMCP-4` (not virtualized, not in OneDrive; `SIMCP4_HOME` overrides). The old copy was left
  in place.
- **The "no admin" shortcuts work** after the move: Explorer -> `cmd.exe /c ""%USERPROFILE%\SiMCP-4\game\Apps\
  SimCity 4.exe" -CPUCount:1 -w"` started the game unelevated (opened read/write by a normal-user process), with the
  player's own Plugins (NAM.log in Documents updated, title "SC4Fix r7") and without the SiMCP plugin.

## Session 2026-10-08 (Phase 2: economy actions, dialogs, founding, saving)

- **Regions**: when SiMCP's user folder already has a region before the game's first start there, the game copies
  only some shipped regions (it made `timbuktu` lowercase and `Downloads`); `game_launch` now copies missing shipped
  regions itself (never overwriting). The game reads the region list at start-up: regions added while it runs need
  a restart (LoadRegion returns status 2). **LoadRegion takes the display name** from region.ini ("Timbuktu"), not
  the folder name ("timbuktu" -> status 2).
- **Taxes** (budget slot 37 SetTaxRate(g, float)): R$ 8.9 -> 9.5 read back at `[B+0x70]`; 23 % for I-D clamped by
  the tool to 20.0 (the Budget window's limit); monthly income responded (3327 -> 4801).
- **Departments**: the map at `[B+0x54]` holds 18 departments (Health 120 %, Education 96 %, Police, Fire, Water,
  Power, Sanitation, Mass Transit, Road Services, Airports, Seaports, School Buses, Ambulances, Dept. of Corrections,
  Parks and Recreation, Landmarks, Building Maintenance, Business Deals), max 120 % (100 % for parks, landmarks,
  building maintenance, business deals); slot 15 = monthly expense. SetFundingPercentage (slot 11) with a pointer to
  a float in the bridge's request area: Education 96 -> 110 %, its expense 287 -> 330; Parks 150 -> clamped 100.
- **Ordinances**: 21 (Maxis + CAM, one with a vtable inside SC4CustomOrdinanceHost.dll - so the tool reads them
  through cISC4Ordinance slots, not fields); IsOrdinanceAvailable (slot 7) + SetOrdinanceOn (slot 13): Smoke
  Detector Program enacted.
- **Loans**: IssueBond(25000) (slot 40): funds 206 -> 25,206; loan record (list at `[B+0x780]`): payment 309 / month,
  total 37,080, ends 2036-02 (120 months at 8.5 %). After the month: funds +451 = last month's income 4790 - expense
  4339 exactly; the loan's paid 309.
- **Dialogs** (window manager service 0xA417445E, vtable 0xAE46E8): IsModal (slot 42); topmost modal window
  `[wm+0x38]`; nest count `[wm+0x17C]`. "QuitCity 0" opened the save-or-quit dialog (buttons Cancel, Exit Without
  Saving, "Option Disabled" - the save-warning plugin's change); an advisor popup (root 0x4A9DB60C, button Close id 1,
  text in an HTML control) was open behind it. GZWinClickButton <id> <root> closed each one.
- **Founding a city**: Mayor Mode = button 0xC988BC79 (city control panel, layout 0xC973B411) opens Establish City
  (root 0x6A414973); GZWinSetWindowText on the edit fields 0xAA4149BF (city) / 0xAA4149D2 (mayor), "Easy", then
  "Establish City": MCP Town (mayor SiMCP, easy) founded on MCP Test tile (6, 0), fireworks; funds 1,000,000 (CAM's
  easy start), all taxes 9 %.
- **Speed / pause**: SimSpeedFast / Slow set S+0x3C; SimSpeedPause toggles the user pause count S+0x30.
- **Saving**: the SaveCity command saves to "City - <city name>.sc4" in the region folder (the city's path field
  +0x4C still names the tile's old file until saved) and then shows a "City Saved. (City - MCP Town.sc4)" notice
  (root 0xAA8DEF97, OK id 0) that holds the deferred call until answered; "SaveCity 0" shows it too. save_city answers
  it. Saving SiMCP's copy of a shipped city (Making Money Tutorial) is refused unless allow_shipped.
- **Popups**: app slots 23 / 24 Get/SetPopupDialogsEnabled toggle (read back).
