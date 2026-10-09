"""Content formats written by SiMCP: S3D models, FSH textures, generated buildings (no game needed)."""
import struct

from sc4_mcp import content, fsh, s3d


def test_textured_mesh_round_trip():
    verts = [(0, 0, 0, 0, 1), (1, 0, 0, 1, 1), (1, 1, 0, 1, 0), (0, 1, 0, 0, 0)]
    m = s3d.textured_mesh(verts, [(0, 1, 2), (0, 2, 3)], 0x12345600)
    b = s3d.write(m)
    assert b[:4] == b"3DMD" and struct.unpack_from("<I", b, 4)[0] == len(b)
    back = s3d.parse(b)
    assert back == m
    assert back.verts[0].count == 4 and s3d.stride_of(back.verts[0].fmt) == 20
    assert back.mats[0].textures[0].instance == 0x12345600


def test_chunk_sizes_are_exact():
    b = s3d.write(content.box_mesh(10, 8, 20, 0x100, 0x101))
    o, tags = 8, []
    while o < len(b):
        tag, size = b[o:o + 4], struct.unpack_from("<I", b, o + 4)[0]
        tags.append(tag)
        o += size
    assert o == len(b)
    assert tags == [b"HEAD", b"VERT", b"INDX", b"PRIM", b"MATS", b"ANIM", b"PROP", b"REGP"]


def test_box_mesh_parts_and_tiling():
    m = content.box_mesh(14, 10, 28, 0x200, 0x201)
    assert len(m.meshes) == 2 and [mt.textures[0].instance for mt in m.mats] == [0x200, 0x201]
    walls = m.verts[0]
    pts = [struct.unpack_from("<5f", walls.data, 20 * i) for i in range(walls.count)]
    assert all(0 <= u <= 1.0001 and 0 <= v <= 1.0001 for *_, u, v in pts)        # the game clamps UVs
    xs, ys, zs = zip(*[(x, y, z) for x, y, z, _, _ in pts])
    assert (min(xs), max(xs), min(zs), max(zs), min(ys), max(ys)) == (-7, 7, -5, 5, 0, 28)
    # 4 walls of 14 / 10 m in 4 m columns, 7 rows of 4 m: (4 + 3 + 4 + 3) * 7 quads, both faces
    assert len(m.indices[0].data) // 6 == 14 * 7 * 4


def test_fsh_argb_round_trip():
    rgba = bytes([10, 20, 30, 255, 200, 100, 50, 128] * 8)
    b = fsh.write_argb(4, 4, rgba)
    assert b[:4] == b"SHPI" and b[12:16] == b"G264"
    w, h, back = fsh.read_first(b)
    assert (w, h, back) == (4, 4, rgba)


def test_wall_tile_and_fixed_point():
    assert len(content.wall_tile((200, 100, 50))) == 32 * 32 * 4
    assert content._fx(16.0) == 1048576 and content._fx(0.04) == 2621


def test_growable_design(tmp_path, monkeypatch):
    """A growable design from the game's own data (skipped where SimCity_1.dat is not installed)."""
    import pytest
    from sc4_mcp import dbpf, gamedata
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = content.growable_building("Test House", "residential", 1, 9, 14, 7, lot_size=(1, 2), stage=1)
    d = dbpf.DBPF(r["file"])
    ex = {e.group: dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR}
    lot = {p.id: p.values for p in ex[content.G_LOTS].props}
    bld = {p.id: p.values for p in ex[content.G_SIMCP_BUILDINGS].props}
    fam = int(r["family"], 16)
    assert lot[content.P_LOT_FAMILY] == [fam] and bld[content.P_FAMILY] == [fam]
    rows = [v for k, v in lot.items() if content.LOT_ROW0 <= k <= 0x88EDCDFF]
    assert [r_[12] for r_ in rows if r_[0] == 0] == [fam]
    assert lot[content.P_LOT_SIZE] == [1, 2] and lot[content.P_STAGE] == [1] and lot[content.P_PURPOSE_TYPES] == [1]
    assert {0x2000, 0x2001, 0x2002, 0x2003} <= set(bld[content.P_GROUPS])            # every building style
    assert bld[content.P_NAME_KEY] == [dbpf.T_LTEXT, content.G_SIMCP_NAMES, int(r["building"], 16)]
    assert any(e.type == dbpf.T_LTEXT for e in d)


