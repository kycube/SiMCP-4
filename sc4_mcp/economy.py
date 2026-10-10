"""Budget actions with the game's own functions and the player's limits (re/reports/economy/REPORT.md, verified in
notes/LIVE_FACTS.md): taxes, department funding, ordinances, loans."""

from __future__ import annotations

import struct

from . import bridge as bridgemod
from . import city, memory

G_ORDINANCES = 0xB43D90

GROUPS = {0x4A357B40: "Public Safety", 0x6A357B7F: "Health & Education", 0xAA369059: "Transportation",
          0x4A357EAF: "Utilities", 0x6A357B96: "City Beautification", 0xEA597195: "Government Buildings",
          0x0A5A72D1: "Business Deals"}

# Budget simulator slots (Windows order)
B_SET_TAX = 37
B_ISSUE_BOND = 40
# Department slots
D_SET_FUNDING = 11
D_EXPENSE = 15
D_INCOME = 16
# cISC4Ordinance slots
O_ID, O_NAME, O_DESC, O_FIRST_YEAR = 6, 7, 8, 9
O_ENACT, O_REPEAL, O_CONSTANT = 11, 12, 13
O_AVAILABLE, O_ON, O_ENABLED, O_ADJUSTED, O_IS_INCOME = 17, 18, 19, 20, 22
# Ordinance simulator slots
OS_IS_AVAILABLE, OS_SET_ON = 7, 13

UI_TAX_MAX = 20.0          # the Budget window's spinners: 0.0 .. 20.0 in 0.1 steps
LOAN_STEP, LOAN_MIN, LOAN_MAX = 5000, 5000, 100000   # the Loans window's spinner


class EconomyError(RuntimeError):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def _vt(p, obj, slot):
    return p.u32(p.u32(obj) + 4 * slot)


def call32(g, obj: int, slot: int, *args) -> int:
    return g.bridge.call_function(_vt(g.proc, obj, slot), list(args), this=obj).ret[0]


def call64(g, obj: int, slot: int, *args) -> int:
    r = g.bridge.call_function(_vt(g.proc, obj, slot), list(args), this=obj)
    v = (r.ret[0] & 0xFFFFFFFF) | ((r.ret[1] & 0xFFFFFFFF) << 32)
    return v - (1 << 64) if v >> 63 else v


def gz_text(g, s: int) -> str:
    """Text of any cIGZString (cIGZString slot 5 ToChar -> char*), whatever class implements it."""
    if not s:
        return ""
    c = g.bridge.call_function(_vt(g.proc, s, 5), [], this=s).ret[0] & 0xFFFFFFFF
    return g.proc.cstr(c, 1024) if c else ""


def _map_nodes(p, hdr: int) -> list[int]:
    out, stack, cur = [], [], p.u32(hdr + 4)
    while (cur and cur != hdr) or stack:
        while cur and cur != hdr:
            stack.append(cur)
            cur = p.u32(cur + 8)
        cur = stack.pop()
        out.append(cur)
        cur = p.u32(cur + 0xC)
    return out


