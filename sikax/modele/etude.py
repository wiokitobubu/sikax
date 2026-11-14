"""Paramètres de l'étude (type d'analyse, durée, pesanteur, précision)."""

from __future__ import annotations

from dataclasses import dataclass, replace

TYPES_ETUDE = ("statique", "cinematique", "dynamique")

METHODES = ("Radau", "BDF", "LSODA", "DOP853", "RK45")
"""Intégrateurs de ``scipy.integrate.solve_ivp`` proposés pour l'étude dynamique.

Radau et BDF sont implicites (robustes face aux problèmes raides : ressorts
très rigides, amortissements forts, solides très légers) ; LSODA bascule seul
entre une méthode explicite et BDF ; DOP853 et RK45 sont explicites."""
METHODE_PAR_DEFAUT = "Radau"


@dataclass
class Etude:
    type: str = "cinematique"
    """``statique`` : PFS dans la configuration courante ;
    ``cinematique`` : mouvement imposé par les moteurs, efforts par le PFD ;
    ``dynamique`` : mouvement calculé par intégration du PFD."""

    duree: float = 2.0
    pas: float = 0.01
    """Pas d'échantillonnage des résultats (s)."""

    pesanteur: bool = True
    gx: float = 0.0
    gy: float = -9.81

    inertie: bool = True
    """Étude cinématique : vrai = efforts par le PFD, faux = quasi-statique (PFS)."""

    tolerance: float = 1e-10
    """Tolérance de fermeture des liaisons (m ou rad)."""

    precision: float = 1e-8
    """Tolérance relative de l'intégrateur en dynamique."""

    methode: str = METHODE_PAR_DEFAUT
    """Intégrateur de l'étude dynamique (voir ``METHODES``)."""

    def __post_init__(self) -> None:
        if self.type not in TYPES_ETUDE:
            self.type = "cinematique"
        if self.methode not in METHODES:
            self.methode = METHODE_PAR_DEFAUT

    def nombre_de_pas(self) -> int:
        if self.pas <= 0.0 or self.duree <= 0.0:
            return 0
        return int(round(self.duree / self.pas))

    def copie(self) -> "Etude":
        return replace(self)
