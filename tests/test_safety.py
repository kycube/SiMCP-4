"""The gates that keep tools inside what they promise: the cheat allow-list and the read-only Lua check."""

import pytest

from sc4_mcp import cheats, luaquery


@pytest.mark.parametrize("name,arg,line", [
    ("WeaknessPays", "", "weaknesspays"),
    ("whattimeizit", "7", "whattimeizit 7"),
    ("hellomynameis", "Ada", "hellomynameis Ada"),
    ("stopwatch", "magnify 10", "stopwatch magnify 10"),
    ("gp", "off", "gp off"),
])
def test_cheat_lines(name, arg, line):
    assert cheats._line(name, arg) == line


@pytest.mark.parametrize("name,arg", [
    ("createexception", ""), ("fps", "0"), ("moolah", "1000000"), ("recorder", ""), ("nosuch", ""),
    ("weaknesspays", "extra"), ("whattimeizit", "25"), ("hellomynameis", "two words"),
    ("hellomynameis", "x;ExecuteScript"), ("stopwatch", "magnify 0"), ("casper", "maybe"),
])
def test_cheats_refused(name, arg):
    with pytest.raises(cheats.CheatError):
        cheats._line(name, arg)


@pytest.mark.parametrize("expr", [
    "game.g_population", "game.g_road_tile_count + game.g_street_tile_count",
    "game.trend_value(game_trends.G_FUNDS, 12) * 1000", "math.max(game.g_funds, 0) > 5000 and true",
    "tostring(game.g_city_r_population) .. 'x'", "game.difficulty_level()",
])
def test_lua_allowed(expr):
    luaquery.check(expr)


@pytest.mark.parametrize("expr", [
    "game.g_funds = 5", "os.execute('x')", "loadstring('x')()", "dofile('a')", "game.ordinance_set_on(1)",
    "{1}", "game.g_x; y", "game.g_x[1]", "game:trend_value(1)", "function() end", "local x",
    "game.deposit_funds(5)", "sc4game.budget.deposit_funds(1)", "_G", "game", "string.rep('a', 9)",
    "game_trends.G_FUNDS.x",
])
def test_lua_refused(expr):
    with pytest.raises(luaquery.LuaError):
        luaquery.check(expr)
