# coding: utf-8

"""
Current QGIS interface state capture module.

This module provides the :class:`StateCapture` class, responsible for
capturing the visible state of all docks and toolbars in the QGIS
interface at a given moment, in order to save it as a workspace.

**Toolbars excluded from capture:**

- ``QToolBar`` — widgets without a valid name.
- ``mBrowserToolbar`` — linked to the Browser dock (managed by Qt signal).
- ``mAdvancedDigitizeToolBar`` — linked to the Advanced Digitizing dock.
- ``mGpsToolBar`` — linked to the GPS dock.
- ``mBookmarkToolbar`` — linked to the Bookmarks dock.
- ``processingToolbar`` — linked to the Processing dock.

:author: Adnan Benaboud — CNR
"""

from qgis.PyQt.QtWidgets import QToolBar
from qgis.PyQt.QtCore import Qt
from qgis.utils import iface

from ..core.plugin_discovery import is_valid


class StateCapture:
    """
    Capture the current state of the QGIS interface.

    Iterates over the plugin registry provided by
    :class:`~perspective_manager.core.plugin_discovery.PluginDiscovery`
    and records for each dock and toolbar: its visibility, area
    and line (for toolbars).

    :example:

    .. code-block:: python

        discovery = PluginDiscovery()
        discovery.scan()
        capture   = StateCapture(discovery)
        data      = capture.capture("Field survey")
    """

    #: Toolbars excluded from capture — linked to a dock or without valid name.
    EXCLUDED_TOOLBARS = [
        "QToolBar",
        "mBrowserToolbar",
        "mAdvancedDigitizeToolBar",
        "mGpsToolBar",
        "mBookmarkToolbar",
        "processingToolbar",
    ]

    def __init__(self, discovery):
        """
        Initialize the instance with the discovery registry.

        :param discovery: QGIS plugin discovery instance.
        :type discovery: PluginDiscovery
        """
        self.discovery = discovery

    def capture(self, name: str) -> dict:
        """
        Capture the current state of all docks and toolbars.

        Iterates over :attr:`PluginDiscovery.registry` and
        records for each plugin:

        - The state of its docks (visibility, area).
        - The state of its toolbars (visibility, area, line).

        Duplicates and invalid widgets are ignored.
        Toolbars in :attr:`EXCLUDED_TOOLBARS` are excluded.

        :param name: Name of the workspace to create.
        :type name: str
        :return: Captured workspace dictionary.
        :rtype: dict

        :example:

        .. code-block:: python

            data = capture.capture("Field survey")
            # → {
            #     "name": "Field survey",
            #     "plugins": {
            #         "__qgis_native__": {
            #             "docks": [
            #                 {"name": "Layers",
            #                  "visible": True, ...}
            #             ],
            #             "toolbars": [
            #                 {"name": "mMapNavToolBar",
            #                  "line": 1, ...}
            #             ]
            #         },
            #         "georelai": {...}
            #     }
            # }
        """
        main_win = iface.mainWindow()
        data     = {"name": name, "plugins": {}}

        for plugin_name, plugin_data in self.discovery.registry.items():
            docks_state     = []
            toolbars_state  = []
            seen_dock_names = set()
            seen_tb_names   = set()

            # ── Capture docks ─────────────────────
            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]

                if not is_valid(dock):
                    continue
                if dock_info["name"] in seen_dock_names:
                    continue

                seen_dock_names.add(dock_info["name"])
                area = main_win.dockWidgetArea(dock)

                docks_state.append({
                    "name":    dock_info["name"],
                    "label":   dock_info["label"],
                    "visible": dock.isVisible(),
                    "area":    self.discovery._area_to_str(area),
                })

            # ── Capture toolbars ──────────────────
            for tb_info in plugin_data.get("toolbars", []):
                tb = tb_info["object"]

                if not is_valid(tb):
                    continue
                if tb_info["name"] in self.EXCLUDED_TOOLBARS:
                    continue
                if tb_info["name"] in seen_tb_names:
                    continue

                seen_tb_names.add(tb_info["name"])
                area     = main_win.toolBarArea(tb)
                area_str = self.discovery._area_to_str(area)

                toolbars_state.append({
                    "name":    tb_info["name"],
                    "label":   tb_info["label"],
                    "visible": tb.isVisible(),
                    "area":    area_str,
                    "line":    self._detect_line(main_win, tb, area_str),
                })

            if docks_state or toolbars_state:
                data["plugins"][plugin_name] = {
                    "docks":    docks_state,
                    "toolbars": toolbars_state,
                }

        return data

    def _detect_line(self, main_win, toolbar: QToolBar,
                     area_str: str) -> int:
        """
        Detect the line number of a toolbar within its area.

        Compares the geometric position of the toolbar with those
        of other visible toolbars in the same area to determine
        which line it is on (1 = first line).

        :param main_win: QGIS main window.
        :param toolbar: Toolbar whose line number to find.
        :type toolbar: QToolBar
        :param area_str: Toolbar area (``"top"``, ``"bottom"``,
            ``"left"``, ``"right"``).
        :type area_str: str
        :return: Line number (starts at 1). Returns ``1`` if
            position is not found.
        :rtype: int

        :example:

        .. code-block:: python

            line = capture._detect_line(main_win, toolbar, "top")
            # → 2  (second line of the top area)
        """
        area_map = {
            "top":    Qt.TopToolBarArea,
            "bottom": Qt.BottomToolBarArea,
            "left":   Qt.LeftToolBarArea,
            "right":  Qt.RightToolBarArea,
        }
        area = area_map.get(area_str, Qt.TopToolBarArea)

        # Visible toolbars in the same area
        same_area = [
            tb for tb in main_win.findChildren(QToolBar)
            if main_win.toolBarArea(tb) == area and tb.isVisible()
        ]

        # Sort by Y position (horizontal areas) or X (vertical areas)
        if area_str in ("top", "bottom"):
            same_area.sort(key=lambda t: t.geometry().y())
            positions   = sorted(set(t.geometry().y() for t in same_area))
            current_pos = toolbar.geometry().y()
        else:
            same_area.sort(key=lambda t: t.geometry().x())
            positions   = sorted(set(t.geometry().x() for t in same_area))
            current_pos = toolbar.geometry().x()

        try:
            return positions.index(current_pos) + 1
        except ValueError:
            return 1