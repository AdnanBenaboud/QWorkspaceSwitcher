# coding: utf-8

"""
Module de découverte dynamique des widgets des plugins QGIS.

Ce module fournit la classe :class:`PluginDiscovery`, responsable de
scanner l'interface QGIS et les plugins installés pour détecter
automatiquement leurs :class:`QDockWidget`, :class:`QToolBar` et
:class:`QMenu`.

**Stratégies de détection pour les plugins tiers :**

1. ``plugin.docks`` — attribut liste de :class:`QDockWidget`.
2. ``plugin.toolbar`` — attribut unique :class:`QToolBar`.
3. Inspection via ``dir()`` — parcours de tous les attributs du plugin.

**Structure du registre retourné :**

.. code-block:: python

    {
        "__qgis_native__": {
            "display_name": "QGIS — natif",
            "docks":    [{"name": "Layers", "label": "Couches", ...}],
            "toolbars": [{"name": "mMapNavToolBar", ...}],
            "menus":    [],
        },
        "georelai": {
            "display_name": "georelai",
            "docks":    [...],
            "toolbars": [...],
            "menus":    [{"name": "study_menu", "label": "Étude", ...}],
        },
    }

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtWidgets import QDockWidget, QToolBar, QMenu
from qgis.PyQt.QtCore import Qt
from qgis.utils import plugins, iface


class PluginDiscovery:
    """
    Découverte dynamique des widgets (docks, toolbars, menus) de QGIS
    et des plugins installés.

    Le résultat est stocké dans :attr:`registry` après appel à :meth:`scan`.

    :exemple:

    .. code-block:: python

        discovery = PluginDiscovery()
        registry  = discovery.scan()

        for plugin_name, plugin_data in registry.items():
            print(plugin_name, plugin_data["display_name"])
    """

    def __init__(self):
        """Initialise l'instance avec un registre vide."""
        self.registry = {}

    def scan(self) -> dict:
        """
        Lance le scan complet de l'interface QGIS.

        Réinitialise le registre, scanne les widgets natifs QGIS
        puis ceux de chaque plugin installé.

        :return: Registre complet des widgets découverts.
        :rtype: dict

        :exemple:

        .. code-block:: python

            registry = discovery.scan()
            native   = registry["__qgis_native__"]
        """
        self.registry = {}
        self._scan_native()
        self._scan_plugins()
        return self.registry

    def _scan_native(self):
        """
        Scanne les widgets natifs de la fenêtre principale QGIS.

        Détecte tous les :class:`QDockWidget` et :class:`QToolBar`
        présents dans la fenêtre principale et les enregistre sous
        la clé ``__qgis_native__``.
        """
        main_win        = iface.mainWindow()
        native_docks    = []
        native_toolbars = []

        for dock in main_win.findChildren(QDockWidget):
            native_docks.append(self._describe_dock(dock))

        for toolbar in main_win.findChildren(QToolBar):
            native_toolbars.append(self._describe_toolbar(toolbar))

        if native_docks or native_toolbars:
            self.registry["__qgis_native__"] = {
                "display_name": "QGIS — natif",
                "docks":        native_docks,
                "toolbars":     native_toolbars,
                "menus":        [],
            }

    def _scan_plugins(self):
        """
        Scanne les widgets de chaque plugin QGIS installé.

        Pour chaque plugin (hors ``perspective_manager``), utilise
        trois stratégies successives pour détecter les widgets :

        1. **Attribut ``docks``** — liste de :class:`QDockWidget`.
        2. **Attribut ``toolbar``** — instance unique de :class:`QToolBar`.
        3. **Inspection ``dir()``** — parcours de tous les attributs
           si les deux premières stratégies échouent.

        Les doublons sont évités via des ensembles de noms et d'identifiants.
        """
        claimed_docks    = set()
        claimed_toolbars = set()

        for plugin_name, plugin_instance in plugins.items():
            if plugin_name == "perspective_manager":
                continue

            plugin_docks    = []
            plugin_toolbars = []
            seen_dock_names = set()
            seen_tb_names   = set()

            # ── Stratégie 1 — attribut docks ──────
            if hasattr(plugin_instance, 'docks'):
                try:
                    for dock in plugin_instance.docks:
                        if isinstance(dock, QDockWidget):
                            name = self._get_name(dock)
                            if name not in seen_dock_names:
                                seen_dock_names.add(name)
                                plugin_docks.append(
                                    self._describe_dock(dock)
                                )
                                claimed_docks.add(id(dock))
                except Exception:
                    pass

            # ── Stratégie 2 — attribut toolbar ────
            if hasattr(plugin_instance, 'toolbar'):
                try:
                    tb = plugin_instance.toolbar
                    if isinstance(tb, QToolBar):
                        name = self._get_name(tb)
                        if name not in seen_tb_names:
                            seen_tb_names.add(name)
                            plugin_toolbars.append(
                                self._describe_toolbar(tb)
                            )
                            claimed_toolbars.add(id(tb))
                except Exception:
                    pass

            # ── Stratégie 3 — inspection dir() ────
            # Utilisée seulement si les deux premières échouent
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
                            plugin_toolbars.append(
                                self._describe_toolbar(attr)
                            )
                            claimed_toolbars.add(id(attr))

            # ── Scan des menus ─────────────────────
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
        Découvre les :class:`QMenu` rattachés à un plugin.

        Inspecte tous les attributs du plugin à la recherche
        d'instances :class:`QMenu`. Les doublons sont évités
        via l'identifiant mémoire du widget.

        :param plugin_instance: Instance du plugin à inspecter.
        :return: Liste des menus découverts, chacun sous la forme
            ``{"object": QMenu, "name": str, "label": str}``.
        :rtype: list[dict]
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
                    "label":  attr.title()       or attr_name,
                })

        return found_menus

    # ─────────────────────────────────────────────
    # DESCRIPTION DES WIDGETS
    # ─────────────────────────────────────────────

    def _describe_dock(self, dock: QDockWidget) -> dict:
        """
        Construit le dictionnaire de description d'un :class:`QDockWidget`.

        :param dock: Widget panneau à décrire.
        :type dock: QDockWidget
        :return: Dictionnaire avec les clés ``type``, ``object``, ``name``,
            ``label``, ``visible``, ``floating``, ``area``.
        :rtype: dict
        """
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
        """
        Construit le dictionnaire de description d'une :class:`QToolBar`.

        :param toolbar: Barre d'outils à décrire.
        :type toolbar: QToolBar
        :return: Dictionnaire avec les clés ``type``, ``object``, ``name``,
            ``label``, ``visible``, ``floating``, ``area``.
        :rtype: dict
        """
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

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _get_name(self, widget) -> str:
        """
        Retourne le nom identifiant d'un widget Qt.

        Priorité : ``objectName()`` > ``windowTitle()`` normalisé
        > nom de la classe Python.

        :param widget: Widget Qt à identifier.
        :return: Nom du widget.
        :rtype: str
        """
        if widget.objectName():
            return widget.objectName()
        if widget.windowTitle():
            return widget.windowTitle().lower().replace(" ", "_")
        return widget.__class__.__name__

    def _area_to_str(self, area) -> str:
        """
        Convertit une constante Qt de zone de dock/toolbar en chaîne.

        :param area: Constante Qt (ex. ``Qt.LeftDockWidgetArea``).
        :return: Chaîne parmi ``"left"``, ``"right"``, ``"top"``,
            ``"bottom"``. Retourne ``"left"`` par défaut.
        :rtype: str
        """
        mapping = {
            Qt.LeftDockWidgetArea:   "left",
            Qt.RightDockWidgetArea:  "right",
            Qt.TopDockWidgetArea:    "top",
            Qt.BottomDockWidgetArea: "bottom",
        }
        return mapping.get(area, "left")

    def str_to_area(self, area_str: str):
        """
        Convertit une chaîne de zone en constante Qt.

        :param area_str: Chaîne parmi ``"left"``, ``"right"``,
            ``"top"``, ``"bottom"``.
        :type area_str: str
        :return: Constante Qt correspondante.
            Retourne ``Qt.LeftDockWidgetArea`` par défaut.
        """
        mapping = {
            "left":   Qt.LeftDockWidgetArea,
            "right":  Qt.RightDockWidgetArea,
            "top":    Qt.TopDockWidgetArea,
            "bottom": Qt.BottomDockWidgetArea,
        }
        return mapping.get(area_str, Qt.LeftDockWidgetArea)


# ─────────────────────────────────────────────────
# FONCTION UTILITAIRE
# ─────────────────────────────────────────────────

def is_valid(widget) -> bool:
    """
    Vérifie qu'un widget Qt est toujours valide en mémoire.

    Les widgets Qt peuvent être détruits côté C++ tout en conservant
    leur référence Python. Cette fonction détecte ce cas en appelant
    une méthode simple et en capturant le :class:`RuntimeError`.

    :param widget: Widget Qt à vérifier.
    :return: ``True`` si le widget est valide, ``False`` s'il a été détruit.
    :rtype: bool

    :exemple:

    .. code-block:: python

        if is_valid(dock):
            dock.setVisible(True)
    """
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False