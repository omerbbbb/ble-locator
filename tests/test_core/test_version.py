from core.version import _VERSION, get_version


def test_get_version_returns_string():
    v = get_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_version_format():
    v = get_version()
    parts = v.split(".")
    assert len(parts) == 3
    for p in parts:
        assert p.isdigit()


def test_fallback_version():
    assert _VERSION == "3.2.0"
