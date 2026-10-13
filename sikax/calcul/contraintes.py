"""Équations de contrainte élémentaires du plan.

Coordonnées généralisées : pour chaque solide mobile ``k``, le triplet
``q[3k:3k+3] = (xG, yG, θ)`` — position du centre de gravité et orientation.
Le bâti porte l'indice ``-1`` ; ses points sont donnés directement en
coordonnées globales.

Un point lié à un solide est décrit par une *attache* ``(k, sx, sy)`` : indice
du solide et coordonnées du vecteur G→P dans le repère du solide.

Chaque contrainte fournit :

- ``phi``   : le résidu Φ(q, t) (nul quand la liaison est respectée) ;
- ``jac``   : les lignes de la jacobienne Φq ;
- ``phi_t`` : la dérivée partielle ∂Φ/∂t (non nulle pour un moteur) ;
- ``gamma`` : le second membre de l'équation en accélération, Φq·q̈ = γ.

Les formules de ``jac`` et ``gamma`` sont vérifiées par différences finies
dans ``tests/test_contraintes.py``.
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Tuple

import numpy as np

from ..geometrie.vecteurs import normaliser_angle

Attache = Tuple[int, float, float]
Loi = Callable[[float], Tuple[float, float, float]]


def bras(q: np.ndarray, attache: Attache) -> Tuple[float, float, float, float]:
    """Position globale du point attaché et bras de levier G→P (repère global)."""
    k, sx, sy = attache
    if k < 0:
        return sx, sy, 0.0, 0.0
    i = 3 * k
    c, s = math.cos(q[i + 2]), math.sin(q[i + 2])
    ax = c * sx - s * sy
    ay = s * sx + c * sy
    return q[i] + ax, q[i + 1] + ay, ax, ay


def vitesse_point(qd: np.ndarray, k: int, ax: float, ay: float) -> Tuple[float, float]:
    """Vitesse du point de bras de levier (ax, ay) sur le solide ``k``."""
    if k < 0:
        return 0.0, 0.0
    i = 3 * k
    w = qd[i + 2]
    return qd[i] - ay * w, qd[i + 1] + ax * w


def _angle(q: np.ndarray, k: int) -> float:
    return q[3 * k + 2] if k >= 0 else 0.0


class Contrainte:
    """Classe de base d'un bloc d'équations de contrainte."""

    n_eq = 1

    def phi(self, q: np.ndarray, t: float, sortie: np.ndarray, i: int) -> None:
        raise NotImplementedError

    def jac(self, q: np.ndarray, t: float, J: np.ndarray, i: int) -> None:
        raise NotImplementedError

    def phi_t(self, q: np.ndarray, t: float, sortie: np.ndarray, i: int) -> None:
        """Dérivée partielle par rapport au temps (nulle par défaut)."""

    def gamma(self, q: np.ndarray, qd: np.ndarray, t: float, sortie: np.ndarray, i: int) -> None:
        raise NotImplementedError


class Coincidence(Contrainte):
    """Le point Pj du solide j coïncide avec le point Pi du solide i (2 équations)."""

    n_eq = 2

    def __init__(self, attache_i: Attache, attache_j: Attache) -> None:
        self.i = attache_i
        self.j = attache_j

    def phi(self, q, t, sortie, i):
        pix, piy, _, _ = bras(q, self.i)
        pjx, pjy, _, _ = bras(q, self.j)
        sortie[i] = pjx - pix
        sortie[i + 1] = pjy - piy

    def jac(self, q, t, J, i):
        ki, kj = self.i[0], self.j[0]
        if ki >= 0:
            _, _, ax, ay = bras(q, self.i)
            c = 3 * ki
            J[i, c] -= 1.0
            J[i, c + 2] += ay
            J[i + 1, c + 1] -= 1.0
            J[i + 1, c + 2] -= ax
        if kj >= 0:
            _, _, ax, ay = bras(q, self.j)
            c = 3 * kj
            J[i, c] += 1.0
            J[i, c + 2] -= ay
            J[i + 1, c + 1] += 1.0
            J[i + 1, c + 2] += ax

    def gamma(self, q, qd, t, sortie, i):
        gx = gy = 0.0
        ki, kj = self.i[0], self.j[0]
        if kj >= 0:
            _, _, ax, ay = bras(q, self.j)
            w2 = qd[3 * kj + 2] ** 2
            gx += ax * w2
            gy += ay * w2
        if ki >= 0:
            _, _, ax, ay = bras(q, self.i)
            w2 = qd[3 * ki + 2] ** 2
            gx -= ax * w2
            gy -= ay * w2
        sortie[i] = gx
        sortie[i + 1] = gy


class AngleRelatif(Contrainte):
    """θj − θi = c(t).

    Avec ``loi`` nulle, c est la constante ``c0`` et l'écart est ramené dans
    ]-π, π] (orientation fixe d'une glissière ou d'un encastrement). Avec une
    loi, c(t) = c0 + f(t) et l'angle est suivi sans repliement (moteur).
    """

    def __init__(self, ki: int, kj: int, c0: float, loi: Optional[Loi] = None) -> None:
        self.ki = ki
        self.kj = kj
        self.c0 = c0
        self.loi = loi

    def phi(self, q, t, sortie, i):
        ecart = _angle(q, self.kj) - _angle(q, self.ki) - self.c0
        if self.loi is None:
            sortie[i] = normaliser_angle(ecart)
        else:
            sortie[i] = ecart - self.loi(t)[0]

    def jac(self, q, t, J, i):
        if self.ki >= 0:
            J[i, 3 * self.ki + 2] -= 1.0
        if self.kj >= 0:
            J[i, 3 * self.kj + 2] += 1.0

    def phi_t(self, q, t, sortie, i):
        if self.loi is not None:
            sortie[i] = -self.loi(t)[1]

    def gamma(self, q, qd, t, sortie, i):
        sortie[i] = self.loi(t)[2] if self.loi is not None else 0.0


class _SurAxe(Contrainte):
    """Géométrie commune aux contraintes définies par un axe lié au solide i."""

    def __init__(self, attache_i: Attache, angle_axe: float, attache_j: Attache) -> None:
        self.i = attache_i
        self.j = attache_j
        self.alpha = angle_axe

    def _geometrie(self, q):
        """u (axe), n (normale), d = Pj − Pi, bras de levier des deux points."""
        beta = _angle(q, self.i[0]) + self.alpha
        ux, uy = math.cos(beta), math.sin(beta)
        pix, piy, aix, aiy = bras(q, self.i)
        pjx, pjy, ajx, ajy = bras(q, self.j)
        return ux, uy, -uy, ux, pjx - pix, pjy - piy, aix, aiy, ajx, ajy

    def _cinematique(self, q, qd):
        ux, uy, nx, ny, dx, dy, aix, aiy, ajx, ajy = self._geometrie(q)
        ki, kj = self.i[0], self.j[0]
        vix, viy = vitesse_point(qd, ki, aix, aiy)
        vjx, vjy = vitesse_point(qd, kj, ajx, ajy)
        wi = qd[3 * ki + 2] if ki >= 0 else 0.0
        wj = qd[3 * kj + 2] if kj >= 0 else 0.0
        # terme centripète a_j·ωj² − a_i·ωi²
        cx = ajx * wj * wj - aix * wi * wi
        cy = ajy * wj * wj - aiy * wi * wi
        return ux, uy, nx, ny, dx, dy, vjx - vix, vjy - viy, wi, cx, cy


class PointSurDroite(_SurAxe):
    """Le point Pj reste sur la droite liée au solide i passant par Pi : n·d = 0."""

    def phi(self, q, t, sortie, i):
        _, _, nx, ny, dx, dy, *_ = self._geometrie(q)
        sortie[i] = nx * dx + ny * dy

    def jac(self, q, t, J, i):
        ux, uy, nx, ny, dx, dy, aix, aiy, ajx, ajy = self._geometrie(q)
        ki, kj = self.i[0], self.j[0]
        if ki >= 0:
            c = 3 * ki
            J[i, c] -= nx
            J[i, c + 1] -= ny
            J[i, c + 2] += -(ux * dx + uy * dy) - (-nx * aiy + ny * aix)
        if kj >= 0:
            c = 3 * kj
            J[i, c] += nx
            J[i, c + 1] += ny
            J[i, c + 2] += -nx * ajy + ny * ajx

    def gamma(self, q, qd, t, sortie, i):
        ux, uy, nx, ny, dx, dy, ddx, ddy, wi, cx, cy = self._cinematique(q, qd)
        sortie[i] = (nx * dx + ny * dy) * wi * wi + 2.0 * wi * (ux * ddx + uy * ddy) + nx * cx + ny * cy


class TranslationPilotee(_SurAxe):
    """Déplacement imposé le long de l'axe : u·d = c0 + f(t) (moteur linéaire)."""

    def __init__(self, attache_i: Attache, angle_axe: float, attache_j: Attache, c0: float, loi: Loi) -> None:
        super().__init__(attache_i, angle_axe, attache_j)
        self.c0 = c0
        self.loi = loi

    def phi(self, q, t, sortie, i):
        ux, uy, _, _, dx, dy, *_ = self._geometrie(q)
        sortie[i] = ux * dx + uy * dy - self.c0 - self.loi(t)[0]

    def jac(self, q, t, J, i):
        ux, uy, nx, ny, dx, dy, aix, aiy, ajx, ajy = self._geometrie(q)
        ki, kj = self.i[0], self.j[0]
        if ki >= 0:
            c = 3 * ki
            J[i, c] -= ux
            J[i, c + 1] -= uy
            J[i, c + 2] += (nx * dx + ny * dy) - (-ux * aiy + uy * aix)
        if kj >= 0:
            c = 3 * kj
            J[i, c] += ux
            J[i, c + 1] += uy
            J[i, c + 2] += -ux * ajy + uy * ajx

    def phi_t(self, q, t, sortie, i):
        sortie[i] = -self.loi(t)[1]

    def gamma(self, q, qd, t, sortie, i):
        ux, uy, nx, ny, dx, dy, ddx, ddy, wi, cx, cy = self._cinematique(q, qd)
        sortie[i] = (
            (ux * dx + uy * dy) * wi * wi
            - 2.0 * wi * (nx * ddx + ny * ddy)
            + ux * cx
            + uy * cy
            + self.loi(t)[2]
        )


