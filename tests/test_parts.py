"""Buildings from parts (partmodel): the builder, the game model with baked light, per-view turned models (no game
needed except where noted)."""
import struct

import pytest

from sc4_mcp import content, partmodel, s3d

HOUSE = {"materials": {"wall": {"pattern": "clapboard", "color": "#c8b89a"},
                       "roof": {"pattern": "roof_shingle", "color": "#5a4a40"}},
         "parts": [{"type": "box", "x": 4, "y": 4, "w": 8, "d": 7, "h": 3, "mat": "wall"},
                   {"type": "roof", "x": 4, "y": 4, "w": 8, "d": 7, "z": 3, "style": "gable_x", "mat": "roof",
                    "gable": "wall"}]}


def _points(m):
    out = []
    for vb in m.verts:
        st = s3d.stride_of(vb.fmt)
        out += [struct.unpack_from("<3f", vb.data, i) for i in range(0, len(vb.data), st)]
    return out


def test_turned_per_view():
    """View index r = (lot facing - camera rotation) mod 4 (north 0); the model is drawn fixed to the camera with +Z
    toward the lower left, so view r turns it (r + 2) quarter turns."""
    m = s3d.textured_mesh([(1, 0, 0, 0, 0), (0, 2, 3, 1, 0), (0, 0, 0, 0, 1)], [(0, 1, 2)], 0x100)
    assert [s3d.view_turns(r) for r in range(4)] == [2, 3, 0, 1]
    assert _points(s3d.turned(m, 2)) == _points(m)                          # facing south, camera 0: as built
    half = _points(s3d.turned(m, 0))
    assert half[0] == (-1, 0, 0) and half[1] == (0, 2, -3)                 # x, z negated; y (up) kept
    assert _points(s3d.turned(m, 3))[1] == (-3, 2, 0)                       # one turn: (x, z) -> (-z, x)
    assert _points(s3d.turned(s3d.turned(m, 1), 3)) == _points(m)                 # 3 + 1 turns


def test_parts_to_game_model():
    mesh, mats = partmodel.Builder(dict(HOUSE, lot=1)).build()
    model, textures, (w, h, d) = partmodel.to_s3d(mesh, mats, 1, 0x5000)
    m = s3d.parse(model)
    assert len(m.meshes) == len(textures) >= 4                  # one mesh per (material, light) group
    assert {mt.textures[0].instance for mt in m.mats} == {i for i, _ in textures}
    assert abs(w - 8.8) < 0.01 and abs(d - 7.8) < 0.01 and 5.8 < h < 6.1   # overhang; ridge 3 + 3.5 tan 40
    pts = _points(m)
    xs, ys, zs = zip(*pts)
    # lot centre at the origin, x mirrored (+x is west): parts x 3.6 .. 12.4 -> 4.4 .. -4.4
    assert abs(max(xs) - 4.4) < 0.01 and abs(min(xs) + 4.4) < 0.01 and min(ys) >= 0
    # every triangle faces out: the walls' outward normal points away from the house's centre
    vb, ib = m.verts[0], m.indices[0]
    assert ib.data and len(ib.data) % 6 == 0


def test_light_levels():
    up = partmodel.light_level((0, 0, 1))
    toward = partmodel.light_level(partmodel.LIGHT_SUN)
    away = partmodel.light_level(-partmodel.LIGHT_SUN)
    assert toward == partmodel.LIGHT_STEPS and away == 0 and 0 < up < toward
    assert (partmodel.light_rgb(toward) > partmodel.light_rgb(away)).all()


def test_parts_errors():
    with pytest.raises(partmodel.GameError):
        partmodel.Builder({"lot": 1, "parts": [{"type": "spire"}]}).build()
    with pytest.raises(partmodel.GameError):
        partmodel.Builder({"lot": 1, "parts": [{"type": "box", "x": 0, "y": 0, "w": 1, "d": 1, "h": 1,
                                                "mat": "nothing"}]}).build()
    with pytest.raises(partmodel.GameError):
        partmodel.Builder({"lot": 1, "parts": [{"type": "box", "x": 0}]}).build()


