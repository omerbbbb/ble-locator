"""WiFi scanner for macOS using CoreWLAN (pyobjc).

Runs scans in a background thread. Results are cached and served from
get_active(). Does NOT interfere with the active WiFi connection.

Note: macOS requires Location Services for SSID/BSSID. Without it,
we still get RSSI, channel, and security — enough for signal quality
monitoring, just not for unique AP identification.
"""

import hashlib
import threading
import time
from typing import Dict, Optional

from core.models import SignalReading, SignalType


_HOTSPOT_KEYWORDS = {"iphone", "android", "pixel", "galaxy", "phone", "hotspot",
                     "mobile", "cellular", "samsung", "xiaomi", "oneplus"}

_ROUTER_KEYWORDS = {"router", "modem", "home", "dlink", "netgear", "asus",
                    "tp-link", "tplink", "linksys", "airport", "orbi",
                    "eero", "mesh", "fiber", "bezeq", "partner", "hot",
                    "cellcom", "012", "019"}


def _build_wifi_name(ssid: str, bssid: Optional[str], channel: int) -> str:
    """Build a human-readable name. Tries to hint at device type from SSID."""
    if not ssid:
        if bssid:
            return f"📶 Unknown ({bssid[-8:]})"
        band = "2.4GHz" if channel <= 14 else "5GHz"
        return f"📶 Unknown ({band}, ch{channel})"

    lower = ssid.lower()
    band = "2.4GHz" if channel <= 14 else "5GHz"

    if any(k in lower for k in _HOTSPOT_KEYWORDS):
        return f"📱 {ssid}"          # likely a phone hotspot
    if any(k in lower for k in _ROUTER_KEYWORDS):
        return f"🏠 {ssid}"          # likely a home router
    return f"📶 {ssid}"              # generic WiFi network


# The CLLocationManager MUST stay alive for the whole app lifetime, otherwise
# the authorization prompt is dismissed before the user can answer and the
# callback never fires. We keep it (and its delegate) in module globals.
_location_manager = None
_location_delegate = None


def _request_location_permission():
    """Ask macOS for Location Services access (needed for SSID/BSSID).

    Without this, CoreWLAN returns networks but with empty SSID/BSSID,
    so we can't identify individual APs — not even the connected one.

    Must be called on the main thread (where the Qt run loop lives).
    """
    global _location_manager, _location_delegate
    if _location_manager is not None:
        return  # already requested

    try:
        import objc
        from CoreLocation import CLLocationManager
        from Foundation import NSObject

        class _LocDelegate(NSObject):
            def locationManagerDidChangeAuthorization_(self, manager):
                pass  # status changes are picked up on next scan

        _location_delegate = _LocDelegate.alloc().init()
        _location_manager = CLLocationManager.alloc().init()
        _location_manager.setDelegate_(_location_delegate)

        status = CLLocationManager.authorizationStatus()
        if status == 0:  # NotDetermined
            _location_manager.requestWhenInUseAuthorization()
        # Starting updates nudges macOS to surface the prompt and to actually
        # grant SSID access once authorized.
        _location_manager.startUpdatingLocation()
    except Exception:
        pass


class MacOSWifiScanner:
    def __init__(self, scan_interval: float = 5.0):
        self._registry: Dict[str, SignalReading] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._scan_interval = scan_interval

    async def start(self) -> None:
        if self._running:
            return
        try:
            from CoreWLAN import CWWiFiClient
            client = CWWiFiClient.sharedWiFiClient()
            if client.interface() is None:
                return
        except Exception:
            return

        _request_location_permission()
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._scan_interval + 3)
            self._thread = None

    def get_active(self, max_age: float = 15.0) -> Dict[str, SignalReading]:
        now = time.time()
        return {
            did: r for did, r in self._registry.items()
            if now - r.timestamp <= max_age
        }

    def get_reading(self, device_id: str) -> Optional[SignalReading]:
        return self._registry.get(device_id)

    def _scan_loop(self):
        while self._running:
            self._do_scan()
            for _ in range(int(self._scan_interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _do_scan(self):
        try:
            from CoreWLAN import CWWiFiClient
            client = CWWiFiClient.sharedWiFiClient()
            iface = client.interface()
            if iface is None:
                return

            networks, error = iface.scanForNetworksWithName_error_(None, None)
            if error is not None or networks is None:
                return

            now = time.time()
            for net in networks:
                ssid = net.ssid() or ""
                bssid = (net.bssid() or "").upper()
                rssi = int(net.rssiValue())
                channel_obj = net.wlanChannel()
                channel = channel_obj.channelNumber() if channel_obj else 0
                freq = self._channel_to_freq(channel)

                security = ""
                try:
                    security = str(net.security()) if net.security() else ""
                except Exception:
                    pass

                if bssid:
                    device_id = f"wifi_{bssid.replace(':', '')}"
                    name = _build_wifi_name(ssid, bssid, channel)
                else:
                    fingerprint = f"{channel}_{security}"
                    short_hash = hashlib.md5(fingerprint.encode()).hexdigest()[:6]
                    device_id = f"wifi_ch{channel}_{short_hash}"
                    name = _build_wifi_name(ssid, None, channel)

                self._registry[device_id] = SignalReading(
                    device_id=device_id,
                    name=name,
                    rssi=rssi,
                    timestamp=now,
                    signal_type=SignalType.WIFI,
                    channel=channel,
                    frequency_mhz=freq,
                )
        except Exception:
            pass

    @staticmethod
    def _channel_to_freq(channel: int) -> float:
        if 1 <= channel <= 14:
            if channel == 14:
                return 2484.0
            return 2407.0 + channel * 5.0
        if 32 <= channel <= 177:
            return 5000.0 + channel * 5.0
        return 0.0
