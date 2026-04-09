import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QUrl

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
        self.assertIn("queueOfflineMapDownload", html)
        self.assertIn("window.updateOfflineCacheProgress", html)
        self.assertIn("window.updateOfflineCacheCoverage", html)
        self.assertIn("离线地图模式已启用", html)


if __name__ == "__main__":
    unittest.main()
