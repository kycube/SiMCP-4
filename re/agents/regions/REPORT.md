# regions: region view, region and city files, neighbours, thumbnails (SC4 1.1.641, static only)

Scratch folder: `<workbench>\re\regions\`. It holds the offline readers `save_index.py` (DBPF index), `idx2.py` (object table plus record splitting), `rv.py` (region-view record), `flat.py` (terrain), `png.py` (thumbnails), `names.py` (record types to CLSID names), plus `konrad_index.txt` and `thumb_*.png`.

## 1. Answers

**Q1. Region management.** Confidence: CONFIRMED by code unless marked otherwise.

- **Classes and vtables**
  - **cSC4Nation** (vtable 0xA8EF00, 18 slots) follows the header order. Fields: +0x14/+0x18 vector of cISC4Region\*, +0x20 active index.
    - Slot 6 GetRegionCount, 8 GetActiveRegion, 9 **SetActiveRegion(int index)** (Windows takes an index), 11 GetRegion(i) 0x497740.
    - Slot 12 DeleteRegion 0x497F60 (removes the folder with 0x91BF93), slot 13 AddNewRegion(cIGZString) 0x497EE0.
  - **cSC4Region** (vtable 0xA8FA40, ctor 0x4A5B30) follows the header order for slots 0-24; slot 25 0x4A53E0 is an extra slot.
    - Slots 3 GetName (+0xC), 5 GetDirectoryName (+0x20), 7 LoadConfig 0x4A6CD0 (reads region.ini).
    - Slot 8 Init 0x4A6C80: LoadConfig, then 0x4A6B00 (config.bmp), 0x4A6330, 0x4A51C0.
    - Slot 9 Shutdown 0x4A5BE0 **writes region.ini**: Name, Terrain type, Water Min, Water Max. The key names are a string table at 0xB0954C..0xB09564.
    - Slot 10 Delete 0x4A65A0 deletes region.ini and config.bmp.
    - Slots 11 GetCity 0x4A4930, 13 RemoveCity, 14 DeleteCity 0x4A5120, 15 ReloadCity 0x4A5030, 16 MoveCity 0x4A7200.
    - Slots 18/19 Get/SetBaseTerrainType (+0x34), 20 GetBaseTerrainHeight 0x4A4CA0, 21 GetWaterPrefs (bytes +0x38/+0x3C).
- **Region view buttons** (layout 0xAA920991, handler 0x7AFAA0 on window message 0x287259F6 = button id):
  - 0x2A5B0000 **Create New Region** -> dialog 0x777FF0 (layout 0x8A5AB1CB).
  - 0x2A5B0001 Load Region -> 0x7780C0.
  - 0x2A5B0002 **Delete Region** -> confirmation 0x778130, then nation[12](view+0x1A4 = region index), 0x7AC270, then app[12] RequestGoToRegionView(0).
- **New region dialog**:
  - Controls: name edit 0x2000, "Plains" 0x1000 / "Water" 0x1001, Create 0x8A5B9959, Cancel 0xCA5B9966.
  - The OK handler is 0x778470. It validates the name (0x91977C) and rejects duplicates (0x777E50 shows an error).
  - Then: `idx = nation[13](name)`, `r = nation[11](idx)`, `r[8]()` Init, `r[19](water ? 1 : 0)`, `r[9]()` Shutdown (writes region.ini).
  - The view then makes it the active region: nation[9](idx), then app[12](0).
- **What AddNewRegion writes** (0x4A67B0 / 0x4A6880):
  - Creates the folder `<name>`, or `<name> (n)` if it exists (format "%s (%d)" at 0xA8FAA8).
  - Picks at random one of the 6 template bitmaps (SimCity_1.dat, type 0x856DDBAC, group 0x6A1EED2C, instances 0x6C3568C4..C9; 16x16 BMPs, one 15 wide). The RNG is at 0xB217C0.
  - Exports it as `config.bmp`.
  - So "from scratch" means a random grid layout, no terrain data, and no city files.
- **Terrain of a tile that has no .sc4 file** (terrain generator 0x748130, reached from 0x7503D5):
  - The new-city spec is app[39] GetNewCitySpecification(): +0x000 a char path, +0x200 a height image, +0x204 another source.
  - With an empty path and no image, the tile is **flat at GetBaseTerrainHeight() x scale**.
  - The base heights come from the "Region UI Tuning Parameters" exemplar (6534284A-690F693F-AA383BFE): 0xCA383CAD = 90 (Plains), 0xCA383CAE = 64 (Water). 0x7ABF10 copies them into the table 0xB217B0[type].
  - **Measured scale**: SiMCP's MCP Town (Terrain type 0) has every one of its 65x65 vertices at exactly **270.0 m = 90 x 3**. Konradshohe's minimum is 192.05 (about 64 x 3). Sea level 250 corresponds to grey 83.3.
  - The static constant at 0xB0D5E8 reads 1.5 (default 50.0 at 0xB0D5E4). It sits in .data, so it is probably tuned at runtime (GUESS).
  - A grey image is converted by 0x740D60: per-pixel value x the same scale, resampled bilinearly.
- **RegionBitmapLoad** (command 0x6A9757C2, region handler 0x7AF720 -> **0x7AEDD0**; also registered in the city table):
  - Opens a file dialog (0x919E96) and loads the picture (0x602C30 / 0x5447B0).
  - Requires a size of exactly **(gridW x 64 + 1) x (gridH x 64 + 1)**, else "Region bitmap size is incorrect -- %dx%d, should be %dx%d".
  - Then **DeleteCity on every tile** (region[14]).
  - Per tile: copies a (64 << sizeShift)-pixel square into an image (graphics system [0xB43C9C] slot 3), stores it at spec+0x200, calls `app[6] RequestNewCity(0x7AEA00(tile, 1))`, then app slot 15 SaveCity(path, false) and app[14] CloseCity.
  - In short: it generates and saves every city of the region. It is modal because of the file dialog.
- **Rename**: there is no region rename UI. Region SetName (slot 4) plus Shutdown would rewrite region.ini; LoadRegion uses that display name (LIVE_FACTS).

**Q2. City tiles.**
- **Region view object** (cSC4WinRegionView; its vtable ends at 0xAB94B8, slot 0x7AFAA0 at 0xAB949C). The command target is view+0xDC.
  - +0xE0 is the popup/selection object; 0x74C6E0(it) returns the selected tile record.
  - +0x118/+0x11C is a vector of tile records, stride 0x80: +8 grid x, +0xC grid z, +0x18 size shift (0 small, 1 medium, 2 large).
  - +0x1A4 is the region index.
- **City popup** (layout 0xCA539340; 0x0A8CD184 is the "Start New City" variant):
  - Text fields 0x4A552000 name, 0x4A552001 mayor, 0x4A552002..06 R / C / I and rating numbers. These are LIKELY filled from the RegionalCity getters (slots 9-14).
  - Buttons 0x4A560000 Play, 0x4A560001 Close, 0x4A560002 Import City, 0x4A560003 **Delete City**.
- **Play**:
  - `ref = 0x7AEA00(tile, create=1)`. It calls region[11](x, z); if that is empty it builds a new cSC4RegionalCity (new 0x1A0, ctor 0x4AC040), runs Init, SetCitySize(1 << shift, 1 << shift), SetPosition(x, z, 0) and names it "New City".
  - Then **0x7ADC20(ref)** (thiscall on the view, ret 4): path = RegionalCity[31] GetCitySaveFilePath.
    - If the path is non-empty and **app[13] LoadCity(path, ref)** succeeds, done.
    - Otherwise it clears spec+0x200 and calls **app[6] RequestNewCity(ref)**.
  - The LoadCity command handler 0x7AF4B0 walks the same tile vector (it reads GetEstablished, slot 43) and calls the same 0x7ADC20.
- **Delete City** (0x7B0099):
  - Confirmation 0x778220, then `region[14] DeleteCity(&ref)` = RemoveCity (slot 13) plus **DeleteFile of the .sc4**.
  - Then 0x7ABB80 / 0x7AE510 / 0x7B5430 refresh the view.
  - The tile then regenerates flat at the base height. This also loses the shipped terrain of the "New City (n).sc4" tiles.
- **Region::GetCity(x, z)**: map at region+0x50 keyed by grid square; returns `cRZAutoRefCount<cISC4RegionalCity>*` (dereference to get the city) or 0.

**Q3. Regional play.** Confidence: LIKELY unless marked.
- **Neighbours simulator** (vtable 0xAB1EE0).
  - Slot 12 0x6CF030 FindCityOnOtherSideOfConnection(cellX, cellZ) (CONFIRMED): 0x6CE820 classifies the edge (x < 0 west = 3, z < 0 north = 0, x >= size x 64 east = 1, z >= size x 64 south = 2). The region square is the city position + cell/64 ± 1. Then region[11](rx, rz).
  - Connections are cSC4NeighborConnection objects (CLSID 0x0A134F24; 3 in Konradshohe) stored in the city save. Fields: type (0-12 per the header enum), connection cell, active / visited flags.
- **Regional copy and matching**: the regional city keeps copies in its list at obj+0x90. RegionalCity[20] FindConnection(type, x, z) 0x4A7B40 matches GetType (conn slot 5) and GetConnectionCell (slot 6) (CONFIRMED). These copies are written into the region-view record as embedded serializables, so the neighbour side matches by cell without loading the other city.
- **Regional demand**: the region-view record carries 3 maps {u32 demand id -> s32 value}. Konradshohe has 40 entries: 0x1001 = 15432, 0x1010 R$, 0x1011..., 0x2010 jobs... These are the census and extrapolations (RegionalCity slots 9/10/17-19). The DemandSim "regional" index 0x10000 aggregates them.
- **Commuting** goes through connection->AsTrafficSource (conn slot 4) into the traffic simulator (GUESS).
- **Deals**:
  - Offers come as advice: 7 cSC4AdviceNeghborDeal objects (0x6A3848DB) in Konradshohe, so the accept UI is the advisor popup.
  - Decided by neighbours slots 24 ProposeDeal / 25 ProposeDeals / 26 AddDeal (economy report).
  - Stored as cSC4NeighborDeal (0x2A134F42) in the regional city's local deals (slots 68 UpdateLocalDeals 0x4A9110, 69 Set 0x4A90D0, 70 Get 0x4AA0C0), which are the trailing serializables of the region-view record.

**Q4. City save (.sc4 DBPF).** Confidence: CONFIRMED on Konradshohe (187 records).
- **Object table**: type 0x499B23FE, group 0x299B2D1B, instance 0 = {u32 version 1, u32 n (128), u32 total objects (20579), n x {u32 CLSID, u32 count}}.
  - Each listed type T is stored at (T, 0x299B2D1B, 0) as `count` concatenated objects.
  - Object layout: {u32 size including itself, u32 CRC, u32 save-time address (object id), class data (usually u16 version first)}.
  - All 128 records split exactly. The lot count 741 equals LIVE_FACTS.
- **Record type = the class's GetGZCLSID**; names come from sc4-gzids. The writer is the vtable 0xAA268C service (0x5D38D0 reads the table).
  - City 0x8990C372, budget 0xE990BE01, departments 0xE990BFFC, line items 0xAA313C9F.
  - Demand sim 0x2990BFF2, cSC4Demand 0x8990C12D, residential 0x4990C013, simulator/date 0x2990C1E5.
  - Lots 0xC9BD5D4A, buildings 0xA9BD882D, props 0x2977AA47, flora 0xA9C05C85.
  - Networks 0xC9C05C6E, pipes 0x49C05B9F, power lines 0xC9C05C5D, SimGrids 0x49B9E602..0A.
  - History 0x89EFA536, zone manager 0x298F9B2D, neighbours sim 0xC990C0A4, traffic 0x6990C1AA.
  - Each Maxis ordinance is its own CLSID (0x?BF1Dxx, 0x?2F6E8xx, 0x?D072xx, 0x815B4CEF, 0x82B9999B; GetGZCLSID functions 0x80BCB0..0x80EE40; the name and description are inline).
  - Park manager 0xAA3FE6BC; terrain object 0xE98F9525.
- **Records outside the table**:
  - Region view 0xCA027EDB/0xCA027EE1.
  - Terrain (0x7477C0 writes it, 0x747800 reads it):
    - **Heights 0xA9DD6FF4/0xE98F9525/1** = u16 2, then (cellsX+1) x (cellsZ+1) f32. Konradshohe is 129x129, 192.05..282.73 m, matching the live terrain.
    - Instances 0x64..0x67: the 4 edge strips {u16 1, u32 129, 129 f32}, used to match seams. 0x64 is the first column, 0x65 the first row, 0x66 the last column, 0x67 the last row.
    - 0x8A91E7E3/3: {u16 2, u32 nx+1, u32 nz+1, u32 0, f32 min, f32 max, f32 308.0}.
    - 0x8A91E7E0/2: u16 1 + 129² u16 (GUESS: texture / flag map).
  - Names in other languages: LTEXT 0x2026960B group 0x6AAEE931 (city) / 0x6AAEE932 (mayor), instance = language.
  - Thumbnails (Q5).
- **Region-view record v1.13** = cSC4RegionalCity (CLSID 0x6A037C24) Write 0x4A7D10 / Read 0x4AC5B0; offsets checked on Konradshohe:
  - 0x00 u16 1, u16 13; 0x04 x; 0x08 z; 0x0C sizeX; 0x10 sizeZ (grid squares).
  - 0x14 residents (15025 = live); 0x18 C jobs; 0x1C I jobs; 0x20 f32 workforce share.
  - 0x24 s8 mayor rating; **0x25 u8 difficulty** (regions.py calls it "stars"; it is 2 = hard); 0x26 bool (obj+0xA0).
  - **0x27 u32 city serial number** (regions.py calls it "GUID"); 0x2B 4 x u32 language/country (LIKELY); 0x3B u32 birth date.
  - 0x3F u8 established.
  - 0x40 seven length-prefixed strings, in order: name, ?, **mayor**, ?, utility advisor ("Jonas Sparks"), description, ?. Replace regions.py's mayor heuristic with this order.
  - Then f32 world x, f32 world z, f32 base elevation, s32 tutorial GUID (-1).
  - Then 3 maps (u32 n + n x {u32 id, s32 value}).
  - Then commodity floats (12), a list of embedded neighbour connections, a vector {type, x, z, flag}, f64 budget, f64 income, the commodity records, points of interest, and the deals.
- **Offline value**: high for the region view, terrain, thumbnails, the object table and the lot / building counts. The budget layout is not decoded (0xE990BE01; header u16 version 5 ...).

**Q5. Thumbnails.** Confidence: CONFIRMED.
- **When**: on kSC4MessagePreSave 0x26C63343, cSC4City::DoMessage 0x45C1A0 calls 0x459B20, then 0x5DDDC0 (offscreen render, drawing paused), then 0x5DDA90, which calls 0x5DCA10 four times.
- **Records**: PNG type **0x8A2482B9 group 0x4A2482BB**, instances:
  - **0** satellite view (RGBA 258x151)
  - **2** its footprint mask
  - **4** transportation map
  - **6** its mask
  - plus LTEXT 0x2026960B at 1/3/5/7 = "Temp.png".
- **Reading**: 0x5DDA40 -> 0x5DD480, called from the region view tile loader 0x7B13C0 and the popup 0x7770B0.
- **View switch**: Satellite / Transportation buttons 0xABA290E1 / 0xCBA290EC.
- **Fallback art**: SimCity_1.dat type 0x856DDBAC group 0x6A1EED2C holds 256x151 image/mask pairs (0xEA23195D/E) (GUESS: art for tiles without a file).

## 2. Layouts
- **cSC4RegionalCity** (0x1A0 bytes, vtables +0 0xA8FB20 / +4 0xA8FB10 / +8 0xA8FAF8 serializable):
  - +0x14/+0x18 position, +0x1C/+0x20 size, +0x24 residents, +0x28 C jobs, +0x2C I jobs, +0x34 rating (byte), +0x38 difficulty.
  - +0x3C/+0x48/+0x54 census maps, +0x90 connection list, +0xA4 serial, +0xB8 birth date, +0xBC save path.
  - +0xD0 name, +0xF8 mayor, +0x120 description, +0x154 utility advisor name, +0x148/+0x14C world x/z, +0x150 base elevation.
  - +0x168 established (byte), +0x16C tutorial GUID, +0x170 budget (f64), +0x178 income (f64).
- **Slots on Windows**: 9 = GetPopulation(type), 10 = GetPopulation() (overloads swapped), 15 difficulty, 31 save path, 33 name, 35 mayor, 43 established.
- **cSC4Region**: +4 init byte, +0xC name, +0x20 folder, +0x34 terrain type, +0x38/+0x3C water min/max, +0x44 city locations, +0x50 city map, +0x54..0x60 tile vector / count.

## 3. Recipes (main thread, region view, run deferred like LoadCity)
- **Open a tile (x, z)**:
  - `reg = app[35]()`, `ref = reg[11](x, z)`.
  - With a ref: `0x7ADC20(view, ref)`, which is the Play button exactly (honest). Without the view pointer, use `app[13](path from (*ref)[31], ref)`.
  - Without a ref: use the "LoadCity" command, or `0x7AEA00(view, tileRec, 1)` first.
- **Delete city**: `reg[14](&ref)` = the button minus its dialog. It deletes the file: destructive, so ask the player first.
- **New region**: the dialog sequence in Q1. Validate the name yourself. It uses the game's own path, so no restart should be needed (LIKELY).
- **Delete region**: `nation[12](idx)` then `app[12](0)`. Destructive.
- **Offline**:
  - Read cities, thumbnails and terrain with sc4_mcp.dbpf as in the scratch scripts.
  - A flat region is just a folder plus region.ini plus config.bmp: the game generates 270 m (Plains) or 192 m (Water) terrain on first open, but needs a restart to list a new folder.
  - RegionBitmapLoad blocks on its file dialog. Use it only with a player, or hook 0x919E96.

## 4. Live tests
1. Get the region-view window pointer: log ecx in 0x7AF720 during a "LoadCity" command, then check `[ptr+0xDC+...]`, `[ptr+0x1A4]` and the tile vector `[ptr+0x118]`.
2. `reg[11]` on an interior square of a large tile: does it return the city?
3. Call app[13](path, ref) for a shipped tile without the view (does the region view still tear down correctly?).
4. Create a region with nation[13] and run LoadRegion right after, without a restart.
5. Read `[0xB0D5E8]` at runtime (expect 3.0?).
6. Delete City on a test tile: the file disappears and the tile reopens flat at 270 m.
7. Budget record 0xE990BE01: compare its bytes before / after a save with funds `[B+0x28]`.
8. Neighbour deal: after a deal, find the deal in the region-view record of both cities.
