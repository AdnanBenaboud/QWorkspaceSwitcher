from qgis.PyQt.QtWidgets import QDockWidget, QToolBar, QMenu
from qgis.PyQt.QtCore import Qt
from qgis.utils import plugins, iface


class PluginDiscovery:

    def __init__(self):
        self.registry = {}

    def scan(self):
        self.registry = {}
        self._scan_native()
        self._scan_plugins()
        return self.registry

    def _scan_native(self):
        main_win         = iface.mainWindow()
        native_docks     = []
        native_toolbars  = []

        claimed_docks    = set()
        claimed_toolbars = set()

        for dock in main_win.findChildren(QDockWidget):
            native_docks.append(self._describe_dock(dock))
            claimed_docks.add(id(dock))

        for toolbar in main_win.findChildren(QToolBar):
            native_toolbars.append(self._describe_toolbar(toolbar))
            claimed_toolbars.add(id(toolbar))

        if native_docks or native_toolbars:
            self.registry["__qgis_native__"] = {
                "display_name": "QGIS — natif",
                "docks":        native_docks,
                "toolbars":     native_toolbars,
                "menus":        [],
            }

    def _scan_plugins(self):
        main_win         = iface.mainWindow()
        claimed_docks    = set()
        claimed_toolbars = set()

        # ... code existant ...

        for plugin_name, plugin_instance in plugins.items():
            if plugin_name == "perspective_manager":
                continue

            plugin_docks    = []
            plugin_toolbars = []
            seen_dock_names = set()     # ← déduplication
            seen_tb_names   = set()     # ← déduplication

            # Stratégie 1 — self.docks
            if hasattr(plugin_instance, 'docks'):
                try:
                    for dock in plugin_instance.docks:
                        if isinstance(dock, QDockWidget):
                            name = self._get_name(dock)
                            if name not in seen_dock_names:
                                seen_dock_names.add(name)
                                plugin_docks.append(self._describe_dock(dock))
                                claimed_docks.add(id(dock))
                except Exception:
                    pass

            # Stratégie 2 — self.toolbar
            if hasattr(plugin_instance, 'toolbar'):
                try:
                    tb = plugin_instance.toolbar
                    if isinstance(tb, QToolBar):
                        name = self._get_name(tb)
                        if name not in seen_tb_names:
                            seen_tb_names.add(name)
                            plugin_toolbars.append(self._describe_toolbar(tb))
                            claimed_toolbars.add(id(tb))
                except Exception:
                    pass

            # Stratégie 3 — dir() inspection
            if not plugin_docks and not plugin_toolbars:
                for attr_name in dir(plugin_instance):
                    if attr_name.startswith('__'):
                        continue
                    try:
                        attr = getattr(plugin_instance, attr_name)
                    except Exception:
                        continue
                    if isinstance(attr, QDockWidget) \
                            and id(attr) not in claimed_docks:
                        name = self._get_name(attr)
                        if name not in seen_dock_names:
                            seen_dock_names.add(name)
                            plugin_docks.append(self._describe_dock(attr))
                            claimed_docks.add(id(attr))
                    elif isinstance(attr, QToolBar) \
                            and id(attr) not in claimed_toolbars:
                        name = self._get_name(attr)
                        if name not in seen_tb_names:
                            seen_tb_names.add(name)
                            plugin_toolbars.append(self._describe_toolbar(attr))
                            claimed_toolbars.add(id(attr))

            plugin_menus = self._scan_plugin_menus(plugin_instance)

            if plugin_docks or plugin_toolbars or plugin_menus:
                self.registry[plugin_name] = {
                    "display_name": plugin_name,
                    "docks":        plugin_docks,
                    "toolbars":     plugin_toolbars,
                    "menus":        plugin_menus,
                }

    def _scan_plugin_menus(self, plugin_instance) -> list:
        """
        Découvre les QMenu rattachés à un plugin
        en inspectant ses attributs.
        """
        found_menus = []
        seen_ids    = set()

        for attr_name in dir(plugin_instance):
            if attr_name.startswith('__'):
                continue
            try:
                attr = getattr(plugin_instance, attr_name)
            except Exception:
                continue

            if isinstance(attr, QMenu) and id(attr) not in seen_ids:
                seen_ids.add(id(attr))
                found_menus.append({
                    "object": attr,
                    "name":   attr.objectName() or attr_name,
                    "label":  attr.title() or attr_name,
                })

        return found_menus

    # ─────────────────────────────────────────
    # DESCRIPTION
    # ─────────────────────────────────────────

    def _describe_dock(self, dock: QDockWidget) -> dict:
        main_win = iface.mainWindow()
        area     = main_win.dockWidgetArea(dock)
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
        area     = main_win.toolBarArea(toolbar)
        return {
            "type":     "toolbar",
            "object":   toolbar,
            "name":     self._get_name(toolbar),
            "label":    toolbar.windowTitle() or self._get_name(toolbar),
            "visible":  toolbar.isVisible(),
            "floating": toolbar.isFloating(),
            "area":     self._area_to_str(area),
        }

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

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


# ── FONCTION UTILITAIRE ────────────────────────
def is_valid(widget) -> bool:
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False