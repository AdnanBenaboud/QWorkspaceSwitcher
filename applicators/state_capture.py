from qgis.utils import iface
from ..core.plugin_discovery import is_valid
from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt

class StateCapture:
    """
    Photographie l'état courant de l'interface QGIS.
    """
    """
    Photographie l'état courant de l'interface QGIS.
    """
    EXCLUDED_TOOLBARS = [
        "QToolBar",                    # nom de classe générique
        # Toolbars liées à des docks — gérées automatiquement par signal
        #"mLayerToolBar",
        "mBrowserToolbar",
        "mAdvancedDigitizeToolBar",
        "mGpsToolBar",
        "mBookmarkToolbar",
        "processingToolbar",
    ]

    def __init__(self, discovery):
        self.discovery = discovery


    def _detect_line(self, main_win, toolbar, area_str: str) -> int:
        """
        Détecte sur quelle ligne se trouve une toolbar
        en comparant sa position avec les autres toolbars
        de la même zone.
        """
        area_map = {
            "top":    Qt.TopToolBarArea,
            "bottom": Qt.BottomToolBarArea,
            "left":   Qt.LeftToolBarArea,
            "right":  Qt.RightToolBarArea,
        }
        area = area_map.get(area_str, Qt.TopToolBarArea)

        # Récupérer toutes les toolbars visibles dans la même zone
        same_area = [
            tb for tb in main_win.findChildren(QToolBar)
            if main_win.toolBarArea(tb) == area and tb.isVisible()
        ]

        # Trier par position Y (top/bottom) ou X (left/right)
        if area_str in ("top", "bottom"):
            same_area.sort(key=lambda t: t.geometry().y())
            positions = sorted(set(
                t.geometry().y() for t in same_area
            ))
            current_pos = toolbar.geometry().y()
        else:
            same_area.sort(key=lambda t: t.geometry().x())
            positions = sorted(set(
                t.geometry().x() for t in same_area
            ))
            current_pos = toolbar.geometry().x()

        try:
            return positions.index(current_pos) + 1
        except ValueError:
            return 1

        

    def capture(self, name: str) -> dict:
        main_win = iface.mainWindow()
        data = {"name": name, "plugins": {}}

        for plugin_name, plugin_data in self.discovery.registry.items():
            docks_state    = []
            toolbars_state = []
            seen_tb_names  = set()  # ← pour dédupliquer

            # ── Docks ──────────────────────────────
            seen_dock_names = set()
            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]
                if not is_valid(dock):
                    continue
                # Dédupliquer
                if dock_info["name"] in seen_dock_names:
                    continue
                seen_dock_names.add(dock_info["name"])

                area = main_win.dockWidgetArea(dock)
                docks_state.append({
                    "name":    dock_info["name"],
                    "label":   dock_info["label"],
                    "visible": dock.isVisible(),
                    "area":    self.discovery._area_to_str(area),
                })

            # ── Toolbars ───────────────────────────
            for tb_info in plugin_data.get("toolbars", []):
                tb = tb_info["object"]

                if not is_valid(tb):
                    continue

                # Exclure les toolbars non souhaitées
                if tb_info["name"] in self.EXCLUDED_TOOLBARS:
                    continue

                # Dédupliquer
                if tb_info["name"] in seen_tb_names:
                    continue
                seen_tb_names.add(tb_info["name"])

                area = main_win.toolBarArea(tb)
                toolbars_state.append({
                    "name":    tb_info["name"],
                    "label":   tb_info["label"],
                    "visible": tb.isVisible(),
                    "area":    self.discovery._area_to_str(area),
                    "line":    self._detect_line(
                        main_win, tb,
                        self.discovery._area_to_str(area)
                    ),
                })

            if docks_state or toolbars_state:
                data["plugins"][plugin_name] = {
                    "docks":    docks_state,
                    "toolbars": toolbars_state,
                }

        return data