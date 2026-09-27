// NodeClient.swift
// Streams NodeReports to the manager over a WebSocket (URLSessionWebSocketTask).
// Sends a `hello`, then a `report` every interval. Auto-reconnects on failure.

import Foundation
import Combine

@MainActor
final class NodeClient: ObservableObject {
    @Published var status: String = "Idle"
    @Published var connected: Bool = false
    @Published var managerConfirmed: Bool = false
    @Published var sendingCount: Int = 0

    private var task: URLSessionWebSocketTask?
    private var session: URLSession = .shared
    private var running = false
    private var timer: Timer?

    private let nodeId: String
    private let nodeName: String
    private let x: Double
    private let y: Double
    private let scanner: BLEScanner
    private let host: String
    private let port: Int
    private let interval: TimeInterval

    init(nodeId: String, nodeName: String, x: Double, y: Double,
         host: String, port: Int, scanner: BLEScanner,
         interval: TimeInterval = 1.0) {
        self.nodeId = nodeId
        self.nodeName = nodeName
        self.x = x
        self.y = y
        self.host = host
        self.port = port
        self.scanner = scanner
        self.interval = interval
    }

    func start() {
        running = true
        scanner.start()
        connect()
    }

    func stop() {
        running = false
        timer?.invalidate(); timer = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        scanner.stop()
        connected = false
        managerConfirmed = false
        sendingCount = 0
        status = "Stopped"
    }

    private func connect() {
        guard running else { return }
        guard let url = URL(string: "ws://\(host):\(port)") else {
            status = "Bad manager address"; return
        }
        status = "Connecting to \(host)…"
        let t = session.webSocketTask(with: url)
        task = t
        t.resume()
        receiveLoop()

        // hello first
        let hello = WireProtocol.encodeHello(
            nodeId: nodeId, name: nodeName, x: x, y: y)
        send(hello) { [weak self] ok in
            guard let self else { return }
            if ok {
                self.connected = true
                self.status = "Connected — sending"
                self.startReporting()
            } else {
                self.scheduleReconnect()
            }
        }
    }

    private func startReporting() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) {
            [weak self] _ in
            guard let self else { return }
            Task { @MainActor in self.sendReport() }
        }
    }

    private func sendReport() {
        let obs = scanner.currentObservations()
        let json = WireProtocol.encodeReport(nodeId: nodeId, observations: obs)
        send(json) { [weak self] ok in
            guard let self else { return }
            if ok {
                self.sendingCount = obs.count
                self.status = "Connected — \(obs.count) devices, sending"
            } else {
                self.connected = false
                self.managerConfirmed = false
                self.scheduleReconnect()
            }
        }
    }

    private func send(_ text: String, completion: @escaping (Bool) -> Void) {
        guard let task else { completion(false); return }
        task.send(.string(text)) { error in
            DispatchQueue.main.async { completion(error == nil) }
        }
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                if case .string(let text) = message,
                   let data = text.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let msgType = json["type"] as? String, msgType == "ack" {
                    DispatchQueue.main.async { self.managerConfirmed = true }
                }
                self.receiveLoop()
            case .failure:
                DispatchQueue.main.async {
                    self.connected = false
                    self.managerConfirmed = false
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func scheduleReconnect() {
        guard running else { return }
        timer?.invalidate(); timer = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        status = "Disconnected — retrying…"
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.connect()
        }
    }
}
