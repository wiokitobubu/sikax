"""Emplacement des ressources, en développement comme dans l'application installée.

Arborescence attendue à côté du programme ::

    locales/      fichiers de langue (fr.json, en.json…)
    resources/    icons/, themes/, exemples/, cours/, tutoriel/

En développement, ces dossiers sont à la racine du projet. Dans la
distribution Windows produite par PyInstaller, ils sont à côté de
``Sikax.exe`` ; à défaut, on les cherche dans le dossier interne du paquet.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List


def est_fige() -> bool:
    """Vrai quand l'application tourne depuis une distribution PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def racines() -> List[Path]:
    """Dossiers où chercher les ressources, par ordre de priorité."""
    candidats: List[Path] = []
    variable = os.environ.get("SIKAX_RESSOURCES")
    if variable:
        candidats.append(Path(variable))
    if est_fige():
        candidats.append(Path(sys.executable).resolve().parent)
        interne = getattr(sys, "_MEIPASS", None)
        if interne:
            candidats.append(Path(interne))
    candidats.append(Path(__file__).resolve().parent.parent)
    return candidats


def trouver(*parties: str) -> Path:
    """Chemin d'une ressource ; si elle est introuvable, le chemin attendu en priorité."""
    for racine in racines():
        chemin = racine.joinpath(*parties)
        if chemin.exists():
            return chemin
    return racines()[0].joinpath(*parties)


def dossier_locales() -> Path:
    return trouver("locales")


def dossier_resources() -> Path:
    return trouver("resources")


def dossier_icones() -> Path:
    return trouver("resources", "icons")


def dossier_themes() -> Path:
    return trouver("resources", "themes")


def dossier_exemples() -> Path:
    return trouver("resources", "exemples")


def dossier_cours() -> Path:
    """Fiches de cours : une page HTML par fiche, dans un sous-dossier par langue."""
    return trouver("resources", "cours")


def dossier_tutoriel() -> Path:
    """Animations facultatives du tutoriel (``<étape>.gif``), qui remplacent les démonstrations dessinées."""
    return trouver("resources", "tutoriel")


def icone_application() -> Path:
    nom = "sikax.ico" if sys.platform.startswith("win") else "sikax.png"
    return trouver("resources", "icons", nom)
