"""Camera feed abstraction.

Uses Qt Multimedia — works on macOS, Windows, and Linux without changes.
On macOS, explicitly requests camera permission via AVFoundation before
starting the Qt camera (required for PyInstaller bundles).

Accepts any valid video output: QVideoWidget, QGraphicsVideoItem, or QVideoSink.
"""

from __future__ import annotations

import platform

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import (
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
)


def _request_camera_permission_macos(callback):
    """Explicitly ask macOS for camera access. Calls callback(granted: bool)."""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo

        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
        if status == 3:  # Authorized
            callback(True)
            return
        if status in (1, 2):  # Restricted or Denied
            callback(False)
            return
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeVideo,
            lambda granted: callback(granted),
        )
    except ImportError:
        callback(True)


class CameraCapture(QObject):
    error_occurred = pyqtSignal(str)
    started = pyqtSignal()

    def __init__(self, video_output, parent=None):
        super().__init__(parent)
        self._video_output = video_output
        self._camera = None
        self._session = QMediaCaptureSession()
        self._session.setVideoOutput(self._video_output)
        self._pending_start = False

    def start(self):
        if self._camera is not None:
            self._camera.stop()
            self._camera = None

        if platform.system() == "Darwin":
            self._pending_start = True
            _request_camera_permission_macos(self._on_permission_result)
        else:
            self._start_camera()

    def _on_permission_result(self, granted):
        if not self._pending_start:
            return
        self._pending_start = False
        if granted:
            QTimer.singleShot(0, self._start_camera)
        else:
            QTimer.singleShot(0, lambda: self.error_occurred.emit(
                "Camera access denied — enable in System Settings → Privacy → Camera"))

    def _start_camera(self):
        cam_device = QMediaDevices.defaultVideoInput()
        if cam_device.isNull():
            self.error_occurred.emit("No camera found")
            return

        try:
            self._camera = QCamera(cam_device)
            self._camera.errorOccurred.connect(self._on_error)
            self._camera.activeChanged.connect(self._on_active_changed)
            self._session.setCamera(self._camera)
            self._camera.start()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self._pending_start = False
        if self._camera is not None:
            self._camera.stop()

    @property
    def is_active(self) -> bool:
        return self._camera is not None and self._camera.isActive()

    def _on_error(self, error, message):
        self.error_occurred.emit(message)

    def _on_active_changed(self, active):
        if active:
            self.started.emit()
