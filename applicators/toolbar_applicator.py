from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface
from ..core.plugin_discovery import is_valid


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
            toolbar = self._find(tb_cfg["name"])

            if toolbar is None or not is_valid(toolbar):
                print(f"[ToolbarApplicator] Toolbar ignorée : {tb_cfg['name']}")
                continue

            # Cacher les toolbars non visibles maintenant
            if not tb_cfg.get("visible", True):
                toolbar.setVisible(False)

    def apply_all(self, all_toolbars_by_plugin: dict):
        """
        Applique TOUTES les toolbars de tous les plugins
        en respectant les zones et les lignes.

        all_toolbars_by_plugin = {
            "plugin_name": [ {name, visible, area, line}, ... ]
        }
        """
        main_win = iface.mainWindow()

        # ── Étape 1 — Collecter toutes les toolbars visibles ──
        # Grouper par zone puis par ligne
        # { "top": { 1: [tb1, tb2], 2: [tb3] }, ... }
        area_lines = {}

        for plugin_name, toolbars_config in all_toolbars_by_plugin.items():
            for tb_cfg in toolbars_config:
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

        # ── Étape 2 — Retirer toutes les toolbars ─────────────
        # Qt ne peut pas repositionner une toolbar déjà placée
        # sans la retirer d'abord
        all_toolbars = set()
        for area_data in area_lines.values():
            for line_data in area_data.values():
                for entry in line_data:
                    all_toolbars.add(entry["toolbar"])

        for tb in all_toolbars:
            if is_valid(tb):
                main_win.removeToolBar(tb)

        # ── Étape 3 — Replacer dans le bon ordre ──────────────
        for area_str, lines in area_lines.items():
            area = self.AREA_MAP.get(area_str, Qt.TopToolBarArea)

            for line_num in sorted(lines.keys()):
                toolbars_in_line = lines[line_num]

                for idx, entry in enumerate(toolbars_in_line):
                    toolbar = entry["toolbar"]

                    if not is_valid(toolbar):
                        continue

                    # Ajouter dans la zone
                    main_win.addToolBar(area, toolbar)

                    # Saut de ligne avant la première toolbar
                    # de chaque nouvelle ligne (sauf ligne 1)
                    if idx == 0 and line_num > 1:
                        main_win.insertToolBarBreak(toolbar)

                    toolbar.setVisible(True)

    def _find(self, name: str):
        registry = self.discovery.registry
        for plugin_data in registry.values():
            for tb_info in plugin_data.get("toolbars", []):
                if tb_info["name"] == name:
                    return tb_info["object"]
        return None