def test_parts_building_has_a_model_per_view(tmp_path, monkeypatch):
    """A parts building is written with RKT1 and twenty turned models (skipped without the game's data)."""
    from sc4_mcp import dbpf, gamedata
    if gamedata._main_dat() is None:
        pytest.skip("the game's data files are not installed")
    monkeypatch.setattr(content, "FOLDER", str(tmp_path))
    monkeypatch.setattr(content, "MANIFEST", str(tmp_path / "content.json"))
    r = content.model_building("Test Parts House", 0, 0, 0, lot_cells=1, parts_model=HOUSE)
    d = dbpf.DBPF(r["file"])
    models = sorted(e.instance for e in d if e.type == dbpf.T_S3D)
    assert len(models) == 20 and models[19] - models[0] == 4 * 0x100 + 3 * 0x10
    bld = [dbpf.parse_exemplar(d.read(e)) for e in d if e.type == dbpf.T_EXEMPLAR
           and e.group == content.G_SIMCP_BUILDINGS][0]
    ids = {p.id for p in bld.props}
    assert content.P_RKT1 in ids and content.P_RKT0 not in ids
    views = [_points(s3d.parse(d.read(e))) for e in d if e.type == dbpf.T_S3D and e.instance in models[:4]]
    assert views[0] != views[1] and sorted(views[0]) != sorted(views[2])
    assert r["parts"] == 2 and 5.8 < r["size_m"][2] < 6.1


def test_camera_matches_the_games():
    """BAT4Max's camera: a 16 m cell 146 px wide at the closest zoom, 45 degrees from the vertical, turned 22.5."""
    from sc4_mcp import batrender
    right, down, view, k = batrender.camera(4)
    assert abs(k - 6.985) < 0.01 and abs(16 * k * (right[0] - right[2]) - 146) < 0.01
    assert abs(view @ [-0.271, -0.707, -0.653] - 1) < 1e-3 and abs(right @ view) < 1e-9 and abs(down @ view) < 1e-9
    assert abs(batrender.camera(0)[3] - 8 / 20.905) < 1e-3 and abs(batrender.camera(0)[2][1] + 0.5) < 1e-9


def test_baked_views_project_like_the_camera():
    """Every baked view: triangles facing the camera, texture coordinates exactly the camera's projection, tiles of
    at most 256 pixels, the light in the picture (the sunny side brighter than the shaded one)."""
    import numpy as np
    from sc4_mcp import batrender, fsh
    mesh, mats = partmodel.Builder(dict(HOUSE, lot=1)).build()
    scene = batrender.Scene(mesh, mats, 1)
    models, textures = batrender.bake(scene, 0x40000000, 0x50000000)
    assert len(models) == 20 and [i for i, _ in models][:2] == [0x40000000, 0x40000010]
    tex = {i: fsh.read_first(b) for i, b in textures}
    assert all(w <= 256 and h <= 256 for w, h, _ in tex.values())
    right, down, view, k = batrender.camera(4)
    m = s3d.parse(dict(models)[0x40000400])
    for vb, mt in zip(m.verts, m.mats):
        w, h, _ = tex[mt.textures[0].instance]
        assert mt.flags == 0xAB and mt.textures[0].wrap == (3, 3)
        V = np.frombuffer(vb.data, np.float32).reshape(-1, 5)
        px, py = V[:, :3] @ right * k, V[:, :3] @ down * k
        du, dv = V[:, 3] * w - px, V[:, 4] * h - py               # constant offset per tile = an exact projection
        assert np.ptp(du) < 1e-2 and np.ptp(dv) < 1e-2
    img = np.asarray(scene.picture(4, 2), np.float32)
    lum = img[..., :3] @ [0.3, 0.59, 0.11]
    seen = img[..., 3] > 250
    assert lum[seen].max() > 150 and lum[seen].min() < 80        # lit and shaded sides


