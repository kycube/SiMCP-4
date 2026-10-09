"""Region housekeeping (no game needed: a fake game answers status)."""
import os

import pytest

from sc4_mcp import housekeeping


class FakeGame:
    def __init__(self, region):
        self.region = region

    def status(self):
        return {"running": True, "region": self.region}


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setattr(housekeeping.launch, "USER_DIR", str(tmp_path / "UserDir"))
    monkeypatch.setattr(housekeeping, "BACKUPS", str(tmp_path / "backups"))
    for folder, name in (("Alpha", "Alpha"), ("Beta", "Beta Coast")):
        d = tmp_path / "UserDir" / "Regions" / folder
        d.mkdir(parents=True)
        (d / "region.ini").write_text("[Regional Settings]\nName = %s\nTerrain type = 0\n" % name)
    (tmp_path / "UserDir" / "Regions" / "Alpha" / "City - Old Town.sc4").write_bytes(b"not a real city")
    return tmp_path


def test_backup_copies_everything(user):
    out = housekeeping.backup_region("Alpha")
    assert set(out["files"]) == {"region.ini", "City - Old Town.sc4"}
    assert os.path.isdir(out["backup"]) and out["backup"].startswith(str(user / "backups"))


def test_remove_city_moves_it_aside(user):
    out = housekeeping.remove_city(None, "Alpha", "Old Town")
    assert out["removed"] == "City - Old Town.sc4" and os.path.isfile(out["kept_at"])
    assert not (user / "UserDir" / "Regions" / "Alpha" / "City - Old Town.sc4").exists()
    with pytest.raises(housekeeping.HousekeepingError):
        housekeeping.remove_city(None, "Alpha", "Old Town")            # gone now


def test_remove_region_moves_the_folder(user):
    out = housekeeping.remove_region(None, "Alpha")
    assert os.path.isfile(os.path.join(out["kept_at"], "region.ini"))
    assert not (user / "UserDir" / "Regions" / "Alpha").exists()


def test_rename_keeps_other_settings(user):
    out = housekeeping.rename_region(None, "Alpha", "Alpha Bay")
    assert out == {"folder": "Alpha", "name_was": "Alpha", "name": "Alpha Bay"}
    text = (user / "UserDir" / "Regions" / "Alpha" / "region.ini").read_text()
    assert "Name = Alpha Bay" in text and "Terrain type = 0" in text
    with pytest.raises(housekeeping.HousekeepingError):
        housekeeping.rename_region(None, "Alpha", "beta coast")         # another region's name
    with pytest.raises(housekeeping.HousekeepingError):
        housekeeping.rename_region(None, "Alpha", "..\\Beta")            # not a plain name
    assert "note" in housekeeping.rename_region(FakeGame("Somewhere"), "Alpha", "Alpha Two")


def test_refuses_the_loaded_region_by_either_name(user):
    for loaded in ("Beta", "Beta Coast"):                               # folder name or display name
        with pytest.raises(housekeeping.HousekeepingError):
            housekeeping.remove_region(FakeGame(loaded), "Beta")
    assert housekeeping.remove_region(FakeGame("Alpha"), "Beta")["region"] == "Beta"


def test_only_inside_the_regions_folder(user):
    for bad in ("..", "..\\UserDir", "C:\\Windows", "Nope"):
        with pytest.raises(housekeeping.HousekeepingError):
            housekeeping.backup_region(bad)
