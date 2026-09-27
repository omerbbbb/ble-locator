import json
import os

from core.models import Anchor
from storage.json_repository import JsonCalibrationRepository


def test_save_and_load(tmp_path):
    path = str(tmp_path / "cal.json")
    repo = JsonCalibrationRepository(path)
    anchors = {"A1": Anchor("A1", "Test", tx_power=-60, n=2.3, x=1.0, y=2.0)}
    repo.save(anchors)
    loaded = repo.load()
    assert "A1" in loaded
    assert loaded["A1"].tx_power == -60


def test_load_empty(tmp_path):
    path = str(tmp_path / "missing.json")
    repo = JsonCalibrationRepository(path)
    assert repo.load() == {}


def test_corrupt_json(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w") as f:
        f.write("{not json")
    repo = JsonCalibrationRepository(path)
    assert repo.load() == {}
