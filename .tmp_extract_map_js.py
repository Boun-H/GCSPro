from ui.map_bridge import MapBridge
from ui.map_controller import MapController

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

html = MapController(_DummyWebView(), MapBridge())._build_html()
start = html.index('<script>')
end = html.rindex('</script>')
with open('tmp_map_generated.js', 'w', encoding='utf-8') as f:
    f.write(html[start + len('<script>'):end])
print('wrote tmp_map_generated.js')