def test_advice_design(tmp_path, monkeypatch):
    import pytest
    from sc4_mcp import dbpf
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = content.advice_design("Hello", "news", "Welcome to #city#", "A <b>fine</b> day.",
                              "game.g_city_r_population > 10", "good", news_only=True)
    d = dbpf.DBPF(r["file"])
    entries = list(d)
    e = [x for x in entries if x.type == dbpf.T_LUA][0]
    assert e.group == content.G_LUA_ADVICE and e.instance >> 24 == 0xFF
    texts = {x.instance: dbpf.parse_ltext(d.read(x)) for x in entries if x.type == dbpf.T_LTEXT}
    assert sorted(texts.values()) == ["A <b>fine</b> day.", "Welcome to #city#"]
    lua = d.read(e).decode("latin-1")
    assert all("text@%08x" % i in lua for i in texts)
    assert "create_advice_fluff('%s')" % r["guid"] in lua and 'a.trigger  = "game.g_city_r_population > 10"' in lua
    assert "advice_moods.GREAT_JOB" in lua and "a.news_only = 1" in lua
    assert lua.startswith("--#-package:5C4D") and r["package"].startswith("0x5C4D")      # run as a package
    for bad in ('<a href="#link_id#game.x()">x</a>', "end]]", "<script>"):
        with pytest.raises(content.ContentError):
            content.advice_design("Bad", "news", "t", bad)
    with pytest.raises(content.ContentError):                          # triggers are read-only expressions
        content.advice_design("Bad2", "news", "t", "m", "game.deposit_funds(100)")


def test_tree_design(tmp_path, monkeypatch):
    """A tree design: flora exemplar, a model per view (rendered leaf clumps), textures, icon, names."""
    import pytest
    from PIL import Image
    from sc4_mcp import dbpf, gamedata, s3d, trees
    for shape in trees.SHAPES:                                   # every painted shape has a cut-out background
        im = trees.paint(shape, (60, 120, 50), (90, 60, 40), 7)
        assert im.size == (trees.TEX_W, trees.TEX_H) and im.getextrema()[3] == (0, 255)
    m = trees.crossed_planes(8, 12, 0x1234)
    assert len(m.verts[0].data) // 20 == 12 and m.mats[0].textures[0].wrap == (3, 3)
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = trees.design_tree("Test Birch", "broadleaf", 10, 6, (90, 150, 60), (220, 220, 210), 7, "A pale birch")
    d = dbpf.DBPF(r["file"])
    types = {e.type for e in d}
    assert {dbpf.T_EXEMPLAR, dbpf.T_S3D, dbpf.T_FSH, dbpf.T_PNG, dbpf.T_LTEXT} <= types
    ex = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR][0]
    fid = int(r["flora"], 16)
    assert ex.get(0x10) == 0x0F and ex.get(content.P_PLOP) == 7 and ex.get(trees.P_RKT5) is None
    assert ex.get(content.P_RKT1)[2] == int(r["model"], 16) and ex.get(content.P_RKT0) is None   # rendered per view
    assert sum(1 for e in d if e.type == dbpf.T_S3D) == 20
    assert ex.get(content.P_NAME_KEY) == [dbpf.T_LTEXT, content.G_SIMCP_NAMES, fid]
    assert [t["name"] for t in trees.designed()] == ["Test Birch"]
    Image.open(__import__("io").BytesIO(r["texture_png"]))
    with pytest.raises(content.ContentError):
        trees.design_tree("Test Birch", "broadleaf")              # the name is taken
    with pytest.raises(content.ContentError):
        trees.design_tree("Too Tall", "conifer", height=80)
    with pytest.raises(content.ContentError):
        trees.design_tree("Odd", "cactus")


def test_car_design(tmp_path, monkeypatch):
    """A car: every body face written once and facing out (a face written both ways round draws the car black)."""
    import pytest
    from sc4_mcp import dbpf, gamedata, vehicles
    for kind in vehicles.KINDS:
        verts, tris = vehicles.body_mesh(kind)
        assert not {(a, c, b) for a, b, c in tris} & set(tris)
        top = [t for t in tris if all(abs(verts[i][1] - vehicles.KINDS[kind][2]) < 1e-6 for i in t)]
        for a, b, c in top:                                     # the roof faces up
            p, q, r = verts[a], verts[b], verts[c]
            e1, e2 = [q[i] - p[i] for i in range(3)], [r[i] - p[i] for i in range(3)]
            assert e1[2] * e2[0] - e1[0] * e2[2] > 0
    m = vehicles.car_model("van", 0x1234)
    assert [len(i.data) // 6 for i in m.indices][1:] == [2, 2]
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = vehicles.design_car("Test Coupe", "sedan", (200, 30, 30), "rich")
    d = dbpf.DBPF(r["file"])
    ex = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR][0]
    assert ex.parent == (dbpf.T_COHORT, vehicles.G_AUTOMATA, vehicles.COHORTS["rich"])
    assert ex.get(0xAA1DD396) is None                            # the class comes from the cohort
    assert ex.get(vehicles.P_MODEL_DAY)[2] == int(r["model"], 16) and ex.get(vehicles.P_QUERY_NAME) == "Test Coupe"
    with pytest.raises(content.ContentError):
        vehicles.design_car("Odd", "tank")


