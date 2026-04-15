# coding: utf-8

"""
Module de gestion des entrées/sorties de configuration des perspectives.

Ce module fournit la classe :class:`ConfigIO`, couche d'accès aux données
du plugin Gestionnaire de Perspectives. Elle s'appuie sur
:class:`~perspective_manager.core.configuration.Configuration` comme
source unique de vérité en mémoire (``self._cfg``), et synchronise
les modifications vers ``user.psp.json``.

**Architecture des sources de configuration :**

.. code-block:: text

    CONFIG_DEFAULT              (priorité la plus faible)
        ↓
    plugin_a/plugin_a.psp.json  (perspectives déclarées par plugin_a)
        ↓
    plugin_b/plugin_b.psp.json  (perspectives déclarées par plugin_b)
        ↓
    perspectives/user.psp.json  (perspectives utilisateur — priorité maximale)
        ↓
    self._cfg                   (dictionnaire fusionné en mémoire)

**Principe de fonctionnement :**

- Au démarrage, :meth:`_build_cfg` scanne tous les fichiers ``*.psp.json``
  des plugins QGIS installés et les fusionne avec ``user.psp.json``.
- Pendant la session, toutes les opérations (lecture, écriture, suppression)
  passent exclusivement par ``self._cfg`` — aucune lecture fichier.
- Chaque modification met à jour ``self._cfg`` puis écrit ``user.psp.json``.
- Un :class:`QFileSystemWatcher` détecte les modifications externes du fichier
  et reconstruit ``self._cfg`` automatiquement.

:author: Adnan Benaboud — CNR
"""

import os
import json
import glob

from qgis.PyQt.QtCore import QObject, pyqtSignal, QFileSystemWatcher

from .configuration import Configuration


#: Configuration par défaut — liste de perspectives vide.
CONFIG_DEFAULT = {"perspectives": []}


