// ManagerDiscovery.swift
// Discovers BLE Locator managers on the local network via Bonjour/mDNS.

import Foundation
import Network

struct DiscoveredManager: Identifiable, Equatable {
    let id: String
    let host: String
    let port: Int
    let name: String

    init(host: String, port: Int, name: String) {
        self.id = "\(host):\(port)"
        self.host = host
        self.port = port
        self.name = name
    }
}

@MainActor
final class ManagerDiscovery: ObservableObject {
    @Published var managers: [DiscoveredManager] = []
    @Published var searching = false

    private var browser: NWBrowser?

    func start() {
        guard browser == nil else { return }
        searching = true
        managers = []

        let params = NWParameters()
        params.includePeerToPeer = true

        let descriptor = NWBrowser.Descriptor.bonjour(
            type: "_blelocator._tcp", domain: "local.")
        let b = NWBrowser(for: descriptor, using: params)

        b.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                switch state {
                case .failed:
                    self.searching = false
                case .cancelled:
                    self.searching = false
                default:
                    break
                }
            }
        }

        b.browseResultsChangedHandler = { [weak self] results, _ in
            Task { @MainActor in
                guard let self else { return }
                for result in results {
                    if case .service(let name, _, _, _) = result.endpoint {
                        self.resolve(result: result, displayName: name)
                    }
                }
            }
        }

        b.start(queue: .main)
        browser = b
    }

    func stop() {
        browser?.cancel()
        browser = nil
        searching = false
    }

    private func resolve(result: NWBrowser.Result, displayName: String) {
        let conn = NWConnection(to: result.endpoint, using: .tcp)
        conn.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                if case .ready = state {
                    if let path = conn.currentPath,
                       let endpoint = path.remoteEndpoint,
                       case .hostPort(let host, let port) = endpoint {
                        let hostStr = "\(host)"
                            .replacingOccurrences(of: "%.*", with: "", options: .regularExpression)
                        let portNum = Int(port.rawValue)
                        let mgr = DiscoveredManager(
                            host: hostStr, port: portNum, name: displayName)
                        if !self.managers.contains(where: { $0.id == mgr.id }) {
                            self.managers.append(mgr)
                        }
                    }
                    conn.cancel()
                }
            }
        }
        conn.start(queue: .main)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            conn.cancel()
        }
    }
}
