import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QIODeviceBase, QUrl
from PyQt6.QtGui import QImage

from ui.map_bridge import MapBridge
from ui.map_controller import MapController, OFFLINE_CACHE_DIR, TileSchemeHandler


class _DummySignal:
    def connect(self, _slot):
        return None


class _DummyProfile:
    def installUrlSchemeHandler(self, *_args, **_kwargs):
        return None


class _DummyPage:
    def __init__(self):
        self._profile = _DummyProfile()

    def profile(self):
        return self._profile

    def runJavaScript(self, *_args, **_kwargs):
        return None


class _DummyWebView:
    def __init__(self):
        self._page = _DummyPage()
        self.loadFinished = _DummySignal()

    def page(self):
        return self._page

    def setHtml(self, *_args, **_kwargs):
        return None


class MapControllerOfflineTests(unittest.TestCase):
    def test_tile_scheme_resolves_hosted_cache_paths(self):
        handler = TileSchemeHandler(OFFLINE_CACHE_DIR)

        resolved = handler._resolve_local_path(QUrl("gcstile://tiles/google_satellite/5/21/10.png"))

        self.assertEqual(
            resolved,
            OFFLINE_CACHE_DIR / "tiles" / "google_satellite" / "5" / "21" / "10.png",
        )

    def test_build_html_contains_offline_bootstrap_fallback(self):
        controller = MapController(_DummyWebView(), MapBridge())

        html = controller._build_html()

        self.assertIn("window.startOfflineMapFallback = function()", html)
        self.assertIn("window._gcsForceOffline =", html)
        self.assertIn("mapEl.addEventListener('wheel'", html)
        self.assertIn("mapEl.addEventListener('mousedown'", html)
        self.assertIn("btnOfflineDownload", html)
        self.assertIn("offlineDownloadPanel", html)
        self.assertIn("offlineDownloadProgressFill", html)
        self.assertIn("offlineCacheCoverage", html)
        self.assertIn("dragInfo", html)
        self.assertIn("updateDragStatus", html)
        self.assertIn("cachedCoverageLayer", html)
        self.assertIn("btnDrawAreaDownload", html)
        self.assertIn("setOfflineAreaSelectionEnabled", html)
        self.assertIn("buildDrawSelectionRange", html)
        self.assertIn("DEM高程", html)
        self.assertIn("queueOfflineMapDownload", html)
        self.assertIn("window.updateOfflineCacheProgress", html)
        self.assertIn("window.updateOfflineCacheCoverage", html)
        self.assertIn("离线地图模式已启用", html)

    def test_dem_download_does_not_persist_elevation_png(self):
        controller = MapController(_DummyWebView(), MapBridge())

        image = QImage(2, 2, QImage.Format.Format_RGB32)
        image.fill(0xFF336699)
        buffer = QBuffer()
        buffer.open(QIODeviceBase.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        png_bytes = bytes(buffer.data())

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return png_bytes

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch("ui.map_controller.OFFLINE_ELEVATION_DIR", root / "elevation"), patch(
                "ui.map_controller.OFFLINE_DEM_DIR", root / "dem"
            ), patch("ui.map_controller.urlopen", return_value=_FakeResponse()):
                state = controller._download_and_convert_dem_direct("https://example.invalid/dem.png", 5, 10, 12)

            self.assertEqual(state, "downloaded")
            self.assertTrue((root / "dem" / "5" / "10" / "12.dem.bin").exists())
            self.assertTrue((root / "dem" / "5" / "10" / "12.dem.json").exists())
            self.assertFalse((root / "elevation" / "5" / "10" / "12.png").exists())


if __name__ == "__main__":
    unittest.main()
