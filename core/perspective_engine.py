# coding: utf-8

"""
Main engine module of the QWorkspace Switcher plugin.

This module provides the :class:`PerspectiveEngine` class, the orchestrator
of the plugin. It coordinates
:class:`~perspective_manager.core.plugin_discovery.PluginDiscovery`,
:class:`~perspective_manager.core.config_io.ConfigIO` and the applicators
to apply workspaces on the QGIS interface.

**Workspace application flow:**

.. code-block:: text

    apply("Field survey")
        │
        ├── Pass 1 — _hide_all()
        │       → hides all docks and toolbars
        │
        ├── Pass 2 — DockApplicator.apply()
        │       → positions and shows docks
        │
        ├── Pass 3 — ToolbarApplicator.apply_all()
        │       → positions and shows toolbars
        │
        └── Pass 4 — menuBar().setVisible()
                → shows/hides the QGIS menu bar

**Excluded toolbars** (never repositioned):

- ``QWorkspaceSwitcherToolbar`` — the plugin's own toolbar.
- ``QToolBar`` — widgets without a valid name.

**Linked toolbars** (automatically follow their dock):

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


#: Toolbars linked to a dock — visibility follows the dock via Qt signal.
LINKED_TOOLBARS = {
    "mBrowserToolbar",
    "mAdvancedDigitizeToolBar",
    "mGpsToolBar",
    "mBookmarkToolbar",
    "processingToolbar",
}

#: Excluded toolbars — never hidden or repositioned by the plugin.
EXCLUDED_TOOLBARS = {
    "QWorkspaceSwitcherToolbar",
    "QToolBar",
}


class PerspectiveEngine(QObject):
    """
    Orchestrator of the QWorkspace Switcher plugin.

    Coordinates plugin discovery, configuration management
    and workspace application on the QGIS interface.

    **Responsibilities:**

    - Scan installed QGIS plugins via :class:`PluginDiscovery`.
    - Read and write workspaces via :class:`ConfigIO`.
    - Apply workspaces (docks, toolbars, menu bar).
    - Maintain automatic dock ↔ toolbar links.
    - Emit :attr:`perspectiveChanged` on changes.

    :example:

    .. code-block:: python

        engine = PerspectiveEngine()
        engine.initialize()
        engine.apply("Field survey")
    """

    perspectiveChanged = pyqtSignal(str)
    """
    Signal emitted after a workspace is applied.

    Transmits the name of the applied workspace, or ``"__reload__"``
    on external configuration reload.
    """

    DEFAULT_PERSPECTIVE_NAME = "QGIS"
    """Name of the default workspace created on first startup."""

    def __init__(self):
        """
        Initialize the engine with applicators set to ``None``.

        Applicators are instantiated in :meth:`initialize`
        after the plugin scan.
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
    # INITIALIZATION
    # ─────────────────────────────────────────────

    def initialize(self):
        """
        Initialize the engine at plugin startup.

        Performs in order:

        1. Scan installed QGIS plugins.
        2. Instantiate applicators.
        3. Create default ``QGIS`` workspace if absent.
        4. Connect dock ↔ toolbar links.
        5. Connect to :attr:`ConfigIO.configChanged` signal.
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
        Called when ``user.psp.json`` is modified from outside.

        Emits :attr:`perspectiveChanged` with the special value
        ``"__reload__"`` to trigger a UI refresh without
        applying a workspace.
        """
        self.perspectiveChanged.emit("__reload__")

    def _ensure_default_perspective(self):
        """
        Create the default ``QGIS`` workspace if absent or empty.

        Checks that the workspace contains at least one visible widget.
        If not, captures the current QGIS interface state and saves
        it as the default workspace.

        .. note::
            The ``QGIS`` workspace is protected against deletion
            in the user interface.
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
    # WORKSPACES — LIST
    # ─────────────────────────────────────────────

    def list_perspectives(self) -> list:
        """
        Return the list of all workspace names.

        Includes both user and plugin workspaces.

        :return: List of workspace names.
        :rtype: list[str]
        """
        return self.config_io.list_all()

    def list_perspectives_merged(self) -> list:
        """
        Alias for :meth:`list_perspectives`.

        Kept for compatibility with toolbar calls.

        :return: List of workspace names.
        :rtype: list[str]
        """
        return self.config_io.list_all_merged()

    # ─────────────────────────────────────────────
    # WORKSPACES — CREATE
    # ─────────────────────────────────────────────

    def add_perspective(self, name: str) -> bool:
        """
        Create a new workspace by capturing the current QGIS state.

        Rescans plugins before capture to ensure valid Qt references.

        :param name: Name of the new workspace.
        :type name: str
        :return: ``True`` if created, ``False`` if name already exists.
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
    # WORKSPACES — APPLY
    # ─────────────────────────────────────────────

    def apply(self, name: str):
        """
        Load and apply a workspace by name.

        Performs four successive passes:

        1. Hide all docks and toolbars.
        2. Apply dock configuration.
        3. Apply toolbar configuration.
        4. Show or hide the QGIS menu bar.

        Emits :attr:`perspectiveChanged` on success.

        :param name: Name of the workspace to apply.
        :type name: str
        """
        # Rescan to get valid Qt references
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
            # Pass 1 — hide all
            self._hide_all()

            # Pass 2 — apply docks
            for plugin_name, plugin_data in data.get("plugins", {}).items():
                self.dock_applicator.apply(
                    plugin_name,
                    plugin_data.get("docks", [])
                )

            # Pass 3 — apply toolbars
            all_toolbars = {
                plugin_name: plugin_data.get("toolbars", [])
                for plugin_name, plugin_data in data.get(
                    "plugins", {}
                ).items()
            }
            self.toolbar_applicator.apply_all(all_toolbars)

            # Pass 4 — menu bar
            show_menu_bar = data.get("show_menu_bar", True)
            iface.mainWindow().menuBar().setVisible(show_menu_bar)

            self.current_perspective = name
            self.perspectiveChanged.emit(name)

        except Exception as e:
            print(f"[Engine] Error applying workspace '{name}': {e}")

        finally:
            main_win.setUpdatesEnabled(True)

    def _hide_all(self):
        """
        Hide all docks and toolbars from the QGIS interface.

        Respects exclusions:

        - :data:`EXCLUDED_TOOLBARS` — never hidden.
        - :data:`LINKED_TOOLBARS` — managed automatically by their dock.

        Docks linked to a toolbar (via :meth:`_connect_dock_toolbar_links`)
        automatically propagate their visibility to their associated toolbar.
        """
        for plugin_data in self.registry.values():

            # Hide docks
            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]
                if not is_valid(dock):
                    continue
                try:
                    dock.setVisible(False)
                except RuntimeError:
                    pass

            # Hide toolbars
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
    # WORKSPACES — SAVE
    # ─────────────────────────────────────────────

    def save(self, name: str):
        """
        Capture the current QGIS interface state and save it.

        :param name: Name of the workspace to update.
        :type name: str
        """
        data = self.state_capture.capture(name)
        self.config_io.save(name, data)

    def save_from_data(self, name: str, data: dict):
        """
        Save a workspace from a dictionary.

        Used by the user interface after manual modification
        via :class:`~perspective_manager.ui.main_window.MainWindow`.

        :param name: Name of the workspace.
        :type name: str
        :param data: Complete workspace dictionary.
        :type data: dict
        """
        self.config_io.save(name, data)

    # ─────────────────────────────────────────────
    # WORKSPACES — DELETE / RENAME
    # ─────────────────────────────────────────────

    def delete(self, name: str):
        """
        Delete a workspace.

        Resets :attr:`current_perspective` if the deleted workspace
        was the active one.

        :param name: Name of the workspace to delete.
        :type name: str
        """
        self.config_io.delete(name)
        if self.current_perspective == name:
            self.current_perspective = None

    def rename(self, old_name: str, new_name: str):
        """
        Rename a workspace.

        Updates :attr:`current_perspective` if the renamed workspace
        was the active one.

        :param old_name: Current name of the workspace.
        :type old_name: str
        :param new_name: New name of the workspace.
        :type new_name: str
        """
        self.config_io.rename(old_name, new_name)
        if self.current_perspective == old_name:
            self.current_perspective = new_name

    # ─────────────────────────────────────────────
    # REGISTRY ACCESS
    # ─────────────────────────────────────────────

    def get_registry(self) -> dict:
        """
        Return the discovered widget registry.

        Used by the user interface to populate
        dock and toolbar trees.

        :return: Registry of plugins and their widgets.
        :rtype: dict
        """
        return self.registry

    def get_current_perspective(self) -> str:
        """
        Return the name of the currently active workspace.

        :return: Name of the active workspace, or ``None``.
        :rtype: str or None
        """
        return self.current_perspective

    # ─────────────────────────────────────────────
    # DOCK ↔ TOOLBAR LINKS
    # ─────────────────────────────────────────────

    def _connect_dock_toolbar_links(self):
        """
        Connect Qt signals to synchronize toolbar visibility
        with their associated dock.

        When a dock is shown or hidden, its linked toolbar
        follows automatically via the ``visibilityChanged`` signal.

        **Configured links:**

        .. code-block:: text

            Browser              → mBrowserToolbar
            Browser2             → mBrowserToolbar
            AdvancedDigitizingTools → mAdvancedDigitizeToolBar
            GPSInformation       → mGpsToolBar
            BookmarksDockWidget  → mBookmarkToolbar
            ProcessingToolbox    → processingToolbar

        .. note::
            Existing connections are disconnected before
            reconnecting to avoid duplicates.
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

        # Build toolbar index (first occurrence only)
        toolbar_index = {}
        for tb in main_win.findChildren(QToolBar):
            name = tb.objectName()
            if name and name not in toolbar_index:
                toolbar_index[name] = tb

        # Build dock index
        dock_index = {}
        for dock in main_win.findChildren(QDockWidget):
            name = dock.objectName()
            if name and name not in dock_index:
                dock_index[name] = dock

        # Connect links
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