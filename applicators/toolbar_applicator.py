# coding: utf-8

"""
Toolbar configuration applicator module.

This module provides the :class:`ToolbarApplicator` class, responsible for
positioning and displaying :class:`QToolBar` according to the
workspace configuration.

**Excluded toolbars** (never repositioned):

- ``QWorkspaceSwitcherToolbar`` — the plugin's own toolbar.
- ``QToolBar`` — widgets without a valid name.

**Linked toolbars** (managed automatically by their dock via Qt signal):

- ``mBrowserToolbar``
- ``mAdvancedDigitizeToolBar``
- ``mGpsToolBar``
- ``mBookmarkToolbar``
- ``processingToolbar``

**Line management:**

Toolbars are organized by area (``top``, ``bottom``, ``left``,
``right``) and by line number. An ``insertToolBarBreak`` is inserted
before the first toolbar of each line > 1.

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface

from ..core.plugin_discovery import is_valid


#: Toolbars never repositioned by the plugin.
EXCLUDED_TOOLBARS = {
    "QWorkspaceSwitcherToolbar",
    "QToolBar",
}

#: Toolbars linked to a dock — visibility follows the dock via Qt signal.
LINKED_TOOLBARS = {
    "mBrowserToolbar",
    "mAdvancedDigitizeToolBar",
    "mGpsToolBar",
    "mBookmarkToolbar",
    "processingToolbar",
}


class ToolbarApplicator:
    """
    Apply toolbar configuration to the QGIS interface.

    Positions :class:`QToolBar` in the main window areas
    respecting the line order. The ``QWorkspaceSwitcherToolbar``
    is preserved at its current position on each application.

    :example:

    .. code-block:: python

        applicator = ToolbarApplicator(discovery)
        applicator.apply_all({
            "__qgis_native__": [
                {"name": "mMapNavToolBar", "visible": True,
                 "area": "top", "line": 1},
            ]
        })
    """

    #: String → Qt toolbar area constant mapping.
    AREA_MAP = {
        "top":    Qt.TopToolBarArea,
        "bottom": Qt.BottomToolBarArea,
        "left":   Qt.LeftToolBarArea,
        "right":  Qt.RightToolBarArea,
    }

    def __init__(self, discovery):
        """
        Initialize the applicator with the discovery registry.

        :param discovery: QGIS plugin discovery instance.
        :type discovery: PluginDiscovery
        """
        self.discovery = discovery

    def apply(self, plugin_name: str, toolbars_config: list):
        """
        Hide non-visible toolbars of a plugin.

        Does not reposition toolbars — used only to hide toolbars
        whose ``visible`` is ``False``.
        Ignores toolbars from :data:`EXCLUDED_TOOLBARS` and
        :data:`LINKED_TOOLBARS`.

        :param plugin_name: Name of the plugin owning the toolbars.
        :type plugin_name: str
        :param toolbars_config: List of toolbar configurations, each as
            ``{"name": str, "visible": bool, "area": str, "line": int}``.
        :type toolbars_config: list[dict]
        """
        for tb_cfg in toolbars_config:

            if tb_cfg["name"] in EXCLUDED_TOOLBARS:
                continue
            if tb_cfg["name"] in LINKED_TOOLBARS:
                continue

            toolbar = self._find(tb_cfg["name"])
            if toolbar is None or not is_valid(toolbar):
                continue

            if not tb_cfg.get("visible", True):
                toolbar.setVisible(False)

    def apply_all(self, all_toolbars_by_plugin: dict):
        """
        Reposition all visible toolbars according to their area and line.

        Performs in order:

        1. Save the position of ``QWorkspaceSwitcherToolbar``.
        2. Collect visible toolbars grouped by area and line.
        3. Remove all these toolbars from the main window.
        4. Replace them in the correct order with line breaks.
        5. Restore ``QWorkspaceSwitcherToolbar`` to its saved position.

        Toolbars from :data:`EXCLUDED_TOOLBARS` and :data:`LINKED_TOOLBARS`
        are ignored.

        :param all_toolbars_by_plugin: Dictionary
            ``{plugin_name: [toolbar_config, ...]}``.
        :type all_toolbars_by_plugin: dict[str, list[dict]]

        :example:

        .. code-block:: python

            applicator.apply_all({
                "__qgis_native__": [
                    {"name": "mMapNavToolBar",   "visible": True,
                     "area": "top", "line": 1},
                    {"name": "mDigitizeToolBar", "visible": True,
                     "area": "top", "line": 2},
                ],
                "georelai": [
                    {"name": "GeorelaiToolbar",  "visible": True,
                     "area": "top", "line": 3},
                ]
            })
        """
        main_win   = iface.mainWindow()
        area_lines = {}

        # Collect visible toolbars grouped by area and line
        for plugin_name, toolbars_config in all_toolbars_by_plugin.items():
            for tb_cfg in toolbars_config:

                if tb_cfg["name"] in EXCLUDED_TOOLBARS:
                    continue
                if tb_cfg["name"] in LINKED_TOOLBARS:
                    continue
                if not tb_cfg.get("visible", True):
                    continue

                toolbar = self._find(tb_cfg["name"])
                if toolbar is None or not is_valid(toolbar):
                    continue

                area = tb_cfg.get("area", "top")
                line = tb_cfg.get("line", 1)

                if area not in area_lines:
                    area_lines[area] = {}
                if line not in area_lines[area]:
                    area_lines[area][line] = []

                area_lines[area][line].append({
                    "toolbar": toolbar,
                    "config":  tb_cfg,
                })

        # Save position of QWorkspaceSwitcherToolbar
        pm_toolbar = None
        pm_area    = Qt.TopToolBarArea
        for tb in main_win.findChildren(QToolBar):
            if tb.objectName() == "QWorkspaceSwitcherToolbar":
                pm_toolbar = tb
                pm_area    = main_win.toolBarArea(tb)
                break

        # Remove all toolbars to be repositioned
        all_toolbars = set()
        for area_data in area_lines.values():
            for line_data in area_data.values():
                for entry in line_data:
                    all_toolbars.add(entry["toolbar"])

        for tb in all_toolbars:
            if is_valid(tb):
                main_win.removeToolBar(tb)

        # Replace in correct order by area and line
        for area_str, lines in area_lines.items():
            area = self.AREA_MAP.get(area_str, Qt.TopToolBarArea)
            for line_num in sorted(lines.keys()):
                toolbars_in_line = lines[line_num]
                for idx, entry in enumerate(toolbars_in_line):
                    toolbar = entry["toolbar"]
                    if not is_valid(toolbar):
                        continue
                    main_win.addToolBar(area, toolbar)
                    # Insert line break before first toolbar
                    # of each line > 1
                    if idx == 0 and line_num > 1:
                        main_win.insertToolBarBreak(toolbar)
                    toolbar.setVisible(True)

        # Restore QWorkspaceSwitcherToolbar to its saved position
        if pm_toolbar and is_valid(pm_toolbar):
            main_win.addToolBar(pm_area, pm_toolbar)
            pm_toolbar.setVisible(True)

    def _find(self, name: str):
        """
        Search for a :class:`QToolBar` by name in the registry.

        :param name: Name (``objectName``) of the toolbar to find.
        :type name: str
        :return: Toolbar instance, or ``None`` if not found.
        :rtype: QToolBar or None
        """
        for plugin_data in self.discovery.registry.values():
            for tb_info in plugin_data.get("toolbars", []):
                if tb_info["name"] == name:
                    return tb_info["object"]
        return None