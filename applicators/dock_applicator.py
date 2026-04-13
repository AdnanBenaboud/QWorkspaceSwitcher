from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface
from ..core.plugin_discovery import is_valid


class DockApplicator:

    def __init__(self, discovery):
        self.discovery = discovery

    def apply(self, plugin_name: str, docks_config: list):
        main_win = iface.mainWindow()

        # Grouper les docks visibles par zone
        area_groups = {}

        for dock_cfg in docks_config:
            dock = self._find(dock_cfg["name"])

            if dock is None or not is_valid(dock):
                print(f"[DockApplicator] Dock ignoré : {dock_cfg['name']}")
                continue

            # Cacher les docks non visibles
            if not dock_cfg.get("visible", True):
                dock.setVisible(False)
                continue

            area = dock_cfg.get("area", "left")
            if area not in area_groups:
                area_groups[area] = []
            area_groups[area].append({
                "dock":   dock,
                "config": dock_cfg,
            })

        # Appliquer selon le nombre de docks par zone
        for area_str, group in area_groups.items():
            area = self.discovery.str_to_area(area_str)

            if len(group) == 1:
                # ── 1 dock → placement normal ──────────
                self._apply_single(main_win, area, group[0]["dock"])

            elif len(group) == 2:
                # ── 2 docks → split côte à côte ────────
                self._apply_split(main_win, area, group)

            else:
                # ── 3 docks ou plus → tabifier ─────────
                self._apply_tabified(main_win, area, group)

    # ─────────────────────────────────────────
    # 1 DOCK — placement normal
    # ─────────────────────────────────────────

    def _apply_single(self, main_win, area, dock: QDockWidget):
        """Place un seul dock dans la zone."""
        if dock.isFloating():
            dock.setFloating(False)

        main_win.addDockWidget(area, dock)
        dock.setVisible(True)

    # ─────────────────────────────────────────
    # 2 DOCKS — split côte à côte
    # ─────────────────────────────────────────

    def _apply_split(self, main_win, area, group: list):
        """
        Place 2 docks côte à côte dans la même zone
        en utilisant splitDockWidget.

        splitDockWidget(dock1, dock2, orientation)
        → dock1 et dock2 partagent l'espace
        → orientation Qt.Horizontal = côte à côte
        → orientation Qt.Vertical   = l'un au dessus de l'autre
        """
        dock1 = group[0]["dock"]
        dock2 = group[1]["dock"]

        # Réancrer si flottants
        if dock1.isFloating():
            dock1.setFloating(False)
        if dock2.isFloating():
            dock2.setFloating(False)

        # Placer le premier dock dans la zone
        main_win.addDockWidget(area, dock1)
        dock1.setVisible(True)

        # Splitter le deuxième à côté du premier
        # Horizontal = côte à côte (gauche/droite)
        # Vertical   = l'un au dessus de l'autre
        if area in (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea):
            # Zone gauche/droite → split vertical
            main_win.splitDockWidget(dock1, dock2, Qt.Vertical)
        else:
            # Zone haut/bas → split horizontal
            main_win.splitDockWidget(dock1, dock2, Qt.Horizontal)

        dock2.setVisible(True)

    # ─────────────────────────────────────────
    # 3+ DOCKS — tabifier
    # ─────────────────────────────────────────

    def _apply_tabified(self, main_win, area, group: list):
        """
        Place 3 docks ou plus dans la même zone
        en les tabifiant — ils apparaissent comme des onglets.
        """
        # Placer le premier normalement
        first_dock = group[0]["dock"]
        if first_dock.isFloating():
            first_dock.setFloating(False)

        main_win.addDockWidget(area, first_dock)
        first_dock.setVisible(True)

        # Tabifier les suivants sur le premier
        for entry in group[1:]:
            dock = entry["dock"]
            if dock.isFloating():
                dock.setFloating(False)

            main_win.tabifyDockWidget(first_dock, dock)
            dock.setVisible(True)

        # Mettre le premier au premier plan
        first_dock.raise_()

    def _find(self, name: str):
        registry = self.discovery.registry
        for plugin_data in registry.values():
            for dock_info in plugin_data.get("docks", []):
                if dock_info["name"] == name:
                    return dock_info["object"]
        return None