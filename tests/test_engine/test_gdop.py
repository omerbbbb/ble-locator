from engine.gdop import gdop, is_usable_geometry


def test_surrounding_anchors_low_gdop():
    antennas = [(0, 0), (4, 0), (4, 3), (0, 3)]
    g = gdop(antennas, (2, 1.5))
    assert g is not None
    assert g < 2.0


def test_near_collinear_higher_gdop():
    surrounding = [(0, 0), (4, 0), (4, 3), (0, 3)]
    g_surr = gdop(surrounding, (2, 1.5))
    collinear = [(0, 0), (2, 0), (4, 0)]
    g_col = gdop(collinear, (2, 1.5))
    assert g_surr is not None and g_col is not None
    assert g_col > g_surr


def test_single_anchor_returns_none():
    assert gdop([(0, 0)], (1, 1)) is None


def test_is_usable_geometry():
    antennas = [(0, 0), (4, 0), (2, 3)]
    assert is_usable_geometry(antennas, (2, 1))
