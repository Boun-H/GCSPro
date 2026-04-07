from PyQt6.QtCore import QPoint


class PanelManager:
    def __init__(self, host):
        self.host = host
        self._positions = {}
        self._configs = {}

    def register(self, name, panel, anchor="top-left", margin=(100, 100)):
        self._configs[name] = {"anchor": anchor, "margin": margin}
        self._positions.setdefault(name, None)
        panel.panel_name = name

    def show_panel(self, name, panel):
        target = self._positions.get(name) or self._default_position(name, panel)
        panel.move(target)
        panel.show()
        self._positions[name] = panel.pos()

    def hide_panel(self, name, panel):
        self._positions[name] = panel.pos()
        panel.hide()

    def constrain_visible_panels(self):
        for name, panel in self._iter_registered_panels():
            if panel.isVisible():
                clamped = self._clamp_point(panel, panel.pos())
                if clamped != panel.pos():
                    panel.move(clamped)
                self._positions[name] = panel.pos()

    def remember_position(self, name, panel):
        self._positions[name] = self._clamp_point(panel, panel.pos())

    def _default_position(self, name, panel):
        config = self._configs.get(name, {})
        anchor = config.get("anchor", "top-left")
        margin_x, margin_y = config.get("margin", (100, 100))
        rect = self.host.rect()

        if anchor == "top-right":
            point = QPoint(max(0, rect.width() - panel.width() - margin_x), margin_y)
        elif anchor == "bottom-right":
            point = QPoint(
                max(0, rect.width() - panel.width() - margin_x),
                max(0, rect.height() - panel.height() - margin_y),
            )
        else:
            point = QPoint(margin_x, margin_y)

        return self._clamp_point(panel, point)

    def _clamp_point(self, panel, point):
        rect = self.host.rect()
        max_x = max(0, rect.width() - panel.width())
        max_y = max(0, rect.height() - panel.height())
        return QPoint(min(max(point.x(), 0), max_x), min(max(point.y(), 0), max_y))

    def _iter_registered_panels(self):
        for name in self._configs:
            panel = getattr(self.host, f"{name}_panel", None)
            if panel is not None:
                yield name, panel
