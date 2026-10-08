# RE report: view-disasters (SC4 1.1.641, static only)

Scratch folder: `<workbench>\re\view-disasters\`. It holds `h.py` (pe.py helpers), `sw.py` (a symbolic walker that resolves a command id to its case in the city command handler 0x7F1C10), `cmds.txt` and disassembly dumps. All addresses are SC4 VAs. `this` is thiscall in ecx.

## 1. Answers

**Q1. Disasters**
- **Correction to app-city.** The vtable of the disaster layer that matters is 0xA9E390, not 0xA9E3DC (CONFIRMED). `[0xB43D3C]`, city slot 72 (0x459830) and `[city+0x1C4]` all hold the **cISC4DisasterLayer\***, which sits at object+8. It is created in 0x45B017 with clsid 0x61F6ABF5 and iid 0x29B02A2C. The object's QI is 0x577400. Its own +0 vtable is 0xA9E3DC (serializable side) and +0xC is 0xA9E380 (message target).
- **Layer vtable 0xA9E390**: 19 slots in Mac / gzcom-dll order (CONFIRMED). Offsets below are relative to I (the interface pointer).

| Slot | Function | Method and what it does |
|---|---|---|
| 5 | 0x5773C0 | EnableDisasters(bool). It is a **counter at I+0x38**: false adds 1, true subtracts 1, floor 0. |
| 6 | 0x5773B0 | DisastersEnabled: `[I+0x38]==0` |
| 7 | 0x578060 | GetDisasterManager(typeId): STLport map at I+0xB0, value at node+0x14 |
| 8 | 0x578FC0 | DisasterHasBegun(inst) |
| 9 | 0x577E90 | DisasterHasEnded(), no argument (as on the Mac) |
| 10 | 0x5773F0 | IsADisasterOngoing: `[I+0x40]!=0` |
| 11 | 0x577810 | GoToNextDisaster |
| 12 | 0x5775E0 | GetMostRecentDisasterLocation |
| 13 | 0x5783D0 | RegisterDisasterLocation (6 arguments) |
| 16 | 0x577680 | GetDisasterLocationCount: vector I+0xC4..+0xC8, 20-byte records |
| 17 | 0x577920 | GetDisasterLocationByIndex(i, inst\*\*, int\*x, int\*z). **It AddRefs the instance**: the caller must Release. |
| 18 | 0x578900 | GetDisasterCost: returns the pointer `I+0x48` (a struct, not an int) |

- **Managers.** Layer Init (0x578E70) walks the table at 0xA9E3F4, which holds 7 {typeId, clsid} pairs. Each manager is created with iid 0x021E9CBF; its GetID (slot 5) is the type id. On Windows **slot 6 = AttemptDisasterStart(cellX, cellZ)** and slot 7 = AttemptDisasterStart() (overloads swapped, CONFIRMED by argument counts). Shared slots: 8 AddInstanceToList 0x578230; 9 RemoveInstanceFromList 0x578310 (riot uses 0x57D7E0); 10 GetActiveInstanceCount 0x577990; 11 GetInstances 0x577450 (SC4List).

| Type | Type id | Manager vtable | Instance vtable | Slot 6 | Slot 7 |
|---|---|---|---|---|---|
| Volcano | 0xC4C90997 | 0xA9E994 | 0xA9EA60 | 0x57F600 | 0x57F5A0 |
| Fire | 0x621CDA33 | 0xA9E51C | 0xA9E590 | 0x579150 | 0x4E13E0 |
| Earthquake | 0x42963812 | 0xA9E090 | 0xA9E140 | 0x576D80 | 0x4E13E0 |
| PipeBurst | 0x4A1332E8 | 0xA9E66C | 0xA9E730 | 0x57D180 | 0x57D040 |
| Riot | 0xCA380B06 | 0xA9E798 | 0xA9E818 | 0x57EA10 | 0x4E13E0 |
| Effect | 0x6A7B4397 | 0xA9E1B8 | - | 0x88B3E0 (`xor eax,eax`: does nothing) | 0x4E13E0 |
| Toxic | 0xEBFB0404 | 0xA9E89C | 0xA9E920 | 0x57F220 | 0x4E13E0 |

- Fire's slot 6 calls the fire interface at mgr+0x1C, slot 5 = **IgniteCell(x, z, 0, 0, 0)**. That proves the arguments are **cell** coordinates (CONFIRMED). The community `cGZExtraExtraCheatsDllDirector.cpp` also calls AttemptDisasterStart(nX, nZ).
- **Instance vtables**: slot 3 Shutdown, 4 GetManager, 5 GetID (= type id), 6 GetLocation(int&, int&) 0x62C980 (shared), 7 GetPhase.
- **What the player does (god-mode Disasters menu)** (CONFIRMED):
  - Each menu entry is a type-0x22 exemplar in group **0x29B6C670**:

| Instance | Disaster | Manager id (property 0x4A08C701) |
|---|---|---|
| 1 | Volcano | 0xC4C90997 |
| 2 | Earthquake | 0x42963812 |
| 3 | PipeBurst | 0x4A1332E8 |
| 4 | FlameItem (fire) | none |
| 5 | Meteors | 0x6A6D0EE7 |
| 6 | Tornado | 0x02963821 |
| 7 | Lightning | none |
| 0x0A760F65 | RobotAttack | 0xCA9C3DA7 |
| 0x0C059A77 | Truckasaurus (Autosaurus) | 0x6A6D0EE7 |
| 0x4B9547F1 | UFOs | 0x6A6D0EE7 |
| 0x4A38206D | Riot | (not traced) |

  - Other exemplar properties: 0x4A08C700 = effect name, 0x8A2602B9 = menu order, 0x8A416A99 / 0xCA416AB5 = name / tooltip (LTEXT group 0x8A5E03EC).
  - The menu calls the city view's **SelectTool 0x7E9FA0(category, id, bool)** (thiscall, ret 0xC) with category **0x4A2B2464** and id = exemplar instance. That leads to 0x7E9DB0(IID):
    - it loads the exemplar through `[0xB43CA8]` slot 3;
    - creates the disaster input control (new 0xB4, ctor 0x580220, vtable 0xA9EAA0, control id 0x6A40222A);
    - 0x580460 looks up the manager (layer slot 7) and stores it at tool+0xAC;
    - then view slot 25 SetCurrentViewInputControl(tool, 2).
  - On click, OnMouseUpL (slot 18, 0x580370) calls **mgr->AttemptDisasterStart(cellX, cellZ)**.
  - Meteor, tornado, UFO, robot, autosaurus and lightning have **no registered manager**. They take the effect path (slot 30, 0x5803D0): the effect "<name>_button_trigger" (0x4BB590) is placed at the clicked point.
- **Selecting a tool by message**: message 0x49D993D4 to the view's target (view+0xC), with [msg+8] = category and [msg+0xC] = id, gives SelectTool(cat, id, 1) (0x7F3EC7) (CONFIRMED).
- **ToxicSpill** (0x0BFB41BA) is a hidden command that exists only in a city. The Toxic manager's Init (0x57EC80) registers it; handler 0x57F260 reads 3 sint32 parameters, creates an instance (0x57EFD0) and calls 0x57F090(p0, p1, p2). Probably x, z and a size; this is cheat-class.
- **Disasters on/off**: not a player option. EnableDisasters is a counter and its only callers are 0x5650E0 / 0x565160 (mission / driving code, LIKELY U-Drive). Whether AttemptDisasterStart checks it is not traced (GUESS: it does).
- **Ending**: instances report GetPhase. The managers use RemoveInstanceFromList and the layer's DisasterHasEnded. Messages: 0xCA1B1E64 PeriodStarted / 0xAA1B2002 PeriodEnded / 0xA9C7CAB6 PhaseChange. Damage figures are the advisor variables g_disasters_damage_building_count / g_disasters_damage_cost.
- **Accidental fires and riots** come from the simulation. Fire's own interface (at mgr+0x1C) has IgniteOccupant, IgniteCell, ExtinguishCell, QuickBurnCell, IgniteCellRadius… (slots per cISC4DisasterManagerFire.h, LIKELY).

**Q2. Dispatch** (CONFIRMED)
- `[0xB43D04]` = city slot 39 = `[city+0x124]`, vtable 0xA88108, header order. Key slots:
  - 5 **CanDispatch(type, float x, float z)** 0x469680: GetDispatchSource(type) (slot 15) and then the source decides (stations);
  - 6 **Dispatch(type, x, z)** 0x46A630: returns the dispatch id, 0 = failed;
  - 7 RevokeDispatchByID, 9 RevokeAll, 11 GetDispatchCount(type), 12 GetDispatchIDArray, 21 GetAvailablePylonCount.
- **Types**: 0 police, 1 fire, 5 fire plane (DispatchFireAirTool 0x8C0B0E46), 6 police helicopter (DispatchPoliceAirTool 0xEC0B0E6A). Source: the city command cases 0x7F3140 / 0x7F322D, which build the tool (new 0x90, ctor 0x4BA7D0(type), vtable 0xA90268). No military type was seen.
- DispatchFireTool / DispatchPoliceTool **need city slot 22 GetEstablished** (mayor mode). They only arm the tool.
- The tool's click (OnMouseDownL 0x4BA510, branch 0x4BA766) calls CanDispatch(type, x, z) and then 0x4BA0D0 → Dispatch(type, x, z) with the picked world coordinates.

**Q3. Camera and view** (CONFIRMED unless marked)
- **Globals** (0x602590): `[0xB43DC4]` = cISC4View3DWin\* (= `[[0xB43CBC]+0xF0]`); `[0xB43DC8]` = its cIGZWin; `[0xB43DCC]` = model maker; **`[0xB43DD0]` = renderer**. The region view also sets `[0xB43DD0]` to its own renderer (0x7AD0EB).
- **View vtable 0xABCE40**: 61 slots, exactly the gzcom-dll header order, except SetCostIndicator 42 = (u32, u32) and 43 = (u32).
  - Slots: 4 GetRenderer (`[v+0xF4]`), 8 SetZoom 0x7E60E0, 9/10 ZoomIn/Out, 14 SetRotation 0x7E61D0, 15/16 RotateLeft/Right, 17 SetZoomAndRotation, 18/19 Get/SetCurrentViewFilterInfo, 22/23 Get/SetCurrentViewLevel, 24/25 Get/SetCurrentViewInputControl, 36 PickTerrain.
  - Fields: +0xF0 cSC4CameraControl; +0xF4 renderer; +0x320 view-filter info (refcounted pointer); +0x324 view level; +0x364/+0x368 min/max zoom.
- **Zoom**: SetZoom clamps to min/max, then renderer slot 35. Commands Zoom0..Zoom5 = SetZoom(0..5), so the game's internal zoom is 0..5 (UI 1..6).
- **Rotation**: SetRotation calls renderer slot 38. RotateCW = view slot 15, RotateCCW = slot 16.
- **Renderer vtable 0xABAB60**: slot 16 GetCameraControl.
- **Camera control** layout equals the Mac: view target floats (metres) at +0x44/+0x48/+0x4C; **zoom `[cc+0x108]`**; the zoom getter 0x7CBC40 adds 1 when the custom magnification at +0xF0 is set; rotation at +0x10C (LIKELY).
- GetViewTarget (0x5C55FB) reads renderer slot 16 → cc+0x44.. ; its "cell" form multiplies by `[0xA8E174]` (LIKELY 1/16).
- **Data views and underground**: SetCurrentViewFilterInfo 0x7E63F0 broadcasts PreViewFilterChange 0x06CDB65A, swaps `[v+0x320]`, then Post (0x06CDB65B). SetCurrentViewLevel 0x7E5800 → slot 21 → `[v+0x324]`, with messages 0xC6CDBF1A/B. The underground view is a view level (value not traced). The data-view panel's type → filter mapping was not traced (open).

**Q4. Snapshots and the album** (CONFIRMED)
- **The snapshot is not an independent render.** It copies the current colour buffer (the last frame drawn), so the window must actually render; see the black-window note in LIVE_FACTS.
- **TakeSnapshot command** (0x2BB17574, app-level, case 0x5C8F2A): parameters are path, then 4 uint32. It calls **0x5F9560(cIGZString& path, x, y, w, h)** (cdecl), which:
  1. QIs `[0xB43CA4]` (graphics driver) for cIGZGSnapshotExtension 0xE69BFE2A;
  2. calls slot 3 CopyColorBuffer(x, y, w, h, 0), which returns a cIGZBuffer\*;
  3. passes it to `[0xB43CD0]` slot 8 Write(path, buffer, 100).
  - w and h must be non-zero; status 0 means success.
- **Renderer 0xABAB60** (header order):
  - slot 23 0x7C2530 = **TakeSnapshot(cIGZBuffer\*\* out, bool)**: `[0xB4E1F4]` slot 3 CopyColorBuffer(0, 0, [r+0x68], [r+0x6C], 0), i.e. the whole viewport;
  - slot 22 0x7C2570 = TakeSnapshot(cIGZString& path, bool): calls slot 23, then an image writer (new 0x38, ctor 0x90BC54) slot 8 Write(path, buf, 100).
- **Albums folder**: cISC4App slot 62 (0x449FC0) = user data directory (slot 58) + "Albums\", cached at A+0x15C.
  - Snapshot dialog: 0x7B7530(viewTarget, 0). Photo album: 0x7BDD60.
  - Album listing 0x7B8C70 accepts .png / .jpg / .jpeg / .jp2 / .gif / .bmp; there is also an album.ini.
  - Frame-sequence names "%s%s %03d_%03d.ext" are built in 0x795E50 (likely the animation recorder).
  - The snapshot size options were not traced.

**Q5. Preferences** (CONFIRMED)
- SC4Preferences\* = App slot 38 = `[A+0x3A4]`, also the global `[0xB43CD8]`. The layout follows gzcom-dll (size 0x1734).
- **Day / night**: byte `prefs+0x0` = mode (0 day and night, 1 day only, 2 night only).
  - Commands: EnableDayOnly 0x7F2B4B, EnableNightOnly 0x7F2BCF, EnableDayAndNight → 0x7E70C0(button 0xCA35CB74 / 76 / 78).
  - They act on the 24-hour clock `[0xB43DBC]`: slot 29 Enable(1); slot 5 SetMode(m) (1 = fixed 43200 s = noon, 2 = midnight, 0 = real time); slot 6 GetMode = `[clk+0x74]`. The result is written to the preference byte.
- **Play Options** dialog (layout 0x0A7DF315): object vtable 0xAB4B64, init 0x76AC30, apply 0x76B110. Checkboxes (cIGZWinBtn 0x8810) and the byte each one writes:

| Checkbox id | Option | Preference byte |
|---|---|---|
| 0x4A7F19F2 | Auto Go To Disaster | prefs+0xF08 |
| 0x4A7F19F3 | Edge Scrolling | prefs+0xF09 |
| 0x4A7F19F4 | Auto Edge Reconciliation | prefs+0x4EC |
| 0x4A7F19F5 | Urgent Advice Dialogs | prefs+0xF0B (the advisor popups' gate) |
| 0x4A7F19F6 | Expanded Tooltips | prefs+0xF0A (also written by SetExpandedToolTips) |

  - Apply then broadcasts **kMessageTypePreferencesChanged 0x231BBF91**, calls App slot 17, and calls 0x76AAB0.
- **Video**: App slot 19 **ApplyVideoPreferences(SC4VideoPreferences const\*)** 0x44A1C0 (video preferences at prefs+0xF0C).
  - It copies bytes into render-property slots through `[A+0x628]` slot 6 Set(index, value): +1 → 0, +2 → 1, +3 → 2, +4 → 3, +7 → 6, +5 → 4, …
  - Then it broadcasts 0xC9F775BB.
- **Not traced**: audio options (OpenAudioOptionsDialog object new 0x80, ctor 0x4F2450), tips, music / radio, auto-budget.

## 2. Layouts
- **cISC4DisasterLayer (I)**: +0x38 disable counter; +0x40 ongoing count; +0x48 cost struct; +0xB0 map {typeId → manager}; +0xC4/+0xC8 location vector.
- **Location record** (20 bytes): {inst\*, x, z, occupant\* (LIKELY), int}.
- **Effect disaster tool**: +0xA4 has-manager byte; +0xA8 manager id; +0xAC manager; +0xB0 effect; +0x2C/+0x34 picked x/z.
- **View3DWin**: see Q3. **Camera control**: +0x44 target vec3; +0x108 zoom; +0x10C rotation (LIKELY).
- **Renderer**: +0x68/+0x6C viewport width/height.
- **24-hour clock**: +0x70 enabled byte; +0x74 mode.

## 3. Recipes for the bridge (main thread, city loaded, app state 2)
- **Read the camera**: `v=[0xB43DC4]; cc=[v+0xF0]` → target `[cc+0x44..0x4C]` (metres; /16 gives cells), zoom `[cc+0x108]` (0..5), rotation `[cc+0x10C]`. The commands GetViewTarget / SetViewTarget also work.
- **Set the camera**: `v->vtbl[8](zoom)`, `v->vtbl[14](rot)`, `v->vtbl[17](zoom, rot)`; or the commands Zoom0..Zoom5 / RotateCW / RotateCCW. All honest (no cost).
- **Screenshot to memory**: `r=[v+0xF4]` (or `[0xB43DD0]`); `IGZBuffer* b; r->vtbl[23](&b, false)` → pixels of the last frame; Release afterwards. To a file: `r->vtbl[22](cRZString path, false)`, or the command `TakeSnapshot "<path>" x y w h`.
- **Start a disaster at a cell, the way the tool does it** (needs god mode, like the menu):
  - `L=[0xB43D3C]; m=L->vtbl[7](typeId); inst=m->vtbl[6](cellX, cellZ)` (0 = refused). This is exactly the tool's call for volcano, earthquake and pipe burst.
  - Fire: `m->vtbl[6]` (IgniteCell). Riot / Toxic: their own slot 6. Meteor, tornado, UFO, robot: only through the tool (select category 0x4A2B2464 with the exemplar IID, then a click), or the ToxicSpill command for toxic. Starting a disaster in mayor mode is cheat-class.
- **List active disasters**: for each of the 7 type ids `m=L->vtbl[7](id)`; `m->vtbl[10]()` count; `m->vtbl[11]()` SC4List of instances; each instance `GetLocation`(6) / `GetPhase`(7) / `GetID`(5). Or `L->vtbl[16]()` and `L->vtbl[17](i, &inst, &x, &z)` (Release inst).
- **Dispatch** (honest: the tool's own calls): `d=[0xB43D04]; if (d->vtbl[5](t, fx, fz)) id=d->vtbl[6](t, fx, fz)` with t = 0 police / 1 fire / 5 fire plane / 6 police helicopter; mayor mode only.
- **Play option**: write the byte at prefs+0xF08..F0B / +0x4EC, then broadcast 0x231BBF91 (as the dialog does). Alternatively drive the dialog: OpenPlayOptionsDialog → GZWinClickButton on the checkbox, then Accept 0xEA57DA59.
- **Day / night**: the commands EnableDayOnly / EnableNightOnly / EnableDayAndNight (honest).

## 4. Live tests
1. Read `[[0xB43D3C]]`: expect 0xA9E390 (not 0xA9E3DC).
2. Compare `[cc+0x108]` / `[cc+0x10C]` with the UI zoom and rotation after Zoom0..Zoom5 / RotateCW; check the GetViewTarget "cell" output against the target / 16.
3. Volcano at a cell in god mode: `m(0xC4C90997)->vtbl[6](x, z)`; check that GetActiveInstanceCount goes 0 → 1 and GetLocation returns (x, z). Repeat with L+0x38 = 1 to see whether a disaster is refused while the layer is disabled.
4. Dispatch type 1 at a burning cell: Dispatch returns an id; GetDispatchCount(1) rises; check whether funds change.
5. `r->vtbl[23](&b, 0)`: the buffer's width / height match the viewport (`[r+0x68]`, `[r+0x6C]`); is it black when the window is hidden or a second instance?
6. Which file formats does `TakeSnapshot "<UserDir>\Albums\t.png" 0 0 800 600` write; where do the snapshot dialog's own files go?
7. `ToxicSpill x z n`: what is the third parameter, and does it cost anything?
8. View level values: read `[v+0x324]` with the underground view on and off; read `[v+0x320]` after opening a data view.
9. Toggle Edge Scrolling in Play Options and confirm prefs+0xF09 changes; do the same for the audio dialog, writing down which bytes in prefs+0x4..+0x6C change.