class ConfigIO(QObject):
    """
    Gestionnaire d'entrées/sorties pour les perspectives du plugin.

    Fournit une API unifiée pour lire, créer, modifier et supprimer
    des perspectives. S'appuie sur :class:`Configuration` comme source
    unique de vérité en mémoire.

    **Fichiers gérés :**

    - ``perspectives/user.psp.json`` — perspectives créées par l'utilisateur.
    - ``<plugin>/<plugin>.psp.json`` — perspectives déclarées par les plugins
      (lecture seule, chargées au démarrage).

    **Signaux :**

    - :attr:`configChanged` — émis quand ``user.psp.json`` est modifié
      depuis l'extérieur (ex. éditeur de texte).

    :exemple:

    .. code-block:: python

        config_io = ConfigIO()
        data      = config_io.load("Saisie terrain")
        config_io.save("Saisie terrain", data)
    """

    configChanged = pyqtSignal()
    """Signal émis quand ``user.psp.json`` est modifié depuis l'extérieur."""

    CONFIG_FILE = "user.psp.json"
    """Nom du fichier de configuration utilisateur."""

    def __init__(self):
        """
        Initialise le gestionnaire de configuration.

        - Crée le répertoire ``perspectives/`` si nécessaire.
        - Construit ``self._cfg`` depuis toutes les sources disponibles.
        - Démarre le :class:`QFileSystemWatcher` sur ``user.psp.json``.
        """
        super().__init__()

        self.base_dir    = self._get_base_dir()
        self.config_path = os.path.join(self.base_dir, self.CONFIG_FILE)
        self._writing    = False

        os.makedirs(self.base_dir, exist_ok=True)

        # Source unique de vérité — construite depuis toutes les sources
        self._cfg = self._build_cfg()

        # Surveillance des modifications externes de user.psp.json
        self._watcher = QFileSystemWatcher()
        self._watcher.addPath(self.config_path)
        self._watcher.fileChanged.connect(self._on_file_changed)

    # ─────────────────────────────────────────────
    # INITIALISATION
    # ─────────────────────────────────────────────

    def _get_base_dir(self) -> str:
        """
        Retourne le chemin du répertoire de stockage des perspectives.

        :return: Chemin absolu vers ``<plugin_dir>/perspectives/``.
        :rtype: str
        """
        plugin_dir = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(plugin_dir, "perspectives")

    def _build_cfg(self) -> Configuration:
        """
        Construit la source unique de vérité depuis toutes les sources.

        Scanne tous les fichiers ``*.psp.json`` des plugins QGIS installés,
        les fusionne avec ``user.psp.json`` via :class:`Configuration`,
        puis corrige la fusion des listes de perspectives via
        :meth:`_merge_perspectives`.

        Appelé au démarrage et lors d'un rechargement externe.

        :return: Instance :class:`Configuration` fusionnée.
        :rtype: Configuration
        """
        lst_cfg     = [CONFIG_DEFAULT]
        plugins_dir = os.path.dirname(os.path.dirname(self.base_dir))

        # Scanner les fichiers .psp.json des plugins installés
        psp_files = sorted(glob.glob(
            os.path.join(plugins_dir, "*", "*.psp.json")
        ))

        for fic in psp_files:
            if os.path.normpath(fic) == os.path.normpath(self.config_path):
                continue
            lst_cfg.append(fic)

        # Créer la Configuration fusionnée
        cfg = Configuration(
            lst_cfg=lst_cfg,
            fic_sav=self.config_path
        )

        # Corriger la fusion des listes de perspectives
        # (_deep_update écrase les listes au lieu de les fusionner)
        merged = self._merge_perspectives(lst_cfg + [self.config_path])
        cfg.cfg["perspectives"] = merged

        return cfg

    def _merge_perspectives(self, lst_cfg: list) -> list:
        """
        Fusionne les perspectives de toutes les sources par ordre de priorité.

        Les perspectives utilisateur (``user.psp.json``) sont prioritaires
        sur celles des plugins. En cas de nom identique, la version
        utilisateur écrase la version plugin.

        **Ordre dans la liste retournée :**

        1. Perspectives utilisateur (``user.psp.json``) en premier.
        2. Perspectives plugins non surchargées ensuite.

        :param lst_cfg: Liste des sources — chaque élément est un
            :class:`dict` ou un chemin vers un fichier JSON.
        :type lst_cfg: list
        :return: Liste fusionnée et ordonnée de perspectives.
        :rtype: list

        :exemple:

        .. code-block:: text

            georelai.psp.json → [Saisie terrain, Visualisation]
            user.psp.json     → [QGIS, Saisie terrain (modifiée)]

            Résultat → [QGIS, Saisie terrain (user), Visualisation]
        """
        if not lst_cfg:
            return []

        user_perspectives   = {}
        plugin_perspectives = {}

        for source in lst_cfg:
            if source is None:
                continue

            is_user = (
                isinstance(source, str) and
                os.path.normpath(source) == os.path.normpath(self.config_path)
            )

            if isinstance(source, dict):
                perspectives = source.get("perspectives", [])
            elif isinstance(source, str):
                path = os.path.normpath(source)
                if not os.path.exists(path):
                    continue
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    perspectives = data.get("perspectives", [])
                except Exception as e:
                    print(f"[ConfigIO] Erreur lecture {path} : {e}")
                    perspectives = []
            else:
                continue

            for p in perspectives:
                name = p.get("name")
                if not name:
                    continue
                if is_user:
                    user_perspectives[name]   = p
                else:
                    plugin_perspectives[name] = p

        # Fusionner : user écrase les plugins si même nom
        result = dict(plugin_perspectives)
        result.update(user_perspectives)

        # Ordonner : user d'abord, plugins non surchargés ensuite
        user_names   = list(user_perspectives.keys())
        plugin_names = [
            n for n in plugin_perspectives
            if n not in user_perspectives
        ]

        return [result[n] for n in user_names + plugin_names]

    def _on_file_changed(self, path: str):
        """
        Appelé par :attr:`_watcher` quand ``user.psp.json`` est modifié.

        Ignore les modifications provenant du plugin lui-même (``_writing``).
        Reconstruit ``self._cfg`` depuis toutes les sources et émet
        :attr:`configChanged`.

        :param path: Chemin du fichier modifié.
        :type path: str
        """
        if self._writing:
            return

        # Re-ajouter au watcher si certains éditeurs recréent le fichier
        if os.path.exists(path) and path not in self._watcher.files():
            self._watcher.addPath(path)

        self._cfg = self._build_cfg()
        self.configChanged.emit()

    # ─────────────────────────────────────────────
    # API PUBLIQUE — tout passe par self._cfg
    # ─────────────────────────────────────────────

    def list_all(self) -> list:
        """
        Retourne les noms de toutes les perspectives depuis ``self._cfg``.

        Inclut les perspectives utilisateur et celles des plugins.

        :return: Liste des noms de perspectives dans l'ordre d'affichage
            (utilisateur en premier, plugins ensuite).
        :rtype: list[str]

        :exemple:

        .. code-block:: python

            names = config_io.list_all()
            # → ['QGIS', 'test', 'Modélisation', 'qats']
        """
        return [
            p["name"]
            for p in self._cfg.get("perspectives", [])
        ]

    def list_all_merged(self) -> list:
        """
        Alias de :meth:`list_all`.

        Conservé pour compatibilité avec les appels existants.

        :return: Liste des noms de toutes les perspectives.
        :rtype: list[str]
        """
        return self.list_all()

    def load(self, name: str) -> dict:
        """
        Charge une perspective par son nom depuis ``self._cfg``.

        Aucune lecture fichier — opération en mémoire uniquement.

        :param name: Nom de la perspective à charger.
        :type name: str
        :return: Dictionnaire complet de la perspective,
            ou dictionnaire vide si introuvable.
        :rtype: dict

        :exemple:

        .. code-block:: python

            data = config_io.load("Saisie terrain")
            show_menu = data.get("show_menu_bar", True)
        """
        for p in self._cfg.get("perspectives", []):
            if p["name"] == name:
                return p
        return {}

    def save(self, name: str, data: dict):
        """
        Sauvegarde une perspective dans ``self._cfg`` et ``user.psp.json``.

        Si la perspective existe déjà, elle est mise à jour. Sinon elle
        est ajoutée (la perspective ``QGIS`` est toujours insérée en premier).

        :param name: Nom de la perspective.
        :type name: str
        :param data: Dictionnaire complet de la perspective.
        :type data: dict
        """
        self._writing = True
        try:
            data["name"]  = name
            perspectives  = self._cfg.get("perspectives", [])

            # Mise à jour si la perspective existe déjà
            for i, p in enumerate(perspectives):
                if p["name"] == name:
                    perspectives[i] = data
                    self._cfg["perspectives"] = perspectives
                    self._cfg.sgl_unsaved.emit()
                    self._write_user_from_cfg()
                    return

            # Nouvelle perspective
            if name == "QGIS":
                perspectives.insert(0, data)
            else:
                perspectives.append(data)

            self._cfg["perspectives"] = perspectives
            self._cfg.sgl_unsaved.emit()
            self._write_user_from_cfg()

        finally:
            self._writing = False

    def delete(self, name: str):
        """
        Supprime une perspective de ``self._cfg`` et de ``user.psp.json``.

        Si la perspective provient d'un fichier plugin ``*.psp.json``,
        elle est ajoutée à ``deleted_perspectives`` dans ``user.psp.json``
        afin d'être filtrée lors du prochain rechargement du plugin.

        .. note::
            La suppression est immédiate dans ``self._cfg`` — la perspective
            disparaît de l'UI et de la toolbar sans rechargement.
            Elle sera définitivement absente au prochain démarrage grâce
            à ``deleted_perspectives``.

        :param name: Nom de la perspective à supprimer.
        :type name: str
        """
        self._writing = True
        try:
            # ── Supprimer de self._cfg — effet immédiat ──
            perspectives = [
                p for p in self._cfg.get("perspectives", [])
                if p["name"] != name
            ]
            self._cfg["perspectives"] = perspectives
            self._cfg.sgl_unsaved.emit()

            # ── Persister dans user.psp.json ─────────────
            user_data = self._read_user()

            # Retirer de la liste des perspectives user
            user_data["perspectives"] = [
                p for p in user_data.get("perspectives", [])
                if p["name"] != name
            ]

            # Si perspective plugin → ajouter à la liste noire
            # pour éviter qu'elle réapparaisse au prochain démarrage
            if name in self.get_plugin_perspectives():
                deleted = user_data.get("deleted_perspectives", [])
                if name not in deleted:
                    deleted.append(name)
                user_data["deleted_perspectives"] = deleted

            self._write_user(user_data)

        finally:
            self._writing = False

    def rename(self, old_name: str, new_name: str):
        """
        Renomme une perspective dans ``self._cfg`` et ``user.psp.json``.

        :param old_name: Nom actuel de la perspective.
        :type old_name: str
        :param new_name: Nouveau nom de la perspective.
        :type new_name: str
        """
        self._writing = True
        try:
            # Renommer dans self._cfg
            perspectives = self._cfg.get("perspectives", [])
            for p in perspectives:
                if p["name"] == old_name:
                    p["name"] = new_name
                    break
            self._cfg["perspectives"] = perspectives
            self._cfg.sgl_unsaved.emit()

            # Renommer dans user.psp.json
            user_data  = self._read_user()
            user_persp = user_data.get("perspectives", [])
            for p in user_persp:
                if p["name"] == old_name:
                    p["name"] = new_name
                    break
            user_data["perspectives"] = user_persp
            self._write_user(user_data)

        finally:
            self._writing = False

    def create_perspective(self, name: str) -> bool:
        """
        Crée une nouvelle perspective vide.

        :param name: Nom de la nouvelle perspective.
        :type name: str
        :return: ``True`` si créée avec succès, ``False`` si le nom existe déjà.
        :rtype: bool

        :exemple:

        .. code-block:: python

            if config_io.create_perspective("Mon workflow"):
                print("Créée !")
        """
        if name in self.list_all():
            return False

        empty = {
            "name":           name,
            "icon":           "",
            "button_style":   "text",
            "show_menu_bar":  True,
            "dropdown_menus": [],
            "plugins":        {}
        }
        self.save(name, empty)
        return True

    def validate(self, data: dict) -> bool:
        """
        Valide la structure minimale d'un dictionnaire de perspective.

        :param data: Dictionnaire à valider.
        :type data: dict
        :return: ``True`` si le dictionnaire contient les clés requises.
        :rtype: bool
        """
        return "name" in data and "plugins" in data

    def get_plugin_perspectives(self) -> dict:
        """
        Retourne les perspectives déclarées par les plugins installés.

        Scanne tous les fichiers ``*.psp.json`` des plugins QGIS
        (hors ``user.psp.json``) et retourne un dictionnaire
        ``{nom_perspective: nom_plugin}``.

        :return: Dictionnaire associant chaque perspective à son plugin.
        :rtype: dict[str, str]

        :exemple:

        .. code-block:: python

            plugin_persp = config_io.get_plugin_perspectives()
            # → {"Modélisation": "georelai", "qats": "q4ts"}
        """
        result      = {}
        plugins_dir = os.path.dirname(os.path.dirname(self.base_dir))
        psp_files   = glob.glob(
            os.path.join(plugins_dir, "*", "*.psp.json")
        )

        for fic in psp_files:
            if os.path.normpath(fic) == os.path.normpath(self.config_path):
                continue
            plugin_name = os.path.basename(os.path.dirname(fic))
            try:
                with open(fic, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for p in data.get("perspectives", []):
                    name = p.get("name")
                    if name:
                        result[name] = plugin_name
            except Exception:
                pass

        return result

    # ─────────────────────────────────────────────
    # MÉTHODES PRIVÉES
    # ─────────────────────────────────────────────

    def _read_user(self) -> dict:
        """
        Lit ``user.psp.json`` directement depuis le disque.

        :return: Contenu de ``user.psp.json``, ou ``{"perspectives": []}``
            si le fichier est absent ou corrompu.
        :rtype: dict
        """
        if not os.path.exists(self.config_path):
            return {"perspectives": []}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f) or {"perspectives": []}
        except Exception as e:
            print(f"[ConfigIO] Erreur lecture : {e}")
            return {"perspectives": []}

    def _write_user(self, data: dict):
        """
        Écrit directement ``user.psp.json`` sur le disque.

        Émet :attr:`Configuration.sgl_saved` après écriture.

        :param data: Dictionnaire à sauvegarder.
        :type data: dict
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._cfg.sgl_saved.emit()
        except Exception as e:
            print(f"[ConfigIO] Erreur écriture : {e}")

    def _write_user_from_cfg(self):
        """
        Écrit ``user.psp.json`` depuis ``self._cfg``.

        Ne sauvegarde que les perspectives appartenant à l'utilisateur.
        Les perspectives des plugins sont incluses uniquement si elles
        ont été modifiées par l'utilisateur (overrides).

        **Logique :**

        - Perspective non-plugin → toujours écrite.
        - Perspective plugin non modifiée → ignorée (reste dans le ``.psp.json`` du plugin).
        - Perspective plugin modifiée → écrite comme override dans ``user.psp.json``.
        """
        plugin_perspectives  = self.get_plugin_perspectives()
        original_plugin_data = {}

        # Charger les versions originales des plugins pour détecter les overrides
        plugins_dir = os.path.dirname(os.path.dirname(self.base_dir))
        for name, plugin_name in plugin_perspectives.items():
            # Chercher le fichier .psp.json du plugin
            psp_files = glob.glob(
                os.path.join(plugins_dir, plugin_name, "*.psp.json")
            )
            if not psp_files:
                continue
            try:
                with open(psp_files[0], 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for p in data.get("perspectives", []):
                    if p.get("name") == name:
                        original_plugin_data[name] = p
                        break
            except Exception:
                pass

        # Construire la liste à écrire dans user.psp.json
        user_perspectives = []
        for p in self._cfg.get("perspectives", []):
            name = p.get("name")
            if name not in plugin_perspectives:
                # Perspective utilisateur → toujours écrire
                user_perspectives.append(p)
            else:
                # Perspective plugin → écrire seulement si modifiée (override)
                original = original_plugin_data.get(name)
                if original and p != original:
                    user_perspectives.append(p)

        self._write_user({"perspectives": user_perspectives})