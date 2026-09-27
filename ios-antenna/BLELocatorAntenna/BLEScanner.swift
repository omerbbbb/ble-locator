// BLEScanner.swift
// Wraps CoreBluetooth to collect nearby devices and their RSSI.
//
// NOTE: iOS gives a per-app random UUID for each peripheral (peripheral.identifier),
// never the MAC address. That id is stable for this app on this phone, but will
// NOT match the id the Mac assigns to the same physical device — see README.

import Foundation
import Combine
import CoreBluetooth

final class BLEScanner: NSObject, ObservableObject, CBCentralManagerDelegate {
    @Published var deviceCount: Int = 0
    @Published var bluetoothReady: Bool = false

    private var central: CBCentralManager!
    // target_id -> latest observation
    private var seen: [String: WireProtocol.Observation] = [:]
    private let lock = NSLock()
    private let maxAge: TimeInterval = 15

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    func start() {
        guard central.state == .poweredOn, !central.isScanning else { return }
        central.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
    }

    func stop() {
        if central.isScanning { central.stopScan() }
    }

    /// Fresh observations (drops anything older than maxAge).
    func currentObservations() -> [WireProtocol.Observation] {
        lock.lock(); defer { lock.unlock() }
        let now = Date().timeIntervalSince1970
        let fresh = seen.values.filter { now - $0.timestamp <= maxAge }
        DispatchQueue.main.async { self.deviceCount = fresh.count }
        return Array(fresh)
    }

    // MARK: - CBCentralManagerDelegate

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        DispatchQueue.main.async { self.bluetoothReady = (central.state == .poweredOn) }
        if central.state == .poweredOn { start() }
    }

    func centralManager(_ central: CBCentralManager,
                        didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any],
                        rssi RSSI: NSNumber) {
        let id = peripheral.identifier.uuidString
        let advName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
        let name = advName ?? peripheral.name ?? "Unknown"
        let obs = WireProtocol.Observation(
            targetId: id,
            name: name,
            rssi: RSSI.intValue,
            signalType: "ble",
            distance: nil,
            timestamp: Date().timeIntervalSince1970)
        lock.lock()
        seen[id] = obs
        lock.unlock()
    }
}
