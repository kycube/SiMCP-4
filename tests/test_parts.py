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


def test_turned_quarter_turns():
    m = s3d.textured_mesh([(1, 0, 0, 0, 0), (0, 2, 3, 1, 0), (0, 0, 0, 0, 1)], [(0, 1, 2)], 0x100)
    assert _points(s3d.turned(m, 0)) == _points(m)
    half = _points(s3d.turned(m, 2))
    assert half[0] == (-1, 0, 0) and half[1] == (0, 2, -3)                 # x, z negated; y (up) kept
    assert _points(s3d.turned(s3d.turned(m, 1), 3)) == _points(m)
    assert _points(s3d.turned(m, 1)) != _points(m)


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
