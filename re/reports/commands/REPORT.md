# RE report: commands (cIGZCommandServer, command handlers, GZWin*) - SC4 1.1.641, static only

Scratch: `<workbench>\re\commands\` - the complete list is in **commands.json** (195 registrations: id, name,
param_info, registering function, call site, view, handler).

## 1. Command server implementation (cGZCommandServer)
- **Constructor 0x92AF7C** (CONFIRMED). +0: cIGZCommandServer vptr **0xAD17A0**; +4: cRZSystemService vptr 0xAD176C
  (service id 0xEB903A32, set via 0x91DE0F); +8: vptr 0xAD1754; +0x24: the registry, an STLport map keyed by
  command id (lookup 0x98129C; node value at +0x14 = id, name cRZString, parameter info; layout LIKELY); +0x30 the
  active cIGZCommandDispatcher*; +0x34 the default dispatcher (0x1C bytes, ctor 0x929C74, vtable 0xAD1644, created
  in Init); +0x38 the string command generator/parser (0x1C bytes, ctor 0x92A6C4, vtable 0xAD1708).
- **Windows vtable 0xAD17A0** (CONFIRMED by code):

| Slot | Function | Method |
|---|---|---|
| 0 | 0x92980D | QueryInterface |
| 3 | 0x92A982 | Init |
| 4 | 0x92AE88 | Shutdown |
| 5 | 0x92A9F8 | CreateCommandParameterSet(cIGZCommandParameterSet**) |
| 6 | 0x92B075 | RegisterCommand(id, name, info) |
| 7 | 0x929844 | RegisterCommands(cGZCommandInfo*, n) |
| 8 | 0x92AD10 | RegisterCommandParameterInfo |
| 9 | 0x92AD88 | UnregisterCommand |
| 10 | 0x929881 | UnregisterCommands |
| 11 | 0x92A1F6 | GetCommandInfo |
| 12 | 0x929EE0 | GetCommandID |
| 13 | 0x92AA4A | GetCommandIDFromCommandString |
| 14 | 0x92AAD8 | EnumerateCommands |
| 15 | 0x92AB0B | RegisterCommandGenerator |
| 16 | 0x92A236 | UnregisterCommandGenerator |
| 17 | 0x9DB663 | GetCommandDispatcher |
| 18 | 0x929B92 | SetCommandDispatcher (writes +0x30) |
| **19** | **0x929BBA** | **ExecuteCommand(char const* str, uint32 len, cIGZCommandParameterSet* out)** |
| **20** | **0x929BA8** | **ExecuteCommand(uint32 id, in, out)** |
| 21 | 0x9298AE | ExecuteCommandFormatted (cdecl) |
| 22 | 0x929BCC | ConvertStringToCommand |
| 23 | 0x929BDD | ConvertCommandToString |
| 24 | 0x929BEE | ConvertCommandOutputToString(paramSet, cIGZString&) |

  The two ExecuteCommand overloads are **swapped against the Mac/gzcom-dll declaration order** (ExecuteCommandFormatted
  calls +0x4C with (buf, len, set); the string generator's execute 0x929994 calls +0x50 with (id, in, out); 0x5C4740
  calls +0x4C with "GZWinEnableUserInput 0"). Slots 22-24 forward to [this+0x38] slots 9/10/11.
- **Registry**: the parameter info is NULL for every built-in command (each handler parses its own parameters).
  RegisterCommand registers only if the id is absent. cGZCommandInfo = {uint32 id; char* name; char* info}.
- **Registered commands** (195 registrations = 192 documented + 3 driving-panel commands; 183 unique names):

| Count | View | Registered in | Handler |
|---|---|---|---|
| 35 | app | 0x5C48E0 (vtable 0xAA1CE4) | DoMessage 0x5C8B30 (ListCommands, ExecuteCheat, GamePause, TakeSnapshot, Get/SetPopupModalDialogs*...) |
| 14 | app | 0x5C3FE0 (vtable 0xAA1660), GZWin* | DoMessage 0x5C7180 |
| 7 | app, fail without a city ([0xB43CEC]) | 0x5C45A0 (vtable 0xAA1AFC): PlaceNetwork, PlaceNetworkIntersection, PlaceLot, PlaceZone, Demolish, Get/SetViewTarget | DoMessage 0x5C5380 |
| 104 | city | city view window init 0x7E9900: RegisterCommands(table 0xB0DD98, 0x68) | DoMessage 0x7F53C0 -> 0x7F1C10(id, in, out) |
| 18 | city | city subsystems: 0x45BD20 (Get/Set CityName/MayorName/CitySize/Established), 0x4A4380 TextDecal, 0x69D240 PlaceBuilding, 0x6B2960 PlaceFlora, 0x703250 GetSimulationDate, 0x74FEA0 + 0x7503D5 (altitudes, sea level, ApplyTerrainBrush) | - |
| 3 | city | table 0xB0A110, driving panel (Min/Max/ToggleDrivingPanel) | - |
| 14 | region | region view 0x7B1DFA via [0xB43CB0] (LoadRegion 0x0BB3C277, LoadCity 0x0BB2747D, QuitGame, Cancel, Scroll*, RegionBitmapLoad, SetExpandedToolTips) | 0x7AF720 |

  12 region names reuse city ids (QuitGame 0x6A935E3C, Cancel 0x6A935CF1...). Table 0xB0935C holds
  {id, "kCommandID_*"} pairs.
- **Dispatch** (CONFIRMED): the default dispatcher's slot 5 (0x929AD5) fills the shared command message at disp+0xC
  (iid 0x4B99446A; type = id, in set, out set), calls **cIGZMessageServer2::MessageSend** (synchronous); handlers
  are cIGZMessageTarget2 objects registered with AddNotification(target, commandId). Returns the out set's status
  parameter **0x2B999D2B** (0 when the handler set none).

## 2. Running a command from the bridge (main thread)
- `cs` = GetSystemService(0xEB903A32, 0xCB90253A), also cached at [0xB43CB0].
- `cs->vtbl[5](&out)` creates an empty parameter set (refcount 1); `r = cs->vtbl[19](cmdStr, strlen, out)` parses
  with the game's parser and dispatches: r == 2 means unknown / unregistered command, parse failure or no
  dispatcher; otherwise r is the status (0 success). `cs->vtbl[24](out, str)` turns the output into text;
  `out->Release()`.
- Avoid slot 21 (ExecuteCommandFormatted): its va_list starts at the parameter-set argument.
- **ConvertCommandOutputToString (0x92A810)**: str.Resize(0) (slot 15); walks every parameter in id order, converts
  each variant (variant +0xDC) into a temporary cRZString, quotes (0x929740), appends " " (slot 17) and the value
  (slot 16). Output parameters have ids 0,1,2... plus the status id 0x2B999D2B (text probably ends with it, LIKELY).
- **Parameter set (cGZCommandParameterSet)**: size 0x28, ctor 0x92A5B0, vtable **0xAD16C8**, gzcom-dll order (slot
  15 = deleting dtor); +4 refcount; +8 STLport map<uint32, cRZVariant> header; +0xC count. AppendParameter uses
  id = last key + 1. SetStatusParameterValue (slot 10) = SetParameter(0x2B999D2B, int). Variant getters used by
  handlers (LIKELY): +0x24 bool, +0x60 uint32, +0x6C sint32, +0xDC ToString(cIGZString&).
- **cRZString** (the game's cIGZString): vtable **0xA80810**, size **0x14** {vptr; char* begin; char* end; end of
  storage; refcount} (STLport string; the default ctor allocates 8 bytes via 0x90CF54). **Default ctor 0x578390**
  (thiscall, no args); **ctor(char const*) 0x408480** (thiscall, ret 4). No standalone destructor: vtable slot 28
  (**0x44BF10**, thiscall, 1 arg): flag 0 destroys in place (frees with 0x90CF63), flag 1 also frees the object.
  Windows slots (MSVC reversed overload groups): 3 FromChar(char const*, len); 4 FromChar(char const*); 5 ToChar;
  6 Data; 7 Strlen; 8 IsEqual(char const*, len, bool); 9 IsEqual(cIGZString const&, bool); 10 IsEqual(cIGZString
  const*, bool); 11 CompareTo(char const*, len, bool); 12 CompareTo(cIGZString const&, bool); 13 operator=; 14 Copy;
  15 Resize; 16 Append(cIGZString const&); 17 Append(char const*, len); 18/19 Insert (string / chars); 20/21 Replace;
  22 Erase; 23-26 Find / RFind in the same reversed pattern (LIKELY); 27 Sprintf.

## 3. Handlers and honest play
- **PlaceLot** (0x2BB48D26, handler 0x5C53EA), CONFIRMED same core as the plop tool. Parameters: lot IID, cell x,
  cell z, facing (number or North/East/South/West), effects bool, bool. Requires a city; LotConfigurationManager
  [0xB43D18] slot 8 (IID) must return non-null. Builds the lot-plop view input control (`new 0x158`, ctor 0x4C0430,
  vtable 0xA90738) - the city view builds the same class for the player's tool (0x7EA3E0, 0x7F359F) - then Init,
  **0x4C1740**(&pos(x*16, z*16), facing, effects, &outRect), Shutdown, Release. 0x4C1740 is what the tool's
  OnMouseDownL (0x4C3120) calls: validity check 0x4BE750, tutorial restriction (city +0x148), **funds check** (cost
  vs BudgetSim [0xB43D64] slot 6 GetTotalFunds), then pays and places. Skips: menu availability (any lot IID,
  including unearned rewards / landmarks and growables, LIKELY), the mouse-preview flag and the click sound.
- **PlaceNetwork** (0xCBADE58E, handler 0x5C5B02). Parameters: type 0-12 (or by name), x1, z1, x2, z2, and a 6th
  bool read without a null check (always pass it). Gets cISC4NetworkTool via the network manager slot 5
  GetNetworkTool(type, false), Init. **6th true**: GetUITool (slot 6), then 0x5C4740 replays a real mouse drag
  through the command server (GZWinEnableUserInput 0, GZWinMoveCursorToPosition, GZWinGenerateInputEvent down/up,
  enable input 1) - the player's tool path (LIKELY same cost and rules). **6th false**: PlaceNetworkOccupants(x1,
  z1, x2, z2, 0, 0, true, -1) (slot 7), bypassing the drag / DrawNetworkLine / PlaceAllSegments path, probably no
  cost or funds check: cheat-class (GUESS, test).
- **PlaceZone** (0xEBB48D31, handler 0x5C5926): ZoneManager [0xB43D14] slot 11 PlaceZone(region, type, place=1,
  skipFundsCheck=0, flag, skipZoneSizeCheck=1, checkLotSize=0, &count, &err, 0); "Sim" clears the flag. Funds are
  checked but the zone-size limit is skipped (LIKELY). The player zone tool's own call was not located (system
  callers 0x46708C, 0x4AAECD).
- **Demolish** (0x2BB48D41, handler 0x5C5741): up to 16 rects of 4 ints; cISC4Demolition [0xB43D00] slot 6
  DemolishRegion(true, region, privilege, flags, 0, 0, &cost, 0, 0, 0, 0). Privilege default 1 (user, as the
  bulldozer), "Sim" 0; flags default 1, "None" 0, "Explode" 2. Cost returned as output parameter 0; any payment
  happens inside DemolishRegion (test).
- **SetViewTarget** (0x8BB756A4, 0x5C5D63): camera only ([0xB43DD0] slot 16); the "cell" form uses terrain height.
  GetViewTarget 0x5C55FB. **PlaceNetworkIntersection** (0x2BADF573): not analysed (documented as unimplemented).
- **App calls** ([0xB43C94] = cISC4App*): SaveCity / SaveCityQuick (city, 0x7F2D1D) -> App slot 9
  RequestSaveCity(param0, fast); QuitCity (0x7F2D72) -> App slot 12 RequestGoToRegionView(!param0) (1 skips the
  confirmation); QuitGame (city 0x7F2DE7, region too) -> App slot 10 RequestQuit(showDialog, saveFirst).
- **Region-only**: LoadRegion -> 0x7ADAC0(name); LoadCity -> 0x7AF4B0(name, size filter small/medium/large/any,
  "empty").
- **ExecuteCheat** (0xABAC26B5, 0x5C9A8D): the cheat-code manager [0xB43CAC] (App +0x84), same path as the cheat
  box: cheat-class. **GamePause** (0xCBB17C12, 0x5C9EC2): bool plus All / Draw / Animation / SimulationClock /
  24HourClock, then 0x5F91C0. **TakeSnapshot** (0x5C8B78) and **SimSpeed*** (0x6A935CAD/CB0/CB2/CB5, inside
  0x7F1C10) not traced.
- **Globals** (setter 0x601C10 / cache 0x601C20): [0xB43CEC] city (null outside), [0xB43CB0] command server,
  [0xB43CAC] cheat manager, [0xB43C94] cISC4App*, [0xB43D14] ZoneManager, [0xB43D18] LotConfigurationManager,
  [0xB43D00] Demolition, [0xB43D64] BudgetSimulator, [0xB43CF4] Terrain.

## 4. Threading and state
- ExecuteCommand runs **synchronously on the calling thread** through MessageSend into window and simulation code
  and reuses one shared message object: **main thread only**.
- City-table and city-subsystem commands exist only while a city is loaded (elsewhere r = 2); the 14 region
  commands only in the region view; Place*/Demolish/ViewTarget fail without a city; the 49 other app commands are
  always available.
- **Modal commands** (LIKELY): Open*Dialog, GZWinMessageBox, QuitGame(1, ...), QuitCity(0), possibly SaveCity's
  notification, LoadCity and LoadRegion - run them deferred, or first "SetPopupModalDialogsEnabled 0" (App slots
  23/24; GetPopupModalDialogsSafe also exists).

## 5. GZWin* window lookup and clicking a button
- The GZWin handler gets **cIGZWinMgr** from GetSystemService(**0xA417445E**, **0x5A4**) (+0x18) and stores WinMgr
  slot 3 GetMainWindow() at +0x1C (init 0x5C3FE0).
- Lookup helper 0x5C4EC0: id = param0, parent = param1; with a parent, `root->GetChildWindowFromIDRecursive(parent)`
  (cIGZWin slot 35, +0x8C) then `->GetChildWindowFromIDRecursive(id)`.
- **GZWinClickButton** (0xCBA12CFA, 0x5C7B62): status 2; find the window, QI cIGZWinBtn (**0x8810**); WinMgr slot 15
  (+0x3C)(win, cGZMessage const&) with {7, W/2, H/2, 0} (left down at the centre; W/H from cIGZWin +0xA4/+0xA8)
  then {0xA, W/2, H/2, 0} (left up); status 0. (The 2-argument PostMessageToTarget overload is slot 15 on Windows,
  swapped against gzcom-dll.) The click is posted: the button reacts on the next pump.
- GZWinWaitForWindow, IsWindowPresent, SetWindowText and SelectListboxItem use the same lookup helper (LIKELY).

## Open questions (live tests)
1. "ListCommands" and "GetAppState" through slots 19 and 24 in the region view: r and the text; is the status the
   last token?
2. Funds ([0xB43D64] slot 6) before / after "PlaceLot <IID> x z 0 0 0" = the plop tool's cost?
3. Funds before / after "PlaceNetwork 0 x1 z1 x2 z2 0" and with the 6th parameter 1 (expect 0 to be free).
4. "PlaceZone 1 ..." over an area larger than the zone tool allows: funds and zoned cells.
5. Funds before / after "Demolish x1 z1 x2 z2", and with "Sim".
6. "PlaceLot" with a locked reward IID: does it plop?
7. "QuitCity 1" and "SaveCity 0" from the main thread: does a dialog block the call?
8. "GZWinClickButton <id> 0" on a known UI-layout button id: does the click land on the next pump?
