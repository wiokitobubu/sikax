"""Unités d'affichage.

Toutes les données du modèle, des fichiers et du moteur de calcul sont en
unités SI (m, kg, s, rad, N). Les unités ne concernent que la saisie et
l'affichage : ``Unites`` convertit une valeur SI vers l'unité affichée et
inversement, selon la *dimension* physique de la grandeur.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

LONGUEURS: Dict[str, float] = {"m": 1.0, "cm": 100.0, "mm": 1000.0}
ANGLES: Dict[str, float] = {"rad": 1.0, "deg": 180.0 / math.pi}
SYMBOLES_ANGLE: Dict[str, str] = {"rad": "rad", "deg": "°"}

# Dimensions reconnues (une grandeur sans dimension utilise "sans").
DIMENSIONS = (
    "sans",
    "longueur",
    "angle",
    "temps",
    "vitesse",
    "acceleration",
    "vitesse_angulaire",
    "acceleration_angulaire",
    "force",
    "moment",
    "masse",
    "inertie",
    "raideur",
    "amortissement",
    "amortissement_angulaire",
    "puissance",
    "energie",
    "frequence",
)


@dataclass
class Unites:
    """Unités d'affichage d'un projet (longueur et angle sont au choix)."""

    longueur: str = "mm"
    angle: str = "deg"

    def __post_init__(self) -> None:
        if self.longueur not in LONGUEURS:
            self.longueur = "mm"
        if self.angle not in ANGLES:
            self.angle = "deg"

    def facteur(self, dimension: str) -> Tuple[float, str]:
        """(facteur, symbole) tels que valeur_affichée = valeur_SI × facteur."""
        kl, sl = LONGUEURS[self.longueur], self.longueur
        ka, sa = ANGLES[self.angle], SYMBOLES_ANGLE[self.angle]
        table = {
            "sans": (1.0, ""),
            "longueur": (kl, sl),
            "angle": (ka, sa),
            "temps": (1.0, "s"),
            "vitesse": (kl, f"{sl}/s"),
            "acceleration": (kl, f"{sl}/s²"),
            "vitesse_angulaire": (1.0, "rad/s"),
            "acceleration_angulaire": (1.0, "rad/s²"),
            "force": (1.0, "N"),
            "moment": (1.0, "N·m"),
            "masse": (1.0, "kg"),
            "inertie": (1.0, "kg·m²"),
            "raideur": (1.0 / kl, f"N/{sl}"),
            "amortissement": (1.0 / kl, f"N·s/{sl}"),
            "amortissement_angulaire": (1.0, "N·m·s/rad"),
            "puissance": (1.0, "W"),
            "energie": (1.0, "J"),
            "frequence": (1.0, "Hz"),
        }
        return table.get(dimension, (1.0, ""))

    def symbole(self, dimension: str) -> str:
        return self.facteur(dimension)[1]

    def vers_affichage(self, valeur_si: float, dimension: str) -> float:
        return valeur_si * self.facteur(dimension)[0]

    def depuis_affichage(self, valeur: float, dimension: str) -> float:
        return valeur / self.facteur(dimension)[0]

    def formater(self, valeur_si: float, dimension: str, chiffres: int = 5) -> str:
        k, s = self.facteur(dimension)
        texte = f"{valeur_si * k + 0.0:.{chiffres}g}"  # « + 0.0 » : jamais de « -0 »
        return f"{texte} {s}".strip()
