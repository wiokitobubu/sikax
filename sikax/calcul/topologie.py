"""Validation topologique : mobilité et hyperstatisme à partir du graphe des liaisons.

Méthode (théorie des mécanismes) :

1. Le *graphe des liaisons* a pour sommets les solides (bâti compris) et
   pour arêtes les liaisons. Son nombre cyclomatique γ = L − N + C est le
   nombre de boucles indépendantes (L liaisons, N solides, C composantes
   connexes).
2. Chaque boucle fournit une équation de fermeture cinématique : la somme
   des torseurs cinématiques des liaisons parcourues est nulle. Cela donne
   Ec = d·γ équations (d = 3 dans le plan, 6 dans l'espace) pour
   Ic = Σ ddl inconnues cinématiques.
3. Le rang rc de ce système, évalué dans la configuration courante, donne

       mobilité          m = Ic − rc
       hyperstatisme     h = Ec − rc

   et l'on retrouve la formule statique h = Is − Es + m avec Is = Σ inconnues
   de liaison et Es = d·(N − 1).

L'analyse « dans l'espace » reprend la même géométrie plane mais donne à
chaque liaison son modèle spatial (pivot, rotule, pivot glissant…) : c'est
elle qui révèle l'hyperstatisme réel d'un mécanisme plan.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..modele.liaisons import Liaison
from ..modele.mecanisme import Mecanisme
from ..modele.solide import ID_BATI
from .algebre import TOL_RANG, decomposer, rang, valeurs_singulieres
from .systeme import SystemeMecanique

SEUIL_SINGULARITE = 1e-5


@dataclass
class DetailLiaison:
    id: str
    nom: str
    type: str
    solide_a: str
    solide_b: str
    ddl: int
    inconnues_statiques: int
    modele: str = ""


@dataclass
class Boucle:
    """Boucle indépendante : liste de (identifiant de liaison, sens de parcours)."""

    liaisons: List[Tuple[str, int]]
    solides: List[str]
    hyperstatique: bool = False


@dataclass
class BilanTopologique:
    dimension: int
    nb_solides: int = 0
    nb_liaisons: int = 0
    nb_composantes: int = 1
    nb_boucles: int = 0
    ic: int = 0
    is_: int = 0
    ec: int = 0
    es: int = 0
    rang: int = 0
    mobilite: int = 0
    hyperstatisme: int = 0
    nb_moteurs: int = 0
    mobilite_pilotee: int = 0
    """Nombre de mobilités effectivement fixées par les moteurs."""
    mobilite_libre: int = 0
    """Mobilités restantes une fois les moteurs pris en compte."""
    moteurs_surabondants: int = 0
    liaisons: List[DetailLiaison] = field(default_factory=list)
    boucles: List[Boucle] = field(default_factory=list)
    solides_flottants: List[str] = field(default_factory=list)
    solides_isoles: List[str] = field(default_factory=list)
    avertissements: List[Tuple[str, Dict[str, object]]] = field(default_factory=list)
    proche_singularite: bool = False

    @property
    def isostatique(self) -> bool:
        return self.hyperstatisme == 0

    @property
    def coherent(self) -> bool:
        """Vérifie l'identité h = Is − Es + m (graphe connexe)."""
        return self.hyperstatisme == self.is_ - self.es + self.mobilite

    def liaisons_hyperstatiques(self) -> List[str]:
        vues: List[str] = []
        for boucle in self.boucles:
            if boucle.hyperstatique:
                for lid, _ in boucle.liaisons:
                    if lid not in vues:
                        vues.append(lid)
        return vues


# ------------------------------------------------------------------ graphe

def _liaisons_valides(mecanisme: Mecanisme) -> List[Liaison]:
    return [
        l
        for l in mecanisme.liaisons.values()
        if l.solide_a in mecanisme.solides
        and l.solide_b in mecanisme.solides
        and l.solide_a != l.solide_b
        and l.point_a in mecanisme.solides[l.solide_a].points
        and l.point_b in mecanisme.solides[l.solide_b].points
    ]


def arbre_couvrant(mecanisme: Mecanisme, liaisons: List[Liaison]):
    """Forêt couvrante du graphe des liaisons, parcourue depuis le bâti.

    Retourne (parent, composante, cordes) : ``parent[s] = (solide parent,
    liaison)``, ``composante[s]`` le numéro de composante connexe, et
    ``cordes`` les liaisons hors de l'arbre (une par boucle indépendante).
    """
    voisins: Dict[str, List[Liaison]] = {sid: [] for sid in mecanisme.solides}
    for liaison in liaisons:
        voisins[liaison.solide_a].append(liaison)
        voisins[liaison.solide_b].append(liaison)
    parent: Dict[str, Optional[Tuple[str, Liaison]]] = {}
    composante: Dict[str, int] = {}
    dans_arbre = set()
    racines = [ID_BATI] + [sid for sid in mecanisme.solides if sid != ID_BATI]
    numero = 0
    for racine in racines:
        if racine in parent or racine not in mecanisme.solides:
            continue
        parent[racine] = None
        composante[racine] = numero
        file = deque([racine])
        while file:
            courant = file.popleft()
            for liaison in voisins[courant]:
                autre = liaison.autre_solide(courant)
                if autre not in parent:
                    parent[autre] = (courant, liaison)
                    composante[autre] = numero
                    dans_arbre.add(liaison.id)
                    file.append(autre)
        numero += 1
    cordes = [l for l in liaisons if l.id not in dans_arbre]
    return parent, composante, cordes


