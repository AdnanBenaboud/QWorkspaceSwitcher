# coding: utf-8

"""
Module de capture de l'état courant de l'interface QGIS.

Ce module fournit la classe :class:`StateCapture`, responsable de
photographier l'état visible de tous les docks et toolbars de l'interface
QGIS à un instant donné, afin de le sauvegarder comme perspective.

**Toolbars exclues de la capture :**

- ``QToolBar`` — widgets sans nom valide.
- ``mBrowserToolbar`` — liée au dock Browser (gérée par signal Qt).
- ``mAdvancedDigitizeToolBar`` — liée au dock Numérisation avancée.
- ``mGpsToolBar`` — liée au dock GPS.
- ``mBookmarkToolbar`` — liée au dock Signets.
- ``processingToolbar`` — liée au dock Traitements.

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface

from ..core.plugin_discovery import is_valid


class StateCapture:
    """
    Capture l'état courant de l'interface QGIS.

    Parcourt le registre des plugins fourni par
    :class:`~perspective_manager.core.plugin_discovery.PluginDiscovery`
    et enregistre pour chaque dock et toolbar : sa visibilité, sa zone
    et sa ligne (pour les toolbars).

    :exemple:

    .. code-block:: python

        discovery = PluginDiscovery()
        discovery.scan()
        capture   = StateCapture(discovery)
        data      = capture.capture("Saisie terrain")
    """

    #: Toolbars exclues de la capture — liées à un dock ou sans nom valide.
    EXCLUDED_TOOLBARS = [
        "QToolBar",
        "mBrowserToolbar",
        "mAdvancedDigitizeToolBar",
        "mGpsToolBar",
        "mBookmarkToolbar",
        "processingToolbar",
    ]

    def __init__(self, discovery):
        """
        Initialise l'instance avec le registre de découverte.

        :param discovery: Instance de découverte des plugins QGIS.
        :type discovery: PluginDiscovery
        """
        self.discovery = discovery

    def capture(self, name: str) -> dict:
        """
        Capture l'état courant de tous les docks et toolbars.

        Parcourt le registre :attr:`PluginDiscovery.registry` et
        enregistre pour chaque plugin :

        - L'état de ses docks (visibilité, zone).
        - L'état de ses toolbars (visibilité, zone, ligne).

        Les doublons et les widgets invalides sont ignorés.
        Les toolbars de :attr:`EXCLUDED_TOOLBARS` sont exclues.

        :param name: Nom de la perspective à créer.
        :type name: str
        :return: Dictionnaire de la perspective capturée.
        :rtype: dict

        :exemple:

        .. code-block:: python

            data = capture.capture("Saisie terrain")
            # → {
            #     "name": "Saisie terrain",
            #     "plugins": {
            #         "__qgis_native__": {
            #             "docks": [{"name": "Layers", "visible": True, ...}],
            #             "toolbars": [{"name": "mMapNavToolBar", "line": 1, ...}]
            #         },
            #         "georelai": {...}
            #     }
            # }
        """
        main_win = iface.mainWindow()
        data     = {"name": name, "plugins": {}}

        for plugin_name, plugin_data in self.discovery.registry.items():
            docks_state     = []
            toolbars_state  = []
            seen_dock_names = set()
            seen_tb_names   = set()

            # ── Capturer les docks ────────────────
            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]

                if not is_valid(dock):
                    continue
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

            # ── Capturer les toolbars ─────────────
            for tb_info in plugin_data.get("toolbars", []):
                tb = tb_info["object"]

                if not is_valid(tb):
                    continue
                if tb_info["name"] in self.EXCLUDED_TOOLBARS:
                    continue
                if tb_info["name"] in seen_tb_names:
                    continue

                seen_tb_names.add(tb_info["name"])
                area = main_win.toolBarArea(tb)
                area_str = self.discovery._area_to_str(area)

                toolbars_state.append({
                    "name":    tb_info["name"],
                    "label":   tb_info["label"],
                    "visible": tb.isVisible(),
                    "area":    area_str,
                    "line":    self._detect_line(main_win, tb, area_str),
                })

            if docks_state or toolbars_state:
                data["plugins"][plugin_name] = {
                    "docks":    docks_state,
                    "toolbars": toolbars_state,
                }

        return data

    def _detect_line(self, main_win, toolbar: QToolBar,
                     area_str: str) -> int:
        """
        Détecte le numéro de ligne d'une toolbar dans sa zone.

        Compare la position géométrique de la toolbar avec celles
        des autres toolbars visibles dans la même zone pour déterminer
        sur quelle ligne elle se trouve (1 = première ligne).

        :param main_win: Fenêtre principale QGIS.
        :param toolbar: Toolbar dont on cherche la ligne.
        :type toolbar: QToolBar
        :param area_str: Zone de la toolbar (``"top"``, ``"bottom"``,
            ``"left"``, ``"right"``).
        :type area_str: str
        :return: Numéro de ligne (commence à 1). Retourne ``1`` si
            la position n'est pas trouvée.
        :rtype: int

        :exemple:

        .. code-block:: python

            line = capture._detect_line(main_win, toolbar, "top")
            # → 2  (deuxième ligne de la zone top)
        """
        area_map = {
            "top":    Qt.TopToolBarArea,
            "bottom": Qt.BottomToolBarArea,
            "left":   Qt.LeftToolBarArea,
            "right":  Qt.RightToolBarArea,
        }
        area = area_map.get(area_str, Qt.TopToolBarArea)

        # Toolbars visibles dans la même zone
        same_area = [
            tb for tb in main_win.findChildren(QToolBar)
            if main_win.toolBarArea(tb) == area and tb.isVisible()
        ]

        # Trier par position Y (zones horizontales) ou X (zones verticales)
        if area_str in ("top", "bottom"):
            same_area.sort(key=lambda t: t.geometry().y())
            positions   = sorted(set(t.geometry().y() for t in same_area))
            current_pos = toolbar.geometry().y()
        else:
            same_area.sort(key=lambda t: t.geometry().x())
            positions   = sorted(set(t.geometry().x() for t in same_area))
            current_pos = toolbar.geometry().x()

        try:
            return positions.index(current_pos) + 1
        except ValueError:
            return 1