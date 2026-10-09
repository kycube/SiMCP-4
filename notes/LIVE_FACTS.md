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

## Session 2026-10-08 (Phase 3: building, graphs, the build catalogue, in MCP Town)

All in MCP Town (MCP Test, small, flat at 270 m, easy, funds 1,000,000), game paused between actions.
- **Bridge**: an 8 KB scratch area at the end of the bridge block (layout[6] = its offset 7432) holds call
  arguments (points, vectors, cell regions, cRZStrings, outputs); OP_CALL takes up to 12 arguments. A call into
  the game waits for its next frame (~20 ms): the catalogue batches calls with OP_CALL_SEQ (28 per round trip).
- **History** (`[0xB43DC0]`, vtable 0xA8CCB4): map at +0xC (header, count +0x10 = 140 series in MCP Town), node key
  +0x10, list sentinel +0x14; samples {next, prev, int32 value +8, cRZDate +0xC (Julian day +0x10)}, oldest first,
  monthly (tax rates daily, 100+ kept). The Graphs window's 18 graphs are exemplars in group 0xCA4AD545 (0x6A4AEE40
  series, 0x6A4AEEDC line labels in LTEXT group 0x6A231EAA, 0x6A4AEEE2 scale, 0x8A416A99 title); the advisor Lua
  `game_trends` names 84 more series. Funds series = funds / 1000 (1000 for 1,000,000).