def _chemin_vers_racine(parent, depart: str) -> List[Tuple[str, Optional[Liaison]]]:
    """[(solide, liaison vers son parent)] du solide de départ jusqu'à la racine."""
    chemin = []
    courant = depart
    while True:
        lien = parent[courant]
        chemin.append((courant, lien[1] if lien else None))
        if lien is None:
            return chemin
        courant = lien[0]


def boucles_independantes(mecanisme: Mecanisme, liaisons: Optional[List[Liaison]] = None) -> List[Boucle]:
    """Base de cycles du graphe des liaisons (une boucle par corde de l'arbre)."""
    if liaisons is None:
        liaisons = _liaisons_valides(mecanisme)
    parent, _, cordes = arbre_couvrant(mecanisme, liaisons)
    boucles = []
    for corde in cordes:
        # Parcours : A → B par la corde, puis retour de B vers A dans l'arbre.
        chemin_b = _chemin_vers_racine(parent, corde.solide_b)
        chemin_a = _chemin_vers_racine(parent, corde.solide_a)
        rang_a = {solide: i for i, (solide, _) in enumerate(chemin_a)}
        etapes: List[Tuple[str, int]] = [(corde.id, +1)]
        solides = [corde.solide_a, corde.solide_b]
        for solide, liaison in chemin_b:
            if solide in rang_a:  # ancêtre commun atteint
                descente = chemin_a[: rang_a[solide]]
                for fils, lien in reversed(descente):
                    # on descend du parent vers « fils » par « lien »
                    etapes.append((lien.id, +1 if lien.solide_b == fils else -1))
                    solides.append(fils)
                break
            pere = liaison.autre_solide(solide)
            etapes.append((liaison.id, +1 if liaison.solide_a == solide else -1))
            solides.append(pere)
        boucles.append(Boucle(etapes, solides[:-1]))
    return boucles


# -------------------------------------------------------- torseurs unitaires

def _torseurs_plans(mecanisme: Mecanisme, liaison: Liaison, echelle: float) -> List[np.ndarray]:
    """Torseurs cinématiques unitaires (ωz, Vx(O), Vy(O)) des mobilités planes."""
    tx, ty, rz = liaison.MOBILITES
    px, py = mecanisme.position_liaison(liaison)
    px, py = px / echelle, py / echelle
    beta = mecanisme.angle_axe_global(liaison)
    c, s = math.cos(beta), math.sin(beta)
    colonnes = []
    if rz:
        colonnes.append(np.array([1.0, py, -px]))
    if tx:
        colonnes.append(np.array([0.0, c, s]))
    if ty:
        colonnes.append(np.array([0.0, -s, c]))
    return colonnes


def _torseurs_spatiaux(mecanisme: Mecanisme, liaison: Liaison, echelle: float) -> List[np.ndarray]:
    """Torseurs cinématiques unitaires (ω, V(O)) du modèle spatial de la liaison."""
    px, py = mecanisme.position_liaison(liaison)
    p = np.array([px / echelle, py / echelle, 0.0])
    beta = mecanisme.angle_axe_global(liaison)
    c, s = math.cos(beta), math.sin(beta)
    axes = {"x": np.array([c, s, 0.0]), "y": np.array([-s, c, 0.0]), "z": np.array([0.0, 0.0, 1.0])}
    colonnes = []
    for nature, axe in liaison.modele_3d().mobilites:
        e = axes[axe]
        if nature == "R":
            colonnes.append(np.concatenate([e, np.cross(p, e)]))
        else:
            colonnes.append(np.concatenate([np.zeros(3), e]))
    return colonnes


def matrice_de_fermeture(mecanisme: Mecanisme, dimension: int, liaisons: List[Liaison], boucles: List[Boucle]) -> np.ndarray:
    """Matrice des équations de fermeture cinématique (d·γ lignes, Ic colonnes)."""
    d = 3 if dimension == 2 else 6
    echelle = mecanisme.longueur_caracteristique()
    generateur = _torseurs_plans if dimension == 2 else _torseurs_spatiaux
    colonnes: Dict[str, Tuple[int, List[np.ndarray]]] = {}
    total = 0
    for liaison in liaisons:
        torseurs = generateur(mecanisme, liaison, echelle)
        colonnes[liaison.id] = (total, torseurs)
        total += len(torseurs)
    K = np.zeros((d * len(boucles), total))
    for b, boucle in enumerate(boucles):
        for lid, sens in boucle.liaisons:
            debut, torseurs = colonnes[lid]
            for j, torseur in enumerate(torseurs):
                K[d * b : d * b + d, debut + j] += sens * torseur
    return K


# ------------------------------------------------------------------ analyse