def coordonnee_translation(q: np.ndarray, attache_i: Attache, angle_axe: float, attache_j: Attache) -> float:
    """Abscisse de Pj le long de l'axe lié au solide i, comptée depuis Pi."""
    beta = _angle(q, attache_i[0]) + angle_axe
    pix, piy, _, _ = bras(q, attache_i)
    pjx, pjy, _, _ = bras(q, attache_j)
    return math.cos(beta) * (pjx - pix) + math.sin(beta) * (pjy - piy)


def vitesse_translation(q: np.ndarray, qd: np.ndarray, attache_i: Attache, angle_axe: float, attache_j: Attache) -> float:
    """Dérivée temporelle de ``coordonnee_translation``."""
    ki, kj = attache_i[0], attache_j[0]
    beta = _angle(q, ki) + angle_axe
    ux, uy = math.cos(beta), math.sin(beta)
    pix, piy, aix, aiy = bras(q, attache_i)
    pjx, pjy, ajx, ajy = bras(q, attache_j)
    vix, viy = vitesse_point(qd, ki, aix, aiy)
    vjx, vjy = vitesse_point(qd, kj, ajx, ajy)
    wi = qd[3 * ki + 2] if ki >= 0 else 0.0
    dx, dy = pjx - pix, pjy - piy
    return wi * (-uy * dx + ux * dy) + ux * (vjx - vix) + uy * (vjy - viy)
