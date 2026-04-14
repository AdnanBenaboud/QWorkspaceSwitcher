from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface
from ..core.plugin_discovery import is_valid


# Toolbars à ne jamais repositionner
EXCLUDED_TOOLBARS = {
    "PerspectiveManagerToolbar",  # ← notre plugin
    "QToolBar",                   # ← sans nom
}

# Toolbars liées à des docks — gérées automatiquement par signal Qt
LINKED_TOOLBARS = {
    #"mLayerToolBar",
    "mBrowserToolbar",
    "mAdvancedDigitizeToolBar",
    "mGpsToolBar",
    "mBookmarkToolbar",
    "processingToolbar",
}


class ToolbarApplicator:

    AREA_MAP = {
        "top":    Qt.TopToolBarArea,
        "bottom": Qt.BottomToolBarArea,
        "left":   Qt.LeftToolBarArea,
        "right":  Qt.RightToolBarArea,
    }

    def __init__(self, discovery):
        self.discovery = discovery

    def apply(self, plugin_name: str, toolbars_config: list):
        """
        Applique la config sur toutes les toolbars d'un plugin.
        """
        main_win = iface.mainWindow()

        for tb_cfg in toolbars_config:
            # Skip toolbars exclues
            if tb_cfg["name"] in EXCLUDED_TOOLBARS:
                continue

            # Skip toolbars liées — gérées par leur dock
            if tb_cfg["name"] in LINKED_TOOLBARS:
                continue

            toolbar = self._find(tb_cfg["name"])
            if toolbar is None or not is_valid(toolbar):
                continue

            if not tb_cfg.get("visible", True):
                toolbar.setVisible(False)

    def apply_all(self, all_toolbars_by_plugin: dict):
        """
        Applique TOUTES les toolbars de tous les plugins
        en respectant les zones et les lignes.
        """
        main_win   = iface.mainWindow()
        area_lines = {}

        for plugin_name, toolbars_config in all_toolbars_by_plugin.items():
            for tb_cfg in toolbars_config:

                # Skip toolbars exclues — ne jamais repositionner
                if tb_cfg["name"] in EXCLUDED_TOOLBARS:
                    continue

                # Skip toolbars liées — gérées par leur dock
                if tb_cfg["name"] in LINKED_TOOLBARS:
                    continue

                if not tb_cfg.get("visible", True):
                    continue

                toolbar = self._find(tb_cfg["name"])
                if toolbar is None or not is_valid(toolbar):
                    continue

                area = tb_cfg.get("area", "top")
                line = tb_cfg.get("line", 1)

                if area not in area_lines:
                    area_lines[area] = {}
                if line not in area_lines[area]:
                    area_lines[area][line] = []

                area_lines[area][line].append({
                    "toolbar": toolbar,
                    "config":  tb_cfg,
                })

        # ── Sauvegarder position PerspectiveManagerToolbar ──
        pm_toolbar = None
        pm_area    = Qt.TopToolBarArea
        for tb in main_win.findChildren(QToolBar):
            if tb.objectName() == "PerspectiveManagerToolbar":
                pm_toolbar = tb
                pm_area    = main_win.toolBarArea(tb)
                break

        # ── Retirer toutes les toolbars à repositionner ──────
        all_toolbars = set()
        for area_data in area_lines.values():
            for line_data in area_data.values():
                for entry in line_data:
                    all_toolbars.add(entry["toolbar"])

        for tb in all_toolbars:
            if is_valid(tb):
                main_win.removeToolBar(tb)

        # ── Replacer dans le bon ordre ────────────────────────
        for area_str, lines in area_lines.items():
            area = self.AREA_MAP.get(area_str, Qt.TopToolBarArea)
            for line_num in sorted(lines.keys()):
                toolbars_in_line = lines[line_num]
                for idx, entry in enumerate(toolbars_in_line):
                    toolbar = entry["toolbar"]
                    if not is_valid(toolbar):
                        continue
                    main_win.addToolBar(area, toolbar)
                    if idx == 0 and line_num > 1:
                        main_win.insertToolBarBreak(toolbar)
                    toolbar.setVisible(True)

        # ── Restaurer position PerspectiveManagerToolbar ──────
        if pm_toolbar and is_valid(pm_toolbar):
            main_win.addToolBar(pm_area, pm_toolbar)
            pm_toolbar.setVisible(True)

    def _find(self, name: str):
        """Cherche une QToolBar par son nom dans le registre."""
        registry = self.discovery.registry
        for plugin_data in registry.values():
            for tb_info in plugin_data.get("toolbars", []):
                if tb_info["name"] == name:
                    return tb_info["object"]
        return None