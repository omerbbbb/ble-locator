# BLE Locator Antenna — iPhone app

This is a **separate, native iOS app** (Swift / SwiftUI). It is NOT the desktop
program — it lives in its own folder and is built with Xcode. Its only job:
scan Bluetooth from the iPhone's position and stream what it sees to the
BLE Locator **manager** running on a computer, using the exact same wire protocol
as the desktop "antenna mode" (`net/node_protocol.py`).

```
ble-locator/                ← the computer app (Python)
└── ios-antenna/            ← THIS — the iPhone app (Swift), fully separate
    └── BLELocatorAntenna/
        ├── BLELocatorAntennaApp.swift
        ├── ContentView.swift
        ├── Protocol.swift
        ├── BLEScanner.swift
        └── NodeClient.swift
```

## Build & install on your iPhone (≈5 minutes)

You need a Mac with **Xcode** (free from the App Store) and your Apple ID.

1. Open Xcode → **File ▸ New ▸ Project… ▸ iOS ▸ App**.
   - Product Name: `BLELocatorAntenna`
   - Interface: **SwiftUI**, Language: **Swift**
   - Save it anywhere (e.g. inside this `ios-antenna/` folder).
2. In the new project, delete the auto-created `ContentView.swift` and the
   `…App.swift`, then **drag in all five `.swift` files** from
   `ios-antenna/BLELocatorAntenna/` (check "Copy items if needed").
3. Add three Info keys (project ▸ target ▸ **Info** tab ▸ "+" each row). All
   three are required — without #2 and #3 the phone silently fails to reach the
   manager:
   - `Privacy - Bluetooth Always Usage Description`
     (`NSBluetoothAlwaysUsageDescription`)
     → `BLE Locator uses Bluetooth to sense nearby devices for positioning.`
   - `Privacy - Local Network Usage Description`
     (`NSLocalNetworkUsageDescription`)
     → `BLE Locator streams sensor data to the manager on your local network.`
   - `App Transport Security Settings` (`NSAppTransportSecurity`) → inside it add
     **`Allow Local Networking` = YES** (`NSAllowsLocalNetworking`), so the plain
     `ws://` connection to your computer is permitted.
4. Plug in your iPhone, select it as the run target, set your **Team**
   (Signing & Capabilities ▸ your Apple ID), and press **▶ Run**.
   - Free Apple ID: the app works but expires after 7 days (just re-run to renew).
   - $99/yr developer account: permanent.

## Using it

1. Make sure the iPhone and the manager computer are on the **same Wi-Fi**.
2. On the computer, launch BLE Locator → **Be the Manager**.
3. On the iPhone, open BLE Locator Antenna, set a **name** and its **x/y position**
   in the room, enter the **manager's IP** (shown in the manager's Antenna Net
   tab, or your Mac's System Settings ▸ Wi-Fi ▸ Details), and tap **Start**.
   - (mDNS auto-discovery isn't built into the phone app yet — type the IP.)
4. The iPhone appears in the manager's **Antenna Net** tab; place it and watch
   the **RTLS Targets** tab.

## Known limitations (iOS, not bugs)

- **Device matching across antennas:** iOS only gives a random per-app UUID for
  each Bluetooth device — never the MAC. So the same physical device looks like
  a *different* target to the iPhone vs the Mac, and they won't fuse
  automatically. This works reliably only for devices broadcasting a shared
  stable id (iBeacon / Eddystone / a fixed advertised name). Correlation is the
  next problem to solve.
- **Background scanning is throttled by iOS** — keep the app in the foreground
  (screen on). It's meant to sit propped up in its spot.
- The iPhone sees less device detail than a Mac (Apple hides names/manufacturer
  data), so it's a weaker antenna than a laptop — still a useful extra viewpoint.
