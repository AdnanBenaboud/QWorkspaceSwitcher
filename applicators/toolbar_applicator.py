from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface


class ToolbarApplicator:
    """
    Responsable de l'application de la config
    sur les QToolBar — natives et plugins tiers.
    """

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
        Applique la config sur toutes les toolbars
        d'un plugin donné.

        toolbars_config = [
            { "name": "GeorelaiToolbar",
              "visible": True,
              "area": "top" },
            ...
        ]
        """
        main_win = iface.mainWindow()

        for tb_cfg in toolbars_config:
            toolbar = self._find(tb_cfg["name"])
            if toolbar is None:
                print(f"[ToolbarApplicator] Toolbar introuvable : {tb_cfg['name']}")
                continue

            self._apply_single(main_win, toolbar, tb_cfg)

    def _apply_single(self, main_win, toolbar: QToolBar, config: dict):
        """Applique la config sur une seule QToolBar."""

        # 1 — Réancrer si flottante (QToolBar utilise isFloating mais pas setFloating)
        if toolbar.isFloating():
            # On la réancre en la retirant et rajoutant à la fenêtre principale
            main_win.removeToolBar(toolbar)

        # 2 — Déplacer vers la zone voulue
        area = self.AREA_MAP.get(config.get("area", "top"), Qt.TopToolBarArea)
        main_win.addToolBar(area, toolbar)

        # 3 — Appliquer la visibilité
        toolbar.setVisible(config.get("visible", True))

    def _find(self, name: str):
        """
        Cherche une QToolBar par son nom
        dans le registre du PluginDiscovery.
        """
        registry = self.discovery.registry
        for plugin_data in registry.values():
            for tb_info in plugin_data.get("toolbars", []):
                if tb_info["name"] == name:
                    return tb_info["object"]
        return None