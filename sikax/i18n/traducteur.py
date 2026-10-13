"""Localisation de l'application.

Chaque langue est un fichier JSON du dossier ``locales`` (``fr.json``,
``en.json``…). Les textes y sont rangés par rubriques imbriquées ; le code
les désigne par un chemin pointé :

    tr("action.ouvrir")
    tr("fichier.ouvert", nom="pendule.sikax")   # "{nom} ouvert."

Le français est la langue de référence : une clé absente de la langue active
est cherchée en français, et à défaut la clé elle-même est affichée (et
mémorisée dans ``cles_manquantes``, ce que vérifient les tests).

Ce module n'importe pas Qt : il sert aussi bien à l'interface qu'aux scripts.
Ajouter une langue se réduit à déposer un nouveau fichier dans ``locales``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from ..chemins import dossier_locales

LANGUE_PAR_DEFAUT = "fr"


def aplatir(donnees: Dict[str, Any], prefixe: str = "") -> Dict[str, str]:
    """Transforme les rubriques imbriquées en dictionnaire {"a.b.c": texte}."""
    resultat: Dict[str, str] = {}
    for cle, valeur in donnees.items():
        chemin = f"{prefixe}.{cle}" if prefixe else cle
        if isinstance(valeur, dict):
            resultat.update(aplatir(valeur, chemin))
        else:
            resultat[chemin] = str(valeur)
    return resultat


class Traducteur:
    def __init__(self, dossier: Optional[Path] = None) -> None:
        self._dossier = dossier
        self._reference: Dict[str, str] = {}
        self._textes: Dict[str, str] = {}
        self.langue = LANGUE_PAR_DEFAUT
        self.cles_manquantes: Set[str] = set()
        self._abonnes: List[Callable[[], None]] = []
        self._pret = False

    @property
    def dossier(self) -> Path:
        return self._dossier if self._dossier is not None else dossier_locales()

    # ---------------------------------------------------------------- langues
    def langues_disponibles(self) -> Dict[str, str]:
        """{code: nom affiché} des langues présentes dans le dossier."""
        langues: Dict[str, str] = {}
        if self.dossier.is_dir():
            for fichier in sorted(self.dossier.glob("*.json")):
                try:
                    donnees = json.loads(fichier.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                meta = donnees.get("_meta", {}) if isinstance(donnees, dict) else {}
                langues[fichier.stem] = str(meta.get("langue", fichier.stem))
        return langues

    def _lire(self, code: str) -> Dict[str, str]:
        fichier = self.dossier / f"{code}.json"
        try:
            donnees = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(donnees, dict):
            return {}
        donnees.pop("_meta", None)
        return aplatir(donnees)

    def charger(self, code: str = LANGUE_PAR_DEFAUT) -> bool:
        """Active une langue. Retourne ``False`` si son fichier est absent ou illisible."""
        self._reference = self._lire(LANGUE_PAR_DEFAUT)
        textes = self._reference if code == LANGUE_PAR_DEFAUT else self._lire(code)
        trouve = bool(textes)
        self._textes = textes if trouve else self._reference
        self.langue = code if trouve else LANGUE_PAR_DEFAUT
        self._pret = True
        for abonne in list(self._abonnes):
            abonne()
        return trouve

    def abonner(self, rappel: Callable[[], None]) -> None:
        """Enregistre une fonction appelée à chaque changement de langue."""
        if rappel not in self._abonnes:
            self._abonnes.append(rappel)

    def desabonner(self, rappel: Callable[[], None]) -> None:
        if rappel in self._abonnes:
            self._abonnes.remove(rappel)

    # ------------------------------------------------------------- traduction
    def existe(self, cle: str) -> bool:
        if not self._pret:
            self.charger(self.langue)
        return cle in self._textes or cle in self._reference

    def modele(self, cle: str) -> Optional[str]:
        """Texte brut de la clé, avec ses emplacements ``{nom}`` non remplis, ou ``None``."""
        if not self._pret:
            self.charger(self.langue)
        return self._textes.get(cle, self._reference.get(cle))

    def tr(self, cle: str, /, **parametres: Any) -> str:
        if not self._pret:
            self.charger(self.langue)
        texte = self._textes.get(cle)
        if texte is None:
            texte = self._reference.get(cle)
        if texte is None:
            self.cles_manquantes.add(cle)
            return cle
        if parametres:
            try:
                return texte.format(**parametres)
            except (KeyError, IndexError, ValueError):
                return texte
        return texte


traducteur = Traducteur()


def tr(cle: str, /, **parametres: Any) -> str:
    """Texte de la clé dans la langue active (raccourci vers le traducteur global).

    ``cle`` est un argument positionnel : les paramètres du texte peuvent
    porter n'importe quel nom, y compris ``cle``.
    """
    return traducteur.tr(cle, **parametres)
