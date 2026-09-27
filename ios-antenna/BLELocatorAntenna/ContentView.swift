// ContentView.swift
// Antenna UI: auto-discovers manager on the network, scans BLE, streams to manager.

import SwiftUI
import UIKit

struct ContentView: View {
    @StateObject private var scanner = BLEScanner()
    @StateObject private var discovery = ManagerDiscovery()
    @State private var client: NodeClient?

    @State private var name: String = UIDevice.current.name
    @State private var x: String = "0.0"
    @State private var y: String = "0.0"
    @State private var host: String = ""
    @State private var port: String = "8077"
    @State private var running = false

    @State private var statusText = "Searching for manager…"
    @State private var deviceCount = 0
    @State private var connected = false
    @State private var managerConfirmed = false
    @State private var sendingDevices = 0

    private let nodeId = "ios-" +
        (UIDevice.current.identifierForVendor?.uuidString.prefix(8).lowercased() ?? "phone")

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("This antenna")) {
                    TextField("Name", text: $name)
                    HStack {
                        Text("x (m)")
                        TextField("0.0", text: $x).keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                    }
                    HStack {
                        Text("y (m)")
                        TextField("0.0", text: $y).keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                    }
                }

                Section(header: Text("Manager")) {
                    if !discovery.managers.isEmpty {
                        ForEach(discovery.managers) { mgr in
                            Button {
                                host = mgr.host
                                port = "\(mgr.port)"
                            } label: {
                                HStack {
                                    Image(systemName: "desktopcomputer")
                                        .foregroundColor(.green)
                                    VStack(alignment: .leading) {
                                        Text(mgr.name)
                                            .foregroundColor(.primary)
                                        Text("\(mgr.host):\(mgr.port)")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    if host == mgr.host {
                                        Image(systemName: "checkmark")
                                            .foregroundColor(.blue)
                                    }
                                }
                            }
                        }
                    } else if discovery.searching {
                        HStack {
                            ProgressView()
                                .padding(.trailing, 6)
                            Text("Searching for manager on network…")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                        }
                    }

                    TextField("Manager IP (or auto-discovered above)", text: $host)
                        .keyboardType(.numbersAndPunctuation)
                        .autocorrectionDisabled()
                    HStack {
                        Text("Port")
                        TextField("8077", text: $port).keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                    }
                }

                Section(header: Text("Status")) {
                    Label(scanner.bluetoothReady ? "Bluetooth ready" : "Bluetooth off",
                          systemImage: scanner.bluetoothReady ? "dot.radiowaves.left.and.right" : "exclamationmark.triangle")
                        .foregroundColor(scanner.bluetoothReady ? .green : .orange)

                    if running {
                        if connected && managerConfirmed {
                            Label("Manager confirmed", systemImage: "checkmark.seal.fill")
                                .foregroundColor(.green)
                        } else if connected {
                            Label("Connected, waiting for ack…", systemImage: "arrow.triangle.2.circlepath")
                                .foregroundColor(.orange)
                        } else {
                            Label("Connecting…", systemImage: "wifi.exclamationmark")
                                .foregroundColor(.red)
                        }
                    }

                    Text(statusText).font(.footnote).foregroundColor(.secondary)
                    Text("Devices seen: \(scanner.deviceCount)")
                        .font(.footnote).foregroundColor(.secondary)
                    if running && sendingDevices > 0 {
                        Text("Sending \(sendingDevices) devices to manager")
                            .font(.footnote).foregroundColor(.green)
                    }
                }

                Section {
                    Button(running ? "Stop" : "Start") { toggle() }
                        .frame(maxWidth: .infinity)
                        .foregroundColor(.white)
                        .padding(8)
                        .background(running ? Color.red : Color.blue)
                        .cornerRadius(8)
                        .listRowInsets(EdgeInsets())
                }

                Section {
                    Text("Keep this app open and the screen on. It feeds the "
                         + "manager on your computer.")
                        .font(.caption).foregroundColor(.secondary)
                }
            }
            .navigationTitle("BLE Locator Antenna")
            .onAppear { discovery.start() }
            .onDisappear { discovery.stop() }
            .onChange(of: discovery.managers) { _, newManagers in
                if host.isEmpty, let first = newManagers.first {
                    host = first.host
                    port = "\(first.port)"
                    statusText = "Found manager: \(first.name)"
                }
            }
        }
    }

    private func toggle() {
        if running {
            client?.stop()
            running = false
            statusText = "Stopped"
        } else {
            guard !host.isEmpty else { statusText = "Enter the manager IP first"; return }
            let c = NodeClient(
                nodeId: nodeId,
                nodeName: name.isEmpty ? "iPhone" : name,
                x: Double(x) ?? 0, y: Double(y) ?? 0,
                host: host, port: Int(port) ?? 8077,
                scanner: scanner)
            client = c
            observe(c)
            c.start()
            running = true
        }
    }

    private func observe(_ c: NodeClient) {
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { t in
            if !running { t.invalidate(); return }
            statusText = c.status
            connected = c.connected
            managerConfirmed = c.managerConfirmed
            sendingDevices = c.sendingCount
        }
    }
}

#Preview {
    ContentView()
}
