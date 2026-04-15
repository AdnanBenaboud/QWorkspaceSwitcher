# coding: utf-8

"""
Module du moteur principal du plugin Gestionnaire de Perspectives.

Ce module fournit la classe :class:`PerspectiveEngine`, chef d'orchestre
du plugin. Elle coordonne :class:`~perspective_manager.core.plugin_discovery.PluginDiscovery`,
:class:`~perspective_manager.core.config_io.ConfigIO` et les applicateurs
pour appliquer les perspectives sur l'interface QGIS.

**Flux d'application d'une perspective :**

.. code-block:: text

    apply("Saisie terrain")
        │
        ├── Passe 1 — _hide_all()
        │       → cache tous les docks et toolbars
        │
        ├── Passe 2 — DockApplicator.apply()
        │       → positionne et affiche les docks
        │
        ├── Passe 3 — ToolbarApplicator.apply_all()
        │       → positionne et affiche les toolbars
        │
        └── Passe 4 — menuBar().setVisible()
                → affiche/cache la barre de menus QGIS

**Toolbars exclues** (jamais repositionnées) :

- ``PerspectiveManagerToolbar`` — toolbar du plugin lui-même.
- ``QToolBar`` — widgets sans nom valide.

**Toolbars liées** (suivent automatiquement leur dock) :

- ``mBrowserToolbar`` → dock ``Browser``
- ``mAdvancedDigitizeToolBar`` → dock ``AdvancedDigitizingTools``
- ``mGpsToolBar`` → dock ``GPSInformation``
- ``mBookmarkToolbar`` → dock ``BookmarksDockWidget``
- ``processingToolbar`` → dock ``ProcessingToolbox``

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal, Qt
from qgis.PyQt.QtWidgets import QDockWidget, QToolBar
from qgis.utils import iface

from .plugin_discovery import PluginDiscovery, is_valid
from .config_io import ConfigIO
from ..applicators.dock_applicator import DockApplicator
from ..applicators.toolbar_applicator import ToolbarApplicator
from ..applicators.state_capture import StateCapture


#: Toolbars liées à un dock — leur visibilité suit celle du dock via signal Qt.
LINKED_TOOLBARS = {
    "mBrowserToolbar",
    "mAdvancedDigitizeToolBar",
    "mGpsToolBar",
    "mBookmarkToolbar",
    "processingToolbar",
}

#: Toolbars exclues — jamais cachées ni repositionnées par le plugin.
EXCLUDED_TOOLBARS = {
    "PerspectiveManagerToolbar",
    "QToolBar",
}


class PerspectiveEngine(QObject):
    """
    Chef d'orchestre du plugin Gestionnaire de Perspectives.

    Coordonne la découverte des plugins, la gestion de la configuration
    et l'application des perspectives sur l'interface QGIS.

    **Responsabilités :**

    - Scanner les plugins QGIS installés via :class:`PluginDiscovery`.
    - Lire et écrire les perspectives via :class:`ConfigIO`.
    - Appliquer les perspectives (docks, toolbars, barre de menus).
    - Maintenir les liaisons dock ↔ toolbar automatiques.
    - Émettre :attr:`perspectiveChanged` lors des changements.

    :exemple:

    .. code-block:: python

        engine = PerspectiveEngine()
        engine.initialize()
        engine.apply("Saisie terrain")
    """

    perspectiveChanged = pyqtSignal(str)
    """
    Signal émis après l'application d'une perspective.

    Transmet le nom de la perspective appliquée, ou ``"__reload__"``
    lors d'un rechargement externe de la configuration.
    """

    DEFAULT_PERSPECTIVE_NAME = "QGIS"
    """Nom de la perspective par défaut créée au premier démarrage."""

    def __init__(self):
        """
        Initialise le moteur avec des applicateurs à ``None``.

        Les applicateurs sont instanciés dans :meth:`initialize`
        après le scan des plugins.
        """
        super().__init__()

        self.discovery           = PluginDiscovery()
        self.config_io           = ConfigIO()
        self.registry            = {}
        self.current_perspective = None

        self.dock_applicator    = None
        self.toolbar_applicator = None
        self.state_capture      = None

    # ─────────────────────────────────────────────
    # INITIALISATION
    # ─────────────────────────────────────────────

    def initialize(self):
        """
        Initialise le moteur au démarrage du plugin.

        Effectue dans l'ordre :

        1. Scan des plugins QGIS installés.
        2. Instanciation des applicateurs.
        3. Création de la perspective ``QGIS`` par défaut si absente.
        4. Connexion des liaisons dock ↔ toolbar.
        5. Connexion au signal :attr:`ConfigIO.configChanged`.
        """
        self.registry = self.discovery.scan()

        self.dock_applicator    = DockApplicator(self.discovery)
        self.toolbar_applicator = ToolbarApplicator(self.discovery)
        self.state_capture      = StateCapture(self.discovery)

        self._ensure_default_perspective()
        self._connect_dock_toolbar_links()

        self.config_io.configChanged.connect(self._on_config_changed)

    def _on_config_changed(self):
        """
        Appelé quand ``user.psp.json`` est modifié depuis l'extérieur.

        Émet :attr:`perspectiveChanged` avec la valeur spéciale
        ``"__reload__"`` pour déclencher un rafraîchissement de l'UI
        sans appliquer de perspective.
        """
        self.perspectiveChanged.emit("__reload__")

    def _ensure_default_perspective(self):
        """
        Crée la perspective ``QGIS`` par défaut si elle est absente ou vide.

        Vérifie que la perspective contient au moins un widget visible.
        Si ce n'est pas le cas, capture l'état actuel de l'interface QGIS
        et le sauvegarde comme perspective par défaut.

        .. note::
            La perspective ``QGIS`` est protégée contre la suppression
            dans l'interface utilisateur.
        """
        existing = self.config_io.load(self.DEFAULT_PERSPECTIVE_NAME)

        if existing:
            has_visible = any(
                item.get("visible")
                for plugin_data in existing.get("plugins", {}).values()
                for key in ["docks", "toolbars"]
                for item in plugin_data.get(key, [])
            )
            if has_visible:
                return

        self.registry      = self.discovery.scan()
        self.state_capture = StateCapture(self.discovery)
        data               = self.state_capture.capture(
            self.DEFAULT_PERSPECTIVE_NAME
        )
        self.config_io.save(self.DEFAULT_PERSPECTIVE_NAME, data)

    # ─────────────────────────────────────────────
    # PERSPECTIVES — LISTE
    # ─────────────────────────────────────────────

    def list_perspectives(self) -> list:
        """
        Retourne la liste des noms de toutes les perspectives.

        Inclut les perspectives utilisateur et celles des plugins.

        :return: Liste des noms de perspectives.
        :rtype: list[str]
        """
        return self.config_io.list_all()

    def list_perspectives_merged(self) -> list:
        """
        Alias de :meth:`list_perspectives`.

        Conservé pour compatibilité avec les appels de la toolbar.

        :return: Liste des noms de perspectives.
        :rtype: list[str]
        """
        return self.config_io.list_all_merged()

    # ─────────────────────────────────────────────
    # PERSPECTIVES — CRÉER
    # ─────────────────────────────────────────────

    def add_perspective(self, name: str) -> bool:
        """
        Crée une nouvelle perspective en capturant l'état actuel de QGIS.

        Rescanne les plugins avant la capture pour garantir des références
        Qt valides.

        :param name: Nom de la nouvelle perspective.
        :type name: str
        :return: ``True`` si créée, ``False`` si le nom existe déjà.
        :rtype: bool
        """
        if name in self.config_io.list_all():
            return False

        self.registry      = self.discovery.scan()
        self.state_capture = StateCapture(self.discovery)

        data = self.state_capture.capture(name)
        self.config_io.save(name, data)
        return True

    # ─────────────────────────────────────────────
    # PERSPECTIVES — APPLIQUER
    # ─────────────────────────────────────────────

    def apply(self, name: str):
        """
        Charge et applique une perspective par son nom.

        Effectue quatre passes successives :

        1. Cache tous les docks et toolbars.
        2. Applique la configuration des docks.
        3. Applique la configuration des toolbars.
        4. Affiche ou cache la barre de menus QGIS.

        Émet :attr:`perspectiveChanged` en cas de succès.

        :param name: Nom de la perspective à appliquer.
        :type name: str
        """
        # Rescanner pour avoir des références Qt valides
        self.registry           = self.discovery.scan()
        self.dock_applicator    = DockApplicator(self.discovery)
        self.toolbar_applicator = ToolbarApplicator(self.discovery)
        self.state_capture      = StateCapture(self.discovery)

        data = self.config_io.load(name)
        if not data:
            return

        main_win = iface.mainWindow()
        main_win.setUpdatesEnabled(False)

        try:
            # Passe 1 — cacher tout
            self._hide_all()

            # Passe 2 — appliquer les docks
            for plugin_name, plugin_data in data.get("plugins", {}).items():
                self.dock_applicator.apply(
                    plugin_name,
                    plugin_data.get("docks", [])
                )

            # Passe 3 — appliquer les toolbars
            all_toolbars = {
                plugin_name: plugin_data.get("toolbars", [])
                for plugin_name, plugin_data in data.get("plugins", {}).items()
            }
            self.toolbar_applicator.apply_all(all_toolbars)

            # Passe 4 — barre de menus
            show_menu_bar = data.get("show_menu_bar", True)
            iface.mainWindow().menuBar().setVisible(show_menu_bar)

            self.current_perspective = name
            self.perspectiveChanged.emit(name)

        except Exception as e:
            print(f"[Engine] Erreur lors de l'application de '{name}' : {e}")

        finally:
            main_win.setUpdatesEnabled(True)

    def _hide_all(self):
        """
        Cache tous les docks et toolbars de l'interface QGIS.

        Respecte les exclusions :

        - :data:`EXCLUDED_TOOLBARS` — jamais cachées.
        - :data:`LINKED_TOOLBARS` — gérées automatiquement par leur dock.

        Les docks liés à une toolbar (via :meth:`_connect_dock_toolbar_links`)
        propagent automatiquement leur visibilité à leur toolbar associée.
        """
        for plugin_data in self.registry.values():

            # Cacher les docks
            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]
                if not is_valid(dock):
                    continue
                try:
                    dock.setVisible(False)
                except RuntimeError:
                    pass

            # Cacher les toolbars
            for tb_info in plugin_data.get("toolbars", []):
                tb = tb_info["object"]

                if tb_info["name"] in EXCLUDED_TOOLBARS:
                    continue

                if tb_info["name"] in LINKED_TOOLBARS:
                    continue

                if not is_valid(tb):
                    continue
                try:
                    tb.setVisible(False)
                except RuntimeError:
                    pass

    # ─────────────────────────────────────────────
    # PERSPECTIVES — SAUVEGARDER
    # ─────────────────────────────────────────────

    def save(self, name: str):
        """
        Capture l'état courant de l'interface QGIS et le sauvegarde.

        :param name: Nom de la perspective à mettre à jour.
        :type name: str
        """
        data = self.state_capture.capture(name)
        self.config_io.save(name, data)

    def save_from_data(self, name: str, data: dict):
        """
        Sauvegarde une perspective depuis un dictionnaire.

        Utilisé par l'interface utilisateur après modification
        manuelle via :class:`~perspective_manager.ui.main_window.MainWindow`.

        :param name: Nom de la perspective.
        :type name: str
        :param data: Dictionnaire complet de la perspective.
        :type data: dict
        """
        self.config_io.save(name, data)

    # ─────────────────────────────────────────────
    # PERSPECTIVES — SUPPRIMER / RENOMMER
    # ─────────────────────────────────────────────

    def delete(self, name: str):
        """
        Supprime une perspective.

        Réinitialise :attr:`current_perspective` si la perspective
        supprimée était la perspective active.

        :param name: Nom de la perspective à supprimer.
        :type name: str
        """
        self.config_io.delete(name)
        if self.current_perspective == name:
            self.current_perspective = None

    def rename(self, old_name: str, new_name: str):
        """
        Renomme une perspective.

        Met à jour :attr:`current_perspective` si la perspective
        renommée était la perspective active.

        :param old_name: Nom actuel de la perspective.
        :type old_name: str
        :param new_name: Nouveau nom de la perspective.
        :type new_name: str
        """
        self.config_io.rename(old_name, new_name)
        if self.current_perspective == old_name:
            self.current_perspective = new_name

    # ─────────────────────────────────────────────
    # ACCÈS REGISTRE
    # ─────────────────────────────────────────────

    def get_registry(self) -> dict:
        """
        Retourne le registre des widgets découverts.

        Utilisé par l'interface utilisateur pour alimenter
        les arbres de docks et toolbars.

        :return: Registre des plugins et leurs widgets.
        :rtype: dict
        """
        return self.registry

    def get_current_perspective(self) -> str:
        """
        Retourne le nom de la perspective actuellement active.

        :return: Nom de la perspective active, ou ``None``.
        :rtype: str or None
        """
        return self.current_perspective

    # ─────────────────────────────────────────────
    # LIAISONS DOCK ↔ TOOLBAR
    # ─────────────────────────────────────────────

    def _connect_dock_toolbar_links(self):
        """
        Connecte les signaux Qt pour synchroniser la visibilité
        des toolbars liées à leur dock associé.

        Quand un dock est affiché ou caché, sa toolbar liée
        suit automatiquement via le signal ``visibilityChanged``.

        **Liaisons configurées :**

        .. code-block:: text

            Browser              → mBrowserToolbar
            Browser2             → mBrowserToolbar
            AdvancedDigitizingTools → mAdvancedDigitizeToolBar
            GPSInformation       → mGpsToolBar
            BookmarksDockWidget  → mBookmarkToolbar
            ProcessingToolbox    → processingToolbar

        .. note::
            Les connexions existantes sont déconnectées avant
            reconnexion pour éviter les doublons.
        """
        main_win = iface.mainWindow()

        LINKS = {
            "Browser":                 "mBrowserToolbar",
            "Browser2":                "mBrowserToolbar",
            "AdvancedDigitizingTools": "mAdvancedDigitizeToolBar",
            "GPSInformation":          "mGpsToolBar",
            "BookmarksDockWidget":     "mBookmarkToolbar",
            "ProcessingToolbox":       "processingToolbar",
        }

        # Construire l'index des toolbars (première occurrence uniquement)
        toolbar_index = {}
        for tb in main_win.findChildren(QToolBar):
            name = tb.objectName()
            if name and name not in toolbar_index:
                toolbar_index[name] = tb

        # Construire l'index des docks
        dock_index = {}
        for dock in main_win.findChildren(QDockWidget):
            name = dock.objectName()
            if name and name not in dock_index:
                dock_index[name] = dock

        # Connecter les liaisons
        for dock_name, toolbar_name in LINKS.items():
            dock    = dock_index.get(dock_name)
            toolbar = toolbar_index.get(toolbar_name)

            if dock and toolbar:
                try:
                    dock.visibilityChanged.disconnect()
                except Exception:
                    pass
                dock.visibilityChanged.connect(
                    lambda visible, tb=toolbar: tb.setVisible(visible)
                )