import os
import json
from qgis.PyQt.QtCore import QObject, pyqtSignal, QFileSystemWatcher


class ConfigIO(QObject):

    # Signal émis quand le fichier change
    configChanged = pyqtSignal()

    CONFIG_FILE = "perspectives.json"

    def __init__(self):
        super().__init__()  # ← ajouter super().__init__() en premier
        self.base_dir     = self._get_base_dir()
        self.config_path  = os.path.join(self.base_dir, self.CONFIG_FILE)
        self._writing     = False  # ← flag pour éviter la boucle
        self._ensure_dirs()

        self._watcher = QFileSystemWatcher()
        self._watcher.addPath(self.config_path)
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _on_file_changed(self, path: str):
        """
        Appelé quand le fichier JSON est modifié.
        Re-ajoute le watcher car certains éditeurs
        suppriment et recréent le fichier.
        """
        # Re-ajouter le fichier au watcher
        # (certains éditeurs comme VS Code recréent le fichier)
        if self._writing:
            return  # ← ignorer si c'est nous qui écrivons

        if os.path.exists(path):
            if path not in self._watcher.files():
                self._watcher.addPath(path)
        print(f"[ConfigIO] Fichier modifié détecté : {path}")
        self.configChanged.emit()


    def _get_base_dir(self) -> str:
        plugin_dir = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(plugin_dir, "perspectives")

    def _ensure_dirs(self):
        os.makedirs(self.base_dir, exist_ok=True)
        if not os.path.exists(self.config_path):
            self._write({"perspectives": []})

    def _read(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f) or {"perspectives": []}
        except Exception as e:
            print(f"[ConfigIO] Erreur lecture : {e}")
            return {"perspectives": []}

    def _write(self, data: dict):
        """Écrit le fichier en désactivant le watcher."""
        self._writing = True  # ← désactiver le watcher
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(
                    data, f,
                    ensure_ascii=False,
                    indent=2
                )
        except Exception as e:
            print(f"[ConfigIO] Erreur écriture : {e}")
        finally:
            self._writing = False  # ← réactiver le watcher

    def list_all(self) -> list:
        return [p["name"] for p in self._read().get("perspectives", [])]

    def _get_all(self) -> list:
        return self._read().get("perspectives", [])

    def load(self, name: str) -> dict:
        for p in self._get_all():
            if p["name"] == name:
                return p
        return {}

    def save(self, name: str, data: dict):
        all_data     = self._read()
        perspectives = all_data.get("perspectives", [])
        data["name"] = name

        for i, p in enumerate(perspectives):
            if p["name"] == name:
                perspectives[i] = data
                all_data["perspectives"] = perspectives
                self._write(all_data)
                print(f"[ConfigIO] Perspective mise à jour : {name}")
                return

        if name == "QGIS":
            perspectives.insert(0, data)
        else:
            perspectives.append(data)

        all_data["perspectives"] = perspectives
        self._write(all_data)
        print(f"[ConfigIO] Perspective sauvegardée : {name}")

    def create_perspective(self, name: str) -> bool:
        if name in self.list_all():
            return False
        empty = {
            "name":           name,
            "icon":           "",
            "button_style":   "text",
            "dropdown_menus": [],
            "plugins":        {}
        }
        self.save(name, empty)
        return True

    def delete(self, name: str):
        all_data     = self._read()
        perspectives = [
            p for p in all_data.get("perspectives", [])
            if p["name"] != name
        ]
        all_data["perspectives"] = perspectives
        self._write(all_data)
        print(f"[ConfigIO] Perspective supprimée : {name}")

    def rename(self, old_name: str, new_name: str):
        all_data = self._read()
        for p in all_data.get("perspectives", []):
            if p["name"] == old_name:
                p["name"] = new_name
                break
        self._write(all_data)
        print(f"[ConfigIO] Perspective renommée : {old_name} → {new_name}")

    def validate(self, data: dict) -> bool:
        return "name" in data and "plugins" in data