def test_lot_rows_and_props(tmp_path, monkeypatch):
    """Lot rows: ground on every cell (one cell overridden), a game prop, a tree; props face out; a park design."""
    import pytest
    from sc4_mcp import dbpf, gamedata, lotdesign
    for shape in lotdesign.SHAPES:
        m = lotdesign.prop_mesh(shape, 2, 1, 3, 0x1234)
        tris = [tuple(t) for t in __import__("struct").iter_unpack("<3H", m.indices[0].data)]
        assert tris and not {(a, c, b) for a, b, c in tris} & set(tris)          # single-sided
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    rows, placed = lotdesign.rows(2, None, "grass", [{"prop": "0x29010000", "x": 16, "z": 20, "rotation": 1},
                                                    {"tree": "Maple Tree", "x": 4, "z": 4},
                                                    {"ground": "plaza", "x": 20, "z": 20}])
    grounds = [r for r in rows if r[0] == lotdesign.ROW_TEXTURE]
    assert len(grounds) == 4 and grounds[3][12] == lotdesign.GROUNDS["plaza"]
    prop = [r for r in rows if r[0] == lotdesign.ROW_PROP][0]
    assert prop[2] == 1 and prop[3] == 16 << 16 and prop[12] == 0x29010000
    assert prop[8] - prop[6] == 1 << 16                                         # the 3 x 1 bench turned
    assert len({r[11] for r in rows}) == len(rows)                               # object ids unique in the lot
    with pytest.raises(content.ContentError):
        lotdesign.rows(1, None, "grass", [{"prop": "0x29010000", "x": 40, "z": 2}])    # off the lot
    with pytest.raises(content.ContentError):
        lotdesign.rows(1, None, "grass", [{"prop": "bench", "x": 8, "z": 8}])           # several benches
    p = lotdesign.design_prop("Test Post", "cylinder", 0.5, 0.5, 3, (200, 200, 200))
    r = lotdesign.park("Test Park", 1, "lawn", [{"prop": "Test Post", "x": 8, "z": 8}])
    d = dbpf.DBPF(r["file"])
    lot = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR and e.group == content.G_LOTS][0]
    lrows = [pr.values for pr in lot.props if content.LOT_ROW0 <= pr.id <= 0x88EDCDFF]
    assert [x[0] for x in lrows] == [0, 2, 1] and lrows[2][12] == int(p["prop"], 16)
    assert r["kind"] == "park"


def test_obj_import(tmp_path):
    """An OBJ with two materials (one textured): parts, flipped v, fitted size, preview and model."""
    from PIL import Image
    from sc4_mcp import meshimport
    Image.new("RGB", (100, 60), (200, 0, 0)).save(tmp_path / "red.png")
    (tmp_path / "m.mtl").write_text("newmtl red\nmap_Kd red.png\nnewmtl blue\nKd 0 0 1\n")
    (tmp_path / "m.obj").write_text(
        "mtllib m.mtl\nv 0 0 0\nv 2 0 0\nv 2 4 0\nv 0 4 0\nv 0 0 -1\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n"
        "usemtl red\nf 1/1 2/2 3/3 4/4\nusemtl blue\nf 1 5 2\n")
    o = meshimport.load(str(tmp_path / "m.obj"), 2.0)
    assert o["size_m"] == [4.0, 8.0, 2.0] and o["faces"] == 2
    verts, tris = o["parts"]["red"]
    assert tris == [(0, 1, 2), (0, 2, 3)] and verts[0][4] == 1.0            # OBJ v = 0 -> the game's v = 1
    assert min(v[1] for v in verts) == 0.0 and abs(sum(v[0] for v in verts)) < 1e-9   # stood up, centred
    m, tex = meshimport.model(o, 0x5000)
    assert len(m.meshes) == 2 and [t[0] for t in tex] == [0x5000, 0x5001]
    assert meshimport.texture_for(o["materials"]["red"]).size == (128, 64)        # powers of two
    assert meshimport.preview(o, 64).size == (64, 64)
    import pytest
    with pytest.raises(meshimport.MeshError):
        meshimport.read_obj(str(tmp_path / "missing.obj"))


