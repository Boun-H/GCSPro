import os
import sys

# Reduce Chromium(WebEngine) noisy network logs on unstable/blocked map endpoints.
# This only lowers stderr verbosity and does not disable certificate validation.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--log-level=3 --disable-logging")

# Register custom URL scheme BEFORE QApplication is instantiated (Qt requirement)
from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
def _register_gcstile_scheme():
    scheme = QWebEngineUrlScheme(b"gcstile")
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)
_register_gcstile_scheme()

from PyQt6.QtWidgets import QApplication

# Ensure project root is on sys.path when started from any CWD
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ui.main_window import DroneGroundStation

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("GCS Pro")
    app.setOrganizationName("GCSPro")
    app.setStyle("Fusion")
    # 全局 QToolTip 白色字体深色背景
    app.setStyleSheet(
        "QToolTip { color: #ffffff; background-color: #0d1826;"
        " border: 1px solid #3a6090; border-radius: 4px;"
        " padding: 4px 8px; font-size: 12px; }"
    )
    window = DroneGroundStation()
    window.showMaximized()
    sys.exit(app.exec())