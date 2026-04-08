import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog, QTreeWidgetItem, QComboBox,
    QCheckBox, QInputDialog, QMessageBox
)
from qgis.PyQt.QtCore import Qt

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), 'main_window.ui')
)


class MainWindow(QDialog, FORM_CLASS):

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
        """Recharge la liste des perspectives depuis l'engine."""
        self.listPerspectives.clear()
        for name in self.engine.list_perspectives():
            self.listPerspectives.addItem(name)

    def _on_perspective_selected(self, name: str):
        """Quand l'utilisateur clique sur une perspective — met à jour le champ nom."""
        if name:
            self.inputName.setText(name)

    # ─────────────────────────────────────────────
    # TREE — PLUGINS / DOCKS / TOOLBARS
    # ─────────────────────────────────────────────

    def _populate_tree(self):
        """
        Remplit le QTreeWidget avec tous les plugins
        et leurs docks/toolbars détectés.
        """
        self.treeWidgets.clear()
        self.treeWidgets.setColumnCount(4)
        self.treeWidgets.setHeaderLabels(["Nom", "Type", "Zone", "Visible"])
        self.treeWidgets.setColumnWidth(0, 220)
        self.treeWidgets.setColumnWidth(1, 70)
        self.treeWidgets.setColumnWidth(2, 90)
        self.treeWidgets.setColumnWidth(3, 60)

        registry = self.engine.get_registry()

        for plugin_name, plugin_data in registry.items():
            # ── Niveau 0 — Plugin parent ──────────
            plugin_item = QTreeWidgetItem(self.treeWidgets)
            plugin_item.setText(0, plugin_data["display_name"])
            plugin_item.setFlags(
                plugin_item.flags() | Qt.ItemIsUserCheckable
            )
            plugin_item.setCheckState(0, Qt.Unchecked)
            plugin_item.setExpanded(True)

            # ── Niveau 1 — Docks ──────────────────
            for dock_info in plugin_data.get("docks", []):
                self._add_widget_item(plugin_item, dock_info, "dock")

            # ── Niveau 1 — Toolbars ───────────────
            for tb_info in plugin_data.get("toolbars", []):
                self._add_widget_item(plugin_item, tb_info, "toolbar")

        # Mettre à jour les checkboxes parents quand enfant change
        self.treeWidgets.itemChanged.connect(self._on_item_changed)

    def _add_widget_item(self, parent_item, widget_info: dict, widget_type: str):
        """Ajoute un dock ou toolbar comme enfant dans le tree."""
        child = QTreeWidgetItem(parent_item)
        child.setText(0, widget_info["label"])
        child.setText(1, widget_type)

        # Stocker le nom technique pour la sauvegarde
        child.setData(0, Qt.UserRole, widget_info["name"])
        child.setData(1, Qt.UserRole, widget_type)

        # Colonne 2 — QComboBox zone
        combo = QComboBox()
        if widget_type == "dock":
            combo.addItems(["left", "right", "top", "bottom"])
        else:
            combo.addItems(["top", "bottom", "left", "right"])

        # Pré-sélectionner la zone actuelle
        current_area = widget_info.get("area", "left")
        idx = combo.findText(current_area)
        if idx >= 0:
            combo.setCurrentIndex(idx)

        self.treeWidgets.setItemWidget(child, 2, combo)

        # Colonne 3 — Checkbox visible
        chk = QCheckBox()
        chk.setChecked(widget_info.get("visible", True))
        self.treeWidgets.setItemWidget(child, 3, chk)

        # Checkbox principale (colonne 0)
        child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
        child.setCheckState(0, Qt.Checked if widget_info.get("visible") else Qt.Unchecked)

        return child

    def _on_item_changed(self, item, column):
        """Met à jour la checkbox parent selon l'état des enfants."""
        if column != 0:
            return

        parent = item.parent()
        if parent is None:
            return

        # Compter les enfants cochés
        total   = parent.childCount()
        checked = sum(
            1 for i in range(total)
            if parent.child(i).checkState(0) == Qt.Checked
        )

        # Bloquer le signal pour éviter la récursion
        self.treeWidgets.blockSignals(True)
        if checked == 0:
            parent.setCheckState(0, Qt.Unchecked)
        elif checked == total:
            parent.setCheckState(0, Qt.Checked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)
        self.treeWidgets.blockSignals(False)

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
        self._refresh_list()

    def _on_capture(self):
        """Capture l'état courant de QGIS et remplit le tree."""
        name = self.inputName.text().strip() or "Nouvelle perspective"
        self.engine.save(name)
        self._refresh_list()
        QMessageBox.information(
            self, "Capturé",
            f"Perspective '{name}' sauvegardée depuis l'état actuel."
        )

    def _on_add(self):
        """Crée une nouvelle perspective vide."""
        name, ok = QInputDialog.getText(
            self, "Nouvelle perspective", "Nom :"
        )
        if ok and name.strip():
            self.inputName.setText(name.strip())
            self._refresh_list()

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
        """Supprime la perspective sélectionnée."""
        item = self.listPerspectives.currentItem()
        if not item:
            return
        name = item.text()
        reply = QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la perspective '{name}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.delete(name)
            self._refresh_list()

    # ─────────────────────────────────────────────
    # CONSTRUIRE LE DICT DEPUIS LE TREE
    # ─────────────────────────────────────────────

    def _build_data_from_tree(self, name: str) -> dict:
        """
        Parcourt le QTreeWidget et construit le dict
        de la perspective à sauvegarder.
        """
        data = {"name": name, "plugins": {}}
        registry = self.engine.get_registry()
        plugin_names = list(registry.keys())

        for i in range(self.treeWidgets.topLevelItemCount()):
            plugin_item = self.treeWidgets.topLevelItem(i)
            plugin_name = plugin_names[i]

            docks_cfg    = []
            toolbars_cfg = []

            for j in range(plugin_item.childCount()):
                child = plugin_item.child(j)

                widget_name = child.data(0, Qt.UserRole)
                widget_type = child.data(1, Qt.UserRole)
                visible     = child.checkState(0) == Qt.Checked

                # Lire la zone depuis le QComboBox
                combo = self.treeWidgets.itemWidget(child, 2)
                area  = combo.currentText() if combo else "left"

                entry = {
                    "name":    widget_name,
                    "label":   child.text(0),
                    "visible": visible,
                    "area":    area,
                }

                if widget_type == "dock":
                    docks_cfg.append(entry)
                else:
                    toolbars_cfg.append(entry)

            data["plugins"][plugin_name] = {
                "docks":    docks_cfg,
                "toolbars": toolbars_cfg,
            }

        return data