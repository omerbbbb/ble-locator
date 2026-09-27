# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for BLE Locator — builds a standalone macOS .app bundle.
#
# PyQt6 is handled by PyInstaller's built-in hook (bundles QtCore/QtGui/QtWidgets
# + the cocoa platform plugin), so we do NOT collect_all it (that can break it).
# We DO collect_all the packages with dynamically-imported submodules / native
# frameworks that PyInstaller often under-collects: bleak + pyobjc + scipy/numpy.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['qasync', 'websockets', 'zeroconf']

for pkg in ['bleak', 'scipy', 'numpy', 'objc',
            'CoreBluetooth', 'CoreWLAN', 'CoreLocation', 'Foundation',
            'libdispatch', 'AVFoundation', 'websockets', 'zeroconf']:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] collect_all({pkg!r}) skipped: {e}")

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PyQt5', 'PySide6'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BLE Locator',
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed GUI app
    argv_emulation=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='BLE Locator',
)

app = BUNDLE(
    coll,
    name='BLE Locator.app',
    icon=None,
    bundle_identifier='com.blelocator.app',
    info_plist={
        'CFBundleName': 'BLE Locator',
        'CFBundleDisplayName': 'BLE Locator',
        'CFBundleShortVersionString': '3.2.0',
        'CFBundleVersion': '3.2.0',
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
        # Required — without these macOS terminates the app on first BLE scan:
        'NSBluetoothAlwaysUsageDescription':
            'BLE Locator scans nearby Bluetooth devices to estimate your indoor position.',
        'NSBluetoothPeripheralUsageDescription':
            'BLE Locator scans nearby Bluetooth devices to estimate your indoor position.',
        'NSLocationWhenInUseUsageDescription':
            'BLE Locator uses location access to scan nearby WiFi networks for indoor positioning.',
        'NSCameraUsageDescription':
            'BLE Locator uses the camera to show an AR overlay of device positions in the room.',
    },
)
