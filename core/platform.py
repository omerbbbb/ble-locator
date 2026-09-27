"""Platform detection and scanner factory.

The integration layer: detects what radios are available on this device
and creates the appropriate scanners. Everything above this layer is
platform-agnostic.
"""

import os
import platform as _platform
from dataclasses import dataclass, field
from typing import List


@dataclass
class PlatformCapabilities:
    os: str = ""
    ble: bool = False
    wifi: bool = False
    uwb: bool = False
    details: List[str] = field(default_factory=list)


def app_data_dir(app_name: str = "BLE Locator") -> str:
    system = _platform.system()
    if system == "Darwin":
        return os.path.expanduser(f"~/Library/Application Support/{app_name}")
    elif system == "Windows":
        return os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), app_name)
    else:
        return os.path.join(
            os.environ.get("XDG_DATA_HOME",
                           os.path.expanduser("~/.local/share")),
            app_name.lower().replace(" ", "-"))


def detect() -> PlatformCapabilities:
    system = _platform.system()
    cap = PlatformCapabilities(os=system.lower())

    if system == "Darwin":
        cap.ble = True
        cap.details.append("BLE via CoreBluetooth (bleak)")
        try:
            from CoreWLAN import CWWiFiClient
            if CWWiFiClient.sharedWiFiClient().interface() is not None:
                cap.wifi = True
                cap.details.append("WiFi via CoreWLAN")
        except Exception:
            cap.details.append("WiFi: CoreWLAN not available")

    elif system == "Windows":
        cap.ble = True
        cap.details.append("BLE via WinRT (bleak)")
        cap.wifi = True
        cap.details.append("WiFi via netsh wlan")

    elif system == "Linux":
        cap.ble = True
        cap.details.append("BLE via BlueZ (bleak)")
        cap.wifi = True
        cap.details.append("WiFi via nmcli")

    return cap


def create_scanners(cap: PlatformCapabilities = None):
    """Returns a list of ISignalScanner instances for the current platform.

    This is the only place in the codebase that knows which OS it runs on.
    Everything above (positioning service, algorithms, UI) is platform-agnostic.
    """
    if cap is None:
        cap = detect()

    scanners = []

    if cap.ble:
        from sensor.ble_scanner import BLEScannerImpl
        scanners.append(BLEScannerImpl())

    if cap.wifi:
        wifi_scanner = _create_wifi_scanner(cap.os)
        if wifi_scanner is not None:
            scanners.append(wifi_scanner)

    return scanners


def _create_wifi_scanner(os_name: str):
    """Returns the right WiFi scanner for this OS, or None if unavailable."""
    if os_name == "darwin":
        from sensor.wifi_macos import MacOSWifiScanner
        return MacOSWifiScanner()

    if os_name == "windows":
        from sensor.wifi_windows import WindowsWifiScanner
        return WindowsWifiScanner()

    if os_name == "linux":
        from sensor.wifi_linux import LinuxWifiScanner
        return LinuxWifiScanner()

    return None
