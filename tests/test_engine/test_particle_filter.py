import numpy as np

from core.models import AnchorMeasurement
from engine.particle_filter import ParticleFilter


def test_convergence_from_uniform():
    pf = ParticleFilter(n_particles=500)
    target = (2.0, 1.5)
    anchors = [
        AnchorMeasurement(0, 0, 2.5),
        AnchorMeasurement(4, 0, 2.5),
        AnchorMeasurement(2, 3, 1.5),
    ]
    for _ in range(30):
        pos = pf.update(anchors, 5.0, 4.0)
    assert pos is not None
    assert abs(pos[0] - target[0]) < 0.5
    assert abs(pos[1] - target[1]) < 0.5


def test_spread_decreases_with_updates():
    pf = ParticleFilter(n_particles=500)
    anchors = [
        AnchorMeasurement(0, 0, 2.0),
        AnchorMeasurement(4, 0, 2.0),
        AnchorMeasurement(2, 3, 1.0),
    ]
    pf.update(anchors, 5.0, 4.0)
    spread_early = pf.spread
    for _ in range(20):
        pf.update(anchors, 5.0, 4.0)
    assert pf.spread < spread_early


def test_reset_clears_state():
    pf = ParticleFilter()
    pf.update([AnchorMeasurement(0, 0, 1)], 5.0, 4.0)
    pf.reset()
    assert pf.snapshot() is None
    assert pf.spread == float("inf")


def test_no_anchors_returns_none():
    pf = ParticleFilter()
    assert pf.update([], 5.0, 4.0) is None


def test_meas_sigma_is_0_8():
    assert ParticleFilter.MEAS_SIGMA == 0.8
