"""Moteur : mouvement imposé à une liaison pivot ou glissière."""

from __future__ import annotations

from dataclasses import dataclass, field

from .lois import LoiMouvement


@dataclass
class Moteur:
    """Impose la coordonnée d'une liaison en fonction du temps.

    La coordonnée pilotée est l'angle de B par rapport à A pour une pivot, le
    déplacement de B le long de l'axe pour une glissière.

    - ``relatif`` vrai : coordonnée = valeur dans la configuration initiale + loi(t) ;
    - ``relatif`` faux : coordonnée = loi(t).

    L'effort moteur calculé (couple ou force) est l'action exercée par le
    moteur de A sur B pour réaliser ce mouvement.
    """

    id: str
    nom: str
    liaison: str
    loi: LoiMouvement = field(default_factory=LoiMouvement)
    relatif: bool = True
    actif: bool = True

    def copie(self) -> "Moteur":
        return Moteur(self.id, self.nom, self.liaison, self.loi.copie(), self.relatif, self.actif)