def test_civic_design(tmp_path, monkeypatch):
    """A civic design keeps the Maxis building's service and menu and takes its own numbers."""
    import pytest
    from sc4_mcp import dbpf, gamedata
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = content.civic_building("Test Station", "fire", radius_m=512, strength=250)
    d = dbpf.DBPF(r["file"])
    ex = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR and e.group == content.G_SIMCP_BUILDINGS][0]
    assert ex.get(0x08F55DC2) == 512.0 and ex.get(0x08F55DC0) == 250
    assert 0x1502 in ex.get(content.P_GROUPS)                       # still in the fire menu
    assert r["kind"] == "fire" and ex.get(content.P_PLOP) == 250    # the game's price by default
    with pytest.raises(content.ContentError):
        content.civic_building("Bad", "fire", capacity=10)         # fire has no capacity knob
    with pytest.raises(content.ContentError):
        content.civic_building("Bad", "bakery")


def test_reward_design(tmp_path, monkeypatch):
    """A reward: conditional, in the Rewards menu only, its own exclusion group, a reward advice named after it."""
    import pytest
    from sc4_mcp import dbpf, gamedata
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = content.reward_building("Test Arch", "game.g_city_r_population > 500", "Needs 500 residents")
    d = dbpf.DBPF(r["file"])
    ex = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR and e.group == content.G_SIMCP_BUILDINGS][0]
    assert ex.get(content.P_CONDITIONAL) == 1 and ex.get(content.P_GROUPS) == [content.MENU_REWARDS]
    assert ex.get(content.P_EXCLUSION) not in (0xAA9AE59F, 0xAA9EE012)          # not the game's statue / house group
    lua = [d.read(e).decode("latin-1") for e in d if e.type == dbpf.T_LUA][0]
    assert "create_reward_cityplanning('%s')" % r["building"][2:].lower() in lua
    assert "if (game.g_city_r_population > 500) then" in lua and lua.startswith("--#-package:")
    for bad in ('game.g_city_r_population > 5"', "sc4game.budget.deposit_funds(5)", "x = 1\ny = 2"):
        with pytest.raises(content.ContentError):
            content.reward_building("Bad", bad)


def test_ordinance_and_department(tmp_path, monkeypatch):
    """An ordinance exemplar (type 0x0E, costs, effects, Lua availability) and a budget department's properties."""
    import pytest
    from sc4_mcp import dbpf, orddesign
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    folder = tmp_path / "Plugins" / "140-ordinances" / "zzz_SiMCP"
    monkeypatch.setattr(orddesign, "FOLDER", str(folder))
    monkeypatch.setattr(orddesign.launch, "USER_DIR", str(tmp_path))
    with pytest.raises(content.ContentError):                       # the folder must be SiMCP's own first
        orddesign.design_ordinance("Test Rule", "A rule", -20)
    (tmp_path / "Plugins" / "140-ordinances").mkdir(parents=True)
    r = orddesign.design_ordinance("Test Rule", "A rule", -20, 50, {"crime": 0.9, "mayor_rating": 2},
                                   "game.g_city_r_population > 100")
    d = dbpf.DBPF(r["file"])
    ex = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR][0]
    assert ex.get(0x10) == 0x0E and ex.get(orddesign.P_MONTHLY) == -20 and ex.get(orddesign.P_ENACT) == -50
    assert abs(ex.get(0x28ED0380) - 0.9) < 1e-6 and ex.get(0xAA5B8407) == 2 and ex.get(orddesign.P_INCOME) == 0
    lua = [d.read(e).decode() for e in d if e.type == dbpf.T_LUA][0]
    assert ex.get(orddesign.P_LUA_AVAILABLE) in lua and "game.g_city_r_population > 100" in lua
    for bad in ({"crime": -1}, {"warp_drive": 1.0}):
        with pytest.raises(content.ContentError):
            orddesign.design_ordinance("Bad %d" % len(bad), "x", -1, 0, bad)
    props, recs, info = orddesign.department_props("Archives", "government", 40, 15)
    p = {pr.id: pr.values for pr in props}
    assert p[orddesign.P_BUDGET_PURPOSE] == [orddesign.PURPOSE_EXPENSE, orddesign.PURPOSE_INCOME]
    assert p[orddesign.P_BUDGET_COST] == [40, 15] and p[orddesign.P_DEPT_GROUP][1] == orddesign.BUDGET_GROUPS["government"]
    assert len(set(p[orddesign.P_BUDGET_LINE])) == 2 and len(recs) == 1
    with pytest.raises(content.ContentError):
        orddesign.department_props("X", "space_program", 1)