def test_facade_material():
    mesh, mats = partmodel.Builder({"lot": 1, "materials": {"front": {"facade": {
        "size_m": [6, 3], "palette": {"body": "#7f8e6c"},
        "elements": [{"type": "window", "u": 1, "v": 0.6, "w": 1, "h": 1.4},
                     {"type": "door", "u": 4, "v": 0.8, "w": 0.9, "h": 2.1}]}}},
        "parts": [{"type": "box", "x": 5, "y": 5, "w": 6, "d": 4, "h": 3, "mat": "front"}]}).build()
    assert mats[0].fit and mats[0].tex.shape[1] == 240                           # 6 m at 40 px per metre


def test_dxt_round_trip():
    import numpy as np
    from sc4_mcp import fsh
    rng = np.random.default_rng(1)
    img = np.zeros((32, 32, 4), np.uint8)
    img[..., :3] = rng.integers(60, 200, (32, 32, 3))
    img[..., 3] = 255
    img[:8, :8, 3] = 0
    for code in (fsh.CODE_DXT1, fsh.CODE_DXT3):
        b = fsh.write_dxt(img, code)
        assert b[12:16] == b"G354" and b[24] == code
        w, h, rgba = fsh.read_first(b)
        back = np.frombuffer(rgba, np.uint8).reshape(h, w, 4).astype(int)
        assert (back[:8, :8, 3] < 128).all() and (back[8:, 8:, 3] > 127).all()
        assert np.abs(back[8:, 8:, :3] - img[8:, 8:, :3]).mean() < 40          # lossy, but the same picture


def test_night_layer_for_lit_windows():
    """Lit window glass makes a night light layer: DXT3 textures at the picture's instance + 0x8000."""
    from sc4_mcp import batrender, fsh
    wall = {"facade": {"size_m": [8, 3], "night": {"lit": 1.0},
                       "elements": [{"type": "window", "u": 1, "v": 0.6, "w": 1.2, "h": 1.5},
                                    {"type": "window", "u": 5, "v": 0.6, "w": 1.2, "h": 1.5}]}}
    mesh, mats = partmodel.Builder({"lot": 1, "materials": {"wall": wall},
                                    "parts": [{"type": "box", "x": 4, "y": 4, "w": 8, "d": 8, "h": 3,
                                               "mat": "wall"}]}).build()
    assert mats[0].glow is not None
    models, textures = batrender.bake(batrender.Scene(mesh, mats, 1), 0x40000000, 0x50000000)
    day = {i for i, _ in textures if not i & batrender.NIGHT}
    night = {i: b for i, b in textures if i & batrender.NIGHT}
    assert night and {i - batrender.NIGHT for i in night} <= day
    assert all(b[24] == fsh.CODE_DXT3 for b in night.values())


def test_shell_covers_the_picture():
    """A dense model (a tree) goes on a low-poly shell: few vertices, every seen pixel still covered."""
    import numpy as np
    from sc4_mcp import batrender, vegetation
    pm = vegetation.model("conifer", 10, 5, seed=2)
    pm["lot"] = 1
    mesh, mats = partmodel.Builder(pm).build()
    scene = batrender.Scene(mesh, mats, 1, origin=(2.5, 2.5))
    mb, tx = batrender.bake_view(scene, 4, 2, 0x50000000, lod="shell")
    m = s3d.parse(mb)
    assert sum(v.count for v in m.verts) < 400
    right, down, view, k = batrender.camera(4)
    S = batrender.shell(np.asarray(mesh.arrays()[0], float).reshape(-1, 3, 3)[:, :, [0, 2, 1]] * [-1, 1, 1])
    assert len(S) == 5 * 22


