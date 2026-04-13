import os
import yaml
from qgis.core import QgsUserProfileManager


class ConfigIO:
    """
    Gère la lecture et l'écriture des fichiers YAML
    des perspectives dans le profil utilisateur QGIS.
    """

    PERSPECTIVES_DIR = "perspectives"
    INDEX_FILE = "index.yaml"

    def __init__(self):
        self.base_dir = self._get_base_dir()
        self._ensure_dirs()

    # ─────────────────────────────────────────
    # CHEMINS
    # ─────────────────────────────────────────

    def _get_base_dir(self) -> str:
        """
        Retourne le chemin du dossier perspectives/
        dans le profil QGIS utilisateur.
        Ex: C:/Users/user/AppData/Roaming/QGIS/QGIS3/profiles/default/
                python/plugins/perspective_manager/perspectives/
        """
        plugin_dir = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(plugin_dir, self.PERSPECTIVES_DIR)

    def _ensure_dirs(self):
        """Crée le dossier perspectives/ s'il n'existe pas."""
        os.makedirs(self.base_dir, exist_ok=True)

    def _perspective_path(self, name: str) -> str:
        """Retourne le chemin du fichier YAML d'une perspective."""
        safe_name = name.lower().replace(" ", "_")
        return os.path.join(self.base_dir, f"{safe_name}.yaml")

    # ─────────────────────────────────────────
    # INDEX
    # ─────────────────────────────────────────

    def load_index(self) -> list:
        """
        Retourne la liste des perspectives depuis index.yaml.
        [ { "name": "Saisie terrain", "file": "saisie_terrain.yaml" }, ... ]
        """
        index_path = os.path.join(self.base_dir, self.INDEX_FILE)
        if not os.path.exists(index_path):
            return []
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data.get("perspectives", [])
        except Exception as e:
            print(f"[ConfigIO] Erreur lecture index : {e}")
            return []

    def save_index(self, perspectives: list):
        """Sauvegarde la liste des perspectives dans index.yaml."""
        index_path = os.path.join(self.base_dir, self.INDEX_FILE)
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    {"perspectives": perspectives},
                    f,
                    allow_unicode=True,
                    default_flow_style=False
                )
        except Exception as e:
            print(f"[ConfigIO] Erreur écriture index : {e}")

    # ─────────────────────────────────────────
    # PERSPECTIVES
    # ─────────────────────────────────────────

    def create_perspective(self, name: str) -> bool:
        """
        Crée un fichier YAML vide pour une nouvelle perspective.
        Retourne True si succès, False si le nom existe déjà.
        """
        # Vérifier que le nom n'existe pas déjà
        if name in self.list_all():
            return False

        # Structure vide — pas de docks, pas de toolbars
        empty_data = {
            "name":    name,
            "plugins": {}
        }

        self.save(name, empty_data)
        print(f"[ConfigIO] Nouvelle perspective créée : {name}")
        return True

    def load(self, name: str) -> dict:
        """
        Charge une perspective depuis son fichier YAML.
        Retourne un dict ou {} si introuvable.
        """
        path = self._perspective_path(name)
        if not os.path.exists(path):
            print(f"[ConfigIO] Perspective introuvable : {path}")
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[ConfigIO] Erreur lecture {name} : {e}")
            return {}

    def save(self, name: str, data: dict):
        """
        Sauvegarde une perspective dans son fichier YAML.
        Met aussi à jour index.yaml.
        """
        path = self._perspective_path(name)
        data["name"] = name
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data,
                    f,
                    allow_unicode=True,
                    default_flow_style=False
                )
            self._update_index(name)
            print(f"[ConfigIO] Perspective sauvegardée : {path}")
        except Exception as e:
            print(f"[ConfigIO] Erreur sauvegarde {name} : {e}")

    def delete(self, name: str):
        """Supprime une perspective et la retire de l'index."""
        path = self._perspective_path(name)
        if os.path.exists(path):
            os.remove(path)
        self._remove_from_index(name)
        print(f"[ConfigIO] Perspective supprimée : {name}")

    def rename(self, old_name: str, new_name: str):
        """Renomme une perspective — renomme le fichier et met à jour l'index."""
        old_path = self._perspective_path(old_name)
        new_path = self._perspective_path(new_name)

        if os.path.exists(old_path):
            # Recharger, changer le nom, sauvegarder sous nouveau nom
            data = self.load(old_name)
            data["name"] = new_name
            with open(new_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            os.remove(old_path)

        # Mettre à jour l'index
        index = self.load_index()
        for item in index:
            if item["name"] == old_name:
                item["name"] = new_name
                item["file"] = os.path.basename(new_path)
        self.save_index(index)

    def list_all(self) -> list:
        """Retourne la liste des noms de toutes les perspectives."""
        index = self.load_index()
        return [item["name"] for item in index]

    # ─────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────

    def validate(self, data: dict) -> bool:
        """
        Vérifie que le dict a la structure minimale attendue.
        Retourne True si valide.
        """
        if "name" not in data:
            return False
        if "plugins" not in data and "panels" not in data:
            return False
        return True

    # ─────────────────────────────────────────
    # HELPERS INDEX
    # ─────────────────────────────────────────

    def _update_index(self, name: str):
        """Ajoute une perspective à l'index."""
        index = self.load_index()
        names = [item["name"] for item in index]

        if name not in names:
            safe = name.lower().replace(" ", "_")
            new_entry = {
                "name": name,
                "file": f"{safe}.yaml"
            }

            # La perspective QGIS toujours en premier
            if name == "QGIS":
                index.insert(0, new_entry)
            else:
                index.append(new_entry)

            self.save_index(index)

    def _remove_from_index(self, name: str):
        """Retire une perspective de l'index."""
        index = self.load_index()
        index = [item for item in index if item["name"] != name]
        self.save_index(index)