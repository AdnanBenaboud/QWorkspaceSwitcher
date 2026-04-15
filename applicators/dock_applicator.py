# coding: utf-8

"""
Module d'application de la configuration des panneaux (docks).

Ce module fournit la classe :class:`DockApplicator`, responsable de
positionner et afficher les :class:`QDockWidget` selon la configuration
d'une perspective.

**Stratégies de placement selon le nombre de docks par zone :**

.. code-block:: text

    1 dock  → placement normal (addDockWidget)
    2 docks → split côte à côte ou vertical (splitDockWidget)
    3 docks → tabification en onglets (tabifyDockWidget)

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtWidgets import QDockWidget
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface

from ..core.plugin_discovery import is_valid


class DockApplicator:
    """
    Applique la configuration des panneaux sur l'interface QGIS.

    Positionne les :class:`QDockWidget` dans les zones de la fenêtre
    principale selon la configuration de la perspective active.

    La stratégie de placement dépend du nombre de docks visibles
    dans chaque zone :

    - **1 dock** → placement normal via ``addDockWidget``.
    - **2 docks** → split via ``splitDockWidget``.
    - **3 docks ou plus** → tabification via ``tabifyDockWidget``.

    :exemple:

    .. code-block:: python

        applicator = DockApplicator(discovery)
        applicator.apply("georelai", docks_config)
    """

    def __init__(self, discovery):
        """
        Initialise l'applicateur avec le registre de découverte.

        :param discovery: Instance de découverte des plugins QGIS.
        :type discovery: PluginDiscovery
        """
        self.discovery = discovery

    def apply(self, plugin_name: str, docks_config: list):
        """
        Applique la configuration des docks d'un plugin.

        Pour chaque dock de la configuration :

        - Cache le dock si ``visible`` est ``False``.
        - Groupe les docks visibles par zone.
        - Applique la stratégie de placement adaptée.

        :param plugin_name: Nom du plugin propriétaire des docks.
        :type plugin_name: str
        :param docks_config: Liste des configurations de docks, chacune
            sous la forme ``{"name": str, "visible": bool, "area": str}``.
        :type docks_config: list[dict]

        :exemple:

        .. code-block:: python

            applicator.apply("georelai", [
                {"name": "import_bornes", "visible": True,  "area": "right"},
                {"name": "edition_profil", "visible": False, "area": "left"},
            ])
        """
        main_win    = iface.mainWindow()
        area_groups = {}

        for dock_cfg in docks_config:
            dock = self._find(dock_cfg["name"])

            if dock is None or not is_valid(dock):
                continue

            # Cacher les docks non visibles
            if not dock_cfg.get("visible", True):
                dock.setVisible(False)
                continue

            # Grouper les docks visibles par zone
            area = dock_cfg.get("area", "left")
            if area not in area_groups:
                area_groups[area] = []
            area_groups[area].append({
                "dock":   dock,
                "config": dock_cfg,
            })

        # Appliquer la stratégie selon le nombre de docks par zone
        for area_str, group in area_groups.items():
            area = self.discovery.str_to_area(area_str)

            if len(group) == 1:
                self._apply_single(main_win, area, group[0]["dock"])
            elif len(group) == 2:
                self._apply_split(main_win, area, group)
            else:
                self._apply_tabified(main_win, area, group)

    # ─────────────────────────────────────────────
    # STRATÉGIES DE PLACEMENT
    # ─────────────────────────────────────────────

    def _apply_single(self, main_win, area, dock: QDockWidget):
        """
        Place un dock seul dans une zone.

        Réancre le dock s'il est flottant avant de le placer.

        :param main_win: Fenêtre principale QGIS.
        :param area: Constante Qt de zone (ex. ``Qt.LeftDockWidgetArea``).
        :param dock: Dock à placer.
        :type dock: QDockWidget
        """
        if not is_valid(dock):
            return

        if dock.isFloating():
            dock.setFloating(False)

        main_win.addDockWidget(area, dock)
        dock.setVisible(True)

    def _apply_split(self, main_win, area, group: list):
        """
        Place deux docks côte à côte ou l'un au-dessus de l'autre.

        Utilise ``splitDockWidget`` pour partager l'espace entre les
        deux docks. L'orientation du split dépend de la zone :

        - Zone gauche/droite → split **vertical** (l'un au-dessus de l'autre).
        - Zone haut/bas → split **horizontal** (côte à côte).

        :param main_win: Fenêtre principale QGIS.
        :param area: Constante Qt de zone.
        :param group: Liste de deux entrées ``{"dock": QDockWidget, ...}``.
        :type group: list[dict]
        """
        dock1 = group[0]["dock"]
        dock2 = group[1]["dock"]

        if not is_valid(dock1) or not is_valid(dock2):
            return

        if dock1.isFloating():
            dock1.setFloating(False)
        if dock2.isFloating():
            dock2.setFloating(False)

        main_win.addDockWidget(area, dock1)
        dock1.setVisible(True)

        # Orientation du split selon la zone
        if area in (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea):
            main_win.splitDockWidget(dock1, dock2, Qt.Vertical)
        else:
            main_win.splitDockWidget(dock1, dock2, Qt.Horizontal)

        dock2.setVisible(True)

    def _apply_tabified(self, main_win, area, group: list):
        """
        Place trois docks ou plus en onglets dans la même zone.

        Le premier dock est placé normalement. Les suivants sont
        tabifiés sur le premier via ``tabifyDockWidget``.
        Le premier dock est mis au premier plan après tabification.

        :param main_win: Fenêtre principale QGIS.
        :param area: Constante Qt de zone.
        :param group: Liste d'au moins trois entrées
            ``{"dock": QDockWidget, ...}``.
        :type group: list[dict]
        """
        first_dock = group[0]["dock"]
        if not is_valid(first_dock):
            return

        if first_dock.isFloating():
            first_dock.setFloating(False)

        main_win.addDockWidget(area, first_dock)
        first_dock.setVisible(True)

        # Tabifier les docks suivants sur le premier
        for entry in group[1:]:
            dock = entry["dock"]
            if not is_valid(dock):
                continue
            if dock.isFloating():
                dock.setFloating(False)
            main_win.tabifyDockWidget(first_dock, dock)
            dock.setVisible(True)

        # Mettre le premier dock au premier plan
        first_dock.raise_()

    # ─────────────────────────────────────────────
    # RECHERCHE
    # ─────────────────────────────────────────────

    def _find(self, name: str):
        """
        Cherche un :class:`QDockWidget` par son nom dans le registre.

        :param name: Nom (``objectName``) du dock à trouver.
        :type name: str
        :return: Instance du dock, ou ``None`` si introuvable.
        :rtype: QDockWidget or None
        """
        for plugin_data in self.discovery.registry.values():
            for dock_info in plugin_data.get("docks", []):
                if dock_info["name"] == name:
                    return dock_info["object"]
        return None