import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog, QTreeWidgetItem, QComboBox,
    QCheckBox, QInputDialog, QMessageBox
)
from qgis.PyQt.QtCore import Qt, pyqtSignal

from qgis.PyQt.QtWidgets import QSpinBox


from ..applicators.state_capture import StateCapture

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'main_window.ui')
)

PROTECTED_PERSPECTIVES = ["QGIS"]

class MainWindow(QDialog, FORM_CLASS):

    perspectiveSaved = pyqtSignal()


    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("Gestionnaire de Perspectives")
        self.engine = engine

        # ── Connecter les boutons ──────────────────
        self.btnAdd.clicked.connect(self._on_add)
        self.btnDuplicate.clicked.connect(self._on_duplicate)
        self.btnDelete.clicked.connect(self._on_delete)
        self.btnApply.clicked.connect(self._on_apply)
        self.btnSave.clicked.connect(self._on_save)
        self.btnCapture.clicked.connect(self._on_capture)

        # ── Remplir l'interface ────────────────────
        self._refresh_list()
        self._populate_tree()

        # ── Sélection dans la liste ────────────────
        self.listPerspectives.currentTextChanged.connect(self._on_perspective_selected)

    # ─────────────────────────────────────────────
    # LISTE DES PERSPECTIVES
    # ─────────────────────────────────────────────

    def _refresh_list(self):
        """Recharge la liste en conservant la sélection courante."""
        # Mémoriser la sélection courante
        current_name = self.inputName.text().strip()

        # Bloquer les signaux pendant le rechargement
        self.listPerspectives.blockSignals(True)
        self.listPerspectives.clear()
        for name in self.engine.list_perspectives():
            self.listPerspectives.addItem(name)
        self.listPerspectives.blockSignals(False)

        # Restaurer la sélection si elle existe encore
        if current_name:
            items = self.listPerspectives.findItems(
                current_name, Qt.MatchExactly
            )
            if items:
                self.listPerspectives.blockSignals(True)
                self.listPerspectives.setCurrentItem(items[0])
                self.listPerspectives.blockSignals(False)
                # Garder le panneau central visible
                self._set_editor_visible(True)

    def _on_perspective_selected(self, name: str):
        """
        Quand l'utilisateur clique sur une perspective :
        - Met à jour le champ nom
        - Charge les sélections dans le tree
        """
        if not name:
            self._set_editor_visible(False)
            return

        self.inputName.setText(name)
        self._set_editor_visible(True)        # ← cache le label, montre le tree
        self._load_perspective_in_tree(name)  # ← charge les sélections dans le tree

    # ─────────────────────────────────────────────
    # TREE — PLUGINS / DOCKS / TOOLBARS
    # ─────────────────────────────────────────────

    def _populate_tree(self):
        """Remplit les deux trees depuis le registre."""
        self._populate_docks_tree()
        self._populate_toolbars_tree()

    def _populate_docks_tree(self):
        """Remplit le QTreeWidget des panneaux (treeDocks)."""
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
                continue  # ← ignorer les plugins sans docks

            # Niveau 0 — Plugin parent
            plugin_item = QTreeWidgetItem(self.treeDocks)
            plugin_item.setText(0, plugin_data["display_name"])
            plugin_item.setFlags(plugin_item.flags() | Qt.ItemIsUserCheckable)
            plugin_item.setCheckState(0, Qt.Unchecked)
            plugin_item.setExpanded(True)

            # Niveau 1 — Docks
            for dock_info in docks:
                self._add_dock_item(plugin_item, dock_info)

        self.treeDocks.itemChanged.connect(self._on_dock_item_changed)

    def _populate_toolbars_tree(self):
        """Remplit le QTreeWidget des toolbars (treeToolbars)."""
        self.treeToolbars.clear()
        self.treeToolbars.setColumnCount(3)
        self.treeToolbars.setHeaderLabels(["Nom", "Zone", "Ligne"])
        self.treeToolbars.setColumnWidth(0, 220)
        self.treeToolbars.setColumnWidth(1, 100)
        self.treeToolbars.setColumnWidth(2, 55)

        registry = self.engine.get_registry()

        for plugin_name, plugin_data in registry.items():
            toolbars = plugin_data.get("toolbars", [])
            if not toolbars:
                continue  # ← ignorer les plugins sans toolbars

            # Niveau 0 — Plugin parent
            plugin_item = QTreeWidgetItem(self.treeToolbars)
            plugin_item.setText(0, plugin_data["display_name"])
            plugin_item.setFlags(plugin_item.flags() | Qt.ItemIsUserCheckable)
            plugin_item.setCheckState(0, Qt.Unchecked)
            plugin_item.setExpanded(True)

            # Niveau 1 — Toolbars
            for tb_info in toolbars:
                self._add_toolbar_item(plugin_item, tb_info)

        self.treeToolbars.itemChanged.connect(self._on_toolbar_item_changed)

    def _add_dock_item(self, parent_item, dock_info: dict):
        """Ajoute un dock dans treeDocks."""
        child = QTreeWidgetItem(parent_item)
        child.setText(0, dock_info["label"])
        child.setText(1, "dock")

        child.setData(0, Qt.UserRole, dock_info["name"])
        child.setData(1, Qt.UserRole, "dock")

        # Colonne 2 — Zone
        combo = QComboBox()
        combo.addItems(["left", "right", "top", "bottom"])
        current_area = dock_info.get("area", "left")
        idx = combo.findText(current_area)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self.treeDocks.setItemWidget(child, 2, combo)

        # Checkbox colonne 0
        child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
        child.setCheckState(0, Qt.Unchecked)

        return child

    def _add_toolbar_item(self, parent_item, tb_info: dict):
        """Ajoute une toolbar dans treeToolbars."""
        child = QTreeWidgetItem(parent_item)
        child.setText(0, tb_info["label"])

        child.setData(0, Qt.UserRole, tb_info["name"])
        child.setData(1, Qt.UserRole, "toolbar")

        # Colonne 1 — Zone
        combo = QComboBox()
        combo.addItems(["top", "bottom", "left", "right"])
        current_area = tb_info.get("area", "top")
        idx = combo.findText(current_area)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self.treeToolbars.setItemWidget(child, 1, combo)

        # Colonne 2 — Ligne
        spinbox = QSpinBox()
        spinbox.setMinimum(1)
        spinbox.setMaximum(5)
        spinbox.setValue(tb_info.get("line", 1))
        spinbox.setToolTip("Ligne dans la zone")
        self.treeToolbars.setItemWidget(child, 2, spinbox)

        # Checkbox colonne 0
        child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
        child.setCheckState(0, Qt.Unchecked)

        return child

    def _on_dock_item_changed(self, item, column):
        """Met à jour la checkbox parent dans treeDocks."""
        if column != 0:
            return
        parent = item.parent()
        if parent is None:
            return
        self._update_parent_check(self.treeDocks, parent)

    def _on_toolbar_item_changed(self, item, column):
        """Met à jour la checkbox parent dans treeToolbars."""
        if column != 0:
            return
        parent = item.parent()
        if parent is None:
            return
        self._update_parent_check(self.treeToolbars, parent)

    def _update_parent_check(self, tree, parent):
        """Met à jour l'état de la checkbox parent."""
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
    # ACTIONS BOUTONS
    # ─────────────────────────────────────────────

    def _on_apply(self):
        """Applique la perspective sélectionnée."""
        name = self.listPerspectives.currentItem()
        if not name:
            QMessageBox.warning(self, "Attention", "Sélectionne une perspective.")
            return
        self.engine.apply(name.text())

    def _on_save(self):
        """Sauvegarde la perspective depuis l'état du tree."""
        name = self.inputName.text().strip()
        if not name:
            QMessageBox.warning(self, "Attention", "Donne un nom à la perspective.")
            return

        data = self._build_data_from_tree(name)
        self.engine.save_from_data(name, data)
        self._refresh_list()          # ← refresh sans perdre la sélection
        self.perspectiveSaved.emit()

    def _on_capture(self):
        """
        Capture l'état courant de QGIS :
        1. Rescanne les plugins
        2. Sauvegarde le YAML
        3. Recharge le tree avec la capture fraîche
        """
        name = self.inputName.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Attention",
                "Sélectionne ou crée une perspective d'abord."
            )
            return

        # Rescanner avant de capturer
        self.engine.registry = self.engine.discovery.scan()
        self.engine.state_capture = StateCapture(self.engine.discovery)

        # Sauvegarder l'état actuel
        self.engine.save(name)

        # Recharger le tree avec la capture fraîche
        self._load_perspective_in_tree(name)

        # Rafraîchir la liste et la toolbar
        self._refresh_list()
        self.perspectiveSaved.emit()

        QMessageBox.information(
            self, "Capturé",
            f"Perspective '{name}' mise à jour depuis l'état actuel de QGIS."
        )

    def _on_add(self):
        """
        Crée une nouvelle perspective vide :
        1. Demande le nom
        2. Crée le YAML vide
        3. Sélectionne la perspective dans la liste
        4. Vide toutes les checkboxes du tree
        """
        name, ok = QInputDialog.getText(
            self,
            "Nouvelle perspective",
            "Nom de la perspective :"
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        if name in self.engine.list_perspectives():
            QMessageBox.warning(self, "Nom existant",
                f"Une perspective '{name}' existe déjà.")
            return

        # Créer avec l'état actuel comme base
        success = self.engine.add_perspective(name)
        if not success:
            QMessageBox.critical(self, "Erreur",
                "Impossible de créer la perspective.")
            return

        self._refresh_list()
        self.perspectiveSaved.emit()

        # Sélectionner la nouvelle perspective
        items = self.listPerspectives.findItems(name, Qt.MatchExactly)
        if items:
            self.listPerspectives.setCurrentItem(items[0])

        # Afficher le panneau central
        self.inputName.setText(name)
        self._set_editor_visible(True)

        # Charger l'état actuel dans le tree
        # → l'utilisateur voit ce qui est visible maintenant
        self._load_perspective_in_tree(name)

    def _reset_tree(self):
        """
        Décoche tous les widgets du tree.
        Appelé quand une nouvelle perspective vide est créée.
        """
        for tree in [self.treeDocks, self.treeToolbars]:
            tree.blockSignals(True)
            for i in range(tree.topLevelItemCount()):
                plugin_item = tree.topLevelItem(i)
                plugin_item.setCheckState(0, Qt.Unchecked)
                for j in range(plugin_item.childCount()):
                    child = plugin_item.child(j)
                    child.setCheckState(0, Qt.Unchecked)
                    combo = tree.itemWidget(child, 
                        2 if tree == self.treeDocks else 1)
                    if combo:
                        combo.setCurrentIndex(0)
            tree.blockSignals(False)

    def _load_perspective_in_tree(self, name: str):
        """
        Charge une perspective existante dans le tree —
        coche les docks/toolbars selon ce qui est sauvegardé.
        Appelé quand l'utilisateur sélectionne une perspective existante.
        """
        data = self.engine.config_io.load(name)
        if not data:
            self._reset_tree()
            return

        registry      = self.engine.get_registry()
        plugin_names  = list(registry.keys())

        # ── Charger treeDocks ─────────────────────
        self.treeDocks.blockSignals(True)
        plugins_with_docks = [
            pn for pn in plugin_names
            if registry[pn].get("docks")
        ]

        for i in range(self.treeDocks.topLevelItemCount()):
            plugin_item = self.treeDocks.topLevelItem(i)
            plugin_name = plugins_with_docks[i]
            plugin_data = data.get("plugins", {}).get(plugin_name, {})
            saved_docks = {d["name"]: d for d in plugin_data.get("docks", [])}

            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                saved       = saved_docks.get(widget_name)

                if saved:
                    state = Qt.Checked if saved.get("visible", True) else Qt.Unchecked
                    child.setCheckState(0, state)

                    combo = self.treeDocks.itemWidget(child, 2)
                    if combo:
                        idx = combo.findText(saved.get("area", "left"))
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                else:
                    child.setCheckState(0, Qt.Unchecked)

        self.treeDocks.blockSignals(False)

        # ── Charger treeToolbars ──────────────────
        self.treeToolbars.blockSignals(True)
        plugins_with_toolbars = [
            pn for pn in plugin_names
            if registry[pn].get("toolbars")
        ]

        for i in range(self.treeToolbars.topLevelItemCount()):
            plugin_item  = self.treeToolbars.topLevelItem(i)
            plugin_name  = plugins_with_toolbars[i]
            plugin_data  = data.get("plugins", {}).get(plugin_name, {})
            saved_toolbars = {t["name"]: t for t in plugin_data.get("toolbars", [])}

            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                saved       = saved_toolbars.get(widget_name)

                if saved:
                    state = Qt.Checked if saved.get("visible", True) else Qt.Unchecked
                    child.setCheckState(0, state)

                    # Zone
                    combo = self.treeToolbars.itemWidget(child, 1)
                    if combo:
                        idx = combo.findText(saved.get("area", "top"))
                        if idx >= 0:
                            combo.setCurrentIndex(idx)

                    # Ligne ← nouveau
                    spinbox = self.treeToolbars.itemWidget(child, 2)
                    if spinbox:
                        spinbox.setValue(saved.get("line", 1))
                else:
                    child.setCheckState(0, Qt.Unchecked)

        self.treeToolbars.blockSignals(False)
    def _on_duplicate(self):
        """Duplique la perspective sélectionnée."""
        item = self.listPerspectives.currentItem()
        if not item:
            return
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self, "Dupliquer", "Nouveau nom :",
            text=f"{old_name} - copie"
        )
        if ok and new_name.strip():
            data = self.engine.config_io.load(old_name)
            data["name"] = new_name.strip()
            self.engine.save_from_data(new_name.strip(), data)
            self._refresh_list()

    

    def _on_delete(self):
        item = self.listPerspectives.currentItem()
        if not item:
            return

        name = item.text()

        # Protéger la perspective par défaut
        if name in PROTECTED_PERSPECTIVES:
            QMessageBox.warning(
                self, "Protégée",
                f"La perspective '{name}' est la perspective par défaut — elle ne peut pas être supprimée."
            )
            return

        reply = QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la perspective '{name}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.delete(name)
            self._refresh_list()
            self._reset_tree()
            self._set_editor_visible(False)
            self.perspectiveSaved.emit()

    # ─────────────────────────────────────────────
    # CONSTRUIRE LE DICT DEPUIS LE TREE
    # ─────────────────────────────────────────────

    def _build_data_from_tree(self, name: str) -> dict:
        data = {"name": name, "plugins": {}}
        registry     = self.engine.get_registry()
        plugin_names = list(registry.keys())

        # ── Lire treeDocks ────────────────────────
        plugins_with_docks = [
            pn for pn in plugin_names
            if registry[pn].get("docks")
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
                data["plugins"][plugin_name] = {"docks": [], "toolbars": []}
            data["plugins"][plugin_name]["docks"] = docks_cfg

        # ── Lire treeToolbars ─────────────────────
        plugins_with_toolbars = [
            pn for pn in plugin_names
            if registry[pn].get("toolbars")
        ]
        for i in range(self.treeToolbars.topLevelItemCount()):
            plugin_item  = self.treeToolbars.topLevelItem(i)
            plugin_name  = plugins_with_toolbars[i]
            toolbars_cfg = []

            for j in range(plugin_item.childCount()):
                child       = plugin_item.child(j)
                widget_name = child.data(0, Qt.UserRole)
                visible     = child.checkState(0) == Qt.Checked
                combo       = self.treeToolbars.itemWidget(child, 1)
                area        = combo.currentText() if combo else "top"
                spinbox     = self.treeToolbars.itemWidget(child, 2)
                line        = spinbox.value() if spinbox else 1

                toolbars_cfg.append({
                    "name":    widget_name,
                    "label":   child.text(0),
                    "visible": visible,
                    "area":    area,
                    "line":    line,
                })

            if plugin_name not in data["plugins"]:
                data["plugins"][plugin_name] = {"docks": [], "toolbars": []}
            data["plugins"][plugin_name]["toolbars"] = toolbars_cfg

        return data
    

    def _set_editor_visible(self, visible: bool):
        self.inputName.setVisible(visible)
        self.btnCapture.setVisible(visible)
        self.tabWidget.setVisible(visible)
        self.btnApply.setVisible(visible)
        self.btnSave.setVisible(visible)
        self.btnDuplicate.setVisible(visible)
        self.labelPlaceholder.setVisible(not visible)