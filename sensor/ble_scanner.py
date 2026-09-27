import time
from typing import Dict, Optional

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from core.models import SignalReading, SignalType

MANUFACTURER_NAMES = {
    0x004C: "Apple",
    0x0075: "Samsung",
    0x0006: "Microsoft",
    0x00E0: "Google",
    0x0059: "Nordic Semi",
    0x000F: "Broadcom",
    0x0131: "Xiaomi",
    0x038F: "Garmin",
    0x0157: "Huawei",
    0x0310: "Fitbit",
    0x02FF: "Tile",
    0x00D2: "Sony",
    0x0087: "LG",
    0x001D: "Qualcomm",
    0x0171: "Amazon",
    0x0499: "Ruuvi",
    0x0116: "Logitech",
    0x0078: "Nike",
    0x02E5: "Espressif",
    0x0000: "Ericsson",
    0x000A: "Qualcomm CSR",
    0x0046: "MediaTek",
    0x004F: "Plantronics",
    0x0154: "Google Nest",
    0x02A4: "OnePlus",
    0x011B: "JBL",
    0x03C1: "Bose",
}


# AirPods / Beats model IDs from the 0x07 Proximity-Pairing message.
# These ARE reliably broadcast, so we can name the exact model.
_AIRPODS_MODELS = {
    0x0220: "AirPods",
    0x0F20: "AirPods (3rd gen)",
    0x0E20: "AirPods Pro",
    0x1420: "AirPods Pro 2",
    0x2420: "AirPods Pro 2 (USB-C)",
    0x1920: "AirPods (4th gen)",
    0x0A20: "AirPods Max",
    0x1F20: "AirPods Max (USB-C)",
    0x0320: "Powerbeats3",
    0x0520: "BeatsX",
    0x0620: "Beats Solo3",
    0x0920: "Beats Studio3",
    0x0B20: "Beats Flex",
    0x0C20: "Beats Solo Pro",
    0x1020: "Beats Studio Buds",
    0x1120: "Powerbeats Pro",
    0x1720: "Beats Fit Pro",
}

# Apple continuity message types (the TLV "type" byte). We can identify the
# PROTOCOL in use, which hints at activity, even when the model is hidden.
_APPLE_CONTINUITY_TYPES = {
    0x05: "Apple (AirDrop)",
    0x09: "Apple (AirPlay)",
    0x0C: "Apple (Handoff)",
    0x0D: "Apple (Hotspot target)",
    0x0E: "Apple (Hotspot source)",
    0x0F: "Apple (Nearby Action)",
    0x10: "Apple device",          # Nearby Info — almost every iPhone/iPad/Mac
}


def _resolve_apple_type(data: bytes) -> str:
    """Identify an Apple device from its continuity advertisement.

    IMPORTANT: passive BLE cannot reveal iPhone vs iPad vs Mac — Apple
    encrypts that for privacy. What we CAN read reliably:
      - AirPods / Beats exact model (0x07 proximity pairing)
      - Find My / AirTag (0x12)
      - which continuity protocol is active (hints at the device)
    """
    if len(data) < 2:
        return "Apple device"

    best = "Apple device"
    i = 0
    while i < len(data) - 1:
        msg_type = data[i]
        msg_len = data[i + 1]
        payload = data[i + 2:i + 2 + msg_len]

        # AirPods / Beats — exact model from the 2-byte model id
        if msg_type == 0x07 and len(payload) >= 3:
            model = (payload[1] << 8) | payload[2]
            return _AIRPODS_MODELS.get(model, "AirPods / Beats")

        # Find My (AirTag and Find My-enabled accessories)
        if msg_type == 0x12:
            return "AirTag / Find My"

        # otherwise remember the most specific protocol seen
        label = _APPLE_CONTINUITY_TYPES.get(msg_type)
        if label and best == "Apple device":
            best = label

        if msg_len == 0:
            break
        i += 2 + msg_len

    return best


def _resolve_manufacturer(adv: AdvertisementData) -> str:
    if not adv.manufacturer_data:
        return ""
    for company_id in adv.manufacturer_data:
        name = MANUFACTURER_NAMES.get(company_id)
        if name:
            return name
    return ""


def _resolve_name(device: BLEDevice, adv: AdvertisementData,
                  prev: Optional[SignalReading]) -> str:
    name = adv.local_name or device.name
    if name:
        return name
    if prev and prev.name and prev.name != "Unknown":
        return prev.name

    if adv.manufacturer_data and 0x004C in adv.manufacturer_data:
        return _resolve_apple_type(adv.manufacturer_data[0x004C])

    mfr = _resolve_manufacturer(adv)
    if mfr:
        return f"{mfr} device"
    return "Unknown"


class BLEScannerImpl:
    # Drop devices unseen for this long so the registry can't grow unbounded
    # as BLE address randomisation churns through new identifiers.
    EVICT_AGE = 300.0

    def __init__(self):
        self._registry: Dict[str, SignalReading] = {}
        self._scanner: Optional[BleakScanner] = None
        self._running = False

    def _detection_callback(self, device: BLEDevice, adv: AdvertisementData):
        device_id = device.address
        rssi = adv.rssi if adv.rssi is not None else -100
        prev = self._registry.get(device_id)

        name = _resolve_name(device, adv, prev)
        manufacturer = _resolve_manufacturer(adv)
        service_uuids = tuple(adv.service_uuids) if adv.service_uuids else ()
        tx_power_adv = adv.tx_power

        self._registry[device_id] = SignalReading(
            device_id=device_id,
            name=name,
            rssi=rssi,
            timestamp=time.time(),
            signal_type=SignalType.BLE,
            manufacturer=manufacturer,
            service_uuids=service_uuids,
            tx_power_adv=tx_power_adv,
        )

    async def start(self):
        if self._running:
            return
        self._running = True
        self._scanner = BleakScanner(detection_callback=self._detection_callback)
        await self._scanner.start()

    async def stop(self):
        self._running = False
        if self._scanner is not None:
            try:
                await self._scanner.stop()
            finally:
                self._scanner = None

    def get_active(self, max_age: float = 15.0) -> Dict[str, SignalReading]:
        now = time.time()
        # Evict long-dead entries so the registry stays bounded.
        stale = [did for did, r in self._registry.items()
                 if now - r.timestamp > self.EVICT_AGE]
        for did in stale:
            del self._registry[did]
        return {
            did: r for did, r in self._registry.items()
            if now - r.timestamp <= max_age
        }

    def get_reading(self, device_id: str) -> Optional[SignalReading]:
        return self._registry.get(device_id)
