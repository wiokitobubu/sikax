"""Étude cinématique : le mouvement est imposé par les moteurs.

À chaque instant :

1. position      Φ(q, t) = 0                 (Gauss-Newton, voir ``assemblage``)
2. vitesse       Φq·q̇ = −Φt
3. accélération  Φq·q̈ = γ
4. efforts       Φqᵀ·λ = Q − M·q̈            (PFD ; PFS si l'inertie est négligée)

L'étape 4 est une dynamique inverse : connaissant le mouvement, on obtient
les actions de liaison et l'effort que chaque moteur doit fournir.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .algebre import conditionnement, rang, resoudre
from .assemblage import ResultatAssemblage, assembler
from .enregistreur import Enregistreur
from .erreurs import CalculInterrompu, ErreurCalcul
from .resultats import Resultats
from .systeme import SystemeMecanique

Progression = Optional[Callable[[float], None]]
Annulation = Optional[Callable[[], bool]]

SEUIL_CONDITIONNEMENT = 1e7


def _echelle(systeme: SystemeMecanique) -> np.ndarray:
    w = np.ones(systeme.n)
    w[2::3] = systeme.mecanisme.longueur_caracteristique()
    return w


def assembler_ou_echouer(systeme: SystemeMecanique, q: np.ndarray, t: float, tolerance: float, moteurs: bool = True) -> np.ndarray:
    resultat = assembler(systeme, q, t, moteurs, tolerance)
    if not resultat.converge:
        raise ErreurCalcul("assemblage_impossible", residu=resultat.residu)
    return resultat.q


def _avancer(systeme: SystemeMecanique, q: np.ndarray, prediction: np.ndarray, t_avant: float, t: float, tolerance: float) -> ResultatAssemblage:
    """Position à l'instant t, avec replis si la première tentative échoue."""
    essai = assembler(systeme, prediction, t, True, tolerance)
    if essai.converge:
        return essai
    essai = assembler(systeme, q, t, True, tolerance)
    if essai.converge:
        return essai
    # Continuation : on rejoint t par petits pas depuis la dernière position sûre.
    for divisions in (4, 16, 64):
        courant = q
        reussi = True
        for etape in range(1, divisions + 1):
            intermediaire = t_avant + (t - t_avant) * etape / divisions
            essai = assembler(systeme, courant, intermediaire, True, tolerance)
            if not essai.converge:
                reussi = False
                break
            courant = essai.q
        if reussi:
            return essai
    return essai


def analyse_cinematique(
    systeme: SystemeMecanique,
    temps: np.ndarray,
    inertie: bool = True,
    tolerance: float = 1e-10,
    progression: Progression = None,
    annule: Annulation = None,
) -> Resultats:
    if systeme.n == 0:
        raise ErreurCalcul("aucun_solide")
    w = _echelle(systeme)
    t0 = float(temps[0])
    q = assembler_ou_echouer(systeme, systeme.q0, t0, tolerance)

    J = systeme.jacobienne(q, t0)
    r = rang(J / w) if J.size else 0
    if r < systeme.n:
        rang_liaisons = rang(J[: systeme.nc_liaisons] / w) if systeme.nc_liaisons else 0
        mobilite = systeme.n - rang_liaisons
        if len(systeme.moteurs) >= mobilite:
            # Assez de moteurs, mais ils ne commandent pas le mouvement ici (point mort).
            raise ErreurCalcul("position_initiale_singuliere", mobilite=systeme.n - r)
        raise ErreurCalcul("mobilite_non_pilotee", mobilite=systeme.n - r, moteurs=len(systeme.moteurs))

    enregistreur = Enregistreur(systeme, temps.size)
    qd = np.zeros(systeme.n)
    qdd = np.zeros(systeme.n)
    t_avant = t0
    arret: Optional[float] = None
    singulier: Optional[float] = None
    hyperstatisme = systeme.nc - r

    for i, t in enumerate(temps):
        t = float(t)
        if annule is not None and annule():
            raise CalculInterrompu()
        if i > 0:
            dt = t - t_avant
            essai = _avancer(systeme, q, q + qd * dt + 0.5 * qdd * dt * dt, t_avant, t, tolerance)
            if not essai.converge:
                arret = t
                break
            q = essai.q
        J = systeme.jacobienne(q, t)
        Js = J / w
        qd_s, r_v, _ = resoudre(Js, -systeme.phi_t(q, t))
        qd = qd_s / w
        qdd_s, _, _ = resoudre(Js, systeme.gamma(q, qd, t))
        qdd = qdd_s / w
        if r_v < systeme.n:
            # Position singulière : le mouvement n'y est plus déterminé par les moteurs.
            arret = t
            break
        if singulier is None and conditionnement(Js) > SEUIL_CONDITIONNEMENT:
            singulier = t
        second_membre = systeme.forces(q, qd, t)
        if inertie:
            second_membre = second_membre - systeme.masses * qdd
        multiplicateurs, _, _ = resoudre(J.T, second_membre)
        enregistreur.noter(t, q, qd, qdd, multiplicateurs, J)
        t_avant = t
        if progression is not None and (i % 20 == 0 or i == temps.size - 1):
            progression((i + 1) / temps.size)

    resultats = enregistreur.resultats("cinematique")
    resultats.hyperstatisme = hyperstatisme
    resultats.mobilite_libre = 0
    if arret is not None:
        resultats.complet = False
        resultats.ajouter_message("avertissement", "mouvement_impossible", t=arret)
    if singulier is not None:
        resultats.ajouter_message("avertissement", "configuration_singuliere", t=singulier)
    if hyperstatisme > 0:
        resultats.ajouter_message("info", "hyperstatique_norme_minimale", h=hyperstatisme)
    if not inertie:
        resultats.ajouter_message("info", "quasi_statique")
    elif not systeme.masse_definie_positive:
        resultats.ajouter_message("info", "inertie_partielle")
    return resultats