def test_brush_design(tmp_path, monkeypatch):
    """A brush design scales the base brush's radius and strength lists and is offered to terraform."""
    import pytest
    from sc4_mcp import brushdesign, dbpf, gamedata, terrain
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = brushdesign.design_brush("Wide Hill", "mountain_default", 2.0, 0.5)
    d = dbpf.DBPF(r["file"])
    ex = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR][0]
    base = dict(gamedata.exemplars(brushdesign.G_BRUSHES))[terrain.god_brushes()["mountain_default"]]
    assert ex.get(0x10) == 0x27
    assert ex.get(0x8A020202) == [v * 2 for v in base.get(0x8A020202)]
    assert ex.get(0x8A020203) == pytest.approx([v * 0.5 for v in base.get(0x8A020203)])
    assert terrain.god_table()["simcp_wide_hill"] == int(r["brush"], 16)
    with pytest.raises(content.ContentError):
        brushdesign.design_brush("Odd", "volcano_of_doom")


def test_timed_animated_and_seasonal_props(tmp_path, monkeypatch):
    """Timed props carry the game's timing properties and a two-state RKT4; animated props one block per frame;
    a seasonal tree is four date-timed props placed together."""
    import pytest
    from sc4_mcp import dbpf, gamedata, lotdesign, trees
    t = {p.id: p.values for p in lotdesign.timing_props("spin", [19, 6], {"start": [12, 1], "days": 90})}
    assert t[lotdesign.P_HOURS] == [19.0, 6.0] and t[lotdesign.P_DATE_START] == [12, 1] and t[lotdesign.P_DATE_EVERY] == [365]
    with pytest.raises(content.ContentError):
        lotdesign.timing_props(hours=[25, 3])
    rk = lotdesign.model_key_props(0x1234, True)[0]
    assert rk.id == lotdesign.P_RKT4 and rk.values[7] == 0x1234 and rk.values[8] == 1 and rk.values[15] == 0
    m = lotdesign.animate(lotdesign.prop_mesh("box", 2, 1, 3, 0x10), "spin", frames=8)
    assert len(m.verts) == 8 and [f[0] for f in m.meshes[0].frames] == list(range(8))
    for season in ("spring", "summer", "autumn", "winter"):
        assert trees.paint("broadleaf", (60, 120, 50), (90, 60, 40), 3, season).getextrema()[3] == (0, 255)
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = lotdesign.design_seasonal_tree("Test Birch", "broadleaf")
    d = dbpf.DBPF(r["file"])
    exs = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR]
    assert sorted(tuple(x.get(lotdesign.P_DATE_START)) for x in exs) == [(3, 1), (6, 1), (9, 1), (12, 1)]
    assert all(x.get(lotdesign.P_RKT4) and x.get(content.P_RKT0) is None for x in exs)
    rows, _ = lotdesign.rows(1, None, "lawn", [{"seasonal_tree": "Test Birch", "x": 8, "z": 8}])
    assert len([r_ for r_ in rows if r_[0] == lotdesign.ROW_PROP]) == 4


def test_transit_station_copies_the_lot(tmp_path, monkeypatch):
    """A station's lot is the game's, its building row SiMCP's (skipped without the game's data)."""
    import pytest
    from sc4_mcp import dbpf, gamedata
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = content.transit_station("Test Light Rail", "light_rail", 12, 10, 7)
    d = dbpf.DBPF(r["file"])
    lot = dbpf.parse_exemplar(d.read([e for e in d if e.group == content.G_LOTS][0]))
    rows = [p.values for p in lot.props if content.LOT_ROW0 <= p.id <= content.LOT_ROW0 + 0x4FF]
    assert sorted(r_[0] for r_ in rows).count(7) == 3                    # the station's light rail tiles
    assert [r_[12] for r_ in rows if r_[0] == 0] == [int(r["building"], 16)]
    assert r["lot_cells"] == [3, 1] and r["kind"] == "transit_light_rail"
    with pytest.raises(content.ContentError):
        content.transit_station("Test Nothing", "zeppelin")
