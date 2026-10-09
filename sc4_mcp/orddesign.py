"""New ordinances and budget departments, through the DLLs installed in this setup (null-45's
SC4CustomOrdinanceHost and CustomBudgetDepartments; their documentation is in their source repositories).

An ordinance is an exemplar of type 0x0E (any group, a unique instance): name / description (LTEXT keys 0x6A416B21 /
0xCA416B2A), enactment and retraction income (0x28EBBC37 / 0x28EBBC38, negative = a cost), monthly constant income
(0x28EBBC39, negative = an expense; 0x28EBBC3C true for income ordinances), effects (crime, mayor rating, pollution,
demand... Maxis' ordinance properties) and an availability condition - here a Lua function the DLL calls
(0x6B23D830), defined by a package script beside it from the agent's read-only expression. The host reads
ordinances only from Plugins\\140-ordinances (and sub-folders), so SiMCP's mirror keeps that folder its own (the
player's folder is a junction inside it) and writes designs to 140-ordinances\\zzz_SiMCP. The game stores an
ordinance's properties in a city's save: once a city is saved with it, later changes to the design are ignored
there.

A budget department is a set of properties on a building exemplar (the game's Budget Item properties plus the
DLL's 0x90222B81 budget group and 0x4252085F name key): every building of that design adds its line item.
"""

from __future__ import annotations

import os
import random
import re
import time

from . import content, dbpf, launch

FOLDER = os.path.join(launch.USER_DIR, "Plugins", "140-ordinances", "zzz_SiMCP")
T_ORDINANCE = 0x0E
G_SIMCP_ORDINANCES = 0x5C4D0F10
P_NAME_KEY, P_DESC_KEY, P_NAME_STR, P_DESC_STR = 0x6A416B21, 0xCA416B2A, 0x28EBBC32, 0x28EBBC34
P_ENACT, P_RETRACT, P_MONTHLY, P_INCOME = 0x28EBBC37, 0x28EBBC38, 0x28EBBC39, 0x28EBBC3C
P_LUA_AVAILABLE = 0x6B23D830
EFFECTS = {   # name -> (property, type, what)
    "crime": (0x28ED0380, "f", "crime multiplier (0.9 = 10 % less)"),
    "mayor_rating": (0xAA5B8407, "i", "added to the mayor rating everywhere"),
    "air_pollution": (0x08F79B8E, "f", "air pollution multiplier"),
    "water_pollution": (0xE8F79C8B, "f", "water pollution multiplier"),
    "garbage": (0xE8F79C90, "f", "garbage multiplier"),
    "flammability": (0x28F42AA0, "f", "flammability multiplier"),
    "water_use": (0xA8F4EB0C, "f", "water use multiplier"),
    "power_use": (0x0911E117, "f", "power consumption reduction factor"),
    "traffic_air_pollution": (0x8A67E378, "f", "traffic air pollution multiplier"),
    "school_eq_boost": (0xA92D9D7A, "f", "% of every EQ value (100 = unchanged)"),
    "health_hq_boost": (0xE91B3AEE, "f", "% of every HQ value (100 = unchanged)"),
    "demand_r_low": (0x2A651010, "f", "R$ demand factor"), "demand_r_medium": (0x2A651020, "f", "R$$ demand"),
    "demand_r_high": (0x2A651030, "f", "R$$$ demand"), "demand_cs_low": (0x2A653110, "f", "Cs$ demand"),
    "demand_cs_medium": (0x2A653120, "f", "Cs$$ demand"), "demand_cs_high": (0x2A653130, "f", "Cs$$$ demand"),
    "demand_co_medium": (0x2A653320, "f", "Co$$ demand"), "demand_co_high": (0x2A653330, "f", "Co$$$ demand"),
    "demand_i_resource": (0x2A654100, "f", "IR demand"), "demand_i_dirty": (0x2A654200, "f", "ID demand"),
    "demand_i_manufacturing": (0x2A654300, "f", "IM demand"), "demand_i_high_tech": (0x2A654400, "f", "IHT demand"),
}
BUDGET_GROUPS = {"business_deals": 0x0A5A72D1, "city_beautification": 0x6A357B96, "government": 0xEA597195,
                 "health_education": 0x6A357B7F, "public_safety": 0x4A357B40, "transportation": 0xAA369059,
                 "utilities": 0x4A357EAF}
