#!/bin/bash
# Build BLE Locator as a standalone macOS .app and place it on the Desktop.
set -e
cd "$(dirname "$0")"

echo "==> Ensuring PyInstaller is installed"
.venv/bin/pip install --quiet pyinstaller

echo "==> Cleaning previous build"
rm -rf build dist

echo "==> Building (this takes a minute)…"
.venv/bin/pyinstaller ble_locator.spec --noconfirm

echo "==> Ad-hoc code-signing (stable identity so macOS remembers the Bluetooth grant)"
codesign --force --deep --sign - "dist/BLE Locator.app"

echo "==> Copying to Desktop"
rm -rf "$HOME/Desktop/BLE Locator.app"
cp -R "dist/BLE Locator.app" "$HOME/Desktop/BLE Locator.app"
# strip quarantine just in case
xattr -dr com.apple.quarantine "$HOME/Desktop/BLE Locator.app" 2>/dev/null || true

echo ""
echo "✅ Done.  ~/Desktop/BLE Locator.app"
echo "   Double-click it. Approve the Bluetooth prompt on first launch."
