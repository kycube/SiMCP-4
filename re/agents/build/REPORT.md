# RE report: building like the player (networks, zones, plop, bulldoze, terraform, flora, picking). SC4 1.1.641, static only

Scratch folder: `<workbench>\re\build\`. It holds `h.py` and `run.sh` (wrappers around pe.py) and the disassembly dumps `ui_down/ui_up/pas/placezone/plop/demo/zminit.txt`.

**Conventions used below:**
- **Slot numbers** are Windows vtable slots.
- **Calling convention:** everything is thiscall (callee pops) unless noted.
- **Budget** means `B = [0xB43D64]` (vtable 0xAB0908). Its slots, CONFIRMED by code:
  - 5 `SetTotalFunds(int64)` 0x690140
  - 6 `GetTotalFunds` 0x68FD10
  - 7 `DepositFunds(int64)` 0x690170
  - 8 `WithdrawFunds(int64)` 0x690200: returns false and changes nothing if funds < amount.
- **The city view** is `V = [0xB43DC4]` (cISC4View3DWin, vtable 0xABCE40). Set by 0x602590.
  - `[0xB43DC8]` is its cIGZWin, `[0xB43DD0]` the renderer (cSC43DRender), `[0xB43DD8]` the renderer's slot 8 (GetViewUtilities).
  - V slots: 24 GetCurrentViewInputControl 0x7E65E0; 25 SetCurrentViewInputControl(ctrl, op) 0x7EBD70; 26 Remove 0x7E9390; **36 PickTerrain(sx, sz, float out[3], bool stopAtWater) 0x7E5840**; 37 PickOccupant.
  - V slots 42/43 are swapped: 42 = SetCostIndicator with 2 args, 43 = SetCostIndicator(cost) with 1 arg; 44 ClearCostIndicator.
- **View input controls** (base ctor 0x5FB320) share these slots: 3 Init, 4 Shutdown, 14 OnKeyDown(vk, mods), **16 OnMouseDownL(sx, sz, mods)**, **18 OnMouseUpL**, **20 OnMouseMove**, 23/24 Activate/Deactivate.
- **The menu's tool dispatcher** is non-virtual **0x7E9FA0** (this = V; args msg, param, bool closeMenus; ret 0xC). The item-click handler 0x7EB2D3 and the button handler 0x7F2273 call it. Messages:

| msg | Tool | Constructor | Gate |
|---|---|---|---|
| 0x4A2B2467 | network (table in 1b) | new 0x58, ctor 0x6620A0(type) | city established |
| 0x4A2B2466 | zone(type) | 0x7E6DA0 | established |
| 0x6A2B245F | plop(lot id) | ctor 0x4C0430 | established |
| 0x4A2B2462 | god-mode terraform (brush, free) | 0x7E5910 | none |
| 0x8A313C52 | mayor-mode terraform (brush, charged) | 0x7E5910 | none |
| 0xEA5AD08D | flora(type) | 0x4BB900 | none |
| 0x6A5AC478 | 0x7E75B0 (not analysed) | | |
| 0x4A2B2464 | disaster tools 0x7E9DB0 | | |

  Each branch creates the control and calls `V->SetCurrentViewInputControl(ctrl, 2)`. "Established" = city slot 22. All CONFIRMED.

## 1. Networks

**a. Who handles the player's drag** (CONFIRMED)
- The network view input control: vtable 0xAAB008, size 0x58, ctor 0x6620A0(type).
  - Its Init 0x662160 takes a *fresh* tool: network manager `NM->GetNetworkTool(type, true)`. NM = city slot 38 = `[city+0x200]`, vtable 0xAA7AD0, slot 5 = 0x6108D0. The control AddRefs it and calls its Init (slot 3).
  - It then calls tool slot 6 `GetUITool(&ui)`.
  - Its mouse handlers forward to the UI object: OnMouseDownL 0x661EE0 → ui slot 9; OnMouseUpL 0x661F50 → ui slot 10; OnMouseMove → ui slot 11.
- **cSC4NetworkToolUI**: size 0x134, ctor 0x645D50, vtable 0xAA9140. Slots: 9 OnMouseDownL 0x645F50, 10 OnMouseUpL 0x646D00, 11 OnMouseMove 0x646AC0.

**b. GetNetworkTool and type numbers** (CONFIRMED)
- `GetNetworkTool(type, createNew)`: type must be ≤ 12. With false it returns the cached tool `[NM+0x88+4*type]`; with true it builds a new one (refcount starts at 0).
- Tool classes and vtables: generic 0xAA8748 (ctor 0x62C5F0(type)); pipe 0xAA99A8; subway 0xAAA5C0; power line 0xAA9F30.
- Type numbers, with the menu item id that selects each:

| Type | Network | Menu id |
|---|---|---|
| 0 | road | 0x8C329937 |
| 1 | rail | 0x29 |
| 2 | elevated highway | 0x31 |
| 3 | street | 0xEA6E379D |
| 4 | pipe | 0x2992F72C |
| 5 | power line | 0x32 |
| 6 | avenue | 0x2B730C5B |
| 7 | subway | 0x299237BF |
| 8 | light rail | 0x2B79E398 |
| 9 | monorail | 0x4BE099DE |
| 10 | one-way road | 0x0BE099C1 |
| 11 | dirt road (RHW under NAM) | 0x2BE099A9 |
| 12 | ground highway | 0x0BE0998F |

- NAM networks are these same types. Ids 0x6A47xxxx open a separate puzzle-piece control (ctor 0x661130(id & 0xFFFF), size 0x90; not analysed).

**c. Tool slots** (vtable 0xAA8748; 81 slots; order matches gzcom-dll; CONFIRMED by argument counts and the UI's call pattern)

| Slot | Function | Method |
|---|---|---|
| 3 | 0x6269C0 | Init |
| 4 | 0x626D30 | Shutdown |
| 5 | 0x626F90 | Reset |
| 6 | 0x623B20 | GetUITool(ui**) |
| 7 | 0x629210 | PlaceNetworkOccupants (8 args) |
| 13 | – | ClearFailureReason (`[+0x20C]=0`) |
| 14 | – | GetFailureState (`[+0x20C]!=0`) |
| 15 | – | GetFailureReasonString(cIGZString&) |
| 16 | – | ClearOccupantHighlights |
| 17 | – | ClearCellPreviews |
| **18** | **0x63AF40** | **`bool DrawNetworkLine(SC4Point<int> const* start, SC4Point<int>* end_inout, bool pathFlag, int type)`**, ret 0x10 |
| **19** | **0x63BDC0** | **`void PlaceAllSegments(bool commit, bool pathFlag, bool allowNeighborConn, int type)`**, ret 0x10 |
| **20** | **0x625640** | **`int GetCostOfSolution()`** |
| 21 | – | EnablePreviewUpdate(bool) (byte +0x234) |
| 22 | 0x62CA20 | SetAnchorPoints(SC4Vector<SC4Point<int>> const*) – copies the vector into +0x118 |
| 30 | – | GetPossibleBridges(SC4Vector<int>&) → bool |
| 31 / 32 | – | Get / SetPreferredBridge(int) |
| 34 | – | SetBridgeAltitudeOverride(float) |
| 41 | – | GetPossibleNeighborConnection(info&) → bool |
| 45 | – | PenWidth(int&, int&) |
| 46 | – | StopPickAtWater |
| 49 | 0x62D450 | QueryUserForPotentialIntersections |

- PlaceAllSegments loops over consecutive anchor pairs: DrawNetworkLine, then 0x63B830 places the segment. When commit is true it also starts a construction crew (ctor 0x6070C0).
- `pathFlag` = **NOT Shift**: GetAsyncKeyState(VK_SHIFT) is read at mouse-down (0x891AE4). What Shift actually changes is a GUESS.

**d. How screen points become cells** (UI pick function 0x6457E0, CONFIRMED)
- `V->PickTerrain(sx, sz, world, tool->StopPickAtWater())`.
- `cell = clamp((int)(world.x / cellSize), 0, nx-1)`, same for z. cellSize and counts come from terrain `[0xB43CF4]` slots 6/7/8.

**e. Drag behaviour** (CONFIRMED)
- **Mouse down** sets `anchors = [c, c]`, calls tool slot 22, and locks the city UI (city slot 106).
- **Every move** (preview 0x645640):
  1. Tool slot 5 Reset; 32 SetPreferredBridge(`[ui+0x64]`, -1 at start); 34 SetBridgeAltitudeOverride(`[ui+0x70]`, -1.0f); 21 EnablePreviewUpdate(1); 13 ClearFailureReason.
  2. `ok = DrawNetworkLine(&anchors[n-2], &cur, pathFlag, type)`. If ok: `anchors[n-1] = cur` (possibly clipped by the tool), slot 22, then `PlaceAllSegments(0, pathFlag, 0, type)`.
  3. Valid = `!GetFailureState`.
  4. `cost = GetCostOfSolution` goes to V slot 43; it shows red if cost > GetTotalFunds.
- **Pausing during the drag** adds a bend anchor (0x6460F0, time-based). A multi-point polyline is therefore just a longer anchor list.
- **Two-cell-wide networks** (PenWidth > 1): with two anchors, the UI moves the start back by one cell along a positive drag axis (0x64565C).
- **Diagonals** come out of the tool's own path solver between two anchors. There is no other curve mechanism.

**f. Mouse up 0x646D00** (CONFIRMED)
- If GetFailureState → cancel and play a sound.
- Else if `GetPossibleBridges(&v)` → the bridge chooser window opens (layout 0x0C525B9E / 0x5386D516) and the commit runs later with the chosen bridge.
- Else → commit **0x645370**:
  1. `cost = GetCostOfSolution`.
  2. **`B->WithdrawFunds((int64)cost)`** (slot 8). If it returns false, **nothing is placed**.
  3. Reset; SetPreferredBridge; SetBridgeAltitudeOverride; SetAnchorPoints; `PlaceAllSegments(0, pathFlag, 1, type)`.
  4. If `GetPossibleNeighborConnection(&info)` and no failure: NeighborsSim `[0xB43D8C]` slot 5 (0x6D15E0) asks a **modal yes/no** (0x78DFF0) → nb.
  5. Reset … SetAnchorPoints; **`PlaceAllSegments(1, pathFlag, nb, type)`**.
  6. Slots 17 then 16 (clear previews); then slot 49 QueryUserForPotentialIntersections; slot 5 Reset; unlock the city UI (slot 107).
- 0x78DFF0 returns "no" straight away when popups are disabled (cISC4App slot 23 = byte A+0x645; slot 24 sets it).
- Slot 49 asks a modal yes/no for each auto-intersection. If yes, it checks funds, places, and does its own WithdrawFunds.

**g. Where the money is taken:** only in the UI (0x645370 and 0x62D450). PlaceAllSegments, 0x63B830 and PlaceNetworkOccupants never touch the budget. So:
- The **PlaceNetwork command with 6th parameter 0 is free (cheat-class)**.
- With 6th parameter 1 it replays a real drag through GZWinMoveCursorToPosition, which **moves the cursor**.

## 2. Zoning
- **Activation:** zone control ctor 0x4DAE80(zoneType), vtable 0xA92CA8, id 0xA766C101, created by 0x7E6DA0 (established only). **Type 0 = de-zone** (button 0x7F27D2, key 0x7EC778).
- **OnMouseUpL 0x4DBAF0:**
  1. ZoneDeveloper `[0xB43DB0]` slot 7 `SetOptions(alt = mods&4, placeStreets = !(mods&1), customSize = mods&2)`. The modifier bits are 1 Ctrl, 2 Shift, 4 Alt (LIKELY).
  2. Pick the end cell.
  3. Build `SC4CellRegion<long>` (gzcom-dll struct, size 0x24; ctor 0x442640(rect*, true); cell-map dtor 0x441A60).
  4. 0x4DA7A0 runs the tutorial check (`[0xB43D38]` slots 8/10), then calls **ZM `[0xB43D14]` slot 11 PlaceZone 0x4DD780** (10 args, ret 0x28, returns bool) as:
     `PlaceZone(&region, type, place=1, skipFunds=0, checkSlope=1, skipZoneSizeCheck=0, checkLotSize=(type!=0), int64* outCost, int* outErr, 0)`.
  - The **8th argument receives the int64 cost**, not a cell count.
- **The preview** (0x4DB240) makes the same call with place=0, plus a set that collects the lots that would be demolished.
- **PlaceZone charges by itself** (CONFIRMED): when `place` is set and cost ≤ funds it calls `WithdrawFunds(cost)`. Otherwise error 1. `skipFunds=1` makes the cost 0.
- **Cost:** for each cell whose zone changes, `zoneCost[new]` (`ZM+0x1E0`) + `dezoneCost[old]` (`ZM+0x260`). Add the demolition cost of networks removed (occupant GetCostOfDemolition) and of lots removed (Demolition slot 7), plus landfill extra.
- **Tuning values** come from the "Zone Manager" exemplar 6534284A-E7E2C2DB-E9482490:
  - zoning cost per cell (E94825B4): R 10/20/50, C 10/20/50, agriculture 10, I 20/50, military/airport/seaport/spaceport 1, landfill 50;
  - de-zoning cost (E94825B5): 1 per cell;
  - minimum drag size (E94825B2, error 3): 1, or 4 for agriculture;
  - maximum drag size (E94825B3, error 4): 32, or 48 for agriculture;
  - maximum slope: E94825B9.
- **The PlaceZone command** passes skipZoneSizeCheck=1 and checkLotSize=0. Funds and cost are the same as the player's tool; it only allows a bigger area in one call and skips the per-lot check at 0x4DDA4A (whose meaning is a GUESS).

## 3. Plopping lots
- **Menu entry:** `0x7E9FA0(0x6A2B245F, id, close)` creates the control with `0x4C0430(0, id, 0, 0)` (size 0x158) — exactly the arguments the PlaceLot command uses — and makes it current.
- **The click** is OnMouseDownL 0x4C3120: PickTerrain → `0x4C1740(cS3DVector3* worldPos, facing = [ctrl+0x3C] (0..3, rotated by OnKeyDown 0x4C3060), effects=1, SC4Rect* out)`, ret 0x10.
- **Inside 0x4C1740:** validity and cost (0x4C1110 / 0x4BE750), tutorial check, `GetTotalFunds ≥ cost` when cost ≠ 0, place, then **`WithdrawFunds(cost)` at 0x4C1C19** (CONFIRMED).
- **Reward / conditional buildings:**
  - The control does not check the conditional status. It only caps plops per activation (`+0x154`): 1000 normally; 1 for a City Exclusion Group or Conditional building; 16 − TrafficSim slot 32 for ferry terminals.
  - The count is tracked for any placement path: CivicBuildingSim DoMessage 0x69E1A0 increments / decrements `status->count` (u16 at +2) on messages 0x99EF1142 / 0x99EF1143 (occupant inserted / removed) for conditional buildings (CONFIRMED).
  - Unlocking (status bit 2) is checked only by the menu builder 0x7EFF40.

## 4. Bulldozing
- **Control:** ctor 0x4B9070 (new 0xD8; the button handler 0x7F26D7 creates it), vtable 0xA901A0, id 0x46DDB5F1. Init 0x4B8AB0 stores the budget at +0x28 and Demolition `[0xB43D00]` at +0x30.
- **Preview** 0x4B93B0: a dry run, `DemolishRegion(0, region, 1, 1, 0, 0, &cost[+0x88], 0, 0, 0, 0)`. A single occupant that answers QI 0x4B44FBE2 instead uses slot 8 `DemolishOccupant(0, occ, 1, 1, &cost, 0, 0)`.
- **OnMouseUpL 0x4B9C50:** **`B->SetTotalFunds(GetTotalFunds() − cost)`** (slot 5). There is no funds check, so money can go negative (LIKELY). Then `DemolishRegion(1, region, privilege=1, flags=1, clearZoned=0, filter=0, &cost, 0, effectOcc, effX, effZ)` (slot 6, 11 args, ret 0x2C), or slot 8 for the single occupant.
- **Demolition never touches the budget** (no budget reference in 0x464000-0x46C000; Init 0x466EF0 stores no budget). So the **Demolish command is free (cheat-class)**.
- Networks, lots and flora in the region all go in one call; the cost is the sum of each occupant's demolition cost (LIKELY).

## 5. Terraforming and flora
- **Terrain scrubber:** ctor 0x4D9430(brushId, bool god) (size 0x130), vtable 0xA92A10, id 0x68E29401. +0x5C = terrain.
  - God mode (message 0x4A2B2462) is free.
  - Mayor mode (0x8A313C52), per application (0x4D9740): `cost = round(terrain slot 62 GetCostPerBrushApplication(brush) × strength[+0x8C])`, then `WithdrawFunds(cost)`. Only on success is terrain slot 57 ApplyBrush(brush, &scrubState[+0x74]) called (argument layout is a GUESS). Mouse-down (0x4D9B90) refuses when funds ≤ 0. CONFIRMED.
- **Level-terrain control** (0x4BDC60, vtable 0xA905C0): terrain slot 49 SetAltitude(rect, alt, 1, 1), free.
- **ApplyTerrainBrush command** (case 6 at 0x74A933 → 0x4D8B90): no budget access → free (cheat-class, LIKELY).
- **Flora control:** ctor 0x4BB900(type), vtable 0xA903B8.
  - Cost per tree = FloraSim `[0xB43D80]` slot 7 GetStaticFloraData(type), int64 at +0x160.
  - While dragging (0x4BBC80): if funds ≥ cost → slot 17 `AddNewFloraOccupant(type, float pos[3], false)`. If that returns an occupant → `WithdrawFunds(cost)` and Aura `[0xB43D60]` slot 6 (x, z, 1).
- **PlaceFlora command** (0x6B33F3) calls slot 17 with no charge (cheat-class).

## 6. Cell picking (an alternative to direct calls)
- **Every control picks through V slot 36**: network, zone, plop, flora and demolish all call it at `[view]+0x90`. The vtable entry is at **0xABCED0**; it calls renderer slot 60 PickTerrain(int, int, float*, false, stopAtWater).
- SC3K-style trick: patch 0xABCED0 so that, while an "inject" flag is set, it returns `((x+0.5)*16, terrain slot 13 GetAltitude, (z+0.5)*16)`. Then call the control's slots 16/20/18 directly with dummy screen coordinates — no SetCursorPos.
- Caveats: the network UI still reads Shift through GetAsyncKeyState, and its pause-to-bend anchors depend on timing.
- **World → screen** (as 0x5C4740 does it): `0x7F78E0(this = [0xB43DD8], cS3DVector3* inout)`.

## Layouts
- **Network UI:** +0x14 tool; +0x18 sound object; +0x1C view; +0x20 tick count; +0x25 dragging; +0x2B pathFlag; +0x34/+0x38 current cell; +0x3C/+0x40 click cell; +0x44 vector<SC4Point<int>> anchors; +0x64 preferred bridge; +0x70 float bridge altitude; +0x80 type; +0x130 bridge dialog.
- **Network control:** +0x1C view; +0x48 tool; +0x4C UI; +0x50 type.
- **Zone control:** +0x30 ZM; +0x3C type; +0x58 optional fixed region; +0x5C..+0x68 rect; +0x6C cell size.
- **Plop control:** +0x2C 0; +0x30 lot id; +0x3C facing; +0x94 preview valid; +0x154 plop cap.

## Recipes for the bridge (main thread)
1. **Network, honest** (= 0x645640 + 0x645370):
   - `t = NM->vtbl[5](type, 1)`; `AddRef`; `t[3]()` (Init).
   - Prepare: `t[5]()`; `t[32](-1)`; `t[34](-1.0f)`; `t[21](1)`; `t[13]()`.
   - Solve: `ok = t[18](&A, &B, 1, type)` (B may come back clipped); `anchors = {A, B[, …]}` (STLport vector {begin, end, cap}; it is copied); `t[22](&anchors)`; `t[19](0, 1, 0, type)`.
   - Check: if `t[14]()`, read the reason with `t[15](str)`. `cost = t[20]()`.
   - Bridges: if `t[30](&v)`, choose one and set it with `t[32](id)` (the player's dialog).
   - Pay: `if (!B[8]((int64)cost))` → insufficient funds, nothing placed.
   - Commit: `t[5]; t[32]; t[34]; t[22]; t[19](0, 1, 1, type)`. Then `nb` = user choice if `t[41](&info)` returns true. Then `t[5]; t[32]; t[34]; t[22]; t[19](1, 1, nb, type)`.
   - Finish: `t[17](); t[16](); [t[49]()]; t[5](); t[4](); Release()`.
   - Same costs and rules as the player. No dialogs if the bridge passes nb itself and skips slot 49 (or disables popups).
2. **Zone:** `ZD[7](alt, streets, custom)`; `ZM[11](&region, type, 1, 0, 1, 0, type != 0, &cost64, &err, 0)`. Honest; split areas into drags of at most 32×32 (48 for agriculture).
3. **Plop:** `PlaceLot` command (same 0x4C1740 path), plus the menu gates (CivicBuildingSim slots 5/6, established city) and one plop per activation for conditional / exclusion buildings.
4. **Bulldoze:** `D[6](0, &r, 1, 1, 0, 0, &c, 0, 0, 0, 0)` → `B[5](B[6]() − c)` → `D[6](1, &r, 1, 1, 0, 0, &c2, 0, 0, 0, 0)`.
5. **Tree:** `F[7](type)+0x160` → funds check → `F[17](type, pos, 0)` → `B[8](cost)` + `Aura[6](x, z, 1)`.
6. **Terraform (mayor mode):** drive the scrubber control through the PickTerrain patch rather than calling ApplyBrush directly.

## Open questions (live tests)
1. Road A→B with the recipe: does funds drop by exactly GetCostOfSolution? Compare with dragging the same road by hand.
2. Does GetCostOfSolution after `t[19](0, …)` cover all anchors of a 3-point polyline?
3. Effect of pathFlag 0 vs 1 (Shift): a diagonal road with each value.
4. Read funds before and after the bulldozer when cost > funds: does it go negative?
5. PlaceZone 8th argument equals the drop in funds; zoning 40×40 with skipZoneSizeCheck=0 → error 4.
6. PlaceLot at (x, z) vs a menu plop: lot origin vs the passed position (cell*16 or center?).
7. With popups disabled (App slot 24 = 0), drag a road to the city edge: no neighbour dialog and no connection.
8. Patch 0xABCED0 and inject a zone drag through slots 16/20/18: are the cells right, is the cursor untouched?
