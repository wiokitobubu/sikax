"""Constantes du format de fichier ``.sikax``.

Un projet Sikax est un document JSON encodé en UTF-8. Toutes les grandeurs
sont en unités SI (m, rad, kg, N, s) ; le bloc ``unites`` ne décrit que les
unités d'affichage choisies par l'utilisateur.

Le numéro ``version`` augmente à chaque évolution du format ;
``sikax.fichiers.migrations`` convertit les anciens fichiers.

- version 1 : Sikax 1.0 ;
- version 2 : Sikax 2.0 — cercles des solides, engrenages et cames, méthode
  d'intégration de l'étude dynamique, photo de fond.
"""

from __future__ import annotations

FORMAT = "sikax"
VERSION = 2
EXTENSION = ".sikax"
DIMENSION = 2
TAILLE_MAX = 50 * 1024 * 1024  # octets : au-delà, le fichier n'est pas un projet Sikax
