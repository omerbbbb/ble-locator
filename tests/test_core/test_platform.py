import os

import pytest

import core.platform as plat
from core.platform import PlatformCapabilities, app_data_dir, detect


def _as_os(monkeypatch, system: str):
    """Simulate a host OS so these tests are deterministic on any machine."""
    monkeypatch.setattr(plat._platform, "system", lambda: system)


def test_app_data_dir_macos(monkeypatch):
    _as_os(monkeypatch, "Darwin")
    assert app_data_dir() == os.path.expanduser("~/Library/Application Support/BLE Locator")


def test_app_data_dir_windows(monkeypatch):
    _as_os(monkeypatch, "Windows")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    assert app_data_dir() == os.path.join("C:/Users/test/AppData/Local", "BLE Locator")


def test_app_data_dir_linux(monkeypatch):
    _as_os(monkeypatch, "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")
    assert app_data_dir() == os.path.join("/tmp/xdg", "ble-locator")


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux"])
def test_app_data_dir_custom_name(monkeypatch, system):
    _as_os(monkeypatch, system)
    assert "myapp" in app_data_dir("MyApp").lower()


@pytest.mark.parametrize("system,expected_os", [
    ("Darwin", "darwin"), ("Windows", "windows"), ("Linux", "linux"),
])
def test_detect_reports_ble_on_supported_os(monkeypatch, system, expected_os):
    _as_os(monkeypatch, system)
    cap = detect()
    assert isinstance(cap, PlatformCapabilities)
    assert cap.os == expected_os
    assert cap.ble is True
    assert len(cap.details) > 0


def test_detect_unknown_os_has_no_radios(monkeypatch):
    _as_os(monkeypatch, "Plan9")
    cap = detect()
    assert cap.os == "plan9"
    assert cap.ble is False and cap.wifi is False


def test_platform_capabilities_defaults():
    cap = PlatformCapabilities()
    assert cap.os == ""
    assert cap.ble is False
    assert cap.wifi is False
    assert cap.uwb is False
    assert cap.details == []
