"""WiFi scanner for Windows using netsh — no extra dependencies required."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Dict, Optional

from core.models import SignalReading, SignalType


class WindowsWifiScanner:
    def __init__(self, scan_interval: float = 5.0):
        self._registry: Dict[str, SignalReading] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._scan_interval = scan_interval

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._scan_interval + 3)
            self._thread = None

    def get_active(self, max_age: float = 15.0) -> Dict[str, SignalReading]:
        now = time.time()
        return {k: v for k, v in self._registry.items()
                if now - v.timestamp <= max_age}

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
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                encoding="utf-8", errors="ignore",
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception:
            return

        now = time.time()
        # netsh outputs blocks separated by blank lines, one block per network
        for block in re.split(r"\n\s*\n", out):
            ssid  = self._field(block, "SSID")
            bssid = self._field(block, "BSSID 1")
            sig   = self._field(block, "Signal")
            ch    = self._field(block, "Channel")

            if not bssid:
                continue

            bssid = bssid.upper()
            rssi  = self._quality_to_rssi(sig)
            channel = int(ch) if ch and ch.isdigit() else 0

            device_id = f"wifi_{bssid.replace(':', '')}"
            name = ssid if ssid else f"WiFi ({bssid[-8:]})"

            self._registry[device_id] = SignalReading(
                device_id=device_id,
                name=name,
                rssi=rssi,
                timestamp=now,
                signal_type=SignalType.WIFI,
                channel=channel,
                frequency_mhz=self._channel_to_freq(channel),
            )

    @staticmethod
    def _field(block: str, key: str) -> str:
        m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", block, re.MULTILINE)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _quality_to_rssi(quality_str: str) -> int:
        """Windows reports signal as 0-100%. Convert to approximate dBm."""
        try:
            q = int(quality_str.replace("%", "").strip())
            return (q // 2) - 100   # 100% → -50 dBm,  0% → -100 dBm
        except (ValueError, AttributeError):
            return -90

    @staticmethod
    def _channel_to_freq(channel: int) -> float:
        if 1 <= channel <= 14:
            return 2484.0 if channel == 14 else 2407.0 + channel * 5.0
        if 32 <= channel <= 177:
            return 5000.0 + channel * 5.0
        return 0.0
