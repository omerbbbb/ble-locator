"""WiFi scanner for Linux using nmcli — no extra dependencies required."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Dict, Optional

from core.models import SignalReading, SignalType


class LinuxWifiScanner:
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
                ["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,CHAN", "dev", "wifi", "list"],
                encoding="utf-8", errors="ignore",
            )
        except Exception:
            return

        now = time.time()
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            ssid, bssid, signal, chan = parts[0], parts[1], parts[2], parts[3]
            bssid = bssid.upper()
            if not bssid or bssid == "--":
                continue

            try:
                rssi = int(signal) // 2 - 100   # nmcli gives 0-100 quality
            except ValueError:
                rssi = -90
            try:
                channel = int(chan)
            except ValueError:
                channel = 0

            device_id = f"wifi_{bssid.replace(':', '')}"
            name = ssid if ssid and ssid != "--" else f"WiFi ({bssid[-8:]})"
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
    def _channel_to_freq(channel: int) -> float:
        if 1 <= channel <= 14:
            return 2484.0 if channel == 14 else 2407.0 + channel * 5.0
        if 32 <= channel <= 177:
            return 5000.0 + channel * 5.0
        return 0.0
