"""The Plugins mirror (temporary folders only)."""
import os

from sc4_mcp import launch


def test_mirror_splits_the_ordinance_folder(tmp_path):
    src = tmp_path / "player" / "Plugins"
    (src / "140-ordinances" / "pack").mkdir(parents=True)
    (src / "140-ordinances" / "pack" / "ord.dat").write_bytes(b"DBPF")
    (src / "150-mods").mkdir()
    user = tmp_path / "user"
    # the old layout: 140-ordinances mirrored as a junction to the player's folder
    (user / "Plugins").mkdir(parents=True)
    launch.ensure_junction(str(user / "Plugins" / "140-ordinances"), str(src / "140-ordinances"))
    out = launch.mirror_plugins(str(user), str(src))
    d = user / "Plugins" / "140-ordinances"
    assert d.is_dir() and not launch.is_junction(str(d))                       # now SiMCP's own folder
    inner = d / launch.PLAYER_SUBFOLDER
    assert launch.is_junction(str(inner)) and (inner / "pack" / "ord.dat").read_bytes() == b"DBPF"
    assert (src / "140-ordinances" / "pack" / "ord.dat").exists()               # the player's file untouched
    assert launch.is_junction(str(user / "Plugins" / "150-mods"))
    # SiMCP's designs beside the junction survive another mirror run
    (d / "zzz_SiMCP").mkdir()
    (d / "zzz_SiMCP" / "mine.dat").write_bytes(b"x")
    launch.mirror_plugins(str(user), str(src))
    assert (d / "zzz_SiMCP" / "mine.dat").exists() and launch.is_junction(str(inner))
    assert out["removed"] == ["140-ordinances"]
