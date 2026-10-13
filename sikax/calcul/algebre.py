"""Algèbre linéaire robuste (rang, noyau, solutions de norme minimale).

Les jacobiennes de liaison sont souvent de rang incomplet : mécanisme
hyperstatique (lignes liées) ou mobile (plus d'inconnues que d'équations).
Toutes les résolutions passent donc par la décomposition en valeurs
singulières plutôt que par une inversion directe.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

TOL_RANG = 1e-9


def _svd(A: np.ndarray, complete: bool):
    """SVD qui ne lève pas : une matrice non finie est d'abord assainie.

    Les indicateurs d'erreur flottante sont ignorés : certaines bibliothèques
    BLAS en lèvent à tort pendant ce calcul.
    """
    with np.errstate(all="ignore"):
        try:
            return np.linalg.svd(A, full_matrices=True) if complete else np.linalg.svd(A, compute_uv=False)
        except np.linalg.LinAlgError:
            propre = np.nan_to_num(A, nan=0.0, posinf=0.0, neginf=0.0)
            try:
                return np.linalg.svd(propre, full_matrices=True) if complete else np.linalg.svd(propre, compute_uv=False)
            except np.linalg.LinAlgError:
                lignes, colonnes = A.shape
                vide = np.zeros(min(lignes, colonnes))
                return (np.eye(lignes), vide, np.eye(colonnes)) if complete else vide


def valeurs_singulieres(A: np.ndarray) -> np.ndarray:
    if A.size == 0:
        return np.zeros(0)
    return _svd(A, False)


def rang(A: np.ndarray, tol: float = TOL_RANG) -> int:
    """Rang numérique : nombre de valeurs singulières > tol × la plus grande."""
    s = valeurs_singulieres(A)
    if s.size == 0 or s[0] <= 0.0:
        return 0
    return int(np.sum(s > tol * s[0]))


def conditionnement(A: np.ndarray, tol: float = TOL_RANG) -> float:
    """Rapport entre la plus grande et la plus petite valeur singulière retenue."""
    s = valeurs_singulieres(A)
    if s.size == 0 or s[0] <= 0.0:
        return 1.0
    retenues = s[s > tol * s[0]]
    return float(s[0] / retenues[-1])


def decomposer(A: np.ndarray, tol: float = TOL_RANG) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """SVD complète A = U·diag(s)·Vt et rang numérique."""
    lignes, colonnes = A.shape
    if lignes == 0 or colonnes == 0:
        return np.eye(lignes), np.zeros(0), np.eye(colonnes), 0
    U, s, Vt = _svd(A, True)
    r = int(np.sum(s > tol * s[0])) if s.size and s[0] > 0.0 else 0
    return U, s, Vt, r


def noyau(A: np.ndarray, tol: float = TOL_RANG) -> np.ndarray:
    """Base orthonormée du noyau de A (colonnes)."""
    _, _, Vt, r = decomposer(A, tol)
    return Vt[r:].T.copy()


def noyau_a_gauche(A: np.ndarray, tol: float = TOL_RANG) -> np.ndarray:
    """Base orthonormée du noyau de Aᵀ (colonnes) : combinaisons de lignes nulles."""
    U, _, _, r = decomposer(A, tol)
    return U[:, r:].copy()


def resoudre(A: np.ndarray, b: np.ndarray, tol: float = TOL_RANG) -> Tuple[np.ndarray, int, float]:
    """Solution de norme minimale de A·x = b au sens des moindres carrés.

    Retourne (x, rang, norme du résidu A·x − b).
    """
    lignes, colonnes = A.shape
    if lignes == 0 or colonnes == 0:
        return np.zeros(colonnes), 0, float(np.linalg.norm(b)) if b.size else 0.0
    with np.errstate(all="ignore"):
        try:
            x, _, r, _ = np.linalg.lstsq(A, b, rcond=tol)
        except np.linalg.LinAlgError:
            return np.zeros(colonnes), 0, float("inf")
        residu = float(np.linalg.norm(A @ x - b))
    return x, int(r), residu
