import os
from qgis.PyQt.QtWidgets import QAction, QToolBar
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from .core.perspectiveEngine import PerspectiveEngine
from .ui.main_window import MainWindow


class PerspectiveManager:

    def __init__(self, iface):
        self.iface            = iface
        self.plugin_dir       = os.path.dirname(__file__)
        self.first_start      = True
        self.main_window      = None
        self.engine           = None
        self.toolbar          = None
        self.perspective_actions = {}  # { name: QAction }

    def initGui(self):
        # ── Moteur ────────────────────────────────
        self.engine = PerspectiveEngine()
        self.engine.initialize()

        # ── Toolbar du plugin ──────────────────────
        self.toolbar = QToolBar("Gestionnaire de Perspectives")
        self.toolbar.setObjectName("PerspectiveManagerToolbar")
        self.iface.addToolBar(self.toolbar)

        # Bouton ouvrir la fenêtre principale
        self.action_open = QAction(
            QIcon(os.path.join(self.plugin_dir, "icon.png")),
            "Gérer les perspectives",
            self.iface.mainWindow()
        )
        self.action_open.triggered.connect(self.run)
        self.toolbar.addAction(self.action_open)
        self.iface.addPluginToMenu("Gestionnaire de Perspectives", self.action_open)

        # Séparateur
        self.toolbar.addSeparator()

        # Boutons des perspectives
        self._refresh_toolbar()

        # Écouter le signal perspectiveChanged
        self.engine.perspectiveChanged.connect(self._on_perspective_changed)

    def unload(self):
        self.iface.removePluginMenu("Gestionnaire de Perspectives", self.action_open)
        if self.toolbar:
            self.toolbar.deleteLater()
        if self.main_window:
            self.main_window.close()
        del self.action_open

    def run(self):
        """Ouvre la fenêtre principale."""
        if self.first_start:
            self.first_start = False
            self.main_window = MainWindow(
                engine=self.engine,
                parent=self.iface.mainWindow()
            )
            # Rafraîchir la toolbar quand une perspective est sauvegardée/supprimée
            self.main_window.perspectiveSaved.connect(self._refresh_toolbar)

        self.main_window.show()
        self.main_window.raise_()

    # ─────────────────────────────────────────────
    # TOOLBAR BOUTONS
    # ─────────────────────────────────────────────

    def _refresh_toolbar(self):
        """Recrée les boutons de perspectives dans la toolbar."""
        for action in self.perspective_actions.values():
            self.toolbar.removeAction(action)
        self.perspective_actions.clear()

        for name in self.engine.list_perspectives():
            action = QAction(name, self.iface.mainWindow())
            action.setToolTip(f"Activer : {name}")
            action.setCheckable(True)

            # Icône spéciale pour la perspective QGIS
            if name == "QGIS":
                action.setIcon(
                    QIcon(os.path.join(self.plugin_dir, "icon.png"))
                )

            action.triggered.connect(
                lambda checked, n=name: self._on_perspective_btn(n)
            )
            self.toolbar.addAction(action)
            self.perspective_actions[name] = action

        current = self.engine.get_current_perspective()
        if current and current in self.perspective_actions:
            self.perspective_actions[current].setChecked(True)

    def _on_perspective_btn(self, name: str):
        """Applique la perspective et met le bouton en état actif."""
        self.engine.apply(name)

    def _on_perspective_changed(self, name: str):
        """
        Quand une perspective est appliquée
        → enfonce le bon bouton, relâche les autres.
        """
        for perspective_name, action in self.perspective_actions.items():
            action.setChecked(perspective_name == name)