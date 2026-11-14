"""Migration des fichiers écrits par d'anciennes versions du format.

``MIGRATIONS[n]`` transforme un document de version ``n`` en document de
version ``n + 1``. Les étapes s'enchaînent jusqu'à la version courante : un
fichier ancien reste lisible sans que le lecteur ait à connaître son format.

Pour faire évoluer le format : incrémenter ``VERSION`` dans ``format.py``,
ajouter ici la fonction de passage, et un test dans ``tests/test_fichiers.py``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from .diagnostics import ErreurLecture, Rapport
from .format import VERSION

Migration = Callable[[Dict[str, Any]], Dict[str, Any]]

def _version_1_vers_2(donnees: Dict[str, Any]) -> Dict[str, Any]:
    """La version 2 n'ajoute que des éléments facultatifs : un fichier 1 est déjà valide."""
    return donnees


MIGRATIONS: Dict[int, Migration] = {1: _version_1_vers_2}


def migrer(donnees: Dict[str, Any], version: int, rapport: Rapport) -> Dict[str, Any]:
    """Amène le document à la version courante du format."""
    courante = version
    while courante < VERSION:
        etape = MIGRATIONS.get(courante)
        if etape is None:
            raise ErreurLecture("migration_impossible", rapport, version=version)
        donnees = etape(donnees)
        courante += 1
    if courante != version:
        rapport.info("fichier_migre", "version", depuis=version, vers=VERSION)
    return donnees
