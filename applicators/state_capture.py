from qgis.utils import iface


class StateCapture:
    """
    Photographie l'état courant de l'interface QGIS —
    docks et toolbars — depuis le registre PluginDiscovery.
    """

    def __init__(self, discovery):
        self.discovery = discovery

    def capture(self, name: str) -> dict:
        """
        Retourne un dict prêt à être sauvegardé
        représentant l'état actuel de l'interface.
        """
        main_win = iface.mainWindow()
        data = {"name": name, "plugins": {}}

        for plugin_name, plugin_data in self.discovery.registry.items():
            docks_state    = []
            toolbars_state = []

            # ── Docks ──────────────────────────────
            for dock_info in plugin_data.get("docks", []):
                dock = dock_info["object"]
                area = main_win.dockWidgetArea(dock)

                docks_state.append({
                    "name":    dock_info["name"],
                    "label":   dock_info["label"],
                    "visible": dock.isVisible(),
                    "area":    self.discovery._area_to_str(area),
                })

            # ── Toolbars ───────────────────────────
            for tb_info in plugin_data.get("toolbars", []):
                tb   = tb_info["object"]
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