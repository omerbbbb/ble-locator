from typing import Dict, Optional

from core.interfaces import ICalibrationRepository
from core.models import Anchor


class AnchorStore:
    def __init__(self, repo: ICalibrationRepository):
        self._repo = repo
        self._anchors: Dict[str, Anchor] = repo.load()

    def all(self) -> Dict[str, Anchor]:
        return dict(self._anchors)

    def get(self, device_id: str) -> Optional[Anchor]:
        return self._anchors.get(device_id)

    def is_anchor(self, device_id: str) -> bool:
        return device_id in self._anchors

    def set(self, anchor: Anchor):
        self._anchors[anchor.device_id] = anchor
        self._repo.save(self._anchors)

    def remove(self, device_id: str):
        self._anchors.pop(device_id, None)
        self._repo.save(self._anchors)
