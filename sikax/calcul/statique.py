"""Étude statique : principe fondamental de la statique (PFS).

Dans une configuration donnée, l'équilibre de chaque solide s'écrit

    Φqᵀ·λ = Q

où Q regroupe les actions extérieures et λ les inconnues de liaison (et les
efforts des moteurs, qui jouent le rôle de blocages). Trois cas :

- système carré et régulier : mécanisme isostatique, solution unique ;
- plus d'inconnues que d'équations indépendantes (hyperstatique) : une
  infinité de solutions, Sikax donne celle de norme minimale et le signale ;
- mobilité non bloquée : l'équilibre n'existe que si les actions ne
  travaillent pas dans cette mobilité ; sinon ``equilibre`` vaut ``False``.

``rechercher_equilibre`` déplace le mécanisme le long de ses mobilités
libres jusqu'à une position d'équilibre stable.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from .algebre import decomposer, rang, resoudre
from .assemblage import assembler
from .cinematique import assembler_ou_echouer
from .enregistreur import Enregistreur
from .erreurs import ErreurCalcul
from .resultats import Resultats
from .systeme import SystemeMecanique

TOL_EQUILIBRE = 1e-7


def _echelle(systeme: SystemeMecanique) -> np.ndarray:
    w = np.ones(systeme.n)
    w[2::3] = systeme.mecanisme.longueur_caracteristique()
    return w


def _niveau_efforts(systeme: SystemeMecanique, Q_s: np.ndarray) -> float:
    """Ordre de grandeur des efforts en jeu, pour juger un résidu d'équilibre."""
    poids = float(np.sum(np.abs(systeme._poids)))
    return max(float(np.linalg.norm(Q_s)), poids, 1e-9)


def analyse_statique(
    systeme: SystemeMecanique,
    t: float = 0.0,
    tolerance: float = 1e-10,
    q_depart: Optional[np.ndarray] = None,
) -> Resultats:
    if systeme.n == 0:
        raise ErreurCalcul("aucun_solide")
    q = assembler_ou_echouer(systeme, systeme.q0 if q_depart is None else q_depart, t, tolerance)
    w = _echelle(systeme)
    J = systeme.jacobienne(q, t)
    nul = np.zeros(systeme.n)
    Q = systeme.forces(q, nul, t)
    multiplicateurs, r, _ = resoudre(J.T / w[:, None], Q / w)
    residu = float(np.linalg.norm((J.T @ multiplicateurs - Q) / w))
    equilibre = residu <= TOL_EQUILIBRE * _niveau_efforts(systeme, Q / w)

    enregistreur = Enregistreur(systeme, 1)
    enregistreur.noter(t, q, nul, nul, multiplicateurs, J)
    resultats = enregistreur.resultats("statique")
    resultats.mobilite_libre = systeme.n - r
    resultats.hyperstatisme = systeme.nc - r
    resultats.equilibre = equilibre
    if not equilibre:
        resultats.ajouter_message("avertissement", "pas_en_equilibre", mobilite=systeme.n - r)
    elif resultats.mobilite_libre > 0:
        resultats.ajouter_message("info", "equilibre_avec_mobilite", mobilite=resultats.mobilite_libre)
    if resultats.hyperstatisme > 0:
        resultats.ajouter_message("info", "hyperstatique_norme_minimale", h=resultats.hyperstatisme)
    return resultats


def _force_reduite(systeme: SystemeMecanique, q: np.ndarray, t: float, w: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Projection des actions sur les mobilités libres : (N, Nᵀ·Q)."""
    J = systeme.jacobienne(q, t) / w
    _, _, Vt, r = decomposer(J)
    N = Vt[r:].T
    Q = systeme.forces(q, np.zeros(systeme.n), t) / w
    return N, N.T @ Q


def rechercher_equilibre(
    systeme: SystemeMecanique,
    t: float = 0.0,
    q_depart: Optional[np.ndarray] = None,
    tolerance: float = 1e-10,
    iterations_max: int = 4000,
) -> Tuple[np.ndarray, bool]:
    """Cherche une position d'équilibre stable à partir de la configuration donnée.

    Le mécanisme est déplacé dans le sens où les actions travaillent (descente
    de l'énergie potentielle), avec un pas qui s'allonge tant que la direction
    se confirme et se raccourcit dès qu'elle s'inverse. Retourne (q, trouvé).
    """
    if systeme.n == 0:
        raise ErreurCalcul("aucun_solide")
    w = _echelle(systeme)
    q = assembler_ou_echouer(systeme, systeme.q0 if q_depart is None else q_depart, t, tolerance)
    N, g = _force_reduite(systeme, q, t, w)
    if N.shape[1] == 0:
        return q, True
    niveau = _niveau_efforts(systeme, systeme.forces(q, np.zeros(systeme.n), t) / w)
    longueur = float(w[2]) if systeme.n >= 3 else 1.0
    pas = 0.02 * longueur
    direction_precedente: Optional[np.ndarray] = None
    for _ in range(iterations_max):
        norme = float(np.linalg.norm(g))
        if norme <= TOL_EQUILIBRE * niveau:
            return q, True
        direction = (N @ g) / norme
        if direction_precedente is not None:
            if float(direction @ direction_precedente) < 0.0:
                pas *= 0.5
            else:
                pas = min(pas * 1.3, 0.1 * longueur)
        if pas < 1e-14 * longueur:
            break
        essai = assembler(systeme, q + pas * direction / w, t, True, tolerance)
        if not essai.converge:
            pas *= 0.5
            continue
        q = essai.q
        direction_precedente = direction
        N, g = _force_reduite(systeme, q, t, w)
    return q, float(np.linalg.norm(g)) <= 1e-5 * niveau


def degre_hyperstatisme(systeme: SystemeMecanique, q: Optional[np.ndarray] = None) -> int:
    """Nombre d'équations de liaison surabondantes dans la configuration q."""
    q = systeme.q0 if q is None else q
    if systeme.n == 0:
        return systeme.nc_liaisons
    J = systeme.jacobienne(q, 0.0, False) / _echelle(systeme)
    return systeme.nc_liaisons - (rang(J) if J.size else 0)
