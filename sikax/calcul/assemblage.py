"""Résolution en position : fermeture des liaisons et déplacement à la souris.

- ``assembler`` cherche la configuration qui respecte les liaisons (et les
  moteurs à l'instant t) la plus proche d'une configuration de départ, par
  la méthode de Gauss-Newton avec pas de norme minimale.
- ``glisser`` déplace un point d'un solide vers une cible en laissant le
  reste du mécanisme suivre : c'est la manipulation de la configuration
  initiale dans l'interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from .algebre import decomposer, resoudre
from .contraintes import Attache, bras
from .systeme import SystemeMecanique

ROTATION_MAX_PAR_ITERATION = 0.5  # rad


@dataclass
class ResultatAssemblage:
    q: np.ndarray
    converge: bool
    iterations: int
    residu: float


def _echelles(systeme: SystemeMecanique) -> np.ndarray:
    """Poids des coordonnées : les angles sont comptés en « longueur × angle »."""
    w = np.ones(systeme.n)
    w[2::3] = systeme.mecanisme.longueur_caracteristique()
    return w


def _limiter(dq: np.ndarray) -> np.ndarray:
    rotation = float(np.max(np.abs(dq[2::3]))) if dq.size else 0.0
    if rotation > ROTATION_MAX_PAR_ITERATION:
        return dq * (ROTATION_MAX_PAR_ITERATION / rotation)
    return dq


def assembler(
    systeme: SystemeMecanique,
    q_depart: np.ndarray,
    t: float = 0.0,
    moteurs: bool = True,
    tolerance: float = 1e-10,
    iterations_max: int = 80,
) -> ResultatAssemblage:
    """Configuration respectant les liaisons, la plus proche de ``q_depart``.

    Ne lève pas d'exception : en cas d'échec, ``converge`` vaut ``False``.
    """
    with np.errstate(all="ignore"):
        resultat = _assembler(systeme, q_depart, t, moteurs, tolerance, iterations_max)
    if not np.all(np.isfinite(resultat.q)):
        return ResultatAssemblage(np.array(q_depart, dtype=float), False, resultat.iterations, float("inf"))
    return resultat


def _assembler(systeme: SystemeMecanique, q_depart: np.ndarray, t: float, moteurs: bool, tolerance: float, iterations_max: int) -> ResultatAssemblage:
    q = np.array(q_depart, dtype=float)
    if systeme.n == 0 or systeme.taille(moteurs) == 0:
        return ResultatAssemblage(q, True, 0, 0.0)
    w = _echelles(systeme)
    # Un écart ne peut pas descendre sous la précision des nombres à l'échelle du mécanisme.
    tolerance = max(tolerance, 1e-12 * float(w[2]))
    phi = systeme.phi(q, t, moteurs)
    residu = float(np.max(np.abs(phi)))
    norme = float(np.linalg.norm(phi))
    for iteration in range(iterations_max):
        if residu <= tolerance:
            return ResultatAssemblage(q, True, iteration, residu)
        J = systeme.jacobienne(q, t, moteurs) / w
        pas, _, _ = resoudre(J, -phi, 1e-10)
        dq = _limiter(pas / w)
        alpha = 1.0
        accepte = False
        while alpha >= 1e-4:
            essai = q + alpha * dq
            phi_essai = systeme.phi(essai, t, moteurs)
            norme_essai = float(np.linalg.norm(phi_essai))
            if norme_essai < norme * (1.0 - 1e-4 * alpha) or np.max(np.abs(phi_essai)) <= tolerance:
                q, phi, norme = essai, phi_essai, norme_essai
                residu = float(np.max(np.abs(phi)))
                accepte = True
                break
            alpha *= 0.5
        if not accepte:
            return ResultatAssemblage(q, residu <= tolerance, iteration + 1, residu)
    return ResultatAssemblage(q, residu <= tolerance, iterations_max, residu)


def glisser(
    systeme: SystemeMecanique,
    q_depart: np.ndarray,
    attache: Attache,
    cible: Tuple[float, float],
    iterations: int = 12,
    tolerance: float = 1e-9,
) -> np.ndarray:
    """Amène au mieux le point attaché sur la cible en respectant les liaisons.

    Les moteurs sont ignorés : l'utilisateur fixe librement la configuration.
    Si la cible est inaccessible, le point s'en approche autant que possible.
    En cas de difficulté numérique, la configuration de départ est rendue.
    """
    depart = np.array(q_depart, dtype=float)
    try:
        with np.errstate(all="ignore"):
            q = _glisser(systeme, depart, attache, cible, iterations, tolerance)
    except np.linalg.LinAlgError:
        return depart
    return q if np.all(np.isfinite(q)) else depart


def _glisser(systeme: SystemeMecanique, q_depart: np.ndarray, attache: Attache, cible: Tuple[float, float], iterations: int, tolerance: float) -> np.ndarray:
    q = np.array(q_depart, dtype=float)
    k = attache[0]
    if k < 0 or systeme.n == 0:
        return q
    w = _echelles(systeme)
    for _ in range(iterations):
        J = systeme.jacobienne(q, 0.0, False) / w
        phi = systeme.phi(q, 0.0, False)
        U, s, Vt, r = decomposer(J, 1e-9)
        if r > 0:
            correction = -(Vt[:r].T @ ((U[:, :r].T @ phi) / s[:r]))
        else:
            correction = np.zeros(systeme.n)
        N = Vt[r:].T
        if N.shape[1] == 0:
            q = q + correction / w
            break
        px, py, ax, ay = bras(q, attache)
        Jp = np.zeros((2, systeme.n))
        Jp[0, 3 * k] = 1.0
        Jp[1, 3 * k + 1] = 1.0
        Jp[0, 3 * k + 2] = -ay
        Jp[1, 3 * k + 2] = ax
        Jp /= w
        ecart = np.array([cible[0] - px, cible[1] - py]) - Jp @ correction
        A = Jp @ N
        AtA = A.T @ A
        amortissement = 1e-8 * float(np.trace(AtA)) / max(AtA.shape[0], 1) + 1e-18
        z = np.linalg.solve(AtA + amortissement * np.eye(AtA.shape[0]), A.T @ ecart)
        dq = _limiter((correction + N @ z) / w)
        q = q + dq
        if float(np.linalg.norm(ecart)) <= tolerance and float(np.max(np.abs(phi), initial=0.0)) <= tolerance:
            break
    return assembler(systeme, q, 0.0, moteurs=False, tolerance=1e-11).q
