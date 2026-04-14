import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog, QTreeWidgetItem, QComboBox,
    QInputDialog, QMessageBox, QSpinBox
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from ..applicators.state_capture import StateCapture

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'main_window.ui')
)

PROTECTED_PERSPECTIVES = ["QGIS"]

HIDDEN_TOOLBARS = {
    "QToolBar",
    "mBrowserToolbar",
    "mAdvancedDigitizeToolBar",
    "mGpsToolBar",
    "mBookmarkToolbar",
    "processingToolbar",
}


class MainWindow(QDialog, FORM_CLASS):

    perspectiveSaved = pyqtSignal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("Gestionnaire de Perspectives")
        self.engine             = engine
        self._current_icon_path = ""

        # Construire les widgets dynamiques D'ABORD
        self._build_style_widgets()

        # Cacher le panneau central
        self._set_editor_visible(False)

        # Connecter les boutons
        self.btnAdd.clicked.connect(self._on_add)
        self.btnDuplicate.clicked.connect(self._on_duplicate)
        self.btnDelete.clicked.connect(self._on_delete)
        self.btnApply.clicked.connect(self._on_apply)
        self.btnSave.clicked.connect(self._on_save)
        self.btnCapture.clicked.connect(self._on_capture)
        self.pushButton_expor_perspectives.clicked.connect(
            self._export_perspectives_json
        )

        # Remplir la liste
        self._refresh_list()
        self._populate_tree()

        # Signal sélection
        self.listPerspectives.currentTextChanged.connect(
            self._on_perspective_selected
        )

    # ─────────────────────────────────────────────
    # CONFIGURATION DU BOUTON
    # ─────────────────────────────────────────────

    def _build_style_widgets(self):
        """Configure les widgets créés dans Qt Designer."""

        # checkBox_icon
        self.checkBox_icon.stateChanged.connect(
            self._on_icon_checkbox_changed
        )
        self.comboBox_emplacement.addItems(
            ["text", "icon", "icon_text", "text_icon"]
        )
        self.comboBox_emplacement.setToolTip(
            "<b>Style du bouton :</b><br>"
            "• <b>text</b> → texte seulement<br>"
            "• <b>icon</b> → icône seulement<br>"
            "• <b>icon_text</b> → icône à gauche + texte<br>"
            "• <b>text_icon</b> → texte à gauche + icône à droite"
        )
        self.comboBox_emplacement.setEnabled(False)
        self.pushButton_importIcon.setEnabled(False)
        self.pushButton_importIcon.clicked.connect(self._on_choose_icon)

        # checkBox_ajoutMenu
        self.checkBox_ajoutMenu.stateChanged.connect(
            self._on_menu_checkbox_changed
        )
        self.treeWidget_menu.setEnabled(False)

        # checkBox_menuBar — True par défaut
        self.checkBox_menuBar.setChecked(True)
        self.checkBox_menuBar.setToolTip(
            "Afficher ou cacher la barre de menus QGIS "
            "quand cette perspective est appliquée"
        )

    def _on_icon_checkbox_changed(self, state: int):
        enabled = state == Qt.Checked
        self.comboBox_emplacement.setEnabled(enabled)
        self.pushButton_importIcon.setEnabled(enabled)
        if not enabled:
            self._current_icon_path = ""
            self.pushButton_importIcon.setIcon(QIcon())
            self.pushButton_importIcon.setText("Choisir l'icône")

    def _on_menu_checkbox_changed(self, state: int):
        self.treeWidget_menu.setEnabled(state == Qt.Checked)
        if state != Qt.Checked:
            self.treeWidget_menu.blockSignals(True)
            for i in range(self.treeWidget_menu.topLevelItemCount()):
                plugin_item = self.treeWidget_menu.topLevelItem(i)
                plugin_item.setCheckState(0, Qt.Unchecked)
                for j in range(plugin_item.childCount()):
                    plugin_item.child(j).setCheckState(0, Qt.Unchecked)
            self.treeWidget_menu.blockSignals(False)

    def _on_choose_icon(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une icône", "",
            "Images (*.png *.jpg *.svg *.ico)"
        )
        if path:
            self._current_icon_path = path
            self.pushButton_importIcon.setIcon(QIcon(path))
            self.pushButton_importIcon.setText(os.path.basename(path))

    # ─────────────────────────────────────────────
    # EXPORT
    # ─────────────────────────────────────────────

    def _export_perspectives_json(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        import shutil

        source_path = self.engine.config_io.config_path
        if not os.path.exists(source_path):
            QMessageBox.warning(
                self, "Fichier introuvable",
                "Aucun fichier perspectives.json à exporter."
            )
            return

        dest_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les perspectives",
            os.path.join(os.path.expanduser("~"), "perspectives.json"),
            "JSON (*.json)"
        )
        if not dest_path:
            return

        try:
            shutil.copy2(source_path, dest_path)
            QMessageBox.information(
                self, "Export réussi",
                f"Perspectives exportées vers :\n{dest_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur export",
                f"Impossible d'exporter le fichier :\n{e}"
            )

    # ─────────────────────────────────────────────
    # LISTE DES PERSPECTIVES
    # ─────────────────────────────────────────────

    def _refresh_list(self):
        current_name = self.inputName.text().strip()

        self.listPerspectives.blockSignals(True)
        self.listPerspectives.clear()
        for name in self.engine.list_perspectives():
            self.listPerspectives.addItem(name)
        self.listPerspectives.blockSignals(False)

        if current_name:
            items = self.listPerspectives.findItems(
                current_name, Qt.MatchExactly
            )
            if items:
                self.listPerspectives.blockSignals(True)
                self.listPerspectives.setCurrentItem(items[0])
                self.listPerspectives.blockSignals(False)
                self._set_editor_visible(True)

    def _on_perspective_selected(self, name: str):
        if not name:
            self._set_editor_visible(False)
            return
        self.inputName.setText(name)
        self._set_editor_visible(True)
        self._load_perspective_in_tree(name)

    # ─────────────────────────────────────────────
    # TREES
    # ─────────────────────────────────────────────

    def _populate_tree(self):
        self._populate_docks_tree()
        self._populate_toolbars_tree()
        self._populate_menus_tree()

    def _populate_docks_tree(self):
        self.treeDocks.clear()
        self.treeDocks.setColumnCount(3)
        self.treeDocks.setHeaderLabels(["Nom", "Type", "Zone"])
        self.treeDocks.setColumnWidth(0, 220)
        self.treeDocks.setColumnWidth(1, 70)
        self.treeDocks.setColumnWidth(2, 100)

        registry = self.engine.get_registry()

        for plugin_name, plugin_data in registry.items():
            docks = plugin_data.get("docks", [])
            if not docks:
                continue

            plugin_item = QTreeWidgetItem(self.treeDocks)
            plugin_item.setText(0, plugin_data["display_name"])
            plugin_item.setFlags(
                plugin_item.flags() | Qt.ItemIsUserCheckable
            )
            plugin_item.setCheckState(0, Qt.Unchecked)
            plugin_item.setExpanded(True)

            for dock_info in docks:
                self._add_dock_item(plugin_item, dock_info)

        self.treeDocks.itemChanged.connect(self._on_dock_item_changed)

    def _populate_toolbars_tree(self, perspective_data: dict = None):
        try:
            self.treeToolbars.itemChanged.disconnect()
        except Exception:
            pass

        self.treeToolbars.clear()
        self.treeToolbars.setColumnCount(2)
        self.treeToolbars.setHeaderLabels(["Nom", "Ligne"])
        self.treeToolbars.setColumnWidth(0, 300)
        self.treeToolbars.setColumnWidth(1, 60)

        registry = self.engine.get_registry()

        for plugin_name, plugin_data in registry.items():
            toolbars = plugin_data.get("toolbars", [])
            if not toolbars:
                continue

            visible_toolbars = [
                tb for tb in toolbars
                if tb["name"] not in HIDDEN_TOOLBARS and tb["name"]
            ]
            if not visible_toolbars:
                continue

            saved_toolbars = {}
            if perspective_data:
                saved_toolbars = {
                    t["name"]: t
                    for t in perspective_data.get(
                        "plugins", {}
                    ).get(plugin_name, {}).get("toolbars", [])
                }

            plugin_item = QTreeWidgetItem(self.treeToolbars)
            plugin_item.setText(0, plugin_data["display_name"])
            plugin_item.setFlags(
                plugin_item.flags() | Qt.ItemIsUserCheckable
            )
            plugin_item.setCheckState(0, Qt.Unchecked)
            plugin_item.setExpanded(True)

            for tb_info in visible_toolbars:
                saved = saved_toolbars.get(tb_info["name"], {})
                line  = saved.get("line", tb_info.get("line", 1))
                self._add_toolbar_item(
                    plugin_item, tb_info, saved_line=line
                )

        self.treeToolbars.itemChanged.connect(self._on_toolbar_item_changed)

    def _populate_menus_tree(self):
        self.treeWidget_menu.clear()
        self.treeWidget_menu.setColumnCount(1)
        self.treeWidget_menu.setHeaderLabels(["Menu"])
        self.treeWidget_menu.setColumnWidth(0, 300)

        registry = self.engine.get_registry()

        for plugin_name, plugin_data in registry.items():
            menus = plugin_data.get("menus", [])
            if not menus:
                continue

            plugin_item = QTreeWidgetItem(self.treeWidget_menu)
            plugin_item.setText(0, plugin_data["display_name"])
            plugin_item.setFlags(
                plugin_item.flags() | Qt.ItemIsUserCheckable
            )
            plugin_item.setCheckState(0, Qt.Unchecked)
            plugin_item.setExpanded(True)

            for menu_info in menus:
                child = QTreeWidgetItem(plugin_item)
                child.setText(0, menu_info["label"])
                child.setData(0, Qt.UserRole, menu_info["name"])
                child.setData(1, Qt.UserRole, plugin_name)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)

        self.treeWidget_menu.itemChanged.connect(
            self._on_menu_item_changed
        )

    def _add_dock_item(self, parent_item, dock_info: dict):
        child = QTreeWidgetItem(parent_item)
        child.setText(0, dock_info["label"])
        child.setText(1, "dock")
        child.setData(0, Qt.UserRole, dock_info["name"])
        child.setData(1, Qt.UserRole, "dock")

        combo = QComboBox()
        combo.addItems(["left", "right", "top", "bottom"])
        idx = combo.findText(dock_info.get("area", "left"))
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self.treeDocks.setItemWidget(child, 2, combo)

        child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
        child.setCheckState(0, Qt.Unchecked)
        return child

    def _add_toolbar_item(self, parent_item, tb_info: dict,
                          saved_line: int = 1):
        child = QTreeWidgetItem(parent_item)
        child.setText(0, tb_info["label"])
        child.setData(0, Qt.UserRole, tb_info["name"])
        child.setData(1, Qt.UserRole, "toolbar")

        spinbox = QSpinBox()
        spinbox.setMinimum(1)
        spinbox.setMaximum(5)
        spinbox.setValue(saved_line)
        spinbox.setToolTip("Ligne dans la zone")
        self.treeToolbars.setItemWidget(child, 1, spinbox)

        child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
        child.setCheckState(0, Qt.Unchecked)
        return child

    # ─────────────────────────────────────────────
    # SIGNALS TREE
    # ─────────────────────────────────────────────

    def _on_dock_item_changed(self, item, column):
        if column != 0:
            return
        parent = item.parent()
        if parent is None:
            return
        self._update_parent_check(self.treeDocks, parent)

    def _on_toolbar_item_changed(self, item, column):
        if column != 0:
            return
        parent = item.parent()
        if parent is None:
            return
        self._update_parent_check(self.treeToolbars, parent)

    def _on_menu_item_changed(self, item, column):
        if column != 0:
            return
        parent = item.parent()
        if parent is None:
            return
        self._update_parent_check(self.treeWidget_menu, parent)

    def _update_parent_check(self, tree, parent):
        total   = parent.childCount()
        checked = sum(
            1 for i in range(total)
            if parent.child(i).checkState(0) == Qt.Checked
        )
        tree.blockSignals(True)
        if checked == 0:
            parent.setCheckState(0, Qt.Unchecked)
        elif checked == total:
            parent.setCheckState(0, Qt.Checked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)
        tree.blockSignals(False)

    # ─────────────────────────────────────────────
    # CHARGER PERSPECTIVE DANS LE TREE
    # ─────────────────────────────────────────────

    def _load_perspective_in_tree(self, name: str):
        data = self.engine.config_io.load(name)
        if not data:
            self._reset_tree()
            return

        # ── Icône ─────────────────────────────────
        icon_path    = data.get("icon", "")
        button_style = data.get("button_style", "text")
        if icon_path:
            self.checkBox_icon.blockSignals(True)
            self.checkBox_icon.setChecked(True)
            self.checkBox_icon.blockSignals(False)
            self._current_icon_path = icon_path
            self.comboBox_emplacement.setEnabled(True)
            self.pushButton_importIcon.setEnabled(True)
            idx = self.comboBox_emplacement.findText(button_style)
            if idx >= 0:
                self.comboBox_emplacement.setCurrentIndex(idx)
            if os.path.exists(icon_path):
                self.pushButton_importIcon.setIcon(QIcon(icon_path))
                self.pushButton_importIcon.setText(
                    os.path.basename(icon_path)
                )
        else:
            self.checkBox_icon.blockSignals(True)
            self.checkBox_icon.setChecked(False)
            self.checkBox_icon.blockSignals(False)
            self._current_icon_path = ""
            self.comboBox_emplacement.setEnabled(False)
            self.pushButton_importIcon.setEnabled(False)
            self.pushButton_importIcon.setIcon(QIcon())
            self.pushButton_importIcon.setText("Choisir l'icône")

        # ── Barre de menus ─────────────────────────
        show_menu_bar = data.get("show_menu_bar", True)
        self.checkBox_menuBar.blockSignals(True)
        self.checkBox_menuBar.setChecked(show_menu_bar)
        self.checkBox_menuBar.blockSignals(False)

        # ── Menus dropdown ─────────────────────────
        dropdown_menus = data.get("dropdown_menus", [])

        if dropdown_menus and isinstance(dropdown_menus[0], str):
            old_plugin     = data.get("dropdown_plugin", "")
            dropdown_menus = [
                {"plugin": old_plugin, "menu": m}
                for m in dropdown_menus
            ]

        has_menus = bool(dropdown_menus)
        self.checkBox_ajoutMenu.blockSignals(True)
        self.checkBox_ajoutMenu.setChecked(has_menus)
        self.checkBox_ajoutMenu.blockSignals(False)
        self.treeWidget_menu.setEnabled(has_menus)

        selected_set = {
            (item["plugin"], item["menu"])
            for item in dropdown_menus
        }

        self.treeWidget_menu.blockSignals(True)
        for i in range(self.treeWidget_menu.topLevelItemCount()):
            plugin_item = self.treeWidget_menu.topLevelItem(i)
            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                menu_name   = child.data(0, Qt.UserRole)
                plugin_name = child.data(1, Qt.UserRole)
                if (plugin_name, menu_name) in selected_set:
                    child.setCheckState(0, Qt.Checked)
                else:
                    child.setCheckState(0, Qt.Unchecked)
        self.treeWidget_menu.blockSignals(False)

        # ── Repeupler treeToolbars ─────────────────
        self._populate_toolbars_tree(perspective_data=data)

        # ── treeDocks ─────────────────────────────
        registry     = self.engine.get_registry()
        plugin_names = list(registry.keys())

        self.treeDocks.blockSignals(True)
        plugins_with_docks = [
            pn for pn in plugin_names if registry[pn].get("docks")
        ]
        for i in range(self.treeDocks.topLevelItemCount()):
            plugin_item = self.treeDocks.topLevelItem(i)
            plugin_name = plugins_with_docks[i]
            plugin_data = data.get("plugins", {}).get(plugin_name, {})
            saved_docks = {
                d["name"]: d for d in plugin_data.get("docks", [])
            }
            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                saved       = saved_docks.get(widget_name)
                if saved:
                    state = Qt.Checked if saved.get("visible", True) \
                            else Qt.Unchecked
                    child.setCheckState(0, state)
                    combo = self.treeDocks.itemWidget(child, 2)
                    if combo:
                        idx = combo.findText(saved.get("area", "left"))
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                else:
                    child.setCheckState(0, Qt.Unchecked)
        self.treeDocks.blockSignals(False)

        # ── treeToolbars — cocher les widgets ─────
        HIDDEN_TB = {
            "PerspectiveManagerToolbar", "QToolBar",
            "mBrowserToolbar", "mAdvancedDigitizeToolBar",
            "mGpsToolBar", "mBookmarkToolbar", "processingToolbar",
        }
        plugins_with_toolbars = [
            pn for pn in plugin_names
            if any(
                t["name"] not in HIDDEN_TB and t["name"]
                for t in registry[pn].get("toolbars", [])
            )
        ]

        self.treeToolbars.blockSignals(True)
        for i in range(self.treeToolbars.topLevelItemCount()):
            plugin_item    = self.treeToolbars.topLevelItem(i)
            plugin_name    = plugins_with_toolbars[i]
            plugin_data    = data.get("plugins", {}).get(plugin_name, {})
            saved_toolbars = {
                t["name"]: t for t in plugin_data.get("toolbars", [])
            }
            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                saved       = saved_toolbars.get(widget_name)
                if saved:
                    state = Qt.Checked if saved.get("visible", True) \
                            else Qt.Unchecked
                    child.setCheckState(0, state)
                else:
                    child.setCheckState(0, Qt.Unchecked)
        self.treeToolbars.blockSignals(False)

    # ─────────────────────────────────────────────
    # RESET TREE
    # ─────────────────────────────────────────────

    def _reset_tree(self):
        for tree in [self.treeDocks, self.treeToolbars]:
            tree.blockSignals(True)
            for i in range(tree.topLevelItemCount()):
                plugin_item = tree.topLevelItem(i)
                plugin_item.setCheckState(0, Qt.Unchecked)
                for j in range(plugin_item.childCount()):
                    child = plugin_item.child(j)
                    child.setCheckState(0, Qt.Unchecked)
                    if tree == self.treeDocks:
                        combo = tree.itemWidget(child, 2)
                        if combo:
                            combo.setCurrentIndex(0)
                    else:
                        spinbox = tree.itemWidget(child, 1)
                        if spinbox:
                            spinbox.setValue(1)
            tree.blockSignals(False)

        self.treeWidget_menu.blockSignals(True)
        for i in range(self.treeWidget_menu.topLevelItemCount()):
            plugin_item = self.treeWidget_menu.topLevelItem(i)
            plugin_item.setCheckState(0, Qt.Unchecked)
            for j in range(plugin_item.childCount()):
                plugin_item.child(j).setCheckState(0, Qt.Unchecked)
        self.treeWidget_menu.blockSignals(False)

        # Réinitialiser checkboxes
        self.checkBox_icon.blockSignals(True)
        self.checkBox_icon.setChecked(False)
        self.checkBox_icon.blockSignals(False)
        self.checkBox_ajoutMenu.blockSignals(True)
        self.checkBox_ajoutMenu.setChecked(False)
        self.checkBox_ajoutMenu.blockSignals(False)
        self.checkBox_menuBar.blockSignals(True)
        self.checkBox_menuBar.setChecked(True)   # ← True par défaut
        self.checkBox_menuBar.blockSignals(False)
        self._current_icon_path = ""
        self.pushButton_importIcon.setIcon(QIcon())
        self.pushButton_importIcon.setText("Choisir l'icône")
        self.comboBox_emplacement.setEnabled(False)
        self.comboBox_emplacement.setCurrentIndex(0)
        self.pushButton_importIcon.setEnabled(False)
        self.treeWidget_menu.setEnabled(False)

    # ─────────────────────────────────────────────
    # ACTIONS BOUTONS
    # ─────────────────────────────────────────────

    def _on_apply(self):
        name = self.listPerspectives.currentItem()
        if not name:
            QMessageBox.warning(
                self, "Attention", "Sélectionne une perspective."
            )
            return
        self.engine.apply(name.text())

    def _on_save(self):
        name = self.inputName.text().strip()
        if not name:
            QMessageBox.warning(self, "Attention", "Donne un nom.")
            return

        data = self._build_data_from_tree(name)

        # Style et icône
        if self.checkBox_icon.isChecked():
            data["button_style"] = self.comboBox_emplacement.currentText()
            data["icon"]         = self._current_icon_path
        else:
            data["button_style"] = "text"
            data["icon"]         = ""

        # Barre de menus ← nouveau
        data["show_menu_bar"] = self.checkBox_menuBar.isChecked()

        # Menus dropdown
        if self.checkBox_ajoutMenu.isChecked():
            dropdown_menus = self._get_selected_menus()
        else:
            dropdown_menus = []
        data["dropdown_menus"] = dropdown_menus

        self.engine.save_from_data(name, data)
        self._refresh_list()
        self.perspectiveSaved.emit()

        QMessageBox.information(
            self, "Sauvegardé",
            f"Perspective '{name}' sauvegardée ✓"
        )

    def _get_selected_menus(self) -> list:
        selected = []
        for i in range(self.treeWidget_menu.topLevelItemCount()):
            plugin_item = self.treeWidget_menu.topLevelItem(i)
            for j in range(plugin_item.childCount()):
                child = plugin_item.child(j)
                if child.checkState(0) == Qt.Checked:
                    selected.append({
                        "plugin": child.data(1, Qt.UserRole),
                        "menu":   child.data(0, Qt.UserRole),
                    })
        return selected

    def _on_capture(self):
        name = self.inputName.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Attention",
                "Sélectionne ou crée une perspective d'abord."
            )
            return

        self.engine.registry      = self.engine.discovery.scan()
        self.engine.state_capture = StateCapture(self.engine.discovery)
        self.engine.save(name)
        self._load_perspective_in_tree(name)
        self._refresh_list()
        self.perspectiveSaved.emit()

        QMessageBox.information(
            self, "Capturé",
            f"Perspective '{name}' mise à jour depuis l'état actuel de QGIS."
        )

    def _on_add(self):
        name, ok = QInputDialog.getText(
            self, "Nouvelle perspective", "Nom de la perspective :"
        )
        if not ok or not name.strip():
            return

        name = name.strip()

        if name in self.engine.list_perspectives():
            QMessageBox.warning(self, "Nom existant",
                f"Une perspective '{name}' existe déjà.")
            return

        success = self.engine.add_perspective(name)
        if not success:
            QMessageBox.critical(self, "Erreur",
                "Impossible de créer la perspective.")
            return

        self._refresh_list()
        self.perspectiveSaved.emit()

        items = self.listPerspectives.findItems(name, Qt.MatchExactly)
        if items:
            self.listPerspectives.setCurrentItem(items[0])

        self.inputName.setText(name)
        self._set_editor_visible(True)
        self._load_perspective_in_tree(name)

    def _on_duplicate(self):
        item = self.listPerspectives.currentItem()
        if not item:
            return
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self, "Dupliquer", "Nouveau nom :",
            text=f"{old_name} - copie"
        )
        if ok and new_name.strip():
            data         = self.engine.config_io.load(old_name)
            data["name"] = new_name.strip()
            self.engine.save_from_data(new_name.strip(), data)
            self._refresh_list()
            self.perspectiveSaved.emit()

    def _on_delete(self):
        item = self.listPerspectives.currentItem()
        if not item:
            return

        name = item.text()

        if name in PROTECTED_PERSPECTIVES:
            QMessageBox.warning(
                self, "Protégée",
                f"La perspective '{name}' ne peut pas être supprimée."
            )
            return

        reply = QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la perspective '{name}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.delete(name)
            self.inputName.clear()
            self.listPerspectives.blockSignals(True)
            self.listPerspectives.clear()
            for n in self.engine.list_perspectives():
                self.listPerspectives.addItem(n)
            self.listPerspectives.blockSignals(False)
            self.perspectiveSaved.emit()
            self._reset_tree()
            self._set_editor_visible(False)

    # ─────────────────────────────────────────────
    # CONSTRUIRE LE DICT DEPUIS LE TREE
    # ─────────────────────────────────────────────

    def _build_data_from_tree(self, name: str) -> dict:
        data         = {"name": name, "plugins": {}}
        registry     = self.engine.get_registry()
        plugin_names = list(registry.keys())

        # ── treeDocks ─────────────────────────────
        plugins_with_docks = [
            pn for pn in plugin_names if registry[pn].get("docks")
        ]
        for i in range(self.treeDocks.topLevelItemCount()):
            plugin_item = self.treeDocks.topLevelItem(i)
            plugin_name = plugins_with_docks[i]
            docks_cfg   = []

            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                visible     = child.checkState(0) == Qt.Checked
                combo       = self.treeDocks.itemWidget(child, 2)
                area        = combo.currentText() if combo else "left"

                docks_cfg.append({
                    "name":    widget_name,
                    "label":   child.text(0),
                    "visible": visible,
                    "area":    area,
                })

            if plugin_name not in data["plugins"]:
                data["plugins"][plugin_name] = {
                    "docks": [], "toolbars": []
                }
            data["plugins"][plugin_name]["docks"] = docks_cfg

        # ── treeToolbars ──────────────────────────
        plugins_with_toolbars = [
            pn for pn in plugin_names if registry[pn].get("toolbars")
        ]
        for i in range(self.treeToolbars.topLevelItemCount()):
            plugin_item  = self.treeToolbars.topLevelItem(i)
            plugin_name  = plugins_with_toolbars[i]
            toolbars_cfg = []

            existing = {
                t["name"]: t
                for t in self.engine.config_io.load(
                    self.inputName.text().strip()
                ).get("plugins", {}).get(plugin_name, {}).get("toolbars", [])
            }

            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                visible     = child.checkState(0) == Qt.Checked
                spinbox     = self.treeToolbars.itemWidget(child, 1)
                line        = spinbox.value() if spinbox else 1

                existing_tb = existing.get(widget_name)
                if existing_tb:
                    area = existing_tb.get("area", "top")
                else:
                    reg_tbs = registry.get(plugin_name, {}).get("toolbars", [])
                    reg_tb  = next(
                        (t for t in reg_tbs if t["name"] == widget_name), {}
                    )
                    area = reg_tb.get("area", "top")

                toolbars_cfg.append({
                    "name":    widget_name,
                    "label":   child.text(0),
                    "visible": visible,
                    "area":    area,
                    "line":    line,
                })

            if plugin_name not in data["plugins"]:
                data["plugins"][plugin_name] = {
                    "docks": [], "toolbars": []
                }
            data["plugins"][plugin_name]["toolbars"] = toolbars_cfg

        return data

    # ─────────────────────────────────────────────
    # VISIBILITÉ PANNEAU CENTRAL
    # ─────────────────────────────────────────────

    def _set_editor_visible(self, visible: bool):
        self.inputName.setVisible(visible)
        self.btnCapture.setVisible(visible)
        self.tabWidget.setVisible(visible)
        self.btnApply.setVisible(visible)
        self.btnSave.setVisible(visible)
        self.btnDuplicate.setVisible(visible)
        self.checkBox_menuBar.setVisible(visible)  # ← nouveau
        self.labelPlaceholder.setVisible(not visible)
        if hasattr(self, 'groupConfig'):
            self.groupConfig.setVisible(visible)