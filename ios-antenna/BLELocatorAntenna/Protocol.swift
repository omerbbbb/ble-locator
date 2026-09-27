// Protocol.swift
// Wire format shared with the desktop manager (see net/node_protocol.py).
// Plain JSON over a WebSocket. Keep these keys in sync with the Python side.

import Foundation

enum WireProtocol {
    static let version = 1

    // One observation of one nearby device.
    struct Observation {
        let targetId: String
        let name: String
        let rssi: Int
        let signalType: String      // "ble"
        let distance: Double?       // nil for RSSI-only (always nil on iOS BLE)
        let timestamp: Double
    }

    // hello — announce this antenna + its fixed position.
    static func encodeHello(nodeId: String, name: String,
                            x: Double, y: Double,
                            txPower: Double = -59, n: Double = 2.5) -> String {
        let dict: [String: Any] = [
            "v": version, "type": "hello",
            "node_id": nodeId, "name": name,
            "x": x, "y": y,
            "tx_power": txPower, "n": n,
            "platform": "iOS", "is_local": false,
        ]
        return jsonString(dict)
    }

    // report — one scan cycle of observations.
    static func encodeReport(nodeId: String, observations: [Observation]) -> String {
        let obs: [[String: Any]] = observations.map { o in
            [
                "target_id": o.targetId,
                "name": o.name,
                "rssi": o.rssi,
                "signal_type": o.signalType,
                "distance": o.distance as Any,   // NSNull-safe below
                "timestamp": o.timestamp,
            ]
        }
        let dict: [String: Any] = [
            "v": version, "type": "report",
            "node_id": nodeId,
            "timestamp": Date().timeIntervalSince1970,
            "observations": obs,
        ]
        return jsonString(dict)
    }

    private static func jsonString(_ dict: [String: Any]) -> String {
        // Replace Optional.none distances with NSNull so JSON encodes `null`.
        let cleaned = sanitize(dict)
        guard let data = try? JSONSerialization.data(withJSONObject: cleaned),
              let s = String(data: data, encoding: .utf8) else { return "{}" }
        return s
    }

    private static func sanitize(_ value: Any) -> Any {
        if let dict = value as? [String: Any] {
            var out: [String: Any] = [:]
            for (k, v) in dict { out[k] = sanitize(v) }
            return out
        }
        if let arr = value as? [Any] { return arr.map { sanitize($0) } }
        if value is NSNull { return value }
        // Optional.none arrives as this; turn any nil into NSNull
        let mirror = Mirror(reflecting: value)
        if mirror.displayStyle == .optional && mirror.children.isEmpty {
            return NSNull()
        }
        if mirror.displayStyle == .optional, let child = mirror.children.first {
            return sanitize(child.value)
        }
        return value
    }
}
