import json
import os
from dataclasses import asdict
from enum import Enum
from typing import Dict

from core.models import Anchor, SignalType
from core.platform import app_data_dir

DEFAULT_PATH = os.path.join(app_data_dir(), "calibration.json")


class JsonCalibrationRepository:
    def __init__(self, path: str = DEFAULT_PATH):
        self._path = path

    def load(self) -> Dict[str, Anchor]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
        anchors = {}
        for key, entry in data.items():
            if "uuid" in entry and "device_id" not in entry:
                entry["device_id"] = entry.pop("uuid")
            if "signal_type" in entry and isinstance(entry["signal_type"], str):
                try:
                    entry["signal_type"] = SignalType(entry["signal_type"])
                except ValueError:
                    entry["signal_type"] = SignalType.BLE
            anchors[key] = Anchor(**entry)
        return anchors

    def save(self, anchors: Dict[str, Anchor]):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(
                {k: asdict(a) for k, a in anchors.items()},
                f, indent=2, default=self._json_default,
            )
        os.replace(tmp, self._path)

    @staticmethod
    def _json_default(obj):
        if isinstance(obj, Enum):
            return obj.value
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
