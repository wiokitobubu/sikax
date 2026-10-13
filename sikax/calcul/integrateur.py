"""Intégrateur de Dormand-Prince d'ordre 5(4) à pas adaptatif.

Schéma explicite classique (celui de ``ode45``) : chaque pas fournit une
solution d'ordre 5 et une estimation d'erreur qui règle le pas suivant.
Écrit ici en numpy pur pour ne pas dépendre de SciPy dans la distribution.
"""

from __future__ import annotations

from typing import Callable, Tuple

import numpy as np

C = (0.0, 1.0 / 5.0, 3.0 / 10.0, 4.0 / 5.0, 8.0 / 9.0, 1.0, 1.0)
A = (
    (),
    (1.0 / 5.0,),
    (3.0 / 40.0, 9.0 / 40.0),
    (44.0 / 45.0, -56.0 / 15.0, 32.0 / 9.0),
    (19372.0 / 6561.0, -25360.0 / 2187.0, 64448.0 / 6561.0, -212.0 / 729.0),
    (9017.0 / 3168.0, -355.0 / 33.0, 46732.0 / 5247.0, 49.0 / 176.0, -5103.0 / 18656.0),
    (35.0 / 384.0, 0.0, 500.0 / 1113.0, 125.0 / 192.0, -2187.0 / 6784.0, 11.0 / 84.0),
)
B5 = A[6] + (0.0,)
B4 = (5179.0 / 57600.0, 0.0, 7571.0 / 16695.0, 393.0 / 640.0, -92097.0 / 339200.0, 187.0 / 2100.0, 1.0 / 40.0)
E = tuple(b5 - b4 for b5, b4 in zip(B5, B4))

Derivee = Callable[[float, np.ndarray], np.ndarray]


def pas_dopri(f: Derivee, t: float, y: np.ndarray, h: float, k1: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Un pas de taille h. Retourne (y(t+h) à l'ordre 5, estimation d'erreur)."""
    k = [k1]
    for etage in range(1, 7):
        yi = y.copy()
        for coefficient, pente in zip(A[etage], k):
            if coefficient != 0.0:
                yi += h * coefficient * pente
        k.append(f(t + C[etage] * h, yi))
    y_nouveau = y.copy()
    erreur = np.zeros_like(y)
    for b, e, pente in zip(B5, E, k):
        if b != 0.0:
            y_nouveau += h * b * pente
        if e != 0.0:
            erreur += h * e * pente
    return y_nouveau, erreur


def norme_erreur(erreur: np.ndarray, y: np.ndarray, y_nouveau: np.ndarray, rtol: float, atol: float) -> float:
    echelle = atol + rtol * np.maximum(np.abs(y), np.abs(y_nouveau))
    return float(np.sqrt(np.mean((erreur / echelle) ** 2))) if erreur.size else 0.0


def facteur_de_pas(erreur: float) -> float:
    """Facteur multiplicatif du pas d'après l'erreur normalisée (1 = à la tolérance)."""
    if erreur <= 0.0:
        return 5.0
    return float(min(5.0, max(0.2, 0.9 * erreur ** (-0.2))))
