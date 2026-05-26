# QworkspaceSwitcher — QGIS Plugin

A QGIS plugin to manage and apply named interface
configurations called **perspectives**.

## Features

- Create perspectives by capturing the current
  QGIS interface state
- Apply a perspective in one click from the toolbar
- Configure each button style (text, icon, both)
- Associate a custom icon to each perspective
- Add dropdown menus from other plugins
- Show/hide the QGIS menu bar per perspective
- Declarative .psp.json system for third-party plugins

## Why QWorkspace Switcher ?

QGIS is a powerful GIS platform but its interface
can be overwhelming, especially for users who
switch between different tasks (data collection,
hydraulic modeling, results analysis...).
QWorkspace Switcher allows you to define dedicated
interface configurations for each workflow and
switch between them instantly.

## Installation

Install directly from the QGIS Plugin Manager:
Plugins → Manage and Install Plugins →
Search "QworkspaceSwitcher"

## Usage

1. Click the gear button in the QworkspaceSwitcher
   toolbar to open the management window
2. Click "+" to create a new perspective
3. Configure panels, toolbars and menus
4. Click "Save"
5. Apply the perspective from the toolbar

## Integration for plugin developers

To integrate your plugin with QworkspaceSwitcher,
declare your widgets in `initGui()` :

```python
class MyPlugin:
    def initGui(self):
        # Expose docks
        self.docks = [self.my_dock1, self.my_dock2]

        # Expose toolbar
        self.toolbar = QToolBar("My Plugin")
        self.toolbar.setObjectName("MyPluginToolbar")
```

Then create a `myplugin.psp.json` file at the root
of your plugin folder. See the documentation for
the full JSON schema.

## License

GPL v2 — see LICENSE file

## Author

Adnan Benaboud — CNR (Compagnie Nationale du Rhône)