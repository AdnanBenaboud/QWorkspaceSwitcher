from qgis.PyQt.QtWidgets import QDockWidget
from qgis.utils import iface


class DockApplicator:
    """
    Responsable de l'application de la config
    sur les QDockWidget — natifs et plugins tiers.
    """

    def __init__(self, discovery):
        self.discovery = discovery

    def apply(self, plugin_name: str, docks_config: list):
        """
        Applique la config sur tous les docks
        d'un plugin donné.

        docks_config = [
            { "name": "edition_profil",
              "visible": True,
              "area": "left" },
            ...
        ]
        """
        main_win = iface.mainWindow()

        for dock_cfg in docks_config:
            dock = self._find(dock_cfg["name"])
            if dock is None:
                print(f"[DockApplicator] Dock introuvable : {dock_cfg['name']}")
                continue

            self._apply_single(main_win, dock, dock_cfg)

    def _apply_single(self, main_win, dock: QDockWidget, config: dict):
        """Applique la config sur un seul QDockWidget."""

        # 1 — Réancrer si flottant
        if dock.isFloating():
            dock.setFloating(False)

        # 2 — Déplacer vers la zone voulue
        area = self.discovery.str_to_area(config.get("area", "left"))
        main_win.addDockWidget(area, dock)

        # 3 — Appliquer la visibilité
        dock.setVisible(config.get("visible", True))

    def _find(self, name: str):
        """
        Cherche un QDockWidget par son nom
        dans le registre du PluginDiscovery.
        """
        registry = self.discovery.registry
        for plugin_data in registry.values():
            for dock_info in plugin_data.get("docks", []):
                if dock_info["name"] == name:
                    return dock_info["object"]
        return None