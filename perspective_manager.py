# coding: utf-8

"""
Module principal du plugin QGIS Gestionnaire de Perspectives.

Ce module fournit la classe :class:`PerspectiveManager`, point d'entrée
du plugin QGIS. Elle gère le cycle de vie du plugin (initialisation,
interface graphique, déchargement) et la toolbar de perspectives.

**Structure de la toolbar :**

.. code-block:: text

    ┌────────────────────────────────────────────────────┐
    │ [⚙] │ | │ [QGIS] │ [Saisie terrain ▼] │ [Maillage] │
    └────────────────────────────────────────────────────┘
      │         │              │                    │
    Ouvrir    Sépa-        Bouton simple      Bouton plugin
    MainWindow rateur      (pas de menu)      (avec menu ▼)

**Fichier de configuration :**

- ``perspectives/user.psp.json`` — perspectives utilisateur.
- ``<plugin>/<plugin>.psp.json`` — perspectives déclarées par les plugins.

:author: Adnan Benaboud — CNR
"""

import os

from qgis.PyQt.QtWidgets import (
    QAction, QToolBar, QToolButton,
    QMenu, QInputDialog, QMessageBox
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt, QTimer

from .core.perspective_engine import PerspectiveEngine
from .core.plugin_discovery import is_valid
from .ui.main_window import MainWindow


class PerspectiveManager:
    """
    Point d'entrée du plugin QGIS Gestionnaire de Perspectives.

    Gère le cycle de vie du plugin, la toolbar QGIS et la
    synchronisation entre l'interface utilisateur et le moteur.

    **Responsabilités :**

    - Initialiser et décharger le plugin (``initGui`` / ``unload``).
    - Créer et maintenir la toolbar ``PerspectiveManagerToolbar``.
    - Créer un bouton :class:`QToolButton` par perspective.
    - Ouvrir :class:`~perspective_manager.ui.main_window.MainWindow`
      à la demande.
    - Rafraîchir la toolbar lors des modifications de configuration.

    :exemple:

    .. code-block:: python

        # Appelé automatiquement par QGIS au chargement du plugin
        manager = PerspectiveManager(iface)
        manager.initGui()
    """

    def __init__(self, iface):
        """
        Initialise le gestionnaire avec l'interface QGIS.

        :param iface: Interface QGIS principale.
        :type iface: QgisInterface
        """
        self.iface               = iface
        self.plugin_dir          = os.path.dirname(__file__)
        self.first_start         = True
        self.main_window         = None
        self.engine              = None
        self.toolbar             = None
        self.perspective_actions = {}
        self.perspective_buttons = {}

    def initGui(self):
        """
        Initialise l'interface graphique du plugin.

        - Crée et initialise le :class:`PerspectiveEngine`.
        - Crée la toolbar ``PerspectiveManagerToolbar``.
        - Ajoute l'action d'ouverture de la :class:`MainWindow`.
        - Crée les boutons de perspectives via :meth:`_refresh_toolbar`.
        - Connecte les signaux de changement de perspective et de
          modification de configuration.
        - Installe le raccourci ``Ctrl+Shift+M`` pour restaurer
          la barre de menus QGIS en cas d'urgence.
        """
        self.engine = PerspectiveEngine()
        self.engine.initialize()

        # Créer la toolbar principale
        self.toolbar = QToolBar("Gestionnaire de Perspectives")
        self.toolbar.setObjectName("PerspectiveManagerToolbar")
        self.iface.addToolBar(self.toolbar)

        # Bouton d'ouverture de la MainWindow
        self.action_open = QAction(
            QIcon(os.path.join(self.plugin_dir, "icon.png")),
            "Gérer les perspectives",
            self.iface.mainWindow()
        )
        self.action_open.triggered.connect(self.run)
        self.toolbar.addAction(self.action_open)
        self.iface.addPluginToMenu(
            "Gestionnaire de Perspectives", self.action_open
        )

        self.toolbar.addSeparator()
        self._refresh_toolbar()

        # Connecter les signaux
        self.engine.perspectiveChanged.connect(
            self._on_perspective_changed
        )
        self.engine.config_io.configChanged.connect(
            self._on_config_file_changed
        )

        # Raccourci de secours pour restaurer la barre de menus
        from qgis.PyQt.QtWidgets import QShortcut
        from qgis.PyQt.QtGui import QKeySequence
        self._shortcut_menu = QShortcut(
            QKeySequence("Ctrl+Shift+M"),
            self.iface.mainWindow()
        )
        self._shortcut_menu.activated.connect(
            lambda: self.iface.mainWindow().menuBar().setVisible(True)
        )

    def unload(self):
        """
        Décharge le plugin et restaure l'interface QGIS.

        - Restaure la barre de menus QGIS (visible).
        - Supprime l'entrée du menu Extensions.
        - Supprime la toolbar.
        - Ferme la :class:`MainWindow` si ouverte.
        """
        self.iface.mainWindow().menuBar().setVisible(True)

        self.iface.removePluginMenu(
            "Gestionnaire de Perspectives", self.action_open
        )
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.main_window:
            self.main_window.close()
        del self.action_open

    def run(self):
        """
        Ouvre la fenêtre principale :class:`MainWindow`.

        Crée la fenêtre au premier appel (``first_start``),
        puis la réaffiche aux appels suivants.
        """
        if self.first_start:
            self.first_start = False
            self.main_window = MainWindow(
                engine=self.engine,
                parent=self.iface.mainWindow()
            )
            self.main_window.perspectiveSaved.connect(
                self._refresh_toolbar
            )
        self.main_window.show()
        self.main_window.raise_()

    # ─────────────────────────────────────────────
    # TOOLBAR
    # ─────────────────────────────────────────────

    def _is_toolbar_valid(self) -> bool:
        """
        Vérifie que la toolbar Qt est encore valide en mémoire.

        :return: ``True`` si la toolbar est valide, ``False`` sinon.
        :rtype: bool
        """
        if self.toolbar is None:
            return False
        try:
            self.toolbar.objectName()
            return True
        except RuntimeError:
            return False

    def _refresh_toolbar(self):
        """
        Recrée tous les boutons de perspectives dans la toolbar.

        Supprime les boutons existants et recrée un
        :class:`QToolButton` par perspective depuis ``self._cfg``.

        **Style des boutons :**

        - ``text`` → texte seulement.
        - ``icon`` → icône seulement.
        - ``icon_text`` → icône à gauche + texte.
        - ``text_icon`` → texte à gauche + icône à droite
          (via ``Qt.RightToLeft``).

        **Menu dropdown :**

        - Si la perspective a des ``dropdown_menus`` →
          bouton avec flèche ``▼`` (``MenuButtonPopup``).
        - Sinon → bouton simple (``DelayedPopup``).
        """
        if not self._is_toolbar_valid():
            return

        # Retirer les anciens boutons
        for action in list(self.perspective_actions.values()):
            try:
                self.toolbar.removeAction(action)
            except RuntimeError:
                pass

        self.perspective_actions.clear()
        self.perspective_buttons.clear()

        for name in self.engine.config_io.list_all_merged():
            data           = self.engine.config_io.load(name)
            style          = data.get("button_style", "text")
            icon_path      = data.get("icon", "")
            dropdown_menus = data.get("dropdown_menus", [])
            has_dropdown   = bool(dropdown_menus)

            btn = QToolButton()
            btn.setToolTip(f"Perspective : {name}")
            btn.setText(name)

            # Icône du bouton
            if icon_path and os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))

            # Style d'affichage
            style_map = {
                "icon":      Qt.ToolButtonIconOnly,
                "icon_text": Qt.ToolButtonTextBesideIcon,
                "text":      Qt.ToolButtonTextOnly,
                "text_icon": Qt.ToolButtonTextBesideIcon,
            }
            btn.setToolButtonStyle(
                style_map.get(style, Qt.ToolButtonTextOnly)
            )

            # text_icon → icône à droite via direction RTL
            if style == "text_icon":
                btn.setLayoutDirection(Qt.RightToLeft)
            else:
                btn.setLayoutDirection(Qt.LeftToRight)

            # Mode dropdown ou bouton simple
            if has_dropdown:
                menu = self._build_perspective_menu(name)
                btn.setMenu(menu)
                btn.setPopupMode(QToolButton.MenuButtonPopup)
            else:
                btn.setPopupMode(QToolButton.DelayedPopup)

            btn.clicked.connect(
                lambda checked, n=name: self.engine.apply(n)
            )
            btn.setCheckable(True)
            if self.engine.get_current_perspective() == name:
                btn.setChecked(True)

            action = self.toolbar.addWidget(btn)
            self.perspective_actions[name] = action
            self.perspective_buttons[name] = btn

    def _on_config_file_changed(self):
        """
        Appelé quand ``user.psp.json`` est modifié depuis l'extérieur.

        Utilise un délai via :class:`QTimer` pour éviter les conflits
        avec les opérations d'écriture en cours sur la toolbar Qt.
        """
        QTimer.singleShot(300, self._safe_refresh)

    def _safe_refresh(self):
        """
        Rafraîchit la toolbar et la MainWindow de manière sécurisée.

        Vérifie la validité de la toolbar avant toute opération.
        Protège contre les erreurs Qt si la toolbar a été détruite.
        """
        if not self._is_toolbar_valid():
            return

        try:
            self._refresh_toolbar()
        except RuntimeError as e:
            print(f"[Plugin] Erreur refresh toolbar : {e}")
            return

        if self.main_window and self.main_window.isVisible():
            try:
                self.main_window._refresh_list()
                current = self.main_window.inputName.text().strip()
                if current:
                    self.main_window._load_perspective_in_tree(current)
            except RuntimeError as e:
                print(f"[Plugin] Erreur refresh MainWindow : {e}")

    def _on_perspective_changed(self, name: str):
        """
        Synchronise l'état enfoncé des boutons de la toolbar.

        Enfonce le bouton de la perspective active et relâche
        les autres. Ignore la valeur spéciale ``"__reload__"``.

        :param name: Nom de la perspective appliquée,
            ou ``"__reload__"`` pour un simple rafraîchissement.
        :type name: str
        """
        if name == "__reload__":
            return
        for perspective_name, btn in self.perspective_buttons.items():
            try:
                btn.setChecked(perspective_name == name)
            except RuntimeError:
                pass

    # ─────────────────────────────────────────────
    # MENU DROPDOWN
    # ─────────────────────────────────────────────

    def _build_perspective_menu(self, name: str) -> QMenu:
        """
        Construit le menu dropdown d'une perspective.

        Charge les ``dropdown_menus`` depuis ``self._cfg`` et
        copie les :class:`QMenu` des plugins correspondants.

        Gère la compatibilité avec l'ancienne structure
        (liste de chaînes avec ``dropdown_plugin``).

        :param name: Nom de la perspective.
        :type name: str
        :return: Menu dropdown prêt à être attaché au bouton.
        :rtype: QMenu
        """
        menu           = QMenu()
        data           = self.engine.config_io.load(name)
        dropdown_menus = data.get("dropdown_menus", [])

        # Compatibilité avec l'ancienne structure (liste de strings)
        if dropdown_menus and isinstance(dropdown_menus[0], str):
            old_plugin     = data.get("dropdown_plugin", "")
            dropdown_menus = [
                {"plugin": old_plugin, "menu": m}
                for m in dropdown_menus
            ]

        if dropdown_menus:
            self._append_plugin_menus(menu, dropdown_menus)

        return menu

    def _append_plugin_menus(self, menu: QMenu, dropdown_menus: list):
        """
        Copie les menus sélectionnés des plugins dans le menu dropdown.

        Groupe les menus par plugin avec un séparateur et un label
        par plugin. Ignore les menus invalides ou introuvables.

        :param menu: Menu cible dans lequel ajouter les sous-menus.
        :type menu: QMenu
        :param dropdown_menus: Liste de ``{"plugin": str, "menu": str}``.
        :type dropdown_menus: list[dict]
        """
        registry     = self.engine.get_registry()
        plugins_seen = set()

        for item in dropdown_menus:
            plugin_name = item["plugin"]
            menu_name   = item["menu"]

            plugin_data = registry.get(plugin_name, {})
            all_menus   = plugin_data.get("menus", [])

            menu_info = next(
                (m for m in all_menus if m["name"] == menu_name),
                None
            )
            if not menu_info:
                continue

            original_menu = menu_info["object"]
            if not is_valid(original_menu):
                continue

            # Ajouter séparateur + label plugin au premier menu du plugin
            if plugin_name not in plugins_seen:
                plugins_seen.add(plugin_name)
                if menu.actions():
                    menu.addSeparator()
                label = QAction(
                    f"── {plugin_data.get('display_name', plugin_name)} ──",
                    menu
                )
                label.setEnabled(False)
                menu.addAction(label)

            copied = self._copy_menu(original_menu, menu)
            menu.addMenu(copied)

    def _copy_menu(self, source_menu: QMenu, parent) -> QMenu:
        """
        Copie récursive d'un :class:`QMenu`.

        Crée un nouveau menu avec les mêmes actions que la source.
        Les actions copiées déclenchent les actions originales du plugin
        via ``original_action.trigger()``.

        :param source_menu: Menu source à copier.
        :type source_menu: QMenu
        :param parent: Widget parent du menu copié.
        :return: Copie du menu source.
        :rtype: QMenu
        """
        copied_menu = QMenu(source_menu.title(), parent)
        copied_menu.setIcon(source_menu.icon())

        for action in source_menu.actions():
            if action.isSeparator():
                copied_menu.addSeparator()

            elif action.menu():
                sub = self._copy_menu(action.menu(), copied_menu)
                copied_menu.addMenu(sub)

            else:
                new_action = QAction(
                    action.icon(),
                    action.text(),
                    copied_menu
                )
                new_action.setEnabled(action.isEnabled())
                new_action.setCheckable(action.isCheckable())
                new_action.setChecked(action.isChecked())
                new_action.setToolTip(action.toolTip())

                original = action
                new_action.triggered.connect(
                    lambda checked, a=original: a.trigger()
                )
                copied_menu.addAction(new_action)

        return copied_menu

    # ─────────────────────────────────────────────
    # ACTIONS DEPUIS LA TOOLBAR
    # ─────────────────────────────────────────────

    def _open_perspective(self, name: str):
        """
        Ouvre la :class:`MainWindow` et sélectionne une perspective.

        :param name: Nom de la perspective à sélectionner.
        :type name: str
        """
        self.run()
        if self.main_window:
            items = self.main_window.listPerspectives.findItems(
                name, Qt.MatchExactly
            )
            if items:
                self.main_window.listPerspectives.setCurrentItem(items[0])

    def _duplicate_perspective(self, name: str):
        """
        Duplique une perspective depuis la toolbar.

        :param name: Nom de la perspective à dupliquer.
        :type name: str
        """
        new_name, ok = QInputDialog.getText(
            None, "Dupliquer", "Nouveau nom :",
            text=f"{name} - copie"
        )
        if ok and new_name.strip():
            data         = self.engine.config_io.load(name)
            data["name"] = new_name.strip()
            self.engine.save_from_data(new_name.strip(), data)
            self._refresh_toolbar()
            if self.main_window:
                self.main_window._refresh_list()

    def _delete_perspective(self, name: str):
        """
        Supprime une perspective depuis la toolbar après confirmation.

        La perspective ``QGIS`` est protégée contre la suppression.

        :param name: Nom de la perspective à supprimer.
        :type name: str
        """
        if name == "QGIS":
            return

        reply = QMessageBox.question(
            None, "Supprimer",
            f"Supprimer la perspective '{name}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.delete(name)
            self._refresh_toolbar()
            if self.main_window:
                self.main_window._refresh_list()
                self.main_window._reset_tree()
                self.main_window._set_editor_visible(False)