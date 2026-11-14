"""Résultats d'une étude : séries temporelles nommées et états du mécanisme.

Un ``Canal`` est une grandeur échantillonnée dans le temps. Sa clé est un
chemin lisible et stable, par exemple ``point/S2/P1/vx`` ou ``liaison/L3/X``,
qui sert de référence pour les courbes et l'export CSV. Les valeurs sont en
unités SI ; ``dimension`` permet à l'interface de choisir l'unité affichée.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from ..physique.torseur import Torseur
from ..physique.unites import Unites


@dataclass
class Canal:
    cle: str
    dimension: str
    valeurs: np.ndarray
    objet: str = ""
    """Nom de l'objet du modèle concerné (affichage)."""

    @property
    def parties(self) -> Tuple[str, ...]:
        return tuple(self.cle.split("/"))

    @property
    def grandeur(self) -> str:
        return self.cle.rsplit("/", 1)[-1]


@dataclass
class Message:
    """Avertissement ou information produit par le calcul (code traduisible)."""

    niveau: str  # "info", "avertissement", "erreur"
    code: str
    parametres: Dict[str, object] = field(default_factory=dict)


@dataclass
class Resultats:
    type_etude: str
    temps: np.ndarray
    solides: List[str]
    """Identifiants des solides mobiles, dans l'ordre des colonnes de ``q``."""
    q: np.ndarray
    """États (une ligne par instant) : poses (x, y, angle) de l'origine de chaque solide."""
    canaux: Dict[str, Canal] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)
    mobilite_libre: int = 0
    hyperstatisme: int = 0
    equilibre: Optional[bool] = None
    """Étude statique : vrai si la configuration est en équilibre."""
    duree_calcul: float = 0.0
    complet: bool = True
    """Faux si le calcul s'est arrêté avant la fin (mouvement impossible, annulation)."""
    methode: str = ""
    """Intégrateur effectivement utilisé (étude dynamique)."""
    zones_singulieres: List[Tuple[float, float]] = field(default_factory=list)
    """Intervalles de temps passés près d'un point mort (étude cinématique)."""

    # ------------------------------------------------------------------ accès
    @property
    def nb_instants(self) -> int:
        return int(self.temps.size)

    def ajouter(self, cle: str, dimension: str, valeurs: Sequence[float], objet: str = "") -> Canal:
        canal = Canal(cle, dimension, np.asarray(valeurs, dtype=float), objet)
        self.canaux[cle] = canal
        return canal

    def canal(self, cle: str) -> Canal:
        try:
            return self.canaux[cle]
        except KeyError:
            raise KeyError(f"grandeur inconnue : « {cle} »") from None

    def valeurs(self, cle: str) -> np.ndarray:
        return self.canal(cle).valeurs

    def valeur(self, cle: str, indice: int = -1) -> float:
        return float(self.canal(cle).valeurs[indice])

    def cles(self, prefixe: str = "") -> List[str]:
        return [c for c in self.canaux if c.startswith(prefixe)]

    def indice_du_temps(self, t: float) -> int:
        """Indice de l'instant le plus proche de t."""
        if self.temps.size == 0:
            return 0
        return int(np.argmin(np.abs(self.temps - t)))

    def pose(self, solide_id: str, indice: int) -> Optional[Tuple[float, float, float]]:
        """Pose (x, y, angle) d'un solide mobile à l'instant d'indice donné."""
        if solide_id not in self.solides or self.q.size == 0:
            return None
        k = self.solides.index(solide_id)
        ligne = self.q[indice]
        return (float(ligne[3 * k]), float(ligne[3 * k + 1]), float(ligne[3 * k + 2]))

    def torseur_liaison(self, liaison_id: str, indice: int = -1) -> Optional[Torseur]:
        """Torseur de l'action de A sur B, réduit au point de liaison."""
        base = f"liaison/{liaison_id}/"
        if base + "X" not in self.canaux:
            return None
        return Torseur.plan(
            self.valeur(base + "X", indice),
            self.valeur(base + "Y", indice),
            self.valeur(base + "N", indice),
            (self.valeur(base + "px", indice), self.valeur(base + "py", indice)),
        )

    def ajouter_message(self, niveau: str, code: str, /, **parametres: object) -> None:
        for message in self.messages:
            if message.code == code and message.niveau == niveau:
                return
        self.messages.append(Message(niveau, code, dict(parametres)))

    # ------------------------------------------------------------------ export
    def vers_csv(
        self,
        chemin: str,
        cles: Optional[Iterable[str]] = None,
        unites: Optional[Unites] = None,
        separateur: str = ";",
        virgule_decimale: bool = True,
        entetes: Optional[Dict[str, str]] = None,
    ) -> int:
        """Écrit les grandeurs choisies dans un fichier CSV. Retourne le nombre de lignes.

        Par défaut le fichier suit les conventions françaises (séparateur « ; »
        et virgule décimale), directement lisible par Excel et LibreOffice.
        """
        unites = unites or Unites()
        choisies = [c for c in (cles if cles is not None else self.canaux) if c in self.canaux]

        def nombre(valeur: float) -> str:
            texte = repr(float(valeur))
            return texte.replace(".", ",") if virgule_decimale else texte

        titres = ["t (s)"]
        facteurs = []
        for cle in choisies:
            canal = self.canaux[cle]
            facteur, symbole = unites.facteur(canal.dimension)
            facteurs.append(facteur)
            nom = (entetes or {}).get(cle, cle)
            titres.append(f"{nom} ({symbole})" if symbole else nom)
        with open(chemin, "w", newline="", encoding="utf-8-sig") as fichier:
            ecrivain = csv.writer(fichier, delimiter=separateur)
            ecrivain.writerow(titres)
            for i in range(self.nb_instants):
                ligne = [nombre(self.temps[i])]
                for cle, facteur in zip(choisies, facteurs):
                    ligne.append(nombre(self.canaux[cle].valeurs[i] * facteur))
                ecrivain.writerow(ligne)
        return self.nb_instants
