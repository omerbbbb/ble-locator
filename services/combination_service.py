"""Combination comparison — which set of antennas locates a target best?

For a chosen target, take the cleaned fixes from the available antennas and
compute the target's position using EVERY antenna subset of size ≥2. Each
combination is scored by predicted accuracy (GDOP, then uncertainty), so the
user can see which antennas to trust and how much each one helps.

Pure logic on top of MultiReceiverService — no UI, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from core.models import TargetEstimate
from services.multireceiver_service import MultiReceiverService


@dataclass
class CombinationResult:
    node_ids: Tuple[str, ...]
    estimate: TargetEstimate

    @property
    def gdop(self) -> Optional[float]:
        return self.estimate.gdop

    @property
    def uncertainty(self) -> Optional[float]:
        return self.estimate.uncertainty_radius


def _score(est: TargetEstimate) -> float:
    """Lower is better. GDOP dominates; uncertainty breaks ties.

    Missing GDOP (degenerate geometry) sorts to the bottom.
    """
    g = est.gdop if est.gdop is not None else 1e6
    u = est.uncertainty_radius if est.uncertainty_radius is not None else 1e3
    return g * 10.0 + u


class CombinationService:
    def __init__(self, service: MultiReceiverService):
        self._service = service

    def list_targets(self, now: float = None) -> List[Tuple[str, str]]:
        """[(target_id, name)] for targets currently seen by ≥2 antennas."""
        per_target = self._service.collect_target_fixes(now)
        out = []
        for tid, entry in per_target.items():
            if len(entry["fixes"]) >= 2:
                out.append((tid, entry["name"]))
        return out

    def compare(
        self,
        target_id: str,
        room_w: float,
        room_h: float,
        now: float = None,
        max_combos: int = 64,
    ) -> List[CombinationResult]:
        """Rank antenna subsets (size ≥2) for one target, best first."""
        per_target = self._service.collect_target_fixes(now)
        entry = per_target.get(target_id)
        if entry is None:
            return []

        fixes = entry["fixes"]            # (node_id, x, y, dist, weight)
        if len(fixes) < 2:
            return []

        results: List[CombinationResult] = []
        n = len(fixes)
        for k in range(2, n + 1):
            for subset in combinations(fixes, k):
                est = MultiReceiverService.estimate_from_fixes(
                    list(subset), entry["name"], target_id,
                    entry["signal_type"], room_w, room_h)
                if est is None:
                    continue
                node_ids = tuple(f[0] for f in subset)
                results.append(CombinationResult(node_ids=node_ids, estimate=est))

        results.sort(key=lambda r: _score(r.estimate))
        return results[:max_combos]
