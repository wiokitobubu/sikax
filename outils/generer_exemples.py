"""Régénère les projets d'exemple de ``resources/exemples`` à partir de la bibliothèque.

    python outils/generer_exemples.py
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from sikax.fichiers import EXTENSION, enregistrer  # noqa: E402
from sikax.modele.bibliotheque import EXEMPLES  # noqa: E402


def main() -> None:
    dossier = RACINE / "resources" / "exemples"
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, constructeur in EXEMPLES.items():
        mecanisme = constructeur()
        mecanisme.auteur = "Sikax"
        chemin = dossier / f"{nom}{EXTENSION}"
        enregistrer(mecanisme, str(chemin), sauvegarde=False)
        print(f"{chemin.relative_to(RACINE)}  ({len(mecanisme.solides) - 1} solides, {len(mecanisme.liaisons)} liaisons)")


if __name__ == "__main__":
    main()
