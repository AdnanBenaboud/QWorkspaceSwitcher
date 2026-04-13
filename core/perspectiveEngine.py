from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QDockWidget, QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface

from .plugin_discovery import PluginDiscovery
from .config_io import ConfigIO

from ..applicators.dock_applicator import DockApplicator
from ..applicators.toolbar_applicator import ToolbarApplicator
from ..applicators.state_capture import StateCapture

from .plugin_discovery import is_valid



class PerspectiveEngine(QObject):
    """
    Chef d'orchestre du plugin.
    - Coordonne PluginDiscovery et ConfigIO
    - Applique les perspectives sur l'interface QGIS
    - Expose le signal perspectiveChanged
    """

    # Signal émis quand une perspective est appliquée
    perspectiveChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.discovery = PluginDiscovery()
        self.config_io = ConfigIO()
        self.registry = {}
        self.current_perspective = None

        # Applicateurs — initialisés à None, créés dans initialize()
        self.dock_applicator    = None
        self.toolbar_applicator = None
        self.state_capture      = None

    # ─────────────────────────────────────────
    # INITIALISATION
    # ─────────────────────────────────────────
    DEFAULT_PERSPECTIVE_NAME = "QGIS"

    def initialize(self):
        """
        Initialise le moteur :
        1. Scanne les plugins
        2. Instancie les applicateurs
        3. Crée la perspective QGIS par défaut si elle n'existe pas
        """
        self.registry = self.discovery.scan()

        self.dock_applicator    = DockApplicator(self.discovery)
        self.toolbar_applicator = ToolbarApplicator(self.discovery)
        self.state_capture      = StateCapture(self.discovery)

        # Créer la perspective par défaut si première utilisation
        self._ensure_default_perspective()

        print(f"[Engine] {len(self.registry)} plugins détectés")

    def _ensure_default_perspective(self):
        """
        Crée la perspective 'QGIS' par défaut
        si elle n'existe pas encore.
        Capture l'état actuel au premier démarrage.
        """
        if self.DEFAULT_PERSPECTIVE_NAME in self.config_io.list_all():
            return  # ← déjà créée — ne pas écraser

        print("[Engine] Création de la perspective QGIS par défaut...")
        data = self.state_capture.capture(self.DEFAULT_PERSPECTIVE_NAME)
        self.config_io.save(self.DEFAULT_PERSPECTIVE_NAME, data)
        print("[Engine] Perspective QGIS par défaut créée ✓")

    # ─────────────────────────────────────────
    # PERSPECTIVES — LISTE
    # ─────────────────────────────────────────

    def list_perspectives(self) -> list:
        """Retourne la liste des noms de perspectives disponibles."""
        return self.config_io.list_all()

    # ─────────────────────────────────────────
    # PERSPECTIVES — APPLIQUER
    # ─────────────────────────────────────────

    def add_perspective(self, name: str) -> bool:
        """
        Crée une nouvelle perspective avec l'état actuel
        de QGIS comme point de départ.
        """
        if name in self.config_io.list_all():
            return False

        # Rescanner avant de capturer — garantit des références valides
        self.registry = self.discovery.scan()
        self.state_capture = StateCapture(self.discovery)

        data = self.state_capture.capture(name)
        self.config_io.save(name, data)
        print(f"[Engine] Nouvelle perspective créée : {name}")
        return True
        
    # ─────────────────────────────────────────
    # PERSPECTIVES — APPLIQUER
    # ─────────────────────────────────────────

    def apply(self, name: str):
        """
        Charge et applique une perspective par son nom.
        Émet perspectiveChanged si succès.
        """
        # Rescanner
        self.registry = self.discovery.scan()
        self.dock_applicator    = DockApplicator(self.discovery)
        self.toolbar_applicator = ToolbarApplicator(self.discovery)
        self.state_capture      = StateCapture(self.discovery)

        data = self.config_io.load(name)
        if not data:
            print(f"[Engine] Perspective introuvable : {name}")
            return

        main_win = iface.mainWindow()
        main_win.setUpdatesEnabled(False)

        try:
            # ── Passe 1 — Cacher tout ─────────────
            self._hide_all()

            # ── Passe 2 — Appliquer les docks ─────
            for plugin_name, plugin_data in data.get("plugins", {}).items():
                self.dock_applicator.apply(
                    plugin_name,
                    plugin_data.get("docks", [])
                )

            # ── Passe 3 — Appliquer les toolbars ──
            # Collecter toutes les toolbars de tous les plugins
            all_toolbars = {
                plugin_name: plugin_data.get("toolbars", [])
                for plugin_name, plugin_data in data.get("plugins", {}).items()
            }
            # Appliquer en une seule passe avec gestion des lignes
            self.toolbar_applicator.apply_all(all_toolbars)

            self.current_perspective = name
            self.perspectiveChanged.emit(name)
            print(f"[Engine] Perspective appliquée : {name}")

        except Exception as e:
            print(f"[Engine] Erreur : {e}")

        finally:
            main_win.setUpdatesEnabled(True)

    def _hide_all(self):
        """
        Cache tous les docks et toolbars connus dans le registre.
        Exclut la toolbar du plugin lui-même.
        """
        EXCLUDED_TOOLBARS = ["PerspectiveManagerToolbar"]

        for plugin_data in self.registry.values():

            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]
                if not is_valid(dock):
                    continue
                try:
                    dock.setVisible(False)
                except RuntimeError:
                    pass

            for tb_info in plugin_data.get("toolbars", []):
                tb = tb_info["object"]
                if tb_info["name"] in EXCLUDED_TOOLBARS:
                    continue
                if not is_valid(tb):
                    continue
                try:
                    tb.setVisible(False)
                except RuntimeError:
                    pass

    # ─────────────────────────────────────────
    # PERSPECTIVES — SAUVEGARDER
    # ─────────────────────────────────────────

    def save(self, name: str):
        """
        Capture l'état courant de l'interface
        et le sauvegarde comme perspective.
        """
        data = self.state_capture.capture(name)
        self.config_io.save(name, data)
        print(f"[Engine] Perspective sauvegardée : {name}")

    def save_from_data(self, name: str, data: dict):
        """
        Sauvegarde une perspective depuis un dict
        (construit par l'éditeur UI).
        """
        self.config_io.save(name, data)

    # ─────────────────────────────────────────
    # PERSPECTIVES — SUPPRIMER / RENOMMER
    # ─────────────────────────────────────────

    def delete(self, name: str):
        """Supprime une perspective."""
        self.config_io.delete(name)
        if self.current_perspective == name:
            self.current_perspective = None

    def rename(self, old_name: str, new_name: str):
        """Renomme une perspective."""
        self.config_io.rename(old_name, new_name)
        if self.current_perspective == old_name:
            self.current_perspective = new_name

    # ─────────────────────────────────────────
    # CAPTURE ÉTAT COURANT
    # ─────────────────────────────────────────

    def _capture_current_state(self, name: str) -> dict:
        """
        Photographie l'état actuel de tous les
        docks et toolbars dans le registre.
        """
        data = {"name": name, "plugins": {}}
        main_win = iface.mainWindow()

        for plugin_name, plugin_data in self.registry.items():
            docks_state = []
            toolbars_state = []

            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]
                area = main_win.dockWidgetArea(dock)
                docks_state.append({
                    "name":    dock_info["name"],
                    "label":   dock_info["label"],
                    "visible": dock.isVisible(),
                    "area":    self.discovery._area_to_str(area),
                })

            for tb_info in plugin_data.get("toolbars", []):
                tb = tb_info["object"]
                area = main_win.toolBarArea(tb)
                toolbars_state.append({
                    "name":    tb_info["name"],
                    "label":   tb_info["label"],
                    "visible": tb.isVisible(),
                    "area":    self.discovery._area_to_str(area),
                })

            if docks_state or toolbars_state:
                data["plugins"][plugin_name] = {
                    "docks":    docks_state,
                    "toolbars": toolbars_state,
                }

        return data

    # ─────────────────────────────────────────
    # APPLIQUER DOCK / TOOLBAR
    # ─────────────────────────────────────────

    def _apply_dock(self, dock: QDockWidget, config: dict):
        """Applique la config sur un QDockWidget."""
        main_win = iface.mainWindow()
        area = self.discovery.str_to_area(config.get("area", "left"))

        # Réancrer si flottant
        if dock.isFloating():
            dock.setFloating(False)

        main_win.addDockWidget(area, dock)
        dock.setVisible(config.get("visible", True))

    def _apply_toolbar(self, toolbar: QToolBar, config: dict):
        """Applique la config sur une QToolBar."""
        main_win = iface.mainWindow()
        area_str = config.get("area", "top")

        area_map = {
            "top":    Qt.TopToolBarArea,
            "bottom": Qt.BottomToolBarArea,
            "left":   Qt.LeftToolBarArea,
            "right":  Qt.RightToolBarArea,
        }
        area = area_map.get(area_str, Qt.TopToolBarArea)

        if toolbar.isFloating():
            toolbar.setFloating(False)

        main_win.addToolBar(area, toolbar)
        toolbar.setVisible(config.get("visible", True))

    # ─────────────────────────────────────────
    # RECHERCHE WIDGETS
    # ─────────────────────────────────────────

    def _find_dock(self, name: str):
        """Cherche un QDockWidget par nom dans le registre."""
        for plugin_data in self.registry.values():
            for dock_info in plugin_data.get("docks", []):
                if dock_info["name"] == name:
                    return dock_info["object"]
        return None

    def _find_toolbar(self, name: str):
        """Cherche une QToolBar par nom dans le registre."""
        for plugin_data in self.registry.values():
            for tb_info in plugin_data.get("toolbars", []):
                if tb_info["name"] == name:
                    return tb_info["object"]
        return None

    # ─────────────────────────────────────────
    # ACCÈS REGISTRE (pour l'UI)
    # ─────────────────────────────────────────

    def get_registry(self) -> dict:
        """Retourne le registre pour alimenter l'éditeur UI."""
        return self.registry

    def get_current_perspective(self) -> str:
        """Retourne le nom de la perspective active."""
        return self.current_perspective