def analyser_topologie(mecanisme: Mecanisme, dimension: int = 2) -> BilanTopologique:
    """Bilan de mobilité et d'hyperstatisme dans la configuration courante."""
    if dimension not in (2, 3):
        raise ValueError("la dimension doit être 2 ou 3")
    d = 3 if dimension == 2 else 6
    bilan = BilanTopologique(dimension)
    liaisons = _liaisons_valides(mecanisme)
    bilan.nb_solides = len(mecanisme.solides)
    bilan.nb_liaisons = len(liaisons)

    for liaison in liaisons:
        bilan.liaisons.append(
            DetailLiaison(
                liaison.id,
                liaison.nom,
                liaison.type,
                liaison.solide_a,
                liaison.solide_b,
                liaison.ddl(dimension),
                liaison.inconnues_statiques(dimension),
                liaison.modele_3d().cle if dimension == 3 else liaison.type,
            )
        )
    bilan.ic = sum(l.ddl for l in bilan.liaisons)
    bilan.is_ = sum(l.inconnues_statiques for l in bilan.liaisons)

    _, composante, _ = arbre_couvrant(mecanisme, liaisons)
    bilan.nb_composantes = len(set(composante.values()))
    relies = {l.solide_a for l in liaisons} | {l.solide_b for l in liaisons}
    for solide in mecanisme.solides_mobiles():
        if solide.id not in relies:
            bilan.solides_isoles.append(solide.id)
        elif composante[solide.id] != composante[ID_BATI]:
            bilan.solides_flottants.append(solide.id)

    boucles = boucles_independantes(mecanisme, liaisons)
    bilan.nb_boucles = len(boucles)
    bilan.ec = d * bilan.nb_boucles
    bilan.es = d * (bilan.nb_solides - 1)

    K = matrice_de_fermeture(mecanisme, dimension, liaisons, boucles)
    bilan.rang = rang(K) if K.size else 0
    # Chaque composante non reliée au bâti garde ses d mouvements d'ensemble.
    flottement = d * (bilan.nb_composantes - 1)
    bilan.mobilite = bilan.ic - bilan.rang + flottement
    bilan.hyperstatisme = bilan.ec - bilan.rang

    if K.size:
        s = valeurs_singulieres(K)
        if s.size and s[0] > 0.0:
            retenues = s[s > TOL_RANG * s[0]]
            bilan.proche_singularite = bool(retenues.size and retenues[-1] < SEUIL_SINGULARITE * s[0])
        if bilan.hyperstatisme > 0:
            U, _, _, r = decomposer(K)
            gauche = U[:, r:]
            for b, boucle in enumerate(boucles):
                if np.linalg.norm(gauche[d * b : d * b + d, :]) > 1e-6:
                    boucle.hyperstatique = True
    bilan.boucles = boucles

    _bilan_moteurs(mecanisme, bilan)

    if not mecanisme.solides_mobiles():
        bilan.avertissements.append(("aucun_solide", {}))
    if bilan.solides_isoles:
        bilan.avertissements.append(("solides_isoles", {"solides": list(bilan.solides_isoles)}))
    if bilan.solides_flottants:
        bilan.avertissements.append(("solides_flottants", {"solides": list(bilan.solides_flottants)}))
    if bilan.proche_singularite:
        bilan.avertissements.append(("configuration_singuliere", {}))
    if bilan.moteurs_surabondants:
        bilan.avertissements.append(("moteurs_surabondants", {"nombre": bilan.moteurs_surabondants}))
    return bilan


def _bilan_moteurs(mecanisme: Mecanisme, bilan: BilanTopologique) -> None:
    """Mobilités pilotées par les moteurs, d'après la jacobienne du mouvement plan."""
    try:
        systeme = SystemeMecanique(mecanisme)
    except (KeyError, ValueError):
        return
    bilan.nb_moteurs = len(systeme.moteurs)
    if systeme.n == 0:
        return
    echelle = np.ones(systeme.n)
    echelle[2::3] = mecanisme.longueur_caracteristique()
    J = systeme.jacobienne(systeme.q0, 0.0, True) / echelle
    rang_liaisons = rang(J[: systeme.nc_liaisons]) if systeme.nc_liaisons else 0
    rang_total = rang(J) if systeme.nc else 0
    bilan.mobilite_pilotee = rang_total - rang_liaisons
    bilan.moteurs_surabondants = bilan.nb_moteurs - bilan.mobilite_pilotee
    bilan.mobilite_libre = systeme.n - rang_total


def mobilite_par_jacobienne(mecanisme: Mecanisme) -> Tuple[int, int]:
    """(mobilité, hyperstatisme) du mouvement plan, calculés sur la jacobienne.

    Sert de contre-vérification indépendante de l'analyse par boucles.
    """
    systeme = SystemeMecanique(mecanisme, avec_moteurs=False)
    if systeme.n == 0:
        return 0, systeme.nc_liaisons
    echelle = np.ones(systeme.n)
    echelle[2::3] = mecanisme.longueur_caracteristique()
    J = systeme.jacobienne(systeme.q0, 0.0, False) / echelle
    r = rang(J) if J.size else 0
    return systeme.n - r, systeme.nc_liaisons - r