def test_walker_sprites():
    """Walker atlases follow the game's layout: per direction, frames left to right wrapping at the page's edge;
    a frame table is a 32-byte header, a count and 8-byte entries; the descriptor names the atlas and tables."""
    import struct
    import numpy as np
    from sc4_mcp import walkers
    dirs = [([np.ones((30, 20 + d % 2 * 3, 4), np.float32)] * 8, (10, 28)) for d in range(8)]
    pages, tables = walkers.pack([dirs, dirs])
    assert len(tables) == 2 and all(len(t) == 8 for t in tables)
    for pg, n, x, y, w, h, ax, ay in tables[0] + tables[1]:
        X, Y = x, y
        assert x + w <= 256
        for _ in range(n):                                      # every frame lies inside its page
            if X + w > 256:
                X, Y = 0, Y + h
            assert Y + h <= 256 and pages[pg][Y:Y + h, X:X + w, 3].min() == 1.0
            X += w
    t = walkers.frame_table(tables[0])
    assert len(t) == 100 and struct.unpack_from("<4I", t) == (walkers.T_FRAMES, 8, 1, 1)
    d = struct.unpack("<12I", walkers.descriptor(0x100, 0x100, 0x101))
    assert d[0] == walkers.T_SPRITE and d[3] == 0x100 and d[9:] == (0x100, 0x101, 11)
    fsh_pages = walkers.write_pages(pages)
    assert fsh_pages[:4] == b"SHPI" and struct.unpack_from("<I", fsh_pages, 8)[0] == len(pages)
    assert [round(walkers.DIR_DEG[k]) % 360 for k in (0, 2, 4, 6)] == [90, 0, 270, 180]


def test_lamp_props_have_night_states():
    """A prop with a glowing material gets the game's lamp-post states: night (the model and a light flare at each
    lamp) and day (the model), and the lamp post's light properties."""
    from sc4_mcp import lotdesign
    model = {"lot": 1, "materials": {"pole": {"color": "#222222"}, "globe": {"color": "#eeeeee", "glow": True}},
             "parts": [{"type": "prism", "cx": 1, "cy": 1, "r": 0.1, "h": 4, "mat": "pole"},
                       {"type": "prism", "cx": 1, "cy": 1, "z": 4, "r": 0.3, "h": 0.5, "mat": "globe"}]}
    mesh, mats = partmodel.Builder(model).build()
    pts = lotdesign.lamp_points(mesh, mats, (1.0, 1.0))
    assert len(pts) == 1 and abs(pts[0][1] - 4.4) < 0.3 and abs(pts[0][0]) < 0.05 and abs(pts[0][2]) < 0.05
    props = {p.id: p.values for p in lotdesign.model_key_props(0x1234, False, views=True, lights=pts)}
    v = props[lotdesign.P_RKT4]
    entries = [v[i:i + 8] for i in range(0, len(v), 8)]
    assert [e[0] for e in entries] == [1, 1, 0]                      # night: model + flare; day: model
    assert entries[1][7] == lotdesign.LIGHT_FLARE and entries[0][7] == entries[2][7] == 0x1234
    assert props[lotdesign.P_LIGHT_STATE] == [0x49A1E995] and props[lotdesign.P_LIGHT_COUNT] == [1]


def test_seasons():
    """Seasonal vegetation: blossom and autumn mixes, a bare winter broadleaf, snow on a winter conifer."""
    from sc4_mcp import vegetation
    spring = vegetation.model("broadleaf", 10, 7, seed=2, season="spring")
    autumn = vegetation.model("broadleaf", 10, 7, seed=2, season="autumn")
    winter = vegetation.model("broadleaf", 10, 7, seed=2, season="winter")
    snowy = vegetation.model("conifer", 10, 5, seed=2, season="winter")
    assert len([k for k in spring["materials"] if k.startswith("leaves")]) == 3
    assert len([k for k in autumn["materials"] if k.startswith("leaves")]) == 4
    assert "twigs" in winter["materials"] and not any(k.startswith("leaves") for k in winter["materials"])
    assert snowy["materials"]["needles"]["snow"] > 0
    mesh, mats = partmodel.Builder(dict(snowy, lot=1)).build()
    assert any(getattr(m, "snow", 0) > 0 for m in mats)
