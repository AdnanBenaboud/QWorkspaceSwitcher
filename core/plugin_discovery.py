from qgis.PyQt.QtWidgets import QDockWidget, QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import plugins, iface


class PluginDiscovery:

    def __init__(self):
        self.registry = {}

    def scan(self):
        self.registry = {}
        
        # D'abord collecter TOUS les docks/toolbars existants
        main_win = iface.mainWindow()
        all_docks = set(id(d) for d in main_win.findChildren(QDockWidget))
        all_toolbars = set(id(t) for t in main_win.findChildren(QToolBar))
        
        # IDs déjà attribués à un plugin
        claimed_docks = set()
        claimed_toolbars = set()

        # ── SCAN PLUGINS ──────────────────────────────────
        for plugin_name, plugin_instance in plugins.items():
            if plugin_name == "perspective_manager":
                continue

            plugin_docks = []
            plugin_toolbars = []

            # Stratégie 1 — plugin expose self.docks (ex: Georelai)
            if hasattr(plugin_instance, 'docks'):
                try:
                    for dock in plugin_instance.docks:
                        if isinstance(dock, QDockWidget):
                            plugin_docks.append(self._describe_dock(dock))
                            claimed_docks.add(id(dock))
                except Exception:
                    pass

            # Stratégie 2 — plugin expose self.toolbar
            if hasattr(plugin_instance, 'toolbar'):
                try:
                    tb = plugin_instance.toolbar
                    if isinstance(tb, QToolBar):
                        plugin_toolbars.append(self._describe_toolbar(tb))
                        claimed_toolbars.add(id(tb))
                except Exception:
                    pass

            # Stratégie 3 — chercher attributs QDockWidget/QToolBar sur l'instance
            if not plugin_docks and not plugin_toolbars:
                for attr_name in dir(plugin_instance):
                    if attr_name.startswith('__'):
                        continue
                    try:
                        attr = getattr(plugin_instance, attr_name)
                    except Exception:
                        continue

                    if isinstance(attr, QDockWidget) and id(attr) not in claimed_docks:
                        plugin_docks.append(self._describe_dock(attr))
                        claimed_docks.add(id(attr))

                    elif isinstance(attr, QToolBar) and id(attr) not in claimed_toolbars:
                        plugin_toolbars.append(self._describe_toolbar(attr))
                        claimed_toolbars.add(id(attr))

            if plugin_docks or plugin_toolbars:
                self.registry[plugin_name] = {
                    "display_name": plugin_name,
                    "docks":    plugin_docks,
                    "toolbars": plugin_toolbars,
                }

        # ── NATIFS QGIS (tout ce qui reste non attribué) ──
        native_docks = []
        native_toolbars = []

        for dock in main_win.findChildren(QDockWidget):
            if id(dock) not in claimed_docks:
                native_docks.append(self._describe_dock(dock))

        for tb in main_win.findChildren(QToolBar):
            if id(tb) not in claimed_toolbars:
                native_toolbars.append(self._describe_toolbar(tb))

        if native_docks or native_toolbars:
            self.registry["__qgis_native__"] = {
                "display_name": "QGIS — natif",
                "docks":    native_docks,
                "toolbars": native_toolbars,
            }

        return self.registry

    # ── DESCRIPTION ───────────────────────────────────────

    def _describe_dock(self, dock: QDockWidget) -> dict:
        main_win = iface.mainWindow()
        area = main_win.dockWidgetArea(dock)
        return {
            "type":     "dock",
            "object":   dock,
            "name":     self._get_name(dock),
            "label":    dock.windowTitle() or self._get_name(dock),
            "visible":  dock.isVisible(),
            "floating": dock.isFloating(),
            "area":     self._area_to_str(area),
        }

    def _describe_toolbar(self, toolbar: QToolBar) -> dict:
        main_win = iface.mainWindow()
        area = main_win.toolBarArea(toolbar)
        return {
            "type":     "toolbar",
            "object":   toolbar,
            "name":     self._get_name(toolbar),
            "label":    toolbar.windowTitle() or self._get_name(toolbar),
            "visible":  toolbar.isVisible(),
            "floating": toolbar.isFloating(),
            "area":     self._area_to_str(area),
        }

    def _get_name(self, widget) -> str:
        if widget.objectName():
            return widget.objectName()
        if widget.windowTitle():
            return widget.windowTitle().lower().replace(" ", "_")
        return widget.__class__.__name__

    def _area_to_str(self, area) -> str:
        mapping = {
            Qt.LeftDockWidgetArea:   "left",
            Qt.RightDockWidgetArea:  "right",
            Qt.TopDockWidgetArea:    "top",
            Qt.BottomDockWidgetArea: "bottom",
        }
        return mapping.get(area, "left")

    def str_to_area(self, area_str: str):
        mapping = {
            "left":   Qt.LeftDockWidgetArea,
            "right":  Qt.RightDockWidgetArea,
            "top":    Qt.TopDockWidgetArea,
            "bottom": Qt.BottomDockWidgetArea,
        }
        return mapping.get(area_str, Qt.LeftDockWidgetArea)