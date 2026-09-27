_VERSION = "3.2.0"


def get_version() -> str:
    try:
        from importlib.metadata import version
        return version("ble-locator")
    except Exception:
        return _VERSION
