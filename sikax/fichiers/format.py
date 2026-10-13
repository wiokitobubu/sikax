"""Constantes du format de fichier ``.sikax``.

Un projet Sikax est un document JSON encodé en UTF-8. Toutes les grandeurs
sont en unités SI (m, rad, kg, N, s) ; le bloc ``unites`` ne décrit que les
unités d'affichage choisies par l'utilisateur.

Le numéro ``version`` augmente à chaque évolution incompatible du format ;
``sikax.fichiers.migrations`` convertit les anciens fichiers.
"""

from __future__ import annotations

FORMAT = "sikax"
VERSION = 1
EXTENSION = ".sikax"
DIMENSION = 2
TAILLE_MAX = 50 * 1024 * 1024  # octets : au-delà, le fichier n'est pas un projet Sikax
