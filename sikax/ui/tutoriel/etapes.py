"""Étapes du tutoriel : une démonstration animée, un titre et deux ou trois puces.

Les textes sont dans les fichiers de langue (``tutoriel.<étape>.titre`` et
``tutoriel.<étape>.puce1`` …). Chaque puce porte un *geste* : ``clic``,
``clic_droit``, ``molette``, ``glisser`` ou ``touche:<texte>`` ; un texte de
touche commençant par « @ » est traduit (``touches.<nom>`` : Entrée, Maj…).
``action`` est la commande dont le bouton est mis en lumière pendant l'étape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Etape:
    cle: str
    action: str = ""
    gestes: Tuple[str, ...] = ()

    @property
    def demo(self) -> str:
        return self.cle


ETAPES: Tuple[Etape, ...] = (
    Etape("bienvenue", "", ("clic", "touche:F5", "touche:F1")),
    Etape("barre", "outil_barre", ("touche:B", "clic", "touche:@entree")),
    Etape("pivot", "outil_pivot", ("touche:1", "clic")),
    Etape("relier", "outil_pivot", ("clic", "clic", "clic_droit")),
    Etape("glissiere", "outil_glissiere", ("touche:2", "glisser", "touche:@maj")),
    Etape("cercle", "outil_cercle", ("touche:D", "glisser", "clic")),
    Etape("engrenage", "outil_engrenage", ("touche:E", "clic", "clic")),
    Etape("came", "outil_came", ("touche:K", "clic", "clic")),
    Etape("moteur", "outil_moteur", ("touche:O", "clic")),
    Etape("force", "outil_force", ("touche:F", "glisser", "touche:C")),
    Etape("calcul", "lancer", ("touche:F5", "touche:@espace", "clic")),
    Etape("vue", "ajuster", ("molette", "clic_droit", "touche:A")),
    Etape("photo", "importer_photo", ("clic", "clic", "clic")),
    Etape("cours", "cours", ("clic", "touche:F1")),
)
