# networks-deals: network map, neighbour deals, options, ticker / opportunities, region import (SC4 1.1.641, static only)

Scratch folder: `<workbench>\re\networks-deals\`. It holds `h.py`, `d.py`, `v.py`, `vtd.py` (vtable dump with function bodies), `sweep.py` (a linear sweep of the whole text section, cached in sweep.pkl) and `lay.py` (UI layout parser). It also holds the dumps `tnm_read.txt`, `f78bd43.txt` (the deal toggle), `opt_init.txt` / `opt_accept.txt` (the Play Options panel) and `tgen.txt`.

Abbreviations:
- **NO** = the cSC4NetworkOccupant object. Its cISC4NetworkOccupant interface is at +0.
- **O** = a cISC4Occupant interface pointer. For network occupants, O = NO + 4.

Live results that were measured afterwards are recorded in `notes/LIVE_FACTS.md`, which wins where they disagree.

## 1. Answers

### Q1. Network map per cell

**Network manager**
- It is not a global. It lives at `[city+0x200]` (city slot 38).
- Vtable 0xAA7AD0, ctor 0x613330, Init 0x610C10.
- On Windows it has 25 slots. Slots up to 12 follow the header order. Windows slots 13-23 are the header's 14-24 shifted down by one: 13 MapPreviewTexture … 22 GetEnglishNetworkName, 23 AddToRetrofitList, 24 extra. CONFIRMED by argument counts.
- Fields: flags (+0x10..+0x12), a dirty rectangle (+0x14..+0x20), vectors (+0x44 / +0x50 / +0x5C / +0x68), a list (+0x78), and 13 cached tools at +0x88+4t.
- **It holds no per-cell data.** The per-cell network cache cSC4NetworkWorldCache belongs to each tool, at tool+0x1C. It is filled lazily; NAM.dll reads it with GetCell 0x647A20. CONFIRMED.

**(a) TrafficNetworkMap: a per-cell grid of the traffic networks**
- `TNM = [0xB43D54]` (city slot 40). Vtable 0xA8FED8, ctor 0x4B3A30, Init 0x4AE4E0. CONFIRMED.
- Fields:
  - `+0x18` = `tile*[]`
  - `+0x1C` = cells X
  - `+0x20` = cells Z
  - byte `+0x24` = shift = log2(cells X)
- `tile(x, z) = [[TNM+0x18] + 4*((z << [TNM+0x24]) + x)]`. Slot 13 GetTileInfoAtCell (0x4B3AC0) and slot 14 SafeGetTileInfoAtCell (0x4AE0C0) read it this way.
- A tile holds `+0` = cISC4NetworkOccupant* and `+0x54` = the next tile in the same cell. Slot 16 (0x4AE0F0) matches on +0, and the save writes it as iid 0xA821EF94.
- The grid only holds what filter `[TNM+0xA4C]` admits (vtable 0xA8FE14, slot 3 = 0x4ADEB0): type 0xC772BF98 **and** HasAnyNetworkFlag(0x1FCF).
  - That covers road, rail, highway, street, avenue, subway, light rail, monorail, one-way road, dirt road and ground highway.
  - It holds **no pipes (bit 4) and no power lines (bit 5)**.
- Inserts go through a pending hash at +0xA70 (slot 47 0x4B3380). The tile array is serialized (Read 0x4B4DE0).

**(b) Walking the occupant manager (all networks)**
- OM `[0xB43D0C]` keeps occupants in 64 m buckets, i.e. 4 x 4 city cells. CONFIRMED (IsCellEmpty 0x49E490, GetFirstOccupant 0x49E5E0).
- Bucket coordinate: `w = city_cell/4 + 0x40` (slot 13), range 0..0xBF.
- `bucket = [[[OM+0x38] + 12*wx] + 4*wz]`, 0 when empty. `head = [bucket]`.
- List nodes are `{next +0, prev +4, O|tag +8}`, with `O = [node+8] & ~1`.
- An occupant on a bucket edge can appear twice, so de-duplicate by pointer.
- The lock at OM+0x14 is not needed for reads.

**Occupant types** (`[O+0x24]`, slot 7), CONFIRMED by their constructors:

| Type | What it is | Notes |
|---|---|---|
| **0xC772BF98** | network piece (ctor 0x61BDD0) | Pipes are cSC4PipeOccupant (CLSID 0x49C05B9F, base 0x65C330 → 0x61BDD0) and carry this type with mask bit 4. Subways carry it with bit 7. |
| **0x0990B2EA** | power-line wire (cSC4PowerLineOccupant, ctor 0x64A270) | Not a network occupant. Cell at `[O+0x40]`, `[O+0x44]`. |
| **0x2890D4DE** | power pole (cSC4PowerPoleOccupant, ctor 0x64DB30) | Cell at +0xC8 / +0xCC on the iid-0xA8C86142 interface. LIKELY: its occupant interface is at +8. |

**(c) cISC4NetworkOccupant**
- iid 0xA821EF94, **vtable 0xAA8080**. The slot order matches the header; the arguments are CONFIRMED.

| Slot | Method | What it reads (offsets from NO) |
|---|---|---|
| 8 / 9 | HasNetworkFlag / HasAnyNetworkFlag | **`[NO+0x13C]`** |
| 12 | GetNetworkFlag | `[NO+0x13C]` |
| 22 | IsOfType(t) | HasNetworkFlag(1 << t) (table 0xAA7CE8) |
| 23 | PieceId | `[NO+0xFC]` |
| 24 / 25 | GetRotation / GetFlip | byte +0x104 & 0x7F / bit 7 |
| 28 | GetVariation | +0x105 |
| 38 | GetEdgeTypesFlag(t) | the edge store at +0x108 |
| 40 | GetActiveEdges | 0x61AE90 |
| 41 | GetActiveEdgesForType | 0x61AEE0 |
| 47 | ConnectsToNeighbor(dir, t) | `(GetEdgeTypesFlag(t) >> 8*dir) & 3 != 0` |
| 48 | AsOccupant | NO+4 |
| 55 | IsIntersection | flag 0x40 **and** PieceId in the set at 0xB4528C |
| 59 | GetOccupiedCell | x = round([NO+0x9C] / 16), z = round([NO+0xA4] / 16) |
| 63 | GetCostOfDemolition | int64 +0x170 |

- **Flag word +0x13C**: bits 0-12 are the eNetworkType mask, 0x400000 = immovable, 0x10000000 = usable, bit 29 = lit, bit 30 = support pylon.
- **Edge store** (+0x108):
  - u8 `+0x108` = count of extra entries
  - u8 `+0x10C` = primary type
  - u32 `+0x110` = primary edges
  - `+0x114` → an array of {u8 type, u32 edges at +4}
- An edges dword holds one byte per direction; a direction is active when `byte & 7` is non-zero.
- GetActiveEdges ORs every entry into a 4-bit mask (bit d = byte d).
- Directions: d = 0 W (x-1), 1 N (z-1), 2 E (x+1), 3 S (z+1). LIKELY: the dx / dz tables 0xAA7858 / 0xAA7878 in the network code match NAM.dll's kNextX / kNextZ.
- Slot 55 is **not** a general intersection test: it only fires for flag 0x40 (avenue) plus a listed piece. Use popcount(mask) > 1, or 3+ active edges, instead.

**Neighbour flag per cell**
- A cell connects to a neighbour when it matches a connection cell in the neighbours list (Q2).
- eNetworkType → ConnectionType table at **0xAA84C4** = [2, 1, 3, 0, 5, 4, 8, 6, 7, 11, 0, 10, 12]. Streets and one-way roads have no connection type. CONFIRMED.

**Traffic volume**
- TrafficSim `[0xB43DA8]` slot 12 GetTrafficEdgeDensity 0x711460(u8 x, u8 z, u32 travelType, bool evening). CONFIRMED.
- Key = `ev<<24 | tt<<16 | x<<8 | z`.
- Hash buckets are `[TS+0x17C]..[TS+0x180]`, bucket = key % n. A node is `{next +0, key +4, TrafficEdgeDensity +8}`.
- A missing key returns the static zero block 0xAB31D0.
- **TrafficEdgeDensity**: u16[16] edge flows at +0x00..+0x1E (two groups of 8, summed separately at 0x4B1483) and **u16 usage at +0x20**.
- The network query window (0x4CEE56) shows the volume per travel type tt = 0..8 as `usage(ev=0) + usage(ev=1)`. A cell's volume is the sum of that over tt. CONFIRMED.

### Q2. Neighbour deals

`N = [0xB43D8C]` (city slot 62), vtable 0xAB1EE0.

**Storage**
- `+0x1C` = the connections list (sentinel*; node {next, prev, cISC4NeighborConnection* +8}).
- `+0x20` = the deals list (same node shape).
- `+0x28` = the tuning exemplar (slot 37) "Neighbor Deals" 6534284A-7A4A8458-6A469021: EA4AD2FF 2.5, EA46932C / 6A469337 / 8A46933D 1000, EA4AE9EF 5000, CA46931F 60, 6B588FAD 90 … CONFIRMED.

**Deal types** (Lua `neighbor_deal_types`)
- 0x4773FFE0 BUYPOWER, E1 SELLPOWER, E2 BUYWATER, E3 SELLWATER, E4 EXPORTGARBAGE, E5 IMPORTGARBAGE.
- Monthly income N[32] = sum of deal[22] over types E1 / E3 / E5; N[33] = the expense. Both skip deals with flags & 0x3D. CONFIRMED.

**ConnectionType** (not the same numbering as eNetworkType)
- 1 rail, 2 road, 3 highway, 4 power, 5 pipe, 6 subway, 7 light rail, 8 avenue, 9 ferry, 10 dirt road, 11 monorail, 12 ground highway.
- The commodity mapping 0x4C40B0 / 0x4C4100 shows what each deal travels on:
  - power deals ride power lines;
  - water deals ride pipes;
  - garbage deals ride roads, highways, avenues, dirt roads or ground highways.

**Deal object** cSC4NeighborDeal
- Vtable 0xAB1DD8, 41 slots. Windows has an extra pair at 16 / 17 compared with the Mac build. Layout in section 2.
- Slot 34 Cancel: SetFlags(4, 1), SetFlags(2, 0), SetAmount(0).
- Slot 35 Activate: needs flag 1 and none of 0x38; sets flag 2 and clears 1 and 4.
- Slot 23 UpdateCost: `cost = max(1, round(N[35] GetDealCost(type, (double)amount, otherCity)))`, skipped when flags & 0x300.

**Offer → accept: the player's path**
1. Each month the advisor feed 0x421AB0 calls `N[25] ProposeDeals(&list, 0)`, which only counts. It sets the Lua globals `g_nd_can_buy/sell_power/water`, `g_nd_can_import/export_garbage`, `g_nd_connection_present_*` and `g_nd_count_*`.
2. Advices of class cSC4AdviceNeghborDeal (0x6A3848DB, ctor 0x420E20) fire through Lua `create_advice_neighbor_deal`. Their message link is `game.window_budget(budget_window_types.NEIGHBOR1 = 0xAA3AC402)`. **There is no accept dialog.**
3. Opening that budget panel (builder 0x77E600) calls **`N[25] ProposeDeals(&list, 1)`**, which puts the offers into N+0x20 with flag 1. The panel then lists the deals per type with `N[30] FindDeals(type, list&)`.
4. Each row has a toggle button, handled by 0x78BCA0 on message 0xE8711255 for the row's button id. Rows are at panel+0x50; a row's deal is at row+0x10.
   - **Toggle on ("Initiate Deal")**: unless `deal[39](0x100)`, call `deal[35] Activate` when flag 2 is clear, then quantise the amount through `deal[11]`. The caption becomes "Cancel Deal".
   - **Toggle off**: when flag 2 is set, call `deal[34] Cancel`, then `deal[37](1, 1)` (back to offered). The caption becomes "Initiate Deal". CONFIRMED.
5. Money moves each month through the budget totals N[32] / N[33]. LIKELY.

**Neighbour connections**
- The network UI commit 0x645370 asks tool slot 41 GetPossibleNeighborConnection.
- Then `N[5] RequestCreateConnection` (0x6D15E0) shows a modal yes/no (LTEXT 6A231EAA-AA8E151B…); it refuses when popups are off.
- The connection is made when PlaceAllSegments runs with nb = 1 (build report).
- cSC4NeighborConnection (CLSID 0x0A134F24, vtable 0xAB2034, ctor 0x6D4680). CONFIRMED.
  - `+0x24` ConnectionType (slot 5)
  - `+0x28 / +0x2C` edge cell (slot 6)
  - `+0x30 / +0x34` region cell on the other side (slot 8)
  - flags byte `+0x38`: bit 0 = visited; bit 1 set = inactive (slot 13 GetIsActive = !bit 1).

### Q3. Options

- `[0xB43CD8]` = **SC4Preferences\*** = app slot 38 GetPreferences = `[A+0x3A4]` (written at 0x602310). Size 0x1734; the sub-block offsets are in gzcom-dll SC4Preferences.h. CONFIRMED.
- **Play Options** panel: layout 0x0A7DF315, root 0x2A57DB82, init 0x76AC30, Accept 0x76B110. Checkbox bytes (all CONFIRMED):

| Option | Checkbox id | Byte |
|---|---|---|
| Auto Go To Disaster | 0x4A7F19F2 | +0xF08 |
| Edge Scrolling | 0x4A7F19F3 | +0xF09 |
| Expanded Tooltips | 0x4A7F19F6 | +0xF0A |
| Urgent Advice Dialogs (the advisor-popup gate) | 0x4A7F19F5 | +0xF0B |
| Auto Edge Reconciliation | 0x4A7F19F4 | +0x4EC |

- **Accept** writes those bytes, posts **kMessageTypePreferencesChanged 0x231BBF91** on the message server and calls **app slot 17 SavePreferences**.
- Graphics Accept 0x792B0E uses app slots 17, **19 ApplyVideoPreferences(const&)** and 20 GetAutoVideoPreferences ("Default Settings"). The video preferences start at prefs+0xF0C. CONFIRMED.
- **Day / night** = prefs+0: 0 both, 1 day only, 2 night only (LIVE).
- **There is no player option** for disasters (disaster layer slot 5 is a counter; see view-disasters) or for the global auto-budget.
- Auto-budget belongs to ResidentialSim Get/SetAutoBudget…, per the header; the slots were not checked (GUESS).
- Not traced (GUESS / OPEN): audio (prefs+4; music +0x10 and audio +0x69 per the header) and the mouse wheel.

### Q4. News ticker and opportunities

**Ticker**
- The advisors-ui report's mapping holds: cSC4WinAdviceList id 0xAA12F33C; entries `[win+0xE0]`, count `[win+0xE4]`; entry +0x68 = the advice; title `[adv+0x34]..[adv+0x38]`.
- The source is every active advice plus news-only advices (flag 1, e.g. advisor 28). Nothing new was found.

**Business deals**
- Each is a reward advice whose GUID is the building IID: casino 0x033A0000, missile range 0x03420000, army base 0x03460000, toxic dump 0x03410000.
- They become available when their Lua condition runs `unlock_reward_building` (CivicBuildingSim status bit 2).
- Their message link is `game.tool_plop_building(building_tool_types.CASINO|MISSILE_TESTING_RANGE|ARMY_BASE|TOXIC_WASTE_DUMP)`, which only **arms the plop tool**.
- Accepting = placing the building (normal plop cost, Rewards menu enabled). **There is no dialog.** CONFIRMED from the texts (LTEXT 6A231EA4-EC193CDC, -EC193CE6, -8C2389DD, -6C1D1D69).

### Q5. Region import (builds on the regions report)

**Where new-tile terrain comes from**
- config.bmp is only the tile layout (read by region Init 0x4A6B00).
- New-tile terrain comes from the new-city spec = **app slot 39 = A+0x3A8**: `+0` char path, `+0x200` image, `+0x204` alternative.
- The generator 0x748130 picks a source:
  1. `+0x204` when it is set;
  2. otherwise, with no path and no image, a flat tile at base height × 3;
  3. otherwise, with an image, `0x740D60(image)`, which turns grey × scale into heights (bilinear);
  4. otherwise `0x742860(path)` loads a file through GZCOM class 0xA2FFB5D3 (iid 0x02FFBB60) — LIKELY a city file used as a template.

**How a height map gets in**
- Only through **RegionBitmapLoad** (command 0x6A9757C2 → 0x7AEDD0).
- It opens the game's own file window (0x79D810, filter "\*.bmp"). The regions report has it calling the picture loaders 0x602C30 / 0x5447B0.
- It insists on **(gridW·64+1) × (gridH·64+1)** pixels ("Region bitmap size is incorrect" at 0x7AF3A2).
- It then deletes, regenerates and saves every tile.
- The Load Region button (0x2A5B0001 → 0x7780C0) only lists regions.

**So an agent cannot get terrain from a plain file drop.** It can either:
- drive RegionBitmapLoad: hook the file window, or put the image pointer at spec+0x200 and call RequestNewCity per tile, as 0x7AEDD0 does; or
- write the .sc4 terrain record itself (offline, regions report Q4).

## 2. Layouts

**cSC4NetworkOccupant**

| Offset | Field |
|---|---|
| +0 | vtable 0xAA8080 |
| +4 | O (0xAA7FF8) |
| +8 | 0xAA7FDC |
| +0xC | property holder 0xAA7F78 |
| +0x20 | 0xAA7F60 |
| +0x28 | type 0xC772BF98 |
| +0x9C..+0xF8 | 4 vertices × 0x18 bytes (x +0x9C, y +0xA0, z +0xA4; heights +0xA0 / +0xB8 / +0xD0 / +0xE8) |
| +0xFC | piece id |
| +0x100 | under-texture |
| +0x104 | rotation \| flip << 7 |
| +0x105 | variation |
| +0x108 | edge store |
| +0x13C | flags |
| +0x140 | path info |
| +0x164 | path override |
| +0x170 | int64 demolition cost |

**Deal** (Windows)

| Offset | Field |
|---|---|
| +0x1C | refcount |
| +0x20 | type |
| +0x24 / +0x28 | region cell on the other side |
| +0x2C / +0x30 | region cell on the city side |
| **+0x34** | **amount** (MWh, cu m or tons, per the query windows) |
| +0x38 / +0x3C | slots 16 / 18 (unnamed) |
| +0x40 | last amount |
| +0x44 | increment amount |
| +0x48 | amount used |
| **+0x50** | **int64 monthly cost** |
| +0x58 / +0x60 / +0x68 / +0x70 | cRZDate start / expiry / current / suspension (day number at +4 of each) |
| **+0x78** | **flags**: 1 offered, 2 active, 4 cancelled, 8 / 0x10 / 0x20 blockers, 0x80 no sync, 0x100 locked, 0x200 / 0x300 frozen cost |

**Neighbours simulator**

| Offset | Field |
|---|---|
| +0x14 | city |
| +0x18 | message server |
| +0x1C | connections |
| +0x20 | deals |
| +0x28 | tuning |
| +0x38 / +0x39 | bytes |
| +0x3C | deals dirty |
| +0x3E | UI disable flag |

## 3. Recipes (bridge calls on the main thread; reads from Python)

1. **network_map()** (read-only, Python, app state 2)
   - Walk each OM bucket that covers the city.
   - For each 0xC772BF98 occupant, NO = O - 4. Read:
     - the mask `[NO+0x13C] & 0x1FFF`;
     - the cell from the vertex;
     - the edges per type from the edge store (or by call, `NO[41](t)`);
     - the piece `[NO+0xFC]`.
   - Intersection = popcount > 1, or 3+ edges.
   - For 0x0990B2EA (and 0x2890D4DE), mark power at the cell `[O+0x40]` / `[O+0x44]`.
   - Take the neighbour cells from the N+0x1C list (connection type via 0xAA84C4).
   - For transport networks only, the TNM grid is faster.
2. **traffic_volume()**: walk the TrafficSim hash once and sum usage `+0x20` per (x, z).
3. **neighbor_deals()**: walk N+0x20 and read type, amount, cost and flags. An honest refresh of the offers is `N[25](&list, 1)`, as the panel does when it opens.
   - **accept(deal)**: `deal[35]()` (Activate), only when flags & 1 and none of 0x138.
   - **cancel(deal)**: `deal[34](); deal[37](1, 1)`.
   - Both mirror the panel toggle exactly (honest play). Opening the panel through Lua `game.window_budget(0xAA3AC402)` also works.
4. **set_play_option(off, on)**: write the byte at `[0xB43CD8]+off`, post 0x231BBF91, then call app slot 17. This is the dialog's own path, so it works at run time.

## 4. Open questions (live tests)

1. Bucket walk vs the map: after drawing an 11-cell road, count type-0xC772BF98 occupants with bit 0 (expect 11). A pipe has bit 4. A power line gives 11 objects of type 0x0990B2EA.
2. TNM: `[[TNM+0x18]+4*((z<<sh)+x)]+0` should equal the road occupant at (x, z); for a pipe cell the tile is 0.
3. Edge bytes on a straight east-west road: expect W and E (bytes 0 and 2) set.
4. Compare the usage summed over tt 0..8 for one road cell with the query window's traffic numbers.
5. Open the budget's Neighbor Deals panel next to a powered neighbour: expect new N+0x20 entries with flag 1; Initiate → flag 2; the next month, funds change by `[deal+0x50]`.
6. Toggle Urgent Advice Dialogs through recipe 4: `[[0xB43CD8]+0xF0B]` flips, the .cfg changes and popups stop.
7. The power-pole occupant interface offset (+8?) and its cell fields.
