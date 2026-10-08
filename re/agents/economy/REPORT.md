# economy: budget, taxes, departments, loans, ordinances, neighbour deals (SC4 1.1.641, static only)

Scratch: `<workbench>\re\economy\`. From the exe's code, the UI layouts and the exemplars only.

## 1. Answers

**Q1. cISC4BudgetSimulator** (CONFIRMED)
- `[0xB43D64]` = `[city+0x160]`, interface at +0; ctor 0x694650, dtor 0x694140; +4 vtable 0xAB08F8 (message target /
  agent, DoMessage 0x693450); +8 vtable 0xAB08E0 (serialisation).
- The 59 slots of vtable 0xAB0908 follow the header with two swapped pairs: **slot 18** = GetTaxIncome(int group)
  0x6904C0; **slot 19** = GetTaxIncome(void) 0x68FD30 (`[+0x670]`, last month's tax); **slot 27** =
  GetDepartmentBudget(cIGZString const&) 0x691B50; **slot 28** = GetDepartmentBudget(uint32 id) 0x691000 (map at +0x54).
- **Funds = int64 at +0x28** (shadow +0x30). Slot 6 GetTotalFunds 0x68FD10; slot 5 SetTotalFunds 0x690140, slot 7
  DepositFunds 0x690170 (amount > 0, saturates) and slot 8 WithdrawFunds 0x690200 (fails if funds < amount) all
  broadcast kSC4MessageFundsChanged 0x772FAD4 (via 0x68FE10). Slot 9 GetMinAllowableFunds = `[+0x7A0]` (-100000).
- Monthly / yearly totals (int64): slot 16 GetTotalMonthlyIncome 0x690A30 = sum of slot 18 over 12 groups + ordinance
  sim slot 23 + neighbours slot 32 + each department's slot 16; slot 14 GetTotalMonthlyExpense 0x690990 (int64) =
  ordinance sim slot 22 + neighbours slot 33 + departments' slot 15 + loan payments. Year to date: slot 10 income
  `[+0x48]`, slot 12 expenses `[+0x40]`. End-of-year estimate: slot 11 (0x690270) = slot 16 x (13 - month) + YTD;
  slot 13 the same for expenses. Last month's totals: income `[+0x830]`, expense `[+0x840]`.
- **Tax rates**: slot 36 GetTaxRate(g) 0x68FD50 = float percent `[+0x70+g*0x80]` (g < 12); slot 37 SetTaxRate(g,
  float) 0x68FD70 stores it with **no clamp**, broadcasts nothing; slot 38 GetWeightedAssessedTaxValue(g) = int64
  `[+0xE0+g*0x80]`. Groups (advisor Lua globals 0x413A10): 0 R$, 1 R$$, 2 R$$$, 3 CS$, 4 CS$$, 5 CS$$$, 6 CO$$,
  7 CO$$$, 8 I-Agriculture, 9 I-Dirty, 10 I-Manufacturing, 11 I-HighTech. Monthly tax per group = WAV[g] x difficulty
  multiplier (table `[+0x814]`) x rate / 1200.
- **Budget window** (window proc 0x768750): tax spinners ids 0x200+g, layout `minmax=(0,200)` step 1; on change it
  calls SetTaxRate(id-0x200, value*0.1) at once (0x768865..0x76891A): **the player's range is 0.0-20.0 % in 0.1
  steps** (tuning MaxTaxRate 25.0 is copied to `[+0x74+g*0x80]` but not enforced). Cancel (0xCA4C352F, 0x764850)
  restores the rates saved at opening. ShowBudgetWindow (slot 24, 0x690330) queues a show / hide (byte +0x850) via
  message 0x29222F02 (data 0x892230F2 show / 0xC92230EE hide). Closing (0x7680D0) calls simulator HiddenResume (the
  window pauses the simulation while open, LIKELY).

**Q2. Departments and line items** (CONFIRMED unless marked)
- Departments: map<id, cISC4DepartmentBudget*> at budget+0x54 (STLport rb-tree: header `[+0x54]`, leftmost
  `[hdr+8]`, key +0x10, value +0x14). Slot 29 GetAllGroups(vector&) (0x28-byte elements: id, cRZString name +4,
  expense int64 +0x18, income int64 +0x20, LIKELY); slot 31 GetDepartmentBudgetsInGroup(group, vector&).
- Groups: Public Safety 0x4A357B40, Health & Education 0x6A357B7F, Transportation 0xAA369059, Utilities 0x4A357EAF,
  City Beautification 0x6A357B96, Government Buildings 0xEA597195, Business Deals 0x0A5A72D1 (window buttons
  0xAA3AC50A.. open a group window via 0x768460(group)).
- Department ids (exemplar property 0xEA54D283; names LIKELY): police / jail 0xA2963983 / 0xA2963984; fire
  0x28F55A9F; health 0x09188F42, 0xAA538CB3; education 0x09188F4C, 0x4A538CC6; power 0x8910BC8A; water 0xAA4014B4;
  recycling / garbage 0x6A42A8F5; toxic dump 0x2A5A723F; parks 0x8A4260A6; landmarks 0x8A416368; city hall /
  government 0xEA59717A; mass transit 0xC921CEEB; toll booth / roads 0xC921CEEA. null-45's custom departments are
  created through slot 25 and marked SetFixedFunding(true).
- cSC4DepartmentBudget: vtable 0xAB0EB0, 34 slots in header order; ctor 0x6AAB90 (new 0x68). Slot 10
  GetFundingPercentage -> float* (+0x34, 1.0 = 100 %); slot 11 SetFundingPercentage(const SC4Percentage&, line)
  (0x6AC1B0 -> 0x6AB810): clamps to [0, `[+0x38]`], ignored for fixed-funding departments (+0x48), sets each
  non-local expense line's current cost = full cost x percentage; slot 12 GetMaxAllowed (+0x38, ctor 1.0); slots 14 /
  15 / 16 ideal cost, current expenses, income; slot 30 year-to-date spending (+0x40).
- The player's funding slider (0x78C11F..0x78C148) calls `dept->SetFundingPercentage(&(value*0.01), 0)`; slider
  maximum = GetMaxAllowed*100 (0x788CD5..0x788D27). Per-building local funding rows go through 0x77BC90 (not traced).
- cISC4LineItem: vtable 0xAB0F58, 20 slots, ctor 0x6AAE20; department slot 20 GetLineItem(n), 21 GetAllLineItems.

**Q3. Loans** (CONFIRMED)
- IssueBond(uint32 amount), slot 40, 0x6916F0: requires amount > 0 and count `[+0x784]` < maximum `[+0x7B0]`; rounds
  down to the increment `[+0x7A8]` (at least one); requires amount <= bond limit `[+0x7B8]` and borrowed `[+0x38]` +
  amount <= slot 42; builds the record, count+1, broadcasts kSC4MessageBondIssued 0xC772FADA, borrowed += amount,
  DepositFunds(amount).
- The Loans window does exactly this ("Accept New Loan" 0xAA4C33E6 -> 0x768EAD -> 0x764BE0 -> IssueBond); amount
  spinner 0x8A4C34D4 `minmax=(5000,100000)` step 5000; shows min(bond limit, limit - borrowed) and disables Accept
  at the limit (0x765F88..0x766010). IssueBond is honest play; the one extra UI rule is the 100,000 cap.
- Terms from "Budget Tuning Parameters" (6534284A-E7E2C2DB-0BFF6824; CAM overrides it with the same loan values): 10
  loans, limit 200,000, increment 5000, 8.5 % interest, 120 months. Slot 42 = loans x per-loan limit (2,000,000);
  slot 43 per-loan limit; slot 44 maximum loans; slot 48 amortisation P*r/(1-(1+r)^-n), r = rate/12; slot 49 =
  payment x n.
- **No early repayment in SC4**: only the ctor, IssueBond and the monthly handler write the count; the Loans window
  has only Accept, Cancel (0x0A4C3354) and scroll buttons. `repay_loan` could only be cheat-class.
- Matured loans are removed monthly (kSC4MessageBondFinished 0xCA3FBDCE, borrowed -= principal).

**Q4. Ordinances** (CONFIRMED)
- Ordinance simulator vtable 0xABEAC0, 26 slots, header order, `[0xB43D90]`; map<clsid, ord*> at +0x30 (includes
  custom-host ordinances, AddOrdinance slot 5 at PostCityInit).
- **SetOrdinanceOn(clsid, bool)** slot 13, 0x80D690: if the state differs, ord->SetOn (slot 25); adds the fee to
  `[+0x28]` (GetEnactmentIncome slot 11 / GetRetracmentIncome slot 12; negative = cost); broadcasts
  kSC4MessageOrdinanceUpdated 0xC2C09554; checks neither availability nor funds. The Ordinances panel's OK
  (0x78B15D..0x78B1A0) calls it for every changed row of its list of *available* ordinances: a tool must check
  IsOrdinanceAvailable (slot 7) first.
- New month (0x80D950): recomputes `[+0x18]` expense / `[+0x20]` income from the pending fee (+0x28) plus each enacted
  ordinance's adjusted monthly income; slots 22 / 23 return the month just computed.
- cSC4OrdinanceSimple: vtable 0xABD9D8, header order plus slot 30 SetKey.

**Q5. Monthly settlement and history** (CONFIRMED)
- The budget is a OneShot, Day and Month agent. Daily (0x6900F0): each tax rate x 10 to history type 0xAABAAA9F+g
  (365 entries). Monthly (0x692510, on 0x66956816): tax income 0x691E20 -> `[+0x670]`, YTD `[+0x750]`; ordinance
  figures `[+0x690+8m]` / `[+0x6F0+8m]`; each department recalculates (slot 29) and SetTotalSpending; loan payments
  and maturity; **SetTotalFunds(funds + income - expense)** - funds change once a month; YTD and last-month fields;
  history 0x6A51178B income, 0xCA5BA3FB expense, 0x4A5BA3D0 funds/1000; YTD reset after December; funds <= minimum
  -> kSC4MessageEndGameForBudgetFailure 0xAA5CF1E3.
- History warehouse `[0xB43DC0]`, vtable 0xA8CCB4: slot 8 GetPoint(type, cIGZDate const&, float&), 5 GetCount, 7
  GetMinMaxAverage, 12 RecordHistoryData; slots 10 / 11 swapped (10 = Dispose(type), 11 = Dispose(type, start, end)).
- Budget cheats in its DoMessage (0x230E27AC): 0xCBF31943 deposits 10000 (may start a riot); 0x4AB87766 +1000;
  0x493F4FE6 sets funds.

**Q6. Neighbour deals** (vtables CONFIRMED, player flow OPEN)
- Neighbours simulator vtable 0xAB1EE0, 38 slots; swapped pairs: 13 = FindConnectionOnOtherSide(conn*), 14 = (type,
  x, z); 29 = FindDeals(type, city, list), 30 = FindDeals(type, list). Deals list at +0x20; slot 28 FindDealsAll(list);
  slots 32 / 33 monthly deal income / expense. ProposeDeal (slot 24, 0x6CF780) builds a deal for a suitable
  connection (slot 23) without adding it; AddDeal (slot 26, 0x6D2870) writes it into the region's records;
  ProposeDeals (slot 25, 0x6D21A0) is the game's own offer logic (NDx tuning, MinBudgetForBuyDeals 0xEA4AE9EF...).
  Deal vtable 0xAB1DD8 (41 slots, ctor 0x6CF270): slot 34 Cancel (flag 4 set, flag 2 cleared), 35 Activate. The
  player's accept / cancel dialog was not found.

## 2. Layouts
- **Budget simulator**: 0x10 refcount; 0x18 city; 0x1C message server; 0x20 land value; 0x24 ordinance sim; 0x28
  funds int64 (0x30 shadow); 0x38 borrowed; 0x40 / 0x48 YTD expense / income; 0x54 department map; 0x70 + g*0x80
  {+0 rate float, +4 max rate float, +0x70 weighted assessed value int64}; 0x670 last month's tax; 0x680 / 0x688
  ordinance YTD; 0x690[12] / 0x6F0[12] monthly ordinance figures; 0x750 tax YTD; 0x780 loan list; 0x784 loan count;
  0x788 loan payments YTD; 0x790 initial funds[3]; 0x79C max tax; 0x7A0 minimum funds; 0x7A8 increment; 0x7B0 max
  loans; 0x7B8 per-loan limit; 0x7C0 interest; 0x7C4 months; 0x814 difficulty multipliers; 0x820 initial taxes;
  0x830 / 0x840 last month's income / expense; 0x850 window-shown byte.
- **Loan record** (list node): +8 end month, +0xC end year, +0x10 principal, +0x18 full cost, +0x20 cost left, +0x28
  paid, +0x30 monthly payment, +0x38 balance. GetAllLoans: 0x20 bytes per loan (months left, years left, principal,
  balance, monthly payment).
- **Department**: 0x10 id, 0x14 name, 0x30 group, 0x34 funding %, 0x38 maximum %, 0x40 YTD spending, 0x48 fixed
  funding, 0x4C line map. **Line item**: 0x30 building count, 0x38 full cost, 0x40 current cost, 0x48 income, 0x54 id,
  0x58 display flags, 0x5C local flag, 0x64 type (0 expense, 1 income).
- **Ordinance simulator**: 0x18 / 0x20 monthly expense / income, 0x28 pending fees, 0x30 map. **Ordinance**: 0x38 id,
  0x3C name, 0x50 description, 0x64 first year, 0x70 / 0x78 enact / repeal fee, 0x80 monthly constant, 0x88 factor,
  0x90 income flag, 0x91 available, 0x92 on, 0x93 enabled, 0x98 adjusted monthly income.
- **Deal**: 0x20 type, 0x24 / 0x2C cells, 0x34 amount, 0x48 used, 0x50 cost, 0x5C..0x74 dates, 0x78 flags.

## 3. Recipes (thiscall, main thread, app state == 2; B = city slot 52, O = 63, N = 62)
- **get_budget** (read-only): funds B[6]; tax per group B[18](g), rates B[36](g); groups B[29] then B[31] and dept
  [15]/[16] (monthly), [30] (YTD), [10] (funding); ordinances O[23]/O[22]; deals N[32]/N[33]; loans B[45]; totals
  B[16]/B[14]; YTD B[10]/B[12]; end of year B[11]/B[13]; last month `[B+0x830]`/`[B+0x840]`.
- **set_tax(group, rate)**: clamp 0..20, round to 0.1, B[37](g, float) - as the UI (CS and CO are separate groups).
- **set_department_funding(dept, pct)**: `d = B[28](id)`, `d[11](&float(pct/100), 0)` (clamps to [0, d[12]] like the UI;
  fixed-funding departments ignore it).
- **ordinances / set_ordinance**: O[18] GetOrdinanceIDArray(buf, &count), O[20](id) -> name ord[7], state ord[17] /
  ord[18], fees ord[11] / ord[12], monthly ord[20]; change: require O[7](id), then O[13](id, on) (fee charged at the
  next monthly settlement).
- **take_loan(amount)**: B[40](amount) (false when the game's limits refuse; also cap 100,000 like the spinner).
  **loans**: B[46](vector&). **repay_loan**: not possible in honest play.
- **neighbor_deals**: N[28](list&) / N[30](type, list&) (elements cISC4NeighborDeal*, LIKELY). Cancelling / adding
  deals (deal[34], N[24] + N[26]) is cheat-class until the UI path is found.
- **Cheat-class only**: B[5] SetTotalFunds, B[7] / B[8], tax rates above 20, ord Force*, O[10] SetOrdinanceAvailable.

## 4. Live tests
1. `[B+0x28]` before / after the 1st of a month: changes once by `[B+0x830]` - `[B+0x840]`.
2. B[36](0..11) vs the Budget window; one spinner change changes only that group's rate.
3. `[d+0x38]` for police, education, parks: real maximum funding (1.0 or 1.2?).
4. IssueBond(7000): 5000 issued, count +1, funds +5000, GetAllLoans 120 months; over the limit -> false.
5. O[13]: `[O+0x28]` changes now; the fee appears in O[22]/O[23] after the next month.
6. N[28] in a city with a power deal: element type; deal[22] GetCost; deal[8] type.
7. Find the deal accept / cancel UI (who calls deal[34] when the player cancels).
8. Order of the budget's and the ordinance sim's month agents (compare O[22] with the budget's ordinance line).