def _f32_bits(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


# ---- departments
def departments(g) -> list[dict]:
    p = g.proc
    B = p.u32(city.G_BUDGET)
    out = []
    for nd in _map_nodes(p, p.u32(B + 0x54)):
        d = p.u32(nd + 0x14)
        out.append({"department": memory.rz_string(p, d + 0x14), "id": "0x%08X" % p.u32(d + 0x10),
                    "group": GROUPS.get(p.u32(d + 0x30), "0x%08X" % p.u32(d + 0x30)),
                    "funding_percent": round(p.f32(d + 0x34) * 100, 1),
                    "max_funding_percent": round(p.f32(d + 0x38) * 100, 1),
                    "fixed_funding": bool(p.u8(d + 0x48)),
                    "monthly_expense": call64(g, d, D_EXPENSE), "monthly_income": call64(g, d, D_INCOME),
                    "_ptr": d})
    return out


def _find_department(g, name: str) -> dict:
    deps = departments(g)
    key = name.strip().lower()
    for d in deps:
        if d["department"].lower() == key or d["id"].lower() == key:
            return d
    matches = [d for d in deps if key in d["department"].lower()]
    if len(matches) == 1:
        return matches[0]
    raise EconomyError("no department %r" % name, "departments: " + ", ".join(d["department"] for d in deps))


def set_department_funding(g, name: str, percent: float) -> dict:
    d = _find_department(g, name)
    if d["fixed_funding"]:
        raise EconomyError("%s has fixed funding" % d["department"], "the game does not let the player change it")
    pct = max(0.0, min(float(percent), d["max_funding_percent"]))
    b = g.bridge
    # SetFundingPercentage(const SC4Percentage&, line): the percentage (a float, 1.0 = 100%) lives in the bridge's
    # request area while the game reads it.
    addr = b.block + bridgemod.B_STR + 1000
    g.proc.write(addr, struct.pack("<f", round(pct, 1) / 100.0))
    call32(g, d["_ptr"], D_SET_FUNDING, addr, 0)
    after = _find_department(g, d["department"])
    return {"department": d["department"], "funding_percent": after["funding_percent"],
            "requested": percent, "clamped_to_max": percent > d["max_funding_percent"],
            "monthly_expense": after["monthly_expense"], "before_percent": d["funding_percent"]}


# ---- taxes
def set_tax(g, group: str, rate: float) -> dict:
    if group not in city.TAX_GROUPS:
        raise EconomyError("unknown tax group %r" % group, "groups: " + ", ".join(city.TAX_GROUPS))
    p = g.proc
    B = p.u32(city.G_BUDGET)
    i = city.TAX_GROUPS.index(group)
    before = round(p.f32(B + 0x70 + i * 0x80), 1)
    r = max(0.0, min(UI_TAX_MAX, round(float(rate), 1)))
    call32(g, B, B_SET_TAX, i, _f32_bits(r))
    after = round(p.f32(B + 0x70 + i * 0x80), 1)
    return {"group": group, "rate": after, "before": before,
            "clamped": r != round(float(rate), 1)}


# ---- ordinances
def ordinances(g) -> list[dict]:
    p = g.proc
    O = p.u32(G_ORDINANCES)
    out = []
    for nd in _map_nodes(p, p.u32(O + 0x30)):
        o = p.u32(nd + 0x14)
        out.append({"ordinance": gz_text(g, call32(g, o, O_NAME) & 0xFFFFFFFF),
                    "id": "0x%08X" % (call32(g, o, O_ID) & 0xFFFFFFFF),
                    "available": bool(call32(g, o, O_AVAILABLE) & 0xFF),
                    "enacted": bool(call32(g, o, O_ON) & 0xFF),
                    "enactment_fee": -call64(g, o, O_ENACT), "repeal_fee": -call64(g, o, O_REPEAL),
                    "monthly_income": call64(g, o, O_ADJUSTED),
                    "income_ordinance": bool(call32(g, o, O_IS_INCOME) & 0xFF),
                    "description": gz_text(g, call32(g, o, O_DESC) & 0xFFFFFFFF)})
    out.sort(key=lambda x: x["ordinance"])
    return out


def set_ordinance(g, name: str, enacted: bool) -> dict:
    ords = ordinances(g)
    key = name.strip().lower()
    hits = [o for o in ords if o["ordinance"].lower() == key or o["id"].lower() == key] or \
           [o for o in ords if key in o["ordinance"].lower()]
    if len(hits) != 1:
        raise EconomyError("no single ordinance matches %r" % name,
                           "ordinances: " + ", ".join(o["ordinance"] for o in ords))
    o = hits[0]
    O = g.proc.u32(G_ORDINANCES)
    oid = int(o["id"], 16)
    if not (call32(g, O, OS_IS_AVAILABLE, oid) & 0xFF):
        raise EconomyError("%s is not available to this city yet" % o["ordinance"],
                           "the Ordinances panel lists only available ordinances")
    call32(g, O, OS_SET_ON, oid, 1 if enacted else 0)
    now = next(x for x in ordinances(g) if x["id"] == o["id"])
    return {"ordinance": o["ordinance"], "enacted": now["enacted"], "was": o["enacted"],
            "fee": (o["enactment_fee"] if enacted else o["repeal_fee"]) if now["enacted"] != o["enacted"] else 0,
            "note": "the fee and the monthly effect are settled with the month's budget"}


# ---- loans
def loans(g) -> dict:
    p = g.proc
    B = p.u32(city.G_BUDGET)
    out = []
    sent = p.u32(B + 0x780)
    node, n = p.u32(sent) if sent else 0, 0
    while node and node != sent and n < 64:
        n += 1
        raw = p.read(node, 0x40)
        end_month, end_year = struct.unpack_from("<II", raw, 8)
        principal, full, left, paid, payment, balance = struct.unpack_from("<qqqqqq", raw, 0x10)
        out.append({"principal": principal, "monthly_payment": payment, "remaining": left, "paid": paid,
                    "total_cost": full, "ends": "%04d-%02d" % (end_year, end_month)})
        node = p.u32(node)
    return {"loans": out, "count": p.u32(B + 0x784),
            "borrowed": struct.unpack("<q", p.read(B + 0x38, 8))[0],
            "max_loans": p.u32(B + 0x7B0), "limit_per_loan": p.u32(B + 0x7B8),
            "interest_percent": round(p.f32(B + 0x7C0) * 100, 2), "months": p.u32(B + 0x7C4)}


def take_loan(g, amount: int) -> dict:
    if amount < LOAN_MIN or amount > LOAN_MAX or amount % LOAN_STEP:
        raise EconomyError("loan amounts are %d to %d in steps of %d (the Loans window)"
                           % (LOAN_MIN, LOAN_MAX, LOAN_STEP))
    p = g.proc
    B = p.u32(city.G_BUDGET)
    before = struct.unpack("<q", p.read(B + 0x28, 8))[0]
    count = p.u32(B + 0x784)
    ok = call32(g, B, B_ISSUE_BOND, amount) & 0xFF
    after = struct.unpack("<q", p.read(B + 0x28, 8))[0]
    if not ok:
        raise EconomyError("the bank refused the loan", "the city has reached its loan limit (see loans)")
    return {"amount": after - before, "funds": after, "loans": p.u32(B + 0x784), "was": count}