PURPOSE_EXPENSE, PURPOSE_INCOME = 0x87BD3990, 0x46261226
P_BUDGET_DEPT, P_BUDGET_LINE, P_BUDGET_PURPOSE, P_BUDGET_COST = 0xEA54D283, 0xEA54D284, 0xEA54D285, 0xEA54D286
P_DEPT_GROUP, P_DEPT_NAME = 0x90222B81, 0x4252085F


class OrdinanceError(content.ContentError):
    pass


def _own_folder() -> None:
    """Plugins\\140-ordinances must be SiMCP's own real folder (the mirror makes it so at game_launch) - never the
    junction into the player's Plugins folder, which SiMCP does not write."""
    parent = os.path.dirname(FOLDER)
    if not os.path.isdir(parent) or launch.is_junction(parent) or os.path.islink(parent):
        raise OrdinanceError("SiMCP's Plugins\\140-ordinances is not its own folder yet",
                             "game_launch once (it re-mirrors the Plugins folder), then design the ordinance")
    real_root = os.path.normcase(os.path.realpath(os.path.join(launch.USER_DIR, "Plugins")))
    if not os.path.normcase(os.path.realpath(parent)).startswith(real_root + os.sep):
        raise OrdinanceError("Plugins\\140-ordinances leads outside SiMCP's user folder")


def _lua_condition(condition: str) -> str:
    from . import luaquery
    if any(c in condition for c in "\r\n\"\\") or "]]" in condition:
        raise OrdinanceError("the condition is one line without quotes, backslashes or ']]'")
    try:
        luaquery.check(condition)
    except luaquery.LuaError as e:
        raise OrdinanceError("condition: %s" % e, getattr(e, "hint", ""))
    return condition


def design_ordinance(name: str, description: str, monthly: int = -50, enact_cost: int = 0,
                     effects: dict | None = None, condition: str = "") -> dict:
    """Write a new ordinance (see the module notes). monthly: income if positive, an expense if negative."""
    content._check_name(name)
    content._check_tokens(description, "description")
    if not description or len(description) > 600:
        raise OrdinanceError("the description is 1-600 characters")
    if not -1_000_000 <= monthly <= 1_000_000 or not 0 <= enact_cost <= 1_000_000:
        raise OrdinanceError("monthly is -1,000,000..1,000,000 and enact_cost 0..1,000,000")
    effects = effects or {}
    for k, v in effects.items():
        if k not in EFFECTS:
            raise OrdinanceError("unknown effect %r" % k, "effects: " + ", ".join(EFFECTS))
        kind = EFFECTS[k][1]
        lim = 100 if k == "mayor_rating" else (200.0 if k.endswith("_boost") else 10.0)
        if not -lim <= float(v) <= lim or (kind == "f" and float(v) < 0):
            raise OrdinanceError("%s is out of range" % k)
    ord_iid, name_iid, desc_iid = content._new_ids(set(), 3)
    props = [dbpf.Property(0x10, dbpf.PT_UINT32, [T_ORDINANCE]),
             dbpf.Property(content.P_NAME, dbpf.PT_STRING, "Ordinance - SiMCP " + content._slug(name)),
             dbpf.Property(P_NAME_STR, dbpf.PT_STRING, name), dbpf.Property(P_DESC_STR, dbpf.PT_STRING, description),
             dbpf.Property(P_NAME_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, G_SIMCP_ORDINANCES, name_iid], True),
             dbpf.Property(P_DESC_KEY, dbpf.PT_UINT32, [dbpf.T_LTEXT, G_SIMCP_ORDINANCES, desc_iid], True),
             dbpf.Property(P_ENACT, dbpf.PT_SINT64, [-int(enact_cost)]),
             dbpf.Property(P_RETRACT, dbpf.PT_SINT64, [0]),
             dbpf.Property(P_MONTHLY, dbpf.PT_SINT64, [int(monthly)]),
             dbpf.Property(P_INCOME, dbpf.PT_BOOL, [1 if monthly > 0 else 0])]
    for k, v in effects.items():
        pid, kind, _ = EFFECTS[k]
        props.append(dbpf.Property(pid, dbpf.PT_FLOAT32 if kind == "f" else dbpf.PT_SINT32,
                                   [float(v) if kind == "f" else int(v)]))
    records = [(dbpf.T_EXEMPLAR, G_SIMCP_ORDINANCES, ord_iid, dbpf.build_exemplar(props)),
               (dbpf.T_LTEXT, G_SIMCP_ORDINANCES, name_iid, dbpf.build_ltext(name)),
               (dbpf.T_LTEXT, G_SIMCP_ORDINANCES, desc_iid, dbpf.build_ltext(description))]
    entry_extra = {}
    if condition:
        condition = _lua_condition(condition)
        fn = "simcp_ordinance_%08x_available" % ord_iid
        props.append(dbpf.Property(P_LUA_AVAILABLE, dbpf.PT_STRING, fn))
        records[0] = (dbpf.T_EXEMPLAR, G_SIMCP_ORDINANCES, ord_iid, dbpf.build_exemplar(props))
        package = 0x5C4E0000 | random.getrandbits(16)
        lua = "\n".join(["--#-package:%08X# -- package signature" % package,
                         "-- SiMCP ordinance design: %s" % re.sub(r"[\r\n]", " ", name),
                         "function %s()" % fn, "   return (%s) and true or false" % condition, "end", ""])
        records.append((dbpf.T_LUA, content.G_LUA_ADVICE, 0xFE000000 | random.getrandbits(24),
                        lua.encode("latin-1", "replace")))
        entry_extra = {"condition": condition, "lua_function": fn}
    _own_folder()
    os.makedirs(FOLDER, exist_ok=True)
    path = os.path.join(FOLDER, "SiMCP_ordinance_%s.dat" % content._slug(name))
    if os.path.exists(path):
        raise OrdinanceError("another design already uses the file %s" % os.path.basename(path))
    dbpf.write_dbpf(path, records)
    entry = {"name": name, "kind": "ordinance", "file": path, "ordinance": "0x%08X" % ord_iid, "monthly": monthly,
             "enact_cost": enact_cost, "effects": effects, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
             **entry_extra}
    items = content._manifest()
    items.append(entry)
    content._save_manifest(items)
    return dict(entry, note="the game loads plugins at start-up: quit_game and game_launch; it is then in "
                            "ordinances() (once available) and set_ordinance enacts it")


def department_props(name: str, group: str, monthly_cost: int = 0, monthly_income: int = 0):
    """The building properties of a custom budget department with an expense and / or an income line, and the
    LTEXT record of its name: ([Property], [record])."""
    if group not in BUDGET_GROUPS:
        raise OrdinanceError("group is %s" % ", ".join(BUDGET_GROUPS))
    if monthly_cost < 0 or monthly_income < 0 or not (monthly_cost or monthly_income):
        raise OrdinanceError("give a monthly_cost and / or a monthly_income (0 or more, not both 0)")
    if not name or len(name) > 60:
        raise OrdinanceError("the department name is 1-60 characters")
    dept, name_iid, line_cost, line_income = content._new_ids(set(), 4)
    depts, lines, purposes, costs, algos = [], [], [], [], []
    for line, purpose, amount in ((line_cost, PURPOSE_EXPENSE, monthly_cost), (line_income, PURPOSE_INCOME, monthly_income)):
        if amount:
            depts.append(dept); lines.append(line); purposes.append(purpose); costs.append(int(amount))
            algos += [line, 0]
    props = [dbpf.Property(P_BUDGET_DEPT, dbpf.PT_UINT32, depts, True),
             dbpf.Property(P_BUDGET_LINE, dbpf.PT_UINT32, lines, True),
             dbpf.Property(P_BUDGET_PURPOSE, dbpf.PT_UINT32, purposes, True),
             dbpf.Property(P_BUDGET_COST, dbpf.PT_SINT64, costs, True),
             dbpf.Property(P_DEPT_GROUP, dbpf.PT_UINT32, [dept, BUDGET_GROUPS[group]], True),
             dbpf.Property(P_DEPT_NAME, dbpf.PT_UINT32, [dept, content.G_SIMCP_NAMES, name_iid], True),
             dbpf.Property(0x9EE1240F, dbpf.PT_UINT32, algos, True)]
    record = (dbpf.T_LTEXT, content.G_SIMCP_NAMES, name_iid, dbpf.build_ltext(name))
    return props, [record], {"department": "0x%08X" % dept, "department_name": name, "group": group,
                             "monthly_cost": monthly_cost, "monthly_income": monthly_income}
