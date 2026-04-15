# coding: utf-8

"""
Module d'application de la configuration des barres d'outils (toolbars).

Ce module fournit la classe :class:`ToolbarApplicator`, responsable de
positionner et afficher les :class:`QToolBar` selon la configuration
d'une perspective.

**Toolbars exclues** (jamais repositionnées) :

- ``PerspectiveManagerToolbar`` — toolbar du plugin lui-même.
- ``QToolBar`` — widgets sans nom valide.

**Toolbars liées** (gérées automatiquement par leur dock via signal Qt) :

- ``mBrowserToolbar``
- ``mAdvancedDigitizeToolBar``
- ``mGpsToolBar``
- ``mBookmarkToolbar``
- ``processingToolbar``

**Gestion des lignes :**

Les toolbars sont organisées par zone (``top``, ``bottom``, ``left``,
``right``) et par numéro de ligne. Un ``insertToolBarBreak`` est inséré
avant la première toolbar de chaque ligne > 1.

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface

from ..core.plugin_discovery import is_valid


#: Toolbars jamais repositionnées par le plugin.
EXCLUDED_TOOLBARS = {
    "PerspectiveManagerToolbar",
    "QToolBar",
}

#: Toolbars liées à un dock — leur visibilité suit celle du dock via signal Qt.
LINKED_TOOLBARS = {
    "mBrowserToolbar",
    "mAdvancedDigitizeToolBar",
    "mGpsToolBar",
    "mBookmarkToolbar",
    "processingToolbar",
}


class ToolbarApplicator:
    """
    Applique la configuration des barres d'outils sur l'interface QGIS.

    Positionne les :class:`QToolBar` dans les zones de la fenêtre
    principale en respectant l'ordre des lignes. La toolbar
    ``PerspectiveManagerToolbar`` est préservée à sa position actuelle
    lors de chaque application.

    :exemple:

    .. code-block:: python

        applicator = ToolbarApplicator(discovery)
        applicator.apply_all({
            "__qgis_native__": [
                {"name": "mMapNavToolBar", "visible": True,
                 "area": "top", "line": 1},
            ]
        })
    """

    #: Correspondance chaîne → constante Qt de zone toolbar.
    AREA_MAP = {
        "top":    Qt.TopToolBarArea,
        "bottom": Qt.BottomToolBarArea,
        "left":   Qt.LeftToolBarArea,
        "right":  Qt.RightToolBarArea,
    }

    def __init__(self, discovery):
        """
        Initialise l'applicateur avec le registre de découverte.

        :param discovery: Instance de découverte des plugins QGIS.
        :type discovery: PluginDiscovery
        """
        self.discovery = discovery

    def apply(self, plugin_name: str, toolbars_config: list):
        """
        Cache les toolbars non visibles d'un plugin.

        Ne repositionne pas les toolbars — utilisé uniquement pour
        masquer les toolbars dont ``visible`` est ``False``.
        Ignore les toolbars de :data:`EXCLUDED_TOOLBARS` et
        :data:`LINKED_TOOLBARS`.

        :param plugin_name: Nom du plugin propriétaire des toolbars.
        :type plugin_name: str
        :param toolbars_config: Liste des configurations de toolbars,
            chacune sous la forme
            ``{"name": str, "visible": bool, "area": str, "line": int}``.
        :type toolbars_config: list[dict]
        """
        for tb_cfg in toolbars_config:

            if tb_cfg["name"] in EXCLUDED_TOOLBARS:
                continue
            if tb_cfg["name"] in LINKED_TOOLBARS:
                continue

            toolbar = self._find(tb_cfg["name"])
            if toolbar is None or not is_valid(toolbar):
                continue

            if not tb_cfg.get("visible", True):
                toolbar.setVisible(False)

    def apply_all(self, all_toolbars_by_plugin: dict):
        """
        Repositionne toutes les toolbars visibles selon leur zone et ligne.

        Effectue dans l'ordre :

        1. Sauvegarde la position de ``PerspectiveManagerToolbar``.
        2. Collecte les toolbars visibles groupées par zone et ligne.
        3. Retire toutes ces toolbars de la fenêtre principale.
        4. Les replace dans le bon ordre avec les sauts de ligne.
        5. Restaure ``PerspectiveManagerToolbar`` à sa position sauvegardée.

        Les toolbars de :data:`EXCLUDED_TOOLBARS` et :data:`LINKED_TOOLBARS`
        sont ignorées.

        :param all_toolbars_by_plugin: Dictionnaire
            ``{plugin_name: [toolbar_config, ...]}``.
        :type all_toolbars_by_plugin: dict[str, list[dict]]

        :exemple:

        .. code-block:: python

            applicator.apply_all({
                "__qgis_native__": [
                    {"name": "mMapNavToolBar",  "visible": True,
                     "area": "top", "line": 1},
                    {"name": "mDigitizeToolBar", "visible": True,
                     "area": "top", "line": 2},
                ],
                "georelai": [
                    {"name": "GeorelaiToolbar", "visible": True,
                     "area": "top", "line": 3},
                ]
            })
        """
        main_win   = iface.mainWindow()
        area_lines = {}

        # Collecter les toolbars visibles groupées par zone et ligne
        for plugin_name, toolbars_config in all_toolbars_by_plugin.items():
            for tb_cfg in toolbars_config:

                if tb_cfg["name"] in EXCLUDED_TOOLBARS:
                    continue
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

        # Sauvegarder la position de PerspectiveManagerToolbar
        pm_toolbar = None
        pm_area    = Qt.TopToolBarArea
        for tb in main_win.findChildren(QToolBar):
            if tb.objectName() == "PerspectiveManagerToolbar":
                pm_toolbar = tb
                pm_area    = main_win.toolBarArea(tb)
                break

        # Retirer toutes les toolbars à repositionner
        all_toolbars = set()
        for area_data in area_lines.values():
            for line_data in area_data.values():
                for entry in line_data:
                    all_toolbars.add(entry["toolbar"])

        for tb in all_toolbars:
            if is_valid(tb):
                main_win.removeToolBar(tb)

        # Replacer dans le bon ordre par zone et ligne
        for area_str, lines in area_lines.items():
            area = self.AREA_MAP.get(area_str, Qt.TopToolBarArea)
            for line_num in sorted(lines.keys()):
                toolbars_in_line = lines[line_num]
                for idx, entry in enumerate(toolbars_in_line):
                    toolbar = entry["toolbar"]
                    if not is_valid(toolbar):
                        continue
                    main_win.addToolBar(area, toolbar)
                    # Insérer un saut de ligne avant la première
                    # toolbar de chaque ligne > 1
                    if idx == 0 and line_num > 1:
                        main_win.insertToolBarBreak(toolbar)
                    toolbar.setVisible(True)

        # Restaurer PerspectiveManagerToolbar à sa position sauvegardée
        if pm_toolbar and is_valid(pm_toolbar):
            main_win.addToolBar(pm_area, pm_toolbar)
            pm_toolbar.setVisible(True)

    def _find(self, name: str):
        """
        Cherche une :class:`QToolBar` par son nom dans le registre.

        :param name: Nom (``objectName``) de la toolbar à trouver.
        :type name: str
        :return: Instance de la toolbar, ou ``None`` si introuvable.
        :rtype: QToolBar or None
        """
        for plugin_data in self.discovery.registry.values():
            for tb_info in plugin_data.get("toolbars", []):
                if tb_info["name"] == name:
                    return tb_info["object"]
        return None