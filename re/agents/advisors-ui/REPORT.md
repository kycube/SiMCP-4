# RE report: advisors-ui (SC4 1.1.641, static only)

Scratch: `<workbench>\re\advisors-ui\` (`layouts_en.txt`: all 271 UI layouts with root clsid, id, caption, buttons and
English labels; `layouts.json`, `ltext_en.json`; `idnames.txt`, the exe's id/name table; helper scripts).

## 1. Answers

**Q1. Advisor system, advisors, advices** (CONFIRMED unless marked)
- **Advisor system** `sys = [0xB43D34]` (city slot 81), vtable 0xA82AC8, iid **0x4A0DD617**, ctor 0x41A0D0; 23 slots in
  gzcom-dll order with the SetGlobalValue overloads swapped (12 = (char*, cIGZString*), 13 = (char*, double)). Fields:
  +0x30 RZRandom (slot 9); **+0x4C advisor map** STLport `map<int32, cRZAutoRefCount<cISC4Advisor>>` (header pointer
  +0x4C, count probably +0x50; node +0x08 left, +0x0C right, +0x10 advisor id, +0x14 cISC4Advisor*; slot 7
  GetAdvisor(id) via 0x6C0030, slot 8 returns &sys+0x4C); +0x58 cISCLua* (slot 10); +0x74/+0x78 context-advice stack
  (slots 18-20); +0x80 data tags (slot 22). Slot 21 GetAdvicePopupPriorityThreshold: field by difficulty (hard +0x24;
  easy / medium probably +0x1C / +0x20), from Lua `ADVICE_POPUP_PRIORITIES_BY_SKILL_LEVEL`.
- **Advisors**: ids from Lua `adv_const`: 1-5 MySim, 21 utilities, 22 health & education, 23 city planning, 24
  transportation, 25 environment, 26 finances, 27 safety, 28 fluff news, 29 city situations, 30 My Street Sim. Lua
  class ids: base 0xCA09F543, HQ 0x6A5F8755, CityPlanning 0x2A5F877D, Finance 0xAA5292D7, Traffic 0x4A3AD3E1,
  Utility 0xCA2C2A2F, Safety 0xEA19E825, CitySituations 0x4BE372CD, MySim 0x4A1DBBBF, MyStreetSim 0x0BF606A5.
- **cISC4Advisor** at obj+8 (QI thunk 0x40F370 does `sub ecx,8`), vtable 0xA811B0, iid **0xCA09F544**, 21 slots in
  gzcom-dll order (incl. SetName slot 7, absent on Mac). Offsets from the interface pointer I: **+0x10 caption**
  cRZString (slot 6); +0x30 personal name (slot 8); **+0x58 id** (slot 5); **+0x70 current-advice list** (slots 9/10:
  STLport list sentinel; node {next, prev, int index into the record vector, cISC4Advice*}, node layout LIKELY);
  **+0x7C..+0x80 vector of every advice** of the advisor, 16-byte records {cISC4Advice*, next eligible day, expiry day,
  last tick} (slots 11/12 scan it).
- **cSC4Advice**: clsid 0x8A09F5F4, **iid 0x8A09F5F5**, vtable 0xA808B8, Init 0x408C70 reads the Lua fields. Slots
  (Mac order): 6 GetMood (+0x84), 7 GetPriority (+0x78, 0..100), 8 GetTrigger (Lua), 10 GetGUID (+0x8C), 11
  GetAdvisorID (+0x74), 13 GetSessionID (+0xB0), 14 SetFlags(mask, bool), 15 CheckFlags(mask), 16 frequency days
  (+0x7C), 17 timeout days (+0x80), **18 GetTextTitle -> cIGZString* = adv+0x30**, **20 GetTextMessage -> adv+0x50**,
  25 GetEventSubject (+0xAC), 26 GetEventID (+0xA8), 27 GetCommandID (+0xB4), 28 UpdateText (calls slot 30,
  0x409300). Title / message are 0x20-byte localized strings (vtable 0xA85478): a cRZString then the LTEXT key {type
  0x2026960B, group, instance} at +0x14/+0x18/+0x1C. Title text `[adv+0x34]..[adv+0x38]`, instance `[adv+0x4C]`;
  message `[adv+0x54]..[adv+0x58]`, instance `[adv+0x6C]`; group 0x6A231EA4; a failed load gives
  `***_NOT_IN_TEXT_DATABASE_***`.
- Moods: 0 alarm, 1 bad job, 3 neutral, 5 great job, 7 fluff. Flags (+0x70): 0x1 news_only, **0x2 active**, 0x4 once,
  0x40 event-driven, 0x100 persist, 0x800 class mismatch, 0x4000 queued for popup, 0x8000 no_timeout (0x8, 0x400,
  0x1000, 0x2000 internal).
- Lua feeds it: `advices` / `advisors` tables from `create_advice_*` / `create_reward_*` / `advisors:new`; triggers
  compiled as `'%s = function () return (%s); end'`. Simulate (round-robin, index obj+0x64, 0x40F494): an advice not
  active, not event-driven, eligible today and whose trigger is true goes through **Activate 0x40DF20** (appended to
  the current list, flag 2, expiry = today + timeout, **posts kSC4MessageAdvisors_AdviceAdded 0x8A09FA64** with the
  advice as the message's void* (0x40DA10), plus AdviceCommand 0x8A09FA6C if it has a command). Deactivate 0x40DF90
  clears 0x40A, sets the next eligible day (0x7FFFFFFF for "once"), posts AdviceRemoved 0x8A09FA65.

**Q2. News ticker** (layout and code CONFIRMED; content mapping LIKELY)
- Layout **0x2A2AED99** (group 0x96A006B0): bottom strip root 0xCA2AEDC0 (class 0x89E1567C); **ticker =
  cSC4WinAdviceList id 0xAA12F33C**; ticker click button 0xCA2AEDCD; "Open News Window" 0xCA2AEDCC; news window root
  0xAA231508, its list 0x6A231531, close 0x4A231510.
- Controller: ctor 0x76F160 (vtables 0xAB5114 / 0xAB5104 / 0xAB50EC); DoMessage 0x7721A0 handles AdviceAdded /
  AdviceRemoved / 0xCA09FA6C / MySimsChanged 0xAA25827C; Rebuild 0x770740 writes mood-coloured HTML and calls AddEntry
  (0x77124F).
- cSC4WinAdviceList: clsid 0xCA1492AC, factory 0x793D20 (new 0xE8, ctor 0x793CB0), cIGZWin vtable 0xAB58B0 at +0,
  **cISC4WinAdviceList vtable 0xAB5880 at +0xD8** (4 AddEntry (9 args, 0x793DA0), 5 RebuildHTML, 7 ClearList). Entries:
  sentinel `[win+0xE0]`, count `[win+0xE4]`, push_back order; each node holds a 0x70-byte entry at node+8: cRZString
  texts at +0x00/+0x14/+0x28/+0x3C/+0x50 (HTML headline variants), **+0x68 the cISC4Advice as cIGZUnknown*** (ref-
  counted), bools +0x64/+0x6C. News-only advices (flag 1) appear only there.

**Q3. Window manager and windows** (CONFIRMED)
- **cIGZWinMgr** = GetSystemService(0xA417445E, 0x5A4): W32 subclass (ctor 0x9DAE9F), **vtable 0xAE46E8** (base 0xAE4910,
  purecall 0x5D4A10); gzcom-dll order except swaps 12/13 and 14/15. 3 GetMainWindow `[+0x40]`; 28 capture `[+0x30]`; 36
  focus `[+0x34]`; **41 DoModalWin(win) 0x9DBDA3**; **42 IsModal = `[mgr+0x17C] != 0`**; 43 nest count `[+0x17C]`; 44
  GZMsgBox 0x9DB04A (GZCOM class 0x593, iid 0x57C, 0x118 bytes); **63 modal loop 0x9DA84F** (Windows-only).
- DoModalWin: pushes the window onto a container at mgr+0x38 (0x5447B0; removal 0x54DB10), sets window flag **0x1000**
  (cIGZWin slot 68), runs PeekMessage / TranslateMessage / DispatchMessageA plus `[mgr+0x58]` slot 16
  (ProcessPostedMessages) per turn; ends when a private registered message (id from 0x9DA71A(0xF)) carries (win,
  result); returns the result.
- **cGZWin**: +0x04 WinMgr; **+0x10 id** (slot 63); **+0x44 -> {sentinel*, guard}** child list, node {next, prev,
  cIGZWin* +8}; +0x48 parent (slot 11); +0x4C notification target (slots 86/87); **+0x50 caption cRZString** (slot 73;
  text `[w+0x54]..[w+0x58]`); +0xA8..+0xB4 rect L, T, R, B (slots 41/42 W/H); **+0xC8 flags** (slot 67: 1 visible, 2
  enabled, 0x1000 modal); +0xCC instance id (slot 65); slots 13 GetChildCount, 32 EnumChildren, 34/35
  GetChildWindowFromID(Recursive). Buttons QI to cIGZWinBtn 0x8810 (labels probably in the caption, LIKELY).
- Clicking = GZWinClickButton (WinMgr slot 15 posts down 7 / up 0xA); posted window messages are drained inside the
  modal loop.
- **Dialog map** (layout instance, root id, buttons):

| Dialog | Layout | Root id | Buttons |
|---|---|---|---|
| Save / Quit | 0x0A55161D | 0xAA921F4F | 0x8A921F5B "Save and Quit", 0x8A921F65 "Quit without Save", 0x8A921F70 Cancel |
| Exit to region with save | 0x6A553AA4 | 0xAA921F4F | same three ids |
| Quit game | 0x4A551B4C | 0xAA921F4F | 0x8A921F65, 0x8A921F70 |
| Exit choice | 0xEAAEEC1B | 0x6AAEEC4A | 0x6AAEEC41 "Exit to Region", 0x6AAEEC42 "Exit and Play City", 0x6AAEEC43 Cancel |
| Can't save during a disaster | 0x4A89B3F2 | 0x2A96ED21 | Accept 0xEA57DA59, Cancel 0x6A57DA48 |
| **Advisor popup** | **0x4A5A89D4 (mood < 3) / 0x4A5A89D5** | **0x4A9DB60C** | **Close = id 1** |
| Mission offer | 0x2BB16D50 | 0xEBB16D71 | Accept 6, Free Ride 7, Cancel 1 |
| Mission result | 0x0BBC06B6 / 0x4BBC080F | 0xEBBC081E | Close 1 |
| Tutorial step | 0x0A2DD355 | 0x4A35B0F2 | Continue 0xCA8D8595, Exit Tutorial 0x4A383DA6 |
| Tutorial exit | 0x6A5E73C0 | 0xEA5E748C | Exit Tutorial 0xEA5E7834, Cancel 0xCA5E77DA |
| Budget / loans | 0xAA3ACDFE | 0xAA3AC002 | Accept 0xAA4C353B, Cancel 0xCA4C352F |
| Establish city | 0x2A41436B | 0x6A414973 | Establish City 0x2A4144BE, Cancel 0x8A414491 |
| Obliterate | 0x2A41436C | 0x27DF05BE | |
| Edge reconcile | 0x8A4D0A17 / 0xCA4D0B22 / 0x0A4D0C43 | 0x6A4D0A59 | 0x6A4D0A6B, 0x6A4D0A71 |
| Missing-plugins warning | 0xEA89B6C3 | 0x2A5CFB2C | Accept 0xAA89FAF5 |

  Ids 1/6/7 look like Win32 IDOK / IDYES / IDNO (GUESS). Disaster alerts and My Sim windows not mapped (disaster alerts
  are probably advisor popups).

**Q4. Popups vs. modal loops** (CONFIRMED)
- App slots 23/24 Get/SetPopupDialogsEnabled = byte A+0x645 (cSC4App+0x651); the commands Get/SetPopupModalDialogs-
  Enabled (0x5F9090 / 0x5F90B0) wrap them. **GetPopupModalDialogsSafe 0x5F9000** is true only if all mouse buttons are
  up (GetKeyState), `!WinMgr->IsModal()`, a city exists and city slot 108 (UI lock count) == 0.
- Advisor popup tracker (ctor 0x762E70, vtables 0xAB4968 / 0xAB4954, DoMessage 0x763450; LIKELY clsid 0xCA5A7559): on
  AdviceAdded it queues the advice if (flags & 0x6000) == 0, sets 0x4000 and posts 0xEA83607B to itself; re-posts while
  not Safe; drops the popup unless popups are enabled, the preference byte `[[0xB43CD8]+0xF0B]` is set, priority >=
  threshold, no tutorial runs (tutorial slot 8) and `[0xB43D44]` slot 13 is false; otherwise opens the layout above,
  pauses the simulation clock and the 24-hour clock (scope 0x5F9320 -> 0x5F91C0) and calls **DoModalWin** (a nested
  modal loop blocking the poster). Mission popups (0x52E910) the same.
- Generic message / confirm helpers 0x78DD80, 0x78DFF0 (layout 0x8A8DFCF5), 0x78E2F0 return at once when popups are
  disabled; 0x48C6D0, 0x74ED40, 0x7F6268 also check the flag. With popups disabled advices are still activated and shown
  in the ticker and advisor panel, but no popup / generic message box opens.

**Q5. Business deals and rewards** (storage CONFIRMED; player path LIKELY)
- Defined in Lua through `create_reward_*` -> cSC4RewardAdvice (0xAA371C32, vtable 0xA85FF8, GetTrigger 0x43EC30). **The
  advice GUID is the building exemplar IID**: casino 0x033A0000, prison 0x03380000, missile range 0x03420000, toxic dump
  0x03410000, army base 0x03460000 (finance advices); mayor's house 0x031F0000 etc. (rewards). `condition()` returns 0
  HIDDEN, 1 AVAILABLE, or a locked-reason text.
- State in cISC4CivicBuildingSimulator `[0xB43DB4]` (city slot 73, vtable 0xAB0C7C, iid 0x8A41322F): slot 5
  IsBuildingExcluded; **slot 6 GetConditionalBuildingStatus(id)** -> {u8 status (1 hidden, 2 available, 4 advisor-event
  data set); u16 count; SC4String tooltip = the requirement text}; slot 7 Update; slot 8 GetLandmarkCount. Hash table
  buckets `[civic+0x30]..[+0x34]`, node {next, id +4, status +8, count +0xA, tooltip +0xC}. Lua bindings:
  get_reward_building_state 0x40AA60, unlock_reward_building 0x40B760, reward_instance_count 0x40A8E0.
- "Accepting" a deal = placing the unlocked building from the Rewards menu (no accept dialog found). Neighbour deals
  (cSC4NeighborDeal 0x2A134F42, types 0x4773FFE0..E5) not analysed here.

**Q6. Tokens** (CONFIRMED): detokenizer `[0xB43CDC]` = cISC4App slot 42 (+0xA8 = `[A+0x5AC]`); Windows slots 8
Detokenize(key, out); **9 Detokenize(cIGZString const& in, cIGZString& out)** (called with in == out); 10 / 11 Set /
GetHTMLCleanMode. Localized string: ctor **0x603580**(thiscall: group, instance, bool detokenize) on a 0x20-byte object
(LTEXT via the resource manager `[0xB43CA8]` slot 4, iid 0x89B7DC8; detokenizes via 0x603300). Tokens: #city#, #mayor#,
#name#, #tuning_constants.X#, #link_id# in `<a href>` links; unknown tokens probably go to Lua.

## 3. Recipes (main thread, under SEH)
- **advisors()** (read-only): walk `[sys+0x4C]`; per advisor I read caption I+0x10, id I+0x58; walk I+0x70 for active
  advices: mood +0x84, priority +0x78, GUID +0x8C, title +0x30, message +0x50, news_only = flags & 1. Overall mood =
  worst active mood. (Slot 28 UpdateText refreshes tokens, LIKELY harmless.)
- **news()**: window id 0xAA12F33C from the main window (slot 35), walk `[w+0xE0]`; entry+0x68 -> QI 0x8A09F5F5 -> title.
  Fallback: all active advices.
- **city_opportunities()**: civic slot 6 per reward / landmark / deal IID: status, count, tooltip. Require AVAILABLE
  before any PlaceLot (honest play; placing goes through the normal funds check).
- **dialog_status()**: `WinMgr->vtbl[42]()`; if modal, find children with flags & 0x1000 (or the container at
  mgr+0x38); report id +0x10, caption +0x50 and visible children recursively (id, caption, button = QI 0x8810).
- **close_dialog(button)**: match label or id, post the click like GZWinClickButton (WinMgr slot 15, msg 7 then 0xA at
  W/2, H/2) - the player's own path.
- **Auto mode**: SetPopupDialogsEnabled(false) (app slot 24) stops advisor popups and message boxes; poll IsModal for
  the rest; press Cancel / Close (id 1) or the safe default.
- **Threading**: during DoModalWin the main thread sits in PeekMessage / DispatchMessageA - a bridge driven by its own
  window keeps running; framework tick hooks may not (GUESS). The simulation is paused while advisor and mission popups
  are open.

## 4. Live tests
1. `[[0xB43D34]] == 0xA82AC8`; walk the advisor map: 10+ advisors with ids 21-30 and captions.
2. Active advice titles at +0x30 vs the advisor panel; ticker list at `[0xAA12F33C win]+0xE0`.
3. Open Save/Quit: IsModal 1, `[mgr+0x17C]` 1, a child with flags & 0x1000 and id 0xAA921F4F; click Cancel 0x8A921F70.
4. SetPopupDialogsEnabled(0) then a high-priority advice: no popup, flag 2 set.
5. Civic slot 6 for 0x033A0000 before / after legalizing gambling + population; tooltip = the locked-reason text.
6. Does the bridge (hidden window) still answer while an advisor popup is open?
7. Detokenize (slot 9) "#city# #mayor#" vs the names.
