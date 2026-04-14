import os
from qgis.PyQt.QtWidgets import (
    QAction, QToolBar, QToolButton,
    QMenu, QLabel, QInputDialog, QMessageBox
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from .core.perspective_engine import PerspectiveEngine
from .core.plugin_discovery import is_valid
from .ui.main_window import MainWindow


class PerspectiveManager:

    def __init__(self, iface):
        self.iface               = iface
        self.plugin_dir          = os.path.dirname(__file__)
        self.first_start         = True
        self.main_window         = None
        self.engine              = None
        self.toolbar             = None
        self.perspective_actions = {}
        self.perspective_buttons = {}

    def initGui(self):
        self.engine = PerspectiveEngine()
        self.engine.initialize()

        self.toolbar = QToolBar("Gestionnaire de Perspectives")
        self.toolbar.setObjectName("PerspectiveManagerToolbar")
        self.iface.addToolBar(self.toolbar)

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

        self.engine.perspectiveChanged.connect(
            self._on_perspective_changed
        )

        # ── Rafraîchir quand fichier modifié ────────
        self.engine.config_io.configChanged.connect(self._on_config_file_changed)

    def _on_config_file_changed(self):
        """Rafraîchit la toolbar quand le JSON est modifié."""
        print("[Plugin] Fichier JSON modifié → rafraîchissement toolbar")
        self._refresh_toolbar()

        if self.main_window and self.main_window.isVisible():
            self.main_window._refresh_list()
            current = self.main_window.inputName.text().strip()
            if current:
                self.main_window._load_perspective_in_tree(current)


        self.main_window._refresh_list()

    def unload(self):
        iface.mainWindow().menuBar().setVisible(True)
        self.iface.removePluginMenu(
            "Gestionnaire de Perspectives", self.action_open
        )
        if self.toolbar:
            self.toolbar.deleteLater()
        if self.main_window:
            self.main_window.close()
        del self.action_open

    def run(self):
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

    # ─────────────────────────────────────────
    # TOOLBAR
    # ─────────────────────────────────────────

    def _refresh_toolbar(self):
        """Recrée les boutons de perspectives."""
        for action in self.perspective_actions.values():
            self.toolbar.removeAction(action)
        self.perspective_actions.clear()
        self.perspective_buttons.clear()

        for name in self.engine.list_perspectives():
            data      = self.engine.config_io.load(name)
            style     = data.get("button_style", "text")
            icon_path = data.get("icon", "")

            # ── Dropdown configuré ? ──────────────────
            dropdown_menus = data.get("dropdown_menus", [])
            has_dropdown   = bool(dropdown_menus)

            btn = QToolButton()
            btn.setToolTip(f"Perspective : {name}")
            btn.setText(name)

            # Icône
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

            # Pour text_icon — inverser icône et texte
            if style == "text_icon":
                btn.setLayoutDirection(Qt.RightToLeft)  # ← icône à droite
            else:
                btn.setLayoutDirection(Qt.LeftToRight)  # ← icône à gauche

            if has_dropdown:
                # ── Avec dropdown ─────────────────────
                menu = self._build_perspective_menu(name)
                btn.setMenu(menu)
                btn.setPopupMode(QToolButton.MenuButtonPopup)
                # Clic simple → appliquer
                btn.clicked.connect(
                    lambda checked, n=name: self.engine.apply(n)
                )
            else:
                # ── Sans dropdown — bouton simple ──────
                btn.setPopupMode(QToolButton.DelayedPopup)
                btn.clicked.connect(
                    lambda checked, n=name: self.engine.apply(n)
                )

            # Checkable
            btn.setCheckable(True)
            if self.engine.get_current_perspective() == name:
                btn.setChecked(True)

            action = self.toolbar.addWidget(btn)
            self.perspective_actions[name] = action
            self.perspective_buttons[name] = btn

    def _on_perspective_btn(self, name: str):
        self.engine.apply(name)

    def _on_perspective_changed(self, name: str):
        """Synchronise l'état enfoncé des boutons."""
        if name == "__reload__":
            return  # ← juste un signal de reload, pas une perspective
        for perspective_name, btn in self.perspective_buttons.items():
            btn.setChecked(perspective_name == name)

    # ─────────────────────────────────────────
    # MENU DROPDOWN
    # ─────────────────────────────────────────

    def _build_perspective_menu(self, name: str) -> QMenu:
        menu = QMenu()
        data = self.engine.config_io.load(name)

        dropdown_menus = data.get("dropdown_menus", [])
        
        print(f"[DEBUG menu] perspective: {name}")
        print(f"[DEBUG menu] dropdown_menus: {dropdown_menus}")

        # Compatibilité ancienne structure
        if dropdown_menus and isinstance(dropdown_menus[0], str):
            old_plugin     = data.get("dropdown_plugin", "")
            dropdown_menus = [
                {"plugin": old_plugin, "menu": m}
                for m in dropdown_menus
            ]
            print(f"[DEBUG menu] converti ancienne structure: {dropdown_menus}")

        if dropdown_menus:
            self._append_plugin_menus(menu, dropdown_menus)
        else:
            print(f"[DEBUG menu] pas de menus → dropdown vide")

        return menu

    def _append_plugin_menus(self, menu: QMenu, dropdown_menus: list):
        registry = self.engine.get_registry()

        plugins_seen = set()

        for item in dropdown_menus:
            plugin_name = item["plugin"]
            menu_name   = item["menu"]

            print(f"[DEBUG append] plugin: {plugin_name} | menu: {menu_name}")

            plugin_data = registry.get(plugin_name, {})
            all_menus   = plugin_data.get("menus", [])

            print(f"[DEBUG append] menus disponibles: {[m['name'] for m in all_menus]}")

            menu_info = next(
                (m for m in all_menus if m["name"] == menu_name),
                None
            )
            
            print(f"[DEBUG append] menu_info trouvé: {menu_info is not None}")

            if not menu_info:
                continue

            original_menu = menu_info["object"]
            
            print(f"[DEBUG append] is_valid: {is_valid(original_menu)}")

            if not is_valid(original_menu):
                continue

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
        Copie récursive d'un QMenu.
        Les actions déclenchent le comportement original du plugin.
        """
        copied_menu = QMenu(source_menu.title(), parent)
        copied_menu.setIcon(source_menu.icon())

        for action in source_menu.actions():
            if action.isSeparator():
                copied_menu.addSeparator()

            elif action.menu():
                # Sous-menu → récursion
                sub = self._copy_menu(action.menu(), copied_menu)
                copied_menu.addMenu(sub)

            else:
                # Action simple → connecter au trigger original
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

    def _append_active_widgets(self, menu: QMenu, data: dict):
        """
        Ajoute uniquement les widgets visibles ET cochés
        dans la perspective — sans doublons.
        """
        plugins_data = data.get("plugins", {})
        registry     = self.engine.get_registry()

        if not plugins_data:
            return

        # Collecter les widgets visibles sans doublons
        visible_docks    = []
        visible_toolbars = []
        seen_names       = set()  # ← éviter les doublons

        for plugin_name, plugin_data in plugins_data.items():

            for dock in plugin_data.get("docks", []):
                if dock.get("visible") and dock["name"] not in seen_names:
                    seen_names.add(dock["name"])
                    visible_docks.append(dock)

            for tb in plugin_data.get("toolbars", []):
                if tb.get("visible") and tb["name"] not in seen_names:
                    seen_names.add(tb["name"])
                    visible_toolbars.append(tb)

        if not visible_docks and not visible_toolbars:
            return

        menu.addSeparator()
        label = QAction("── Widgets actifs ──", menu)
        label.setEnabled(False)
        menu.addAction(label)

        for dock in visible_docks:
            a = QAction(f"🪟  {dock['label']}", menu)
            a.setEnabled(False)
            menu.addAction(a)

        for tb in visible_toolbars:
            a = QAction(f"🔧  {tb['label']}", menu)
            a.setEnabled(False)
            menu.addAction(a)
    # ─────────────────────────────────────────
    # ACTIONS TOOLBAR
    # ─────────────────────────────────────────

    def _open_perspective(self, name: str):
        """Ouvre la MainWindow sur la perspective donnée."""
        self.run()
        if self.main_window:
            items = self.main_window.listPerspectives.findItems(
                name, Qt.MatchExactly
            )
            if items:
                self.main_window.listPerspectives.setCurrentItem(
                    items[0]
                )

    def _duplicate_perspective(self, name: str):
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