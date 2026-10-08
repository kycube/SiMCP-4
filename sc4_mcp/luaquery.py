"""Read-only questions to the game's Lua state - the advisors' city figures (re/agents/lua-udi R1, LIVE_FACTS).

The app's Lua interpreter (cISC4App slot 47, cISCLua vtable 0xAC4148) runs the advisor scripts. The game keeps
about 300 city figures in it as `game.g_*` (population per zone and wealth, tile counts, coverage, funds...) and
offers read-only helpers (game.trend_value(series, months), ...). SiMCP evaluates an expression with DoString
(slot 54; status 0 = ok), reads the result as text with ToString(-1) (slot 24) and restores the stack (GetTop 6 /
SetTop 7) - on the game's main thread.

The same Lua state runs the advisors, so only expressions pass: names must be game.g_* values, the read-only
game functions below, the game's constant tables, or pure helpers (tostring, tonumber, math.*). No assignment,
statement, table constructor, method call or other function can get through.
"""

from __future__ import annotations

import re

APP_GET_LUA = 47
L_GET_TOP, L_SET_TOP, L_TO_STRING, L_DO_STRING = 6, 7, 24, 54
G_APP = 0xB43C94

READ_ONLY = {"trend_value", "trend_slope", "trend_count", "ordinance_is_on", "ordinance_is_available",
             "ordinance_name", "ordinance_description", "ordinance_enact_fee", "ordinance_repeal_fee",
             "ordinance_monthly_cost", "difficulty_level", "reward_instance_count", "get_reward_building_state",
             "is_tutorial", "building_is_group", "mysim_local_school_grade", "mysim_local_hospital_grade"}
CONSTANT_TABLES = {"game_trends", "tuning_constants", "advice_moods", "network_tool_types", "zone_types"}
HELPERS = {"tostring", "tonumber", "math.floor", "math.ceil", "math.abs", "math.max", "math.min", "math.sqrt",
           "math.mod"}
KEYWORDS = {"and", "or", "not", "true", "false", "nil"}

TOKEN = re.compile(r"""\s*(?:
    (?P<num>\d+(?:\.\d*)?(?:[eE][-+]?\d+)?|0x[0-9A-Fa-f]+|\.\d+) |
    (?P<str>"[^"\\\n]*"|'[^'\\\n]*') |
    (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*) |
    (?P<op>==|~=|<=|>=|\.\.|[-+*/%^<>(),])
)""", re.X)

ENUM_CHUNK = ("local t = {} for k, v in pairs(game) do if string.sub(k, 1, 2) == 'g_' then "
              "table.insert(t, k) end end table.sort(t) return table.concat(t, ',')")


class LuaError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint


def check(expr: str) -> None:
    """Raise LuaError unless expr is a read-only expression of the allowed names."""
    if len(expr) > 400:
        raise LuaError("the expression is too long (400 characters at most)")
    pos, prev = 0, None
    expr = expr.rstrip()
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise LuaError("not allowed here: %r" % expr[pos:pos + 20],
                           "use game.g_* values, read-only game functions, numbers, + - * / and comparisons")
        pos = m.end()
        name = m.group("name")
        if name:
            ok = (name in KEYWORDS or name in HELPERS or re.fullmatch(r"game\.g_\w+", name)
                  or (name.startswith("game.") and name[5:] in READ_ONLY)
                  or (name.split(".")[0] in CONSTANT_TABLES and name.count(".") == 1))
            if not ok:
                raise LuaError("the name %r is not allowed" % name,
                               "allowed: game.g_* values, game.%s, constant tables %s, %s" % (
                                   "/".join(sorted(READ_ONLY)[:4]) + "...", ", ".join(sorted(CONSTANT_TABLES)),
                                   ", ".join(sorted(HELPERS))))
        prev = m


def _v(g, obj: int, slot: int, *args) -> int:
    p = g.proc
    r = g.bridge.call_function(p.u32(p.u32(obj) + 4 * slot), list(args), this=obj)
    if not r.ok:
        raise LuaError("the game's Lua call failed (slot %d, status %d)" % (slot, r.status))
    return r.ret[0] & 0xFFFFFFFF


def _run(g, chunk: str) -> str | None:
    p, b = g.proc, g.bridge
    b.attach()
    lua = _v(g, p.u32(G_APP), APP_GET_LUA)
    if not lua:
        raise LuaError("the game has no Lua interpreter yet")
    s = b.scratch(0x1000)
    data = chunk.encode("latin-1") + b"\0"
    if len(data) > 0x1000:
        raise LuaError("chunk too long")
    top = _v(g, lua, L_GET_TOP)
    p.write(s, data)
    try:
        status = _v(g, lua, L_DO_STRING, s)
        if status != 0:
            raise LuaError("Lua could not evaluate it (status %d)" % status, "check the expression's syntax")
        if _v(g, lua, L_GET_TOP) <= top:
            return None
        sp = _v(g, lua, L_TO_STRING, 0xFFFFFFFF)
        return p.read(sp, 4000).split(b"\0", 1)[0].decode("latin-1") if sp else None
    finally:
        _v(g, lua, L_SET_TOP, top)


def evaluate(g, expr: str) -> dict:
    check(expr)
    text = _run(g, "return tostring(%s)" % expr)
    value: object = text
    if text is not None:
        try:
            value = int(text) if re.fullmatch(r"-?\d+", text) else float(text)
        except ValueError:
            value = {"nil": None, "true": True, "false": False}.get(text, text)
    return {"expression": expr, "value": value}


def variables(g) -> list[str]:
    """The game.g_* figures the game keeps for the advisors (SiMCP's own read-only listing chunk)."""
    text = _run(g, ENUM_CHUNK) or ""
    return [n for n in text.split(",") if n]