- **Networks** (city +0x200 network manager slot 5 GetNetworkTool(type, 1); the UI's preview + commit calls):
  road (10,20)-(20,20) cost 110 = 11 cells x 10, WithdrawFunds charged 110, road built (screenshot); power line 21
  cells 81; avenue 22 cells 1320 (start moved one cell west by the pen-width rule); pipe 17 cells 154; diagonal road
  (10,30)-(26,45) 320. GetCostOfSolution over a 3-point anchor list is not the sum of the legs (150 vs 210 for one
  straight line), so build_network makes one drag per leg (L road 210 + 160 = 370 charged). Dragging over an
  existing road costs the full length again (the game's own preview says so too).
- **Zoning** (ZM slot 11 PlaceZone with the tool's arguments; 10 arguments): R low 10 x 6 cells cost 600 (10 / cell),
  charged by PlaceZone itself; automatic streets appeared between two blocks; I medium 20 / cell.
- **Lots**: the lot configuration manager's hash table (`[0xB216CC]`..`[0xB216D0]`, 3079 buckets, 1955 lots;
  node {next, IID, config}); zone types are an STLport bit vector at +0x44 (bit 15 = plopped). A loaded exemplar
  (resource manager `[0xB43CA8]` slot 3, iid 0xA52160F5) has its property holder at +0x1C (vtable 0xAAF038):
  sorted {id, cSCProperty*} at +0x8 (own) and +0x18 (merged with cohorts); cSCProperty: variant value / array
  pointer +0x8, type u16 +0x12 (0x8000 array; 6 uint32, 9 sint64, 0xA float, 0xE string), count +0x14.
- **Build menus**: 154 items (parks 25, landmarks 30, rewards 27, power 10, ferry 19, education 11, water 6...);
  greyed as in the game: nuclear, fusion and solar plants, the casino and most rewards (CivicBuildingSim slot 6
  status without bit 2). First listing 2.0 s, then 0.3 s.
- **Plop** (PlaceLot <lot> x z facing 1 0): Playground 90 and Medium Playground 210 charged (= 0x49CAC341); coal
  plant 13,000; a taken spot returns status 2 and charges nothing. The lot is centred on the corner of cell (x, z)
  with its rotated size: start = x - size // 2 (2x2 at 40 -> 39..40, 3x3 at 30 -> 29..31, 1x1 at 30 -> 30).
  Facing 0..3 = north, east, south, west (read back from the lot).
- **Bulldoze** (Demolition slot 6, 11 arguments, dry run then SetTotalFunds(funds - cost) then the real run):
  a skateboard park 40; an 11-cell road would cost 22; trees cost nothing to clear.
- **Trees**: FloraSim slot 7 static data (+0x160 = price, 3 for the menu trees), slot 17 AddNewFloraOccupant(type,
  float pos[3], 0), WithdrawFunds, Aura slot 6 (x, z floats, 1): 9 Noble Fir trees, 27 charged. The tree menu is
  the 5 flora exemplars with an icon (group 0xE83E0437; no plugin adds trees here).
- **Slopes and road cost** (Konradshohe, dry runs only, not saved): an 11-cell road quotes 110 on flat ground,
  112-113 with a 5 m rise, 115-117 with a 25-29 m rise: the game's GetCostOfSolution includes the slope.
- **Camera**: view `[0xB43DC4]` +0xF0 camera control: target metres +0x44/+0x48/+0x4C, zoom +0x108 (0..5), rotation
  +0x10C. "SetViewTarget cell 30 30" -> target (488, 270, 488) = cell centre; Zoom4 -> 4; RotateCW -> 1; view level
  +0x324 = 1 (surface). GetViewTarget prints "512 0 512 0".
- **Snapshot**: `TakeSnapshot "<path>" 0 0 1024 768` writes a 1024x768 RGBA PNG of the last frame (UI included),
  status 0; also while the simulation is paused.
- **Virtual pointer**: the bridge hooks view vtable slot 36 (0xABCED0, PickTerrain 0x7E5840) on attach (restored on
  detach); while the deadline `pickActive` (GetTickCount) is in the future it returns SiMCP's point. The disaster
  tool (category 0x4A2B2464 via the dispatcher 0x7E9FA0, vtable 0xA9EAA0) picked it 3 times per click.
  Earthquake (item 2) at (58, 58): manager count 0 -> 1, one disaster location; the parks nearby turned to rubble.
  The managers get the point in **world metres** (the tool's +0x2C/+0x34 = 328, 360 for cell (20, 22)), not cells.
  Meteor (item 5, effect path): the effect is created on mouse-up; the red disaster border showed. Fire (item 4)
  and pipe burst (3) did nothing here (no flammable building under the flame; the pipe carried no water).
- **Dispatch**: "DispatchFireTool" arms the tool (vtable 0xA90268, id 0x68E1900A). A small fire station without a
  road: CanDispatch 1 but Dispatch 0. With a road to it, a click on a reachable road cell dispatched (count 1,
  available pylons 1); a second request failed while the one unit was out.
- **Cheats**: the ExecuteCheat command runs a one-word cheat (weaknesspays: funds +1000, one record in the manager's
  history vector +0x40 {id 0x4AB87766, time, 0, 0}) but returns status 2 for a cheat with an argument (the command
  line splits it). SiMCP builds a cRZString (ctor 0x578390, FromChar(text, len) = slot 3) and calls the manager's
  slot 22 DoDefaultCheatCodeProcessing(&str, &id): "hellomynameis Tester" renamed the mayor (read back), then back to
  SiMCP; weaknesspays +1000.
- **Lua**: app slot 47 = `[A+0x658]` (vtable 0xAC4148). DoString (slot 54) returns 0, or 3 on a syntax error;
  GetTop 6 / ToString(-1) 24 / SetTop 7 read a result: "return tostring(1+2)" -> "3"; game.g_funds 982306 (the
  advisors' last snapshot); game.trend_value(game_trends.G_FUNDS, 6) -> 999; 189 game.g_* names (pairs over game).
- **Day / night**: EnableDayOnly / EnableNightOnly / EnableDayAndNight set prefs byte `[[0xB43CD8]]` 1 / 2 / 0 and
  the clock mode `[[0xB43DBC]+0x74]` 1 / 2 / 0.

## Session 2026-10-08 (Phase 3: growth, and what the long-running game process taught)

- **A stuck game process**: after many hours of development in one game process (pid 40776), the power and
  plumbing simulators did nothing in every city (no power grid at all - even a water tower touching a coal plant
  stayed unpowered; the power / water history series stopped: MCP Town on 2000-03-01, Konradshohe made no new
  sample over two game years), while the budget and other simulators kept going. A fresh process (pid 41796)
  powered the same layout at once. The cause is not known; the prime suspect is an exception caught by the bridge's
  SEH inside game code during early development (a simulator left mid-update). The bridge now counts caught faults
  (game_status warns), and city_status warns when the power or water history stops for over 70 days.
- **Growth in a healthy process** (MCP Village, fresh city on MCP Test tile (6, 1)): road, coal plant facing it,
  a power line through R-low and I-medium zones: lots go under construction within a month; buildings finish only
  while the game's own loop runs (wall-clock construction): with the exact day stepper, 24 houses stayed "under
  construction" for three months, then finished within 3 s of real-time play (population 124). One idle pass per
  stepped day (now in StepDays) finishes a few; real-time play finishes all.
- **advance_time modes**: "natural" (default) runs the game at its fast speed (50 ms per day here, about 13 days
  per second with the slow final approach) and pauses exactly on the target day (three 30-day runs: exact; houses,
  factories and shops completed, population 202). "unthrottled" (ms-per-day S+0x80 = 0) runs 50-140 days per second
  but fewer buildings complete per day. "exact" is the hidden-pause stepper.
- **Zots** (snapshot): crossed car on residential lots = no job access (lot slot 27 HasJobAccess false: no jobs
  anywhere yet); lightning = no power. Lot slot 28 HasRoadAccess; lot flag 0x10 = powered (empty zoned lots
  conduct power from neighbours in a healthy process). Power plants need road access (car zot without one).
- **Saving** rewrites the neighbouring cities' files too (regional data): save_city now reports the open city's own
  "City - <name>.sc4". A city saved while user-paused loads paused, with the 9 one-shot agents (Demand, Traffic,
  Budget, Aura, Commercial, Residential, LandValue, LotDeveloper, BuildingDevelopment) waiting until it runs.
- **Simulator agent lists**: S+0x114+12t = {map header, count}; an STLport map keyed by the agent pointer, node
  value {+0x14 enabled byte, +0x18 cRZString class name}. Types seen: 0 one-shot, 4 day (34), 5 week (1),
  6 month (26), 7 year (2), 10 idle (23).
- **U-Drive-It** (MCP Village, 202 residents): advisor 29 offered "Road Vehicle Training Mission" (guid
  0x8C151EFD at advice +0x8C) and "Aircraft Training Mission" (0xAC1726C8). Situation manager `[city+0x1EC]` slot 21
  InitiateSituationByGuid(guid, 0, 0): with the city paused since load it returned 0 and showed the "mission result"
  dialog (root 0xEBBC081E); after 10 s of real-time play (cars out) it returned 1, chose an automaton (S+0xA4C) and
  opened the offer (root 0xEBB16D71: Cancel 1, Free Drive 7, Accept 6). Accept: drive control `[0xB21D74]` set, its
  +0x30 = the same automaton; status S+0xA48 = 3, time limit S+0xA94 = 164.7 s, target occupant S+0xA50 (slot 8
  position, slot 11 cells: a White Modular House at (2..3, 35)). Keys through the control's slots 14 / 15
  (OnKeyDown / OnKeyUp(vk, 0)): up arrow drove the car east along the road ~25 m/s (automaton slot 7 position
  387.7 -> 442.4 in 2 s); up + left turned it from heading (1, 0) to (-0.6, -0.8) (slot 15 heading; left turns
  toward -z when facing east). A naive waypoint controller left the road and ran out of time: status 2 (failure),
  the result dialog; the road mission was then not offered again for at least a month.
- **My Sims**: the My Sims panel (ToggleMySimPanel; root 0xCA1F1D9C) has five slot buttons 0x8A8F410C/D/E/F and
  0x8A8F4120; a free slot opens "Select A My Sim" (root 0x6A243D9E: gender, sign and face buttons, "Move In My Sim"
  0xCA243E0C, Cancel). "Move In My Sim" arms the move-in tool (vtable 0xA85A20), which picks the house with view
  slot 37 PickOccupant (3 arguments, returns the occupant AddRef'd) in its mouse-move; the bridge now hooks slot 37
  too (0xABCED4) and answers SiMCP's occupant (cISC4Occupant via QI 0x26BB767E on lot slot 48's building). Two Sims
  moved in (MySim1 -> White Modular House, MySim2 -> White Cottage; both age 26, low wealth, job Dolan Dye); the
  game opened an advisor message for the first.
- **Terraforming**: the city view's button handler 0x7ED720 makes the brush tool through 0x7E5910(brush, god):
  mayor buttons 0xEA32DDBB raise -> MayorMountainHill 0xEA33E2FD, 0x4A32DDC7 lower -> MayorValleyDefault 0x0A33E37B,
  0xEA32DDE5 level -> MayorLevelBrush 0x4A524342 (god = 0, charged); god mode uses the brush exemplars in group
  0x6A01FC2A with a menu order. Held 1 s with the virtual pointer (mouse down, moves every 0.1 s, up): raise at
  (45, 15) 270 -> 303.2 m, neighbour +1.7, funds -138; lower (also while user-paused) 303.2 -> 286.5, -138; raise
  along (40..44, 12) +17 / +11 m for 120; level 68. The strength grows with wall-clock time held (timer +0xC0);
  F1-F10 keys set the strength. Modifier bits 1 / 2 / 4 on the mouse calls do not lower.
- **Regions**: the region view window has vtable 0xAB9260 (151 slots); tile records at +0x118 (stride 0x80: +8 x,
  +0xC z, +0x18 size, low byte 0 small / 1 medium / 2 large). 0x7AEA00(tile, 1) (thiscall on the view) returns the
  tile's regional city; 0x7ADC20(ref) deferred = Play: tile (7, 0) and (6, 2) of MCP Test opened as new cities in
  god mode (1.6 s). A god-mode brush (GodMountainDefault) raised (32, 32) from 270 to 889.8 m in 1.5 s, free.
  New region: nation `[A+0x48]` slot 13 AddNewRegion(cRZString "MCP Fresh") -> index 7, slot 11 GetRegion, region
  slots 8 Init / 19 SetBaseTerrainType(0) / 9 Shutdown (region.ini), nation slot 9 SetActiveRegion(7), app slot 12
  RequestGoToRegionView(0) deferred: the region opened without a restart, with a random template layout (medium
  and small tiles). Saved city files: region-view record v1.13 = mayor rating s8 0x24, difficulty 0x25, serial
  0x27, founded 0x3F, strings name / - / mayor / - / utility advisor / description; terrain record
  0xA9DD6FF4/0xE98F9525/1 (65x65 f32 for a small city); thumbnails PNG 0x8A2482B9/0x4A2482BB/0 (satellite) and /4.
- **Content server, stage 1**: a design = one DBPF in `<UserDir>\Plugins\zzz_SiMCP` with a building exemplar (group
  0x5C4D0F00, the template's parent cohort and properties, LTEXT keys dropped, 0x899AFBAD name, 0x8A2602A9
  description, 0xEA260589 -> the new lot, costs) and a lot exemplar (group 0xA8FBD372, the template's rows, the
  building row's IID -> the new building). "MCP Garden" (from the Playground lot 0x6A636333, plop 55, monthly 7):
  after a game restart build_menu listed it under parks (lot 0xDAE61741, available); plop in MCP Village charged 55
  and the playground props appeared. A first attempt picked the lot exemplar as the "building" (same instance in
  two groups) - fixed by excluding the lot group; that file sits in `<SiMCP home>\content-disabled`. In this setup a
  plugin replaces the Playground lot's building (the live lot names 0xB47406A3), so designs use the game's own lot.
- **Content server, stage 2 (own models)**: S3D codec (sc4_mcp/s3d.py) round-trips 398 of 400 sampled game models
  (130 byte-identical; the rest only had wrong chunk sizes from Maxis); FSH writer (32-bit 0x7D, "G264"/"0000");
  DXT1/3 decoding checked on a game texture. A generated box (RKT0 = one 3D model for every zoom and rotation,
  model in 0xBADB57F1, textures in 0x1ABE787D at instances checked free against SimCity_1..5.dat) rendered as a
  real 3D building with a shadow at every rotation: "MCP Tower" (10x10x40 m, plop 800) and "MCP Office"
  (14x10x28 m, plop 900) on generated 1x1 lots (one building row centred, the small plaza's paving texture
  0x258E3000). Texture coordinates beyond 0..1 are clamped (wrap byte 1 does not repeat), so walls are split into
  4 m quads, each with its own 0..1 window tile; faces are written both ways round. The game keeps plugin files
  open while it runs: disabling a design needs the game closed (a failed move had left a copy in
  content-disabled; disable now renames atomically).
- **HTML dialog text**: an HTML window (caption "HTML Window", vtable 0xACD0D8) holds cIGZWinHTML at +0xD8 (vtable
  0xACD050, 34 slots; GetDocument slot 21 copies from [iface+0x70] slot 4 -> a buffer whose slot 6 = data, slot 7 =
  length). Reading those directly gave the mission offer's and the mission result's full text ("You didn't get the
  car to the blinking bulls-eye target before time ran out..."); dialog_status now returns it (entities decoded).
- **Mission attempts** (driving missions are deferred to a later release at the user's request): the road training mission (176 s) failed twice with simple controllers: a slow U-turn at the
  start and drifting off the road into the power line's pylons at (27, 29). Offers come and go (withdrawn for a while
  after a failure; no vehicle while the city is paused).
- **Network map** (MCP Village, 2002): occupant manager `[0xB43D0C]` slot **41** GetOccupantsByStandardCityCells
  (SC4List&, nw*, se*, **type**, -1) filled a list built in the bridge scratch (list = pointer to a root node {next,
  prev, value}): 107 network pieces (type 0xC772BF98, occupant vtable 0xAA7FF8) on the whole 64x64 map, 1484
  occupants with type 0. Slot 40 (the filter overload) faulted when given a type (one caught fault). Slot 48
  ReleaseOccupantList released them and reset the root node to itself (0x413E60 frees only the game's nodes). Slot
  32 GetFirstOccupantByStandardCityCell(occ&, x, z, type) also works (non-owning, first only - usually a prop).
  cISC4NetworkOccupant (QI 0xA821EF94) = occupant - 4, vtable 0xAA8080; getters read +0x13C flags (bit i = network
  type i, e.g. 0x16002001 road), +0xFC piece id (road 0x4B00, street 0x5004B00, road x street 0xAA0800), +0x104
  rotation / flip, +0x10C primary network type, +0x110 its edges (bytes W, N, E, S: road west-east 0x00020002,
  street 0x02000200), +0x108 / +0x114 extra {type, edges} records (the street side of a junction), +0x9C / +0xA4
  position. Memory reads matched slots 12 / 40 / 59 for all 107 pieces. Power lines are other occupants: segments
  0x0990B2EA (CLSID cSC4PowerLineOccupant, one per cell, 15) and poles 0x2890D4DE (6). The whole map reads in 0.9 s;
  network_map drew the village (road along z = 30, streets south of it, two power lines) and find_route went from
  (2, 30) to (4, 35) via the junction at (4, 30). A pipe laid along (26, 33..38) -> (30, 38) (charged 54 + 62) is
  also type 0xC772BF98 but another class (occupant vtable 0xAA9730, network vtable 0xAA97B8) with the same getters
  and fields (flags 0x10000010, primary type 4, edges 0x02000200); the reader accepts any class whose slots 12 / 40
  are those getters, and network_map("pipe") drew it with its corner.
- **Building funding and what it does** (MCP Village, Sept-Oct 2003; a road along z = 41 with a Small Police
  Station (32, 42), Small Fire Station (36, 42), Elementary School (38, 42) and Medical Clinic (41, 42) plopped for
  170 / 180 / 396 / 95). BudgetSim slot 51 GetBudgetItemForPurpose(holder, purpose, item&) gave each building's
  items: coal plant power 300 / month at 100 %; stations 90; school staff 187 + buses 62; clinic staff 600 +
  ambulances 100 (the cost is the full cost; the department pays cost x funding: Education 46 at 25 %, 187 at
  100 %). New schools and clinics start at 25 % ("School / Health Init/Max Allowed Funding" = 25, 120). Setting
  through the simulators as the slider (0x77BC90) does - PowerSim 51, PoliceSim 8, FireSim 9, ResidentialSim 19
  (occupant, &staff, &coverage, school) - with these results:
  - police station 50 %: efficiency (PoliceSim 25) 1.0 -> 0.5 at once; a month later the police coverage map's
    total 156,903 -> 86,919 (-45 %);
  - fire station 50 %: efficiency 0.25 (the fire curve: 50 -> 25); a month later fire coverage 208,590 -> 89,254
    (-57 %), tracts covered 1024 -> 591;
  - coal plant 50 %: efficiency 0.25 (power curve 50 -> 25), output capacity 7497 -> 1874 MWh at once (the city
    used 427, so no shortage); condition stayed 1.0 over the month;
  - school staff 25 -> 100 %: capacity 300 -> 1200 students, staff 10 -> 40 (9 enrolled); clinic staff 25 ->
    100 %: 350 -> 1400 patients, staff 11 -> 46 (17 patients).
  The Police department slider (set_department_funding 80 %) set the station's own funding to 80 % and its
  efficiency to 0.8: the department slider sets every building. The curves come from the tuning exemplars
  (6534284A-E7E2C2DB-28DFCF89 police, -68F5524A fire, -C911E35B utilities, -69189C84 residential), read live
  through the resource manager. Efficiency getters take a hidden result pointer (float* out, occupant) - calling
  PoliceSim 25 with the occupant first faulted (caught). The bridge's OP_CALL now also returns ST0 for functions
  that return float (conv bit 1). All funding was set back afterwards.
- **Traffic volume** (MCP Village): TrafficSim `[0xB43DA8]` hash +0x17C..+0x180 (1543 buckets, 815 used, 1048
  nodes): a node is {next, key ev<<24 | type<<16 | x<<8 | z, TrafficEdgeDensity inline at +8} - the use counter is
  u16 at node +0x28 (not behind a pointer). 131 cells carry trips (walk 732, car 1952); the busiest is the main road
  z = 30 at x 16..26 (122-136 trips, about 70 % by car). map_data("traffic_volume") and network_map(traffic=true).
- **Neighbour deals** (MCP Village, MCP Town is the tile north): a power line from the coal plant to (22, 0) with
  connect_neighbor made connection {type 4 power, edge (22, -1), neighbour tile (6, 0)} at N `[0xB43D8C]` +0x1C.
  The Neighbor Deals panel's builder calls `city slot 62 -> N slot 25 ProposeDeals(list&, 1)` (0x77E735; the
  monthly advisor feed calls it with 0, counting only). With 1, each possible deal goes through 0x6D0520: N slot 24
  ProposeDeal, then it joins the city's deal list (+0x20) - running at once (flags 2): "sell_power" to (6, 0),
  amount 0 (MCP Town has no demand: 0 residents), income 1 a month (N slot 32), dates today .. +1 year. Deal slot
  34 Cancel (SetFlags(4, 1), SetFlags(2, 0), SetAmount(0)) + slot 37 SetFlags(1, 1), as the row's button does,
  removed it from the list at once (income 0); opening the panel again proposed it anew (a new start date).
  Starting an offered deal (slot 35 Activate) is not tried live: no deal stayed offered.
- **Play options**: SC4Preferences `[0xB43CD8]` bytes +0xF08 auto go to disaster, +0xF09 edge scrolling, +0xF0A
  expanded tooltips, +0xF0B urgent advice dialogs, +0x4EC auto edge reconciliation (all on here); set as the
  dialog's Accept does - byte, a cGZMessage2Standard (new 0x2C 0x9133DA, ctor 0x9134D6, SetType slot 5
  0x231BBF91) sent through `[0xB43CCC]` slot 4, app slot 17 SavePreferences: expanded tooltips off then on, SimCity
  4.cfg in SiMCP's UserDir rewritten (276 -> 275 bytes and back), no faults. Video prefs +0xF0C: effects 3, shadows
  3, textures 3, city detail 3, 1024x768x32 windowed; music and sound on.
- **Make Historical**: the R / C / I query windows (layouts 2A567DC1, 4A5672BF, CA56783A) have only "Make
  Historical" (button 0x107A) and Close; lot slot 44 SetHistorical(bool) sets bit 0x20 of lot +0x79 (slot 43
  reads it). The White Modular House at (2, 35): historical true, then false again; the coal plant (plopped) is
  refused by the tool, as the plopped buildings' query windows have no such button. The button's handler is not
  traced (the id is not an immediate in the code; probably a switch).
- **Region import from a height map** (throwaway region "MCP Heightmap"): new_region made a 16x16 random layout;
  writing config.bmp as 2x2 red pixels (4 small tiles) and loading another region and back made the region view
  show 4 small tiles (loading the same region again is a no-op). RegionBitmapLoad (deferred) opens the game's file
  window modally (root 0xEA9660F3, component at +0xD8 vtable 0xADD190; File name edit +0x100 = text-edit
  interface vtable 0xADFA68: slot 49 SetText(char*, len, notify), 46 GetText, 47 length; OK 0xBAA55D58). The
  component's slot 18 fills {mode 2, -, path, folder, name} with path = folder ("c:\\" at first) + typed name: a full
  path became "c:\C:\..." and was quietly dropped, so SiMCP types the name relative to the folder. A 24-bit BMP of
  the right size (129x129) was also dropped silently; an 8-bit greyscale BMP was taken: the game regenerated and
  saved all 4 cities in 51 s. Saved terrain (65x65 per small tile): lowest 210 m = grey 70 x 3, highest ~467 m =
  grey 156 x 3 (height = grey x 3 m confirmed). import_region_terrain then took a 7x5 grid in metres (201-519 m,
  resampled) and the island picture by image_path (converted to 8 bits by Pillow), each in 51 s; tile (1, 1) opened
  as an island corner sloping to the sea. Both tools refuse MCP Test (founded cities) and a region the view is not
  showing.
- **Growable designs** (MCP Village, after a game restart each time): content.growable_building copies a game
  growable lot of the purpose / wealth / size (the index finds 1727: lot property 88EDC791 names a building family;
  the family's buildings are exemplars whose parent cohort carries 27812870) and one building of that family, and
  gives both a new family, the generated model (RKT0) and the size. Checks: the lot configuration manager listed
  "SiMCP_MCP_Cottage" (1x1, zones 1-3) and BuildingDevelopmentSim (vtable 0xAB0AF8; Windows slots 15
  IsBuildingTypeValid, 16 IsBuildingFamilyTypeValid, 20 IsBuildingInFamily - one above the header) knew the
  building and family. Growth: 1x1 lots from 1-cell-deep R$ strips never developed in 5 months with any 1x1 design
  (ours at stage 1 or 2, a pure clone of the Maxis house with its own model) - they stay "ready" - while 2-deep
  strips grew 68 houses (1x2) within a month. A 1x2 design did not grow until its occupant groups carried every
  building style (0x2000-0x2003; the template's 0x2003 Euro-contemporary alone was never picked here): then 5 of 68
  lots grew "MCP Long Cottage" (white walls, green roof) beside Maxis Tiny Bungalows and Cottages, occupied. The
  query name needs an LTEXT (name key 8A416A99 -> 2026960B-5C4D0F01-<building>); without one the game says
  "Building". One game exit (pid 43732) left no trace in the event log; the bridge now writes faults raised in the
  game's own code to `<SiMCP home>\crash.log` (vectored handler; pid, address, registers, return addresses), and
  game_status reports them - none since.
- **Occupancy per lot**: lot slot 53 GetPopulation(developer type) and slot 50 GetCapacity(type, force) (Windows
  order: 50 / 52 are the (type, bool) overloads, 51 the wealth one): White Modular House R$ 5 / 5, "Burner" ID 4 / 5
  jobs, Small Shops CS$ 31 / 32 jobs; types R$ 0x1010 .. R$$$ 0x1030, CS$ 0x3110 .. CS$$$ 0x3130, CO$$ 0x3320,
  CO$$$ 0x3330, IR 0x4100, ID 0x4200, IM 0x4300, IHT 0x4400. lots(occupancy=true) reads 190 lots in 3.5 s (a call
  sequence reports at most 16 results, so 8 lots-and-types per frame).
- **God-mode fire (not solved)**: the Disasters menu's Fire item (exemplar 4, no manager id) makes the disaster tool a
  torch ("torch_active" / "torch_inactive" effects): tool slot 56 (0x5808B0) picks the terrain (view slot 36),
  converts the point to a cell (`[0xB43CEC]` slot 95) and calls the fire manager's interface (QI 0x49B43F57, kept
  at tool +0x2C by the init slot 43 0x580660) IgniteCell(x, z, 0, 1, 0) and SetCause(1). Drags with the virtual
  pointer (terrain or tree occupant picks, 1-2 s) lit nothing - on houses under fire coverage 148-255 or on 169
  oak trees with no coverage (flammability 13) - and calling slot 56 directly faulted (caught: +0x2C was null). The
  slot's caller (a timer while the button is held) is not found yet. Disasters with managers work (earthquake,
  meteor, see above).
- **Transit and garbage** (MCP Village): build_menu's groups were mislabelled - 0x130A is the road-transit menu (bus
  and subway stops, trams, light rail, parking garage, toll booth: 19 items), 0x1300 rail stations, 0x1519 ferry
  terminals and the marina; now "transit", "rail", "ferries" ("transport", "ferry", "other" kept as aliases). The
  Maxis roadside bus stop plopped at (14, 29) facing the road for 150. A landfill zone (45..49, 42..45, 1000)
  showed the no-road-access zot and stayed empty for 100 days; network_map / find_route showed why: the road drawn
  from (31, 37) ended beside the street's dead end at (31, 36) without joining it (street N only, road S only), so
  the civic road was cut off. One road cell over the street end joined them (cell 36 = road + street); within 45
  days the city's garbage mean fell 9.4 -> 1.1 and a trash pile grew - landfill trash is occupants (type
  0x6A11BD2B), not lots. Network reader fix: the primary network type at +0x10C is one byte (the u32 read gave
  garbage, dropping those pieces' sides).
- **Advice and news designs** (Lua content): the advisor system's scripts (Lua, group 0x4A5E8EF6) run only as
  "packages": SCLuaHelp_LoadPackageScripts (0x5FBA20) takes the records whose first line is `--#-package:<hex>#`
  and runs them in number order (0x2000 advice system, 0x3000 advisors, 0x4000 tutorial, 0x01001000 Rush Hour, the
  game's own Living Mall add-on 0x5000); other scripts run only when a package dofile()s them by name. A first
  design without the header never ran (the same text run through the Lua state registered fine). As packages
  numbered 0x5C4Dxxxx: "A note from SiMCP about water" (utilities, trigger "1") opened as an advisor popup and the
  news item "SiMCP Gazette: #city# grows" (trigger game.g_city_r_population > 10) reached the news advisor within
  20 days. Plain texts show with a "***_NOT_IN_TEXT_DATABASE_***" mark; as `text@<instance>` references to LTEXT
  records in group 0x6A231EA4 (the game's advice texts) they read cleanly; #city# becomes the city's name.
  Triggers pass SiMCP's read-only Lua whitelist; links (`#link_id#game...`) are refused (they run actions).
- **Airport zone**: zone("airport") laid zone 11 over 8x6 cells for 48 (development needs airport demand, which
  the small village does not have).
- **Rename**: city slots 13 SetCityName(const cIGZString&), 15 SetCityNameChanged(bool) (byte +0x2D), 17
  SetMayorName (header order holds): MCP Village -> "MCP Hamlet" / mayor "Agent Mayor" and back, read back from the
  city's own fields, no faults.
- **Creating My Sims**: the Select A My Sim dialog (0x6A243D9E) has 21 face buttons (10 male, 11 female; each sets
  a preset name, sign and gender - "Bob Newbie" is the default), a name edit 0x8A243F1F (text-edit slot 49
  SetText), a sign combo 0xAA243F5E (cIGZWinCombo 0x412CE496: slot 28 SetSelection(index, notify), 30
  GetSelection; list order = cISC4MySim::ZodiacSign, Capricorn 0 .. Sagittarius 11) and the gender label
  0xEA243F57. Moved in: "Ada Agent" (Eve Tomayo's face, Scorpio), "Cleo Coder", "Dana Data" (Judith Peynter's face,
  Aquarius, female) - read back from the Sim: the personal name is a cRZString at the cISC4MySim interface - 0x80
  (slot 3 is the Sim's *advisor*, named MySim<n>), slot 16 GetSign in the enum order above (the old reader mapped
  it Aries-first: the two earlier Sims are Bob Newbie, Gemini). A face click right after the dialog opens can be
  lost: SiMCP checks the gender label and clicks again. **Crash found and fixed**: pressing a slot button while
  the My Sim panel is hidden crashed the game (0x771D42: the panel window's handler, vtable 0xAB5120, reads a null
  member +0x34; caught by the new crash log, pid 39120). move_in now opens the panel (ToggleMySimPanel) and waits
  for its parents to show - right after a move-in the game hides them for a moment - and refuses while a dialog
  is open (the panel ignores the toggle under a modal).
- **cISC4MySim / AgentSim MoveIn** take name, gender, sign, bio, a bitmap IID and a bitmap *file path*: a custom
  face picture may be possible through that path (not tried).
- **Review fixes** (an independent read-only review of the day's modules, 24 findings, all handled): region names
  are plain names inside SiMCP's Regions folder (a path is refused); advice texts and design names allow only the
  #city# / #mayor# / #name# tokens (any other #...# may reach the game's Lua; "#sc4game.budget.deposit_funds(5)#"
  is refused), no Lua long brackets, one-line triggers; designs refuse negative costs, capacities outside the
  game's own range and file-name clashes; a corrupt design list is never overwritten; rename_city refuses another
  city's name or file ("MCP Town" from the village), save_city checks the file it will write; Make Historical
  needs a building; network routes keep to one network per piece (no hop from an elevated highway to the road
  below); network_map clamps its area and reads power lines in bulk (whole village 0.9 -> 0.3 s; wire cells at
  [O+0x40]/[O+0x44], 37 of 37 against GetPosition); lists and AddRef'd objects are released on every path; the
  height-map import checks the file window's vtables, cancels it on any error and stops waiting at another
  dialog; the bridge logs faults its guards catch ("caught-in-call", "caught-in-deferred", tested with a call to
  address 0x10) besides first-chance faults, with a re-entry guard and a stack scan bounded by the thread's stack,
  into SIMCP4_HOME\crash.log (the launcher passes the variable); game_status reports only first-chance ones.
- **Strikes and jails**: police / fire strike flag = byte +0xA4 of each simulator (both use 0x6E0120); teachers /
  doctors +0x178 / +0x118 of ResidentialSim. GetChanceOfStrike (police slot 11, fire 12, ResidentialSim 10 / 11)
  takes a hidden result pointer: for each station it reads the station's budget item funding and runs it through
  the strike curve (+0x134 in the police simulator), p = 1 - prod(1 - p_i). Fire at 30 % funding: 22.0 % (the curve
  0:100, 25:25, 50:10, 70:0), 0 % at 100 %. Police stayed 0 % at 30 % for three months: a plugin in this setup loads
  the police strike curve as all zeros (live tuning 68DDAE9E = [0,0, 25,0, 50,0, 70,0]). Jails (Windows slots shifted
  by MSVC's overload grouping: 28 GetJailCapacity(occ), 29 GetJailCapacity() ... 38 ProcessMonthlyCrimeStats - never
  called): capacity +0xD8 = 120, inmates +0xDC, criminals +0xE0, arrests +0xE4 (all 0 here).

## Session 2026-10-08 (Phase 5: low-hanging items)

- **Menu icons for designs**: "MCP Kiosk" (design_model_building, lot 0xFD89BDA2, building 0x70FCDD52) with
  SiMCP's 176x44 four-state PNG (image group 0x6A386D26, exemplar property 0x8A2602B8) shows its drawn box as the
  4th item of Civic -> Parks after a game restart (seen in a game snapshot). The UI path, all with the game's own
  GZWinClickButton command: ToggleMayorPanel; the mayor column (parent 0x69E40A1F) 0x8991EE08 Landscape,
  0x0991EE13 zones, 0xA994824D transport, 0xE991EE2F utilities, 0x0991EE39 Civic, 0xE999C820 bulldoze, 0x6991EE42
  emergency; the Civic submenu (parent 0x699306ED) 0x37 police, 0x38 fire, 0x42 education, 0x89DD5405 health,
  0x09930709 landmarks, 0x34 rewards, 0x03 parks; the item list opens as window 0x8A6E61E0.
- **Snapshots**: the game's TakeSnapshot PNG has alpha 0 in every pixel (viewers that honour alpha show it blank);
  SiMCP now saves it back as opaque RGB. Window captures from outside (PrintWindow, a screen grab) show only black
  with a white box for this game's DirectX window, so the game's own snapshot stays the way to see it.
- **Region housekeeping** (files only): backup_region copies the folder into <SiMCP home>\backups\<folder>-<time>;
  remove_city / remove_region move the city file / region folder there (nothing deleted). Tested on "MCP Heightmap":
  backup made; renamed to "MCP Island" (region.ini Name; the folder keeps its name); after a game restart the
  region loads as "MCP Island" and the tile whose city was moved aside is unfounded. A rename while the game runs
  makes the region unloadable under either name until the game restarts (the game reads the region list at
  start), so rename_region says so. The game reports a loaded region by its display name: the guard refuses the
  loaded region by folder or display name (live: remove_region / remove_city / rename_region on "MCP Test" while it
  was loaded were refused). An offline test found that a city given by its plain name never matched its file
  ("City - <name>.sc4"); fixed.
- **Graphics and sound settings** through the game's own dialogs: OpenGraphicOptionsDialog (root 0x2A57CB82) and
  OpenAudioOptionsDialog (root 0xEA53F5DB), run deferred because they are modal. Radio buttons and checkboxes are
  cGZWinBtn (window vtable 0xADDAF0, the button interface at window-4, vtable 0xADDD50: slot 8 IsOn = bit 0 of
  [btn+0xDC], i.e. [window+0xD8]); they read exactly as the dialog showed (all High, all switches on, 32-bit,
  1024x768, Hardware). GZWinClickButton <id> <root> selects a radio / toggles a checkbox. Volume sliders (window
  vtable 0xAE04D8, interface window+0xD8 vtable 0xAE049C: +8 min 0, +0xC max 1000, +0x10 fraction; slot 4 GetValue,
  slot 5 SetValue(int) clamps, redraws and notifies the dialog 0x887113A3). Live: shadows Low -> Accept -> the
  preference byte video+3 = 1 and the reopened dialog shows Low; shadows High + waves off -> video+3 = 3, +6 = 0,
  SimCity 4.cfg rewritten; music volume 50 -> 30 -> reread 30; all restored. Custom Tunes is disabled without
  custom music files (refused; the dialog is cancelled, no modal left open).
- **Seaport zones** (throwaway city "MCP Harbor" on tile (0, 0) of MCP Island, never saved): the imported island
  slopes 4-6 m per cell to the sea; before founding, god mode's level brush held 3 s from (14, 40) flattened
  everything west of x ~32 to 258.3 m (the god brushes have a very wide reach: 1656 -> 1060 water cells), leaving
  a straight shore at rows 19-20 with 15-39 m of water off it. After founding: a road along row 26 (210), then
  zone("seaport", 18, 20, 26, 25) charged 54 and the zone map reads 12 on all 9x6 cells; no lots are made until
  something develops (seaport demand comes from freight). The zone tool takes a seaport zone inland too (preview
  ok on (10..15, 30..34)): the water rule is the developer's, not the zone tool's.
- **Edge reconcile prompts**: opening a tile whose edges differ from its neighbours' (here the unsaved, levelled
  neighbour and the tile whose city was moved aside) asks once per mismatch; Cancel closes each (dialog_status /
  close_dialog), then the advisors' popups follow (set_popups(false) stops those).
- **One game crash, not reproduced**: in the first try the game died right after close_dialog("Close") on an
  advisor message: 0xC0000005 at 0x7E6C9F reading 0x108. That is the city view's message handler 0x7F3E50
  (window interface vtable 0xABCBC0 = view+0xC) on GZ message type 16 with a city open: it clears the view's
  edge-scroll vectors and calls 0x7E6C60, which reads the zoom of the camera control [view+0xF0] - null in that
  view. Retried after a restart four ways (the same sequence; a city switch then a modal dialog; camera moves and
  snapshots under a modal dialog; the Civic -> Parks menu open in a city that is then left): no fault. The view's
  camera control was non-null throughout (view 0x2CF2814 / 0x1AE57014, one city view in the window tree after a
  leave and reopen).
- **No offered neighbour deals in this version**: the panel's ProposeDeals(list, 1) runs 0x6D0520 per possible
  deal: N slot 24 ProposeDeal makes it, the flag clears its bit 0x80 and links it into the city's deal list (+0x20),
  slot 11 sets its partner, and the term is random between the tuning values 0xAA46934B / 0xEA46934F (1-5 years,
  365 days each) through slots 29 / 25 / 27 (dates). There is no accept step, so no deal waits as "offered": the
  player's way to start a deal is to open the panel (all possible deals start) and cancel the unwanted ones, which
  is what open_neighbor_deals / cancel_neighbor_deal do. The unused start_deal (deal slot 35) was removed.

## Session 2026-10-08 (Phase 6: new trees)

- **Tree designs** (design_tree): "MCP Maple" (red broadleaf, 12 x 9 m, price 5) and "MCP Pine" (conifer, 18 x 7 m,
  price 4) as flora exemplars in group 0xE83E0437 copied from the Maxis "decisious1" menu tree (0x16600000), RKT5
  replaced by RKT0 (one 3D model: three crossed quads, both sides, 128x256 ARGB texture clamped (wrap 3), default
  material 0xA3 = alpha test at 0.5), PNG icon (group 0x6A386D26), LTEXT name 0x5C4D0F01 / description 0x5C4D0F02.
  After a game restart: FloraSim static data for both types gives our prices (5, 4); plant_trees planted 9 of 16
  maples and 9 of 12 pines next to the road z = 30 (the road cells refuse trees; 6 of 8 Maxis maples likewise),
  charged 4 a pine; both trees are first in the game's tree menu (Landscape -> trees, button 0x4A22EA06 under
  0x49923239) with their icons. Seen in a zoom-5 snapshot: the alpha cut-out works and the shadow pass honours it
  (tree-shaped shadows), but the solid planes cast long dark shadows that merge when planted every cell.
- **Planted trees grow**: a flora occupant (type 0x74758926, vtable 0xA88580) keeps its flora type at +0x34,
  position at +0x3C/+0x40/+0x44 (x, altitude, z in metres), a stage byte at +0x2E (1 when planted, 3 on grown
  trees) and its planting day at +0x48. Maxis menu trees use RKT5 models per state (instances +0x10000 per state,
  9 states, each with 5 zooms x 4 rotations), so a freshly planted Maxis maple is a sapling a few pixels big; a
  designed tree (RKT0) shows its one model at every stage. The earlier "9 Noble Fir trees" check counted
  occupants only.

## Session 2026-10-08 (Phase 6: new cars)

- **Cars in the game's data**: vehicles are exemplars of type 0x16 in group 0x096E6739 under cohorts that give the
  class: CheapCarCohort 0xCA47E67E (groups 0x4000, 0x4002, 0x420E cheap, 0x420B civilian cars), SoccerMomCohort
  0x6A511FE1 (0x420A), RichCarCohort 0x2A47E655 (0x420D); vehicles.lua (Lua group 0x4A5E8F3F, 0xFF71C15F) defines
  those groups. A car names its day model 0x09C80416, night model 0x09C80417 (head / tail light quads drawn over it,
  the cheap sedan's is 0x10E42000), query name 0x4B733E12 and automata id 0xEBFC5E5E. The cheap sedan 0x10E40000 is a
  3D model (2.1 x 1.87 x 5.5 m, +z forward, wheels on y = 0) of three meshes - body, undercarriage (a quad at
  0.594 m facing down, FSH 0xABA645E7) and shadow (a blended quad at 0.129 m facing up, FSH 0x10660002) - 100
  identical frames at 30 fps; its texture is a 128 x 128 FSH in 0x1ABE787D (SimCity_2.dat), the 42 x 42 PNG in
  0x4C06F888 is its picture.
- **The vehicle manager** `[0xB43D44]` (vtable 0xA9D1E0): +0xA18 a vector of 0x6C-byte vehicle type records keyed by
  the model's resource key at +0x10 (182 here, groups from +0x3C), +0x44 a list of live vehicles (node +8; 6 to 25
  in MCP Village); a live vehicle keeps its model key at +0x11C (group) / +0x120 (instance) and its position at
  +0x40 / +0x44 / +0x48 (x, altitude, z). Vehicles are not occupants.
- **design_car** "MCP Blue Sedan" (cheap) and "MCP Red Van": after a restart both are in the type table with their
  cohort's groups and drive in the traffic (the sedan 4 of 152 vehicles seen in a minute, the Maxis sedan 6).
  Caught by pausing the game the moment the vehicle list held one and centring the camera on it. **They first drew
  black**: SiMCP had written every face both ways round, as its buildings are; vehicles are lit per face, so the
  unlit back face drew over the front (test cars with the Maxis sedan's own texture, with material flags 0xA3,
  and with the Maxis texture settings were all black too). The Maxis sedan has 48 single-sided triangles whose
  (b - a) x (c - a) points outward; written that way the cars show their paint, glass and lights. Weight 6000 in
  0xEBFC5FBA did not make the sedan more common, so design_car keeps the sedan's 720 and offers no weight.

## Session 2026-10-08 (Phase 7: props and lots)

- **Props in the game's data**: 1,544 exemplars of type 0x1E in group 0xC977C536 (stone bench 0x29010000: size
  0x27812810 [3, 2, 1] = width, height, depth; RKT1 sprites; name key into the locale's group 0x6A554AFD). Several
  share a shown name ("Bench" x5, "Fountain" x6), so a lot object names a prop by id when the name is ambiguous.
- **Lot rows as Maxis writes them** (CS$$$3_2x2, R$2_1x1): props [1, detail, rotation, x, 0, z, bounds from the
  prop's size, 0, object id, prop or family 0xA000xxxx]; trees [4, ..., x +- 1 m, flora id]; ground textures one
  per 16 m cell [2, ..., cell +0.04 .. +16.04 m, texture]; detail 0x20 / 0x10 on decorations (high / medium detail
  only); object ids are arbitrary but unique in the lot. The most used ground textures (FSH 0x0986135E, +4 = the
  closest zoom): light paving 0x258F2000, grass 0x25D60000, plaza tiles 0x258E3000, concrete 0x258D1000, asphalt
  0x258C2000, lawn 0x252B3000, gravel 0x25FB1000, parking 0x25A32000, garden beds 0x26213000.
- **design_prop / design_park**: "MCP Totem" (red cylinder 1.2 x 5 m), "MCP Cone" (orange 1 x 2 m), "MCP Sign" (a
  4 x 3 m board on a post with a "SiMCP" picture on its street side), and "MCP Sculpture Park" (2 x 2 cells, grass
  with plaza paving on the two street-side cells; the game's fountain 0x1CEA0000 and two stone benches, two totems,
  two cones, the sign at the street, two MCP Maples and two Maxis maples). The park's building is a 1 m quad with
  a fully transparent texture (alpha test drops it). After a restart build_menu lists it under parks (2 x 2, 300);
  plopped at (40, 28) facing south onto the road (charged 300) and seen at zoom 5 laid out as designed (the Maxis
  maples are saplings; a small bin by the street the game added). Props are written single-sided, facing out.

## Session 2026-10-08 (Phase 8: agent-supplied models)

- **OBJ import** (meshimport): a test house written as a Wavefront OBJ (13 faces, 50 vertices; materials "wall"
  with a 256 x 128 brick-and-windows PNG and "roof" with a 128 x 128 tile PNG via an MTL's map_Kd; walls, gable
  triangles, an overhanging two-slope roof and a chimney; faces counter-clockwise from outside) became "MCP Gable
  House" (10.8 x 8.8 m, 9 m tall, two meshes and two FSH textures, lawn ground, an MCP Maple and an MCP Cone on the
  lot). After a restart it plopped at (43, 29) facing south (charged 400) and drew correctly at rotations 0 and 2:
  brick walls with windows, the door toward the road, the roof and chimney. OBJ v is flipped (the game's v runs
  down); the model is centred on x / z and stood on y = 0.
- **Night textures**: Maxis models' textures often have a twin at +0x8000 (3,413 of 11,558 references) and at +0x100
  (the next zoom), but the +0x8000 twins seen are unrelated pictures (another sprite atlas, a water tile), not lit
  versions - how 3D models get lit windows at night is still open.
- **Civic buildings in the game's data** (group 0x07BDDF1C; this setup's menus show plugin versions with other ids):
  police kiosk 0x03880000, 4-car local precinct 0x030C0000, 2-engine fire station 0x03100000, urgent care clinic
  0x03110000, K-8 school 0x03140000, coal plant 0x1F4D0000 (group 0xC8DBCCBA). The police simulator reads each
  station as two triples (0x6E0D50: 0x48D71ED0 int -> +0xC, ED1 int -> +0x10, ED2 float -> +8; 0x6E0CB0: ED9, EDA,
  EDB alike): kiosk 100 / 0 / 192.0 and 200 / 20 / 48.0. Fire 0x6AD7C0: 0x08F55DC0 / DC1 / DC2 (200 / 50 / 384.0),
  plus 0x29233E9A..C (96 / 32 / 128.0). Clinic 0x091B42A2 384.0, 0x69220415 500; school 0x691B42B3 384.0,
  0x8922041B 500. Several exemplars share an instance id (0x03100000 also outside the civic group), so a template
  is looked up with its group.
- **design_civic_building "MCP Precinct"** (police, the kiosk's service with 0x48D71ED2 = 384): after a restart it
  was first in the police menu; plopped at (56, 31) facing the road (80), and after 35 exact days the police
  coverage map (2-cell tracts) rose on 295 tracts out to 23.5 cells from the precinct (95 % within 22.5): the
  radius is in metres (384 m = 24 cells; the kiosk's 192 m reaches 12). Coverage at the precinct 152 -> 252. The
  fire, clinic and school numbers follow the same pattern in the data but were not each measured.
- **Rewards** (the game's mechanism): 70 buildings in SimCity_1.dat carry Conditional Building 0xEA3209F8; reward
  templates live in group 0x8A3858D8 (Mayor's House 0x031F0000: groups 0x150B Rewards menu + 0x1938 the MAYOR_HOUSE
  target group for missions, exclusion group 0xEA2E078B one per city, effect curve 0xAA60E745 [-100, 0, 100, 135],
  0xCA5B9305 / 0x2781284F / 0x27812850 effect pairs). What unlocks a reward is a *reward advice* named after the
  building (adv_rewards.lua and the Rush Hour record 0xFF3AFAA5: `a = create_reward_cityplanning('03840000')` with
  `function a.condition()` returning a requirement text while locked and `reward_state.AVAILABLE` when earned;
  missions unlock theirs through `s.reward_guid`). Lua also has game.unlock_reward_building (unused by the game).
- **design_reward**: "MCP Monument" (condition game.g_city_r_population > 10) and "MCP Far Monument" (> 1,000,000),
  identical statue-template buildings (groups [0x150B] only, a new exclusion group each) with a reward advice
  package each. After a restart build_menu("rewards") lists the Monument available and the Far Monument locked,
  still so after 10 more days: the game runs each design's condition itself.
- **Plugins mirror, ordinance folder**: the custom ordinance host reads ordinances only from Plugins\140-ordinances
  and its sub-folders, and SiMCP's mirror had that folder as a junction into the player's Plugins. launch.py now
  makes it SiMCP's own real folder holding a junction "000-player" to the player's folder (the old junction removed
  with rmdir, which removes only the link; tested on temporary folders first); the player's folder still holds only
  cam.ordinances. design_ordinance refuses to write until the folder is SiMCP's own.
- **design_ordinance "MCP Clean Air Pledge"** (type 0x0E exemplar in 140-ordinances\zzz_SiMCP: -30 a month, 100 to
  enact, air pollution 0.9, mayor rating +3, available through a Lua function from "game.g_city_r_population >
  10"): after a restart ordinances() lists it (0x71CCE6AE), first unavailable, available a month later (the DLL
  checks monthly); set_ordinance enacted it (fee 100) and the next month's expenses rose 1,338 -> 1,368 and it
  reports -30 a month.
- **Budget department** on "MCP Town Archive" (design_model_building department "SiMCP Archives", Government,
  40 cost / 15 income; the game's Budget Item properties with new department / line ids plus the DLL's 0x90222B81
  group and 0x4252085F name key): plopped at (44, 29); a month later departments() lists "SiMCP Archives"
  (0x13729023, Government Buildings, fixed funding) with 40 / 15, and the city's monthly totals moved by exactly
  +15 income and +40 expense.
- **Terrain brushes in the game's data**: 30 exemplars of type 0x27 in group 0x6A01FC2A; GodMountainDefault 0x6A33E1BA
  has two layers 0x8A0202xx / 0x8A0203xx (+0 shape id, +1 flag, +2 radius in metres per zoom [800, 500, 300, 150,
  100], +3 strength per zoom [0.1 .. 0.006], +4 / +5 mode and operation), icon 0x8A2602B8, menu order 0x8A2602B9.
- **design_brush "Big Hill"** (GodMountainDefault, radius and strength x2): after a restart terrain_brushes lists
  simcp_big_hill in god mode; on the unfounded tile (7, 0) of MCP Test (left without saving) one second held at
  (16, 32) with the game's brush raised the peak 270 -> 686.5 m (+430) and 1,462 cells by more than 1 m; the same
  second with Big Hill at (48, 32) raised it 270 -> 1,212.7 m (+949) and every one of the 2,080 cells of that half
  of the map by more than 1 m.
- **open_tile right after load_region** once failed reading the region view (ReadProcessMemory error 299: the view
  was still being built); open_tile now retries for up to 5 s (load_region then open_tile at once then worked).

## Session 2026-10-08 (Phase 9: harder items)

- **God-mode fire (solved)**: the Fire button does not select the menu exemplar (4): the disaster tool factory
  0x7E9DB0(item) builds the torch control (new 0x80, ctor 0x5805C0) only for item **0xA9DE8784** and makes it the
  current control (view slot 25, 2); any other item loads the disaster exemplar (group 0x29B6C670) and makes the
  generic disaster tool (vtable 0xA9EAA0, ctor 0x580220) - which is what SiMCP had selected, so nothing lit. The
  torch's vtable is 0xA9EB40 (0xA9EAA0's 31 slots are followed by the string "torch_inactive"; the old "slot 56"
  was slot 16 of the torch): slot 7 init (fire manager 0x621CDA33 QI 0x49B43F57 -> +0x2C), slot 16 OnMouseDownL
  0x5808B0 = pick terrain (view slot 36), city slot 95 to a cell, IgniteCell(x, z, 0, 1, 0), SetCause(1). Live:
  start_disaster("fire", 2, 31) in MCP Village lit the house there (disaster_status: fire 1 at (2, 31); flames and
  the red emergency frame in a snapshot); again at (3, 33) - then leaving the city with the fire burning was fine.
- **A second crash after a cancelled edge-reconcile prompt**: during the torch test the prompt came up; Cancel, then
  leave_city -> the game died: 0xC0000005 at 0x74D290 reading [terrain array + i*36] with the terrain's altitude
  array [+0x6C] null, in the terrain class's own code (vtable 0xAB3CF0, 108 slots). Like the 20:55 crash (the city
  view's camera control null after an advisor dialog closed, a cancelled reconcile prompt just before), objects
  of the city were half torn down. Not reproduced: the Phase 5 run cancelled the prompt and left the city cleanly.
  Until it is understood, avoid leaving a city right after cancelling that prompt (let a few days run first).
- **Flora never changes in normal play**: two test flora pointing at each other as successors (0x2A0348BA, duration
  0x2A0348BB = 30, spread 0x2A0348BC = 0; the wild "clump" chains use 18-24 / 7-10) were planted in MCP Village and
  stayed the same type, growth byte +0x2E = 1, through 3 years of exact days and 4 years at fast speed. The flora
  simulator's growth is off unless the "Flora" debug cheat turns it on (re/agents/cheats), which is also why menu
  trees stay saplings (their RKT5 states 0-2 are growth stages; 3+ share sprite atlases; no seasons).
- **Timed props**: a prop can show only at some hours (0x4A149631 Float32 [from, to], may wrap midnight: parked cars
  [19, 6], skate park [8, 19]) or on some dates (0xCA7515CC Uint8 [month, day], 0x4A764564 days, 0x0A751675 repeat
  every n days: the landmark gnomes [4, 15] 4 / 365). The prop simulator (0x6F3C60) registers such props and
  keeps, per date-timed prop, {every, days, next start day, next end day}. A timed prop must have the RKT4 model key
  with two states as the game's do: state 0 the model, state 1 RKT0 with instance 0 (no model) - the game hides
  it by switching to state 1. SiMCP's first props had RKT0 only and stayed shown (the bench template's properties
  were not the cause); with RKT4 they hide. Live in MCP Village ("MCP Seasons Park", placed 19 July 2018): no tree
  shown (each season prop waits for its next start date), 22 September the autumn props, 12 December bare oaks and
  snowy spruces, 1 May 2019 blossom; a [19, 6] beacon hidden in daylight and shown at night, a [7, 18] one the
  other way round, switching at dusk with the day / night cycle running (forced day or night freezes the clock: no
  switch). The Maxis gnome and night sedan were hidden as expected when plopped.
- **Animated props**: the game's have RKT0 models with one vertex block per frame (pizza sign 15 frames, graffiti
  55, billboard arm 60, an animated tree 20 at 10 fps) and 0xE83A081D true (occupant flag byte +0x2F 0x27 instead
  of 0x07). SiMCP writes spin / sway frames the same way (the pinwheel's occupant gets 0x27), but neither it nor
  the Maxis pizza sign changed between snapshots up to 4 s apart while cars moved: not confirmed.
- **My Sim faces of one's own**: the Select A My Sim dialog lists the game's 21 faces and then the Sims in
  <user folder>\MySim\MySims.dat (std::string at 0xB20E70, read by 0x43B860 each time the dialog opens): u32
  0x4A32E4AA, then per Sim a byte length + name, a byte male, a byte sign (ZodiacSign order), a byte length +
  picture file name without ".bmp" (a BMP in the same folder). Loose BMPs alone are not listed. The game writes
  the file only through its "import from The Sims" button (0x2A243DF9, the computer icon), disabled here because
  The Sims is not installed (0x43BC40 looks it up in the registry). A 36 x 36 24-bit BMP draws at the same size as
  the game's faces. The dialog object is the root window's command listener (+0x10C) - 8: entries at +0x50 (0x30
  bytes: +0 picture instance, 0 for one's own; +8 picture file; +0x1C name; +0x2C male; +0x2D sign), its sort
  order at +0x14, count +0x40, first shown +0x3C, first page button +0x44. Face button i (table 0xAB5208) shows
  order[first + i]; page buttons 0x12345000 + k set first = page * 21, the last page ending at the last face. The
  order is not fixed - adding one face of one's own reshuffled the game's 21 against the buttons - so SiMCP reads
  it, pages, clicks and checks the name box (the edit window's text at +0xE0 / +0xE4). Live in MCP Town: "MCP Face
  Sim" (a 36 x 36 BMP) and "Rosa Test" (a drawn face, renamed, Leo) moved in beside stock Agnes Liu; all three kept
  their faces through save and reload; with Rosa's picture moved away the city loaded fine and showed her face
  blank. While one Sim's own panel shows, the first ToggleMySimPanel only closes it: move_in toggles again.
- **Pedestrians (read, not made yet)**: walkers are exemplars of type 0x17 in group 0xC96E6806 with a model key of
  type 0x29A5D1EC: a 48-byte descriptor pointing at an FSH sprite atlas in group 0x49A593E7 (DXT3, 256 x 256
  pages) and frame tables of type 0x09ADCD75 (two per animation, 8 entries each: the frame's rectangle in the
  atlas and its anchor). New walkers are left for Phase 11 (realism), with the art.
- **Terrain looks**: the ground is drawn with textures of group 0x891B0E1A in SimCity_2.dat (instance = zoom <<
  8 | texture id, zooms 0-4, DXT1 256 x 256, *stored uncompressed*; the closest zoom holds two variants). Which
  texture a spot gets comes from the terrain INI (type 0, group 0x8A5971C5, instance 0xAA597172, in SimCity_1.dat,
  read by 0x74DC30 through the resource manager): [TropicalTextureMapTable], 32 rows of temperature (cold to warm)
  by 16 columns of moisture (dry to wet), plus [TropicalMiscTextures] (beach 0x39, cliffs 0x43 / 0x44) and the
  erosion / hydrology tunables. "Tropical" is the only climate string in the exe (0xAB4218); the Desert /
  Temperate / Arctic tables in the file are commented out and their texture ids (0x01-0x0F, 0x17-0x23) were never
  shipped. The table's ground textures from dry to lush: 0x32 sand, 0x33, 0x36, 0x37, 0x38, 0x35, 0x34, 0x31 dark
  grass. A plugin with the same keys overrides both (after a restart; the running game keeps the plugin open, so
  it cannot be replaced then). *Compressed* terrain textures drew the whole map one flat brown (close to texture
  0x2A): the loader reads the records raw - SiMCP writes them uncompressed, in the game's DXT1 layout (entries at
  16-byte boundaries). Live in MCP Town, in daylight: arctic (snow over the textures) white-grey, arid (table
  shifted 3 steps drier, sandy tint) tan with dry patches, default dark green again after the plugin was moved
  aside. The day / night light colours the ground strongly: at dusk the snow look showed beige (150, 122, 96).
- **Caught faults and the old stall (Phase 9 look)**: the power / water stall of Phase 3 was not seen again.
  Two fresh processes each caught one fault about 4 s after load_city, on the first view command (a snapshot's
  camera move; day_night("day")): a call through a garbage pointer in 0x4E5670, slot 21 of the class whose
  vtable is 0xA934A8 (the ambient audio layer: "cSC4AudioAmbienceLayer" follows it), releasing an interface it
  got with QueryInterface 0xCA400753 from one of its emitter lists. Two other identical runs had none: it
  depends on timing. One of those processes then ran MCP Town 90 days: power and water history kept going -
  this fault is not the stall. The framework's tick (vtable 0xAC3090 slot 16, 0x87A812) keeps a depth counter
  (+0xD8) that defers listener removals (slot 12) into a release queue (+0xAC) flushed when it drops back to 1;
  a fault unwinding through it would leave the counter up and leak every removed listener - but no bridge op
  runs the tick (StepDays calls the simulator's AdvanceTime / RunAgents / RunIdle directly), and the bridge's
  guard only unwinds frames below its own. A fault caught inside a simulator step (an agent mid-update) remains
  the likeliest cause. The bridge's crash log now adds, under each caught fault, the op, the call target or the
  command line that was running ("op 17 fn 00000010" for a deliberate bad call).
