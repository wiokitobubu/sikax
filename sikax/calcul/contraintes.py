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

    def dissipe(self) -> bool:
        """Vrai si la contrainte frotte (engrenage de rendement inférieur à 1)."""
        return False

    def a_effort_radial(self) -> bool:
        """Vrai si la contrainte transmet un effort qui ne travaille pas (effort radial d'engrenage)."""
        return False


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


# ------------------------------------------------------------------ contacts
#
# Les liaisons de contact (engrenages, cames) se placent au point de contact,
# qui se déplace. Leur équation est écrite de sorte que la force généralisée
# Φqᵀ·λ soit exactement l'effort physique appliqué au point de contact : les
# pivots des roues et le guidage du poussoir en reçoivent la bonne part.


def _vitesse(qd: np.ndarray, attache: Attache, ax: float, ay: float) -> Tuple[float, float]:
    return vitesse_point(qd, attache[0], ax, ay)


def _ajouter_force(Q: np.ndarray, k: int, gx: float, gy: float, fx: float, fy: float, px: float, py: float) -> None:
    """Force (fx, fy) appliquée au point (px, py) du solide k de centre de gravité (gx, gy)."""
    if k < 0:
        return
    i = 3 * k
    Q[i] += fx
    Q[i + 1] += fy
    Q[i + 2] += (px - gx) * fy - (py - gy) * fx


def _ajouter_couple(Q: np.ndarray, k: int, couple: float) -> None:
    if k >= 0:
        Q[3 * k + 2] += couple


class EngrenageRoues(Contrainte):
    """Roulement sans glissement des cercles primitifs de deux roues (1 équation).

    Avec φ la direction de la ligne des centres OaOb (orientée de A vers B) :

        Φ = ra·(θa − φ) + s·rb·(θb − φ) − c0

    s = +1 pour un engrenage extérieur, −1 pour un engrenage intérieur (B est
    la couronne). ra et rb sont les rayons primitifs de fonctionnement, de
    rapport Za/Zb et tels que ra + s·rb = entraxe : la force généralisée est
    alors l'effort tangentiel Ft appliqué au point primitif I. Le terme en φ
    rend la relation juste quand la ligne des centres tourne (train
    épicycloïdal) : c'est la formule de Willis.
    """

    def __init__(
        self,
        attache_a: Attache,
        attache_b: Attache,
        ra: float,
        rb: float,
        signe: float,
        q0: np.ndarray,
        angle_pression: float = 0.0,
        rendement: float = 1.0,
        porte_train: int = -1,
    ) -> None:
        self.a = attache_a
        self.b = attache_b
        self.ra = ra
        self.rb = rb
        self.s = signe
        self.k = ra + signe * rb
        self.tan_alpha = math.tan(angle_pression)
        self.rendement = rendement
        self.porte_train = porte_train
        pax, pay, _, _ = bras(q0, attache_a)
        pbx, pby, _, _ = bras(q0, attache_b)
        self._reference = math.atan2(pby - pay, pbx - pax)
        self.c0 = 0.0
        valeur = np.zeros(1)
        self.phi(q0, 0.0, valeur, 0)
        self.c0 = float(valeur[0])

    def _ligne(self, q: np.ndarray):
        pax, pay, aax, aay = bras(q, self.a)
        pbx, pby, abx, aby = bras(q, self.b)
        return pax, pay, aax, aay, pbx, pby, abx, aby, pbx - pax, pby - pay

    def _direction(self, dx: float, dy: float) -> float:
        """Direction de OaOb, suivie continûment d'un appel à l'autre (sans saut de 2π)."""
        phi = self._reference + normaliser_angle(math.atan2(dy, dx) - self._reference)
        self._reference = phi
        return phi

    def phi(self, q, t, sortie, i):
        *_, dx, dy = self._ligne(q)
        phi = self._direction(dx, dy)
        sortie[i] = self.ra * (_angle(q, self.a[0]) - phi) + self.s * self.rb * (_angle(q, self.b[0]) - phi) - self.c0

    def jac(self, q, t, J, i):
        _, _, aax, aay, _, _, abx, aby, dx, dy = self._ligne(q)
        d2 = dx * dx + dy * dy
        coef = -self.k / d2  # −k·∂φ/∂q, terme par terme
        ka, kb = self.a[0], self.b[0]
        if ka >= 0:
            c = 3 * ka
            J[i, c] += coef * dy
            J[i, c + 1] += -coef * dx
            J[i, c + 2] += self.ra - coef * (dx * aax + dy * aay)
        if kb >= 0:
            c = 3 * kb
            J[i, c] += -coef * dy
            J[i, c + 1] += coef * dx
            J[i, c + 2] += self.s * self.rb + coef * (dx * abx + dy * aby)

    def gamma(self, q, qd, t, sortie, i):
        _, _, aax, aay, _, _, abx, aby, dx, dy = self._ligne(q)
        ka, kb = self.a[0], self.b[0]
        vax, vay = _vitesse(qd, self.a, aax, aay)
        vbx, vby = _vitesse(qd, self.b, abx, aby)
        ddx, ddy = vbx - vax, vby - vay
        wa = qd[3 * ka + 2] if ka >= 0 else 0.0
        wb = qd[3 * kb + 2] if kb >= 0 else 0.0
        cx = -abx * wb * wb + aax * wa * wa
        cy = -aby * wb * wb + aay * wa * wa
        d2 = dx * dx + dy * dy
        croix_c = dx * cy - dy * cx
        croix_v = dx * ddy - dy * ddx
        scal_v = dx * ddx + dy * ddy
        sortie[i] = self.k * (croix_c / d2 - 2.0 * scal_v * croix_v / (d2 * d2))

    # -- efforts physiques ----------------------------------------------------
    def geometrie(self, q: np.ndarray):
        """(I, n, t, Oa, Ob) : point primitif, unitaire de OaOb, tangente, centres."""
        pax, pay, _, _, pbx, pby, _, _, dx, dy = self._ligne(q)
        a = math.hypot(dx, dy) or 1e-300
        nx, ny = dx / a, dy / a
        ix, iy = pax + self.ra / self.k * dx, pay + self.ra / self.k * dy
        return (ix, iy), (nx, ny), (-ny, nx), (pax, pay), (pbx, pby)

    def point_contact(self, q: np.ndarray) -> Tuple[float, float]:
        return self.geometrie(q)[0]

    def efforts(self, q: np.ndarray, lam: float) -> Tuple[float, float, Tuple[float, float]]:
        """(Ft, Fr, force totale de A sur B) au point primitif.

        Ft est la composante de l'effort sur B le long de la tangente t ; Fr
        est positif et écarte toujours les roues (dirigé vers le centre de la
        roue qui le reçoit pour une denture extérieure).
        """
        _, (nx, ny), (tx, ty), (pax, pay), (pbx, pby) = self.geometrie(q)
        a = math.hypot(pbx - pax, pby - pay) or 1e-300
        ft = lam * self.k / a
        fr = abs(ft) * self.tan_alpha
        sens = 1.0 if self.s > 0 else -1.0  # couronne : poussée vers l'extérieur
        return ft, fr, (ft * tx + sens * fr * nx, ft * ty + sens * fr * ny)

    def a_effort_radial(self) -> bool:
        return self.tan_alpha > 0.0

    def ajouter_effort_radial(self, q: np.ndarray, lam: float, Q: np.ndarray) -> None:
        (ix, iy), (nx, ny), _, _, _ = self.geometrie(q)
        _, fr, _ = self.efforts(q, lam)
        sens = 1.0 if self.s > 0 else -1.0
        fx, fy = sens * fr * nx, sens * fr * ny
        gax, gay = _centre_de_gravite(q, self.a[0])
        gbx, gby = _centre_de_gravite(q, self.b[0])
        _ajouter_force(Q, self.b[0], gbx, gby, fx, fy, ix, iy)
        _ajouter_force(Q, self.a[0], gax, gay, -fx, -fy, ix, iy)

    def couples(self, q: np.ndarray, lam: float) -> Tuple[float, float]:
        """Couples de l'engrènement sur A et sur B, autour de leurs centres."""
        (ix, iy), _, (tx, ty), (pax, pay), (pbx, pby) = self.geometrie(q)
        a = math.hypot(pbx - pax, pby - pay) or 1e-300
        ft = lam * self.k / a
        cb = (ix - pbx) * (ft * ty) - (iy - pby) * (ft * tx)
        ca = (ix - pax) * (-ft * ty) - (iy - pay) * (-ft * tx)
        return ca, cb

    def dissipe(self) -> bool:
        return self.rendement < 1.0

    def vecteur_pertes(self, q: np.ndarray, qd: np.ndarray, lam: float) -> Optional[np.ndarray]:
        """Frottement de denture : force généralisée par unité de λ, ou ``None`` sans perte.

        La roue menée (celle qui reçoit de la puissance, mesurée par rapport au
        porte-train) subit le couple −(1 − η)·C, où C est le couple que la
        denture exerce sur elle : elle ne reçoit plus que η fois la puissance
        fournie par la roue menante. Le porte-train encaisse la réaction. Le
        frottement est proportionnel à l'effort transmis, donc à λ.
        """
        if self.rendement >= 1.0:
            return None
        ca, cb = self.couples(q, 1.0)
        kc = self.porte_train
        wc = qd[3 * kc + 2] if kc >= 0 else 0.0
        pa = ca * lam * (_angle(qd, self.a[0]) - wc)
        pb = cb * lam * (_angle(qd, self.b[0]) - wc)
        if pb > 0.0 and pb >= pa:
            menee, couple = self.b[0], cb
        elif pa > 0.0:
            menee, couple = self.a[0], ca
        else:
            return None
        g = np.zeros(qd.size)
        _ajouter_couple(g, menee, -(1.0 - self.rendement) * couple)
        _ajouter_couple(g, kc, (1.0 - self.rendement) * couple)
        return g


class EngrenageCremaillere(_SurAxe):
    """Pignon A roulant sans glisser sur la ligne primitive d'une crémaillère B.

        Φ = u·(Oa − Pb) + σ·r·(θa − θb) − c0

    u est la direction de la crémaillère (liée à B), r = m·Za/2 le rayon
    primitif du pignon et σ = ±1 selon le côté de la crémaillère où se trouve
    le pignon. La force généralisée est l'effort tangentiel au point primitif.
    """

    def __init__(
        self,
        attache_b: Attache,
        angle_axe: float,
        attache_a: Attache,
        rayon: float,
        q0: np.ndarray,
        angle_pression: float = 0.0,
        rendement: float = 1.0,
    ) -> None:
        super().__init__(attache_b, angle_axe, attache_a)
        self.r = rayon
        ux, uy, nx, ny, dx, dy, *_ = self._geometrie(q0)
        self.sigma = 1.0 if nx * dx + ny * dy >= 0.0 else -1.0
        self.tan_alpha = math.tan(angle_pression)
        self.rendement = rendement
        self.c0 = 0.0
        valeur = np.zeros(1)
        self.phi(q0, 0.0, valeur, 0)
        self.c0 = float(valeur[0])

    def phi(self, q, t, sortie, i):
        ux, uy, _, _, dx, dy, *_ = self._geometrie(q)
        relatif = _angle(q, self.j[0]) - _angle(q, self.i[0])
        sortie[i] = ux * dx + uy * dy + self.sigma * self.r * relatif - self.c0

    def jac(self, q, t, J, i):
        TranslationPilotee.jac(self, q, t, J, i)
        if self.j[0] >= 0:
            J[i, 3 * self.j[0] + 2] += self.sigma * self.r
        if self.i[0] >= 0:
            J[i, 3 * self.i[0] + 2] -= self.sigma * self.r

    def gamma(self, q, qd, t, sortie, i):
        ux, uy, nx, ny, dx, dy, ddx, ddy, wi, cx, cy = self._cinematique(q, qd)
        sortie[i] = (ux * dx + uy * dy) * wi * wi - 2.0 * wi * (nx * ddx + ny * ddy) + ux * cx + uy * cy

    def geometrie(self, q: np.ndarray):
        """(I, n vers le pignon, u, Oa) : point primitif, normale, direction, centre du pignon."""
        ux, uy, nx, ny, *_ = self._geometrie(q)
        nx, ny = self.sigma * nx, self.sigma * ny
        oax, oay, _, _ = bras(q, self.j)
        return (oax - self.r * nx, oay - self.r * ny), (nx, ny), (ux, uy), (oax, oay)

    def point_contact(self, q: np.ndarray) -> Tuple[float, float]:
        return self.geometrie(q)[0]

    def efforts(self, q: np.ndarray, lam: float) -> Tuple[float, float, Tuple[float, float]]:
        """(Ft, Fr, force totale du pignon A sur la crémaillère B)."""
        _, (nx, ny), (ux, uy), _ = self.geometrie(q)
        ft = lam
        fr = abs(ft) * self.tan_alpha
        return ft, fr, (ft * ux - fr * nx, ft * uy - fr * ny)

    def a_effort_radial(self) -> bool:
        return self.tan_alpha > 0.0

    def ajouter_effort_radial(self, q: np.ndarray, lam: float, Q: np.ndarray) -> None:
        (ix, iy), (nx, ny), _, _ = self.geometrie(q)
        fr = abs(lam) * self.tan_alpha
        gax, gay = _centre_de_gravite(q, self.j[0])
        gbx, gby = _centre_de_gravite(q, self.i[0])
        _ajouter_force(Q, self.j[0], gax, gay, fr * nx, fr * ny, ix, iy)
        _ajouter_force(Q, self.i[0], gbx, gby, -fr * nx, -fr * ny, ix, iy)

    def couples(self, q: np.ndarray, lam: float) -> Tuple[float, float]:
        """(couple sur le pignon autour de son centre, force motrice sur la crémaillère)."""
        (ix, iy), _, (ux, uy), (oax, oay) = self.geometrie(q)
        ca = (ix - oax) * (-lam * uy) - (iy - oay) * (-lam * ux)
        return ca, lam

    def dissipe(self) -> bool:
        return self.rendement < 1.0

    def vecteur_pertes(self, q: np.ndarray, qd: np.ndarray, lam: float) -> Optional[np.ndarray]:
        """Frottement de denture par unité de λ (voir ``EngrenageRoues.vecteur_pertes``)."""
        if self.rendement >= 1.0:
            return None
        ca, _ = self.couples(q, 1.0)
        (ix, iy), _, (ux, uy), _ = self.geometrie(q)
        gbx, gby = _centre_de_gravite(q, self.i[0])
        vbx, vby = vitesse_point(qd, self.i[0], ix - gbx, iy - gby)
        pa = ca * lam * (_angle(qd, self.j[0]) - _angle(qd, self.i[0]))
        pb = lam * (ux * vbx + uy * vby)
        g = np.zeros(qd.size)
        if pb > 0.0 and pb >= pa:
            perte = -(1.0 - self.rendement)
            _ajouter_force(g, self.i[0], gbx, gby, perte * ux, perte * uy, ix, iy)
        elif pa > 0.0:
            _ajouter_couple(g, self.j[0], -(1.0 - self.rendement) * ca)
        else:
            return None
        return g


class DistanceConstante(Contrainte):
    """|Pj − Pi| = L : pointe ou galet d'un poussoir sur une came circulaire (1 équation).

    Pi est le centre du cercle (solide A), Pj la pointe ou le centre du galet
    (solide B), L = R (pointe) ou R + ρ (galet). L'effort transmis est porté
    par la normale au cercle, qui passe par son centre.
    """

    def __init__(self, attache_i: Attache, attache_j: Attache, longueur: float, rayon_came: float) -> None:
        self.i = attache_i
        self.j = attache_j
        self.longueur = longueur
        self.rayon_came = rayon_came

    def _ecart(self, q):
        pix, piy, aix, aiy = bras(q, self.i)
        pjx, pjy, ajx, ajy = bras(q, self.j)
        dx, dy = pjx - pix, pjy - piy
        return pix, piy, aix, aiy, ajx, ajy, dx, dy, math.hypot(dx, dy) or 1e-300

    def phi(self, q, t, sortie, i):
        *_, longueur = self._ecart(q)
        sortie[i] = longueur - self.longueur

    def jac(self, q, t, J, i):
        _, _, aix, aiy, ajx, ajy, dx, dy, longueur = self._ecart(q)
        ex, ey = dx / longueur, dy / longueur
        ki, kj = self.i[0], self.j[0]
        if ki >= 0:
            c = 3 * ki
            J[i, c] -= ex
            J[i, c + 1] -= ey
            J[i, c + 2] -= -ex * aiy + ey * aix
        if kj >= 0:
            c = 3 * kj
            J[i, c] += ex
            J[i, c + 1] += ey
            J[i, c + 2] += -ex * ajy + ey * ajx

    def gamma(self, q, qd, t, sortie, i):
        _, _, aix, aiy, ajx, ajy, dx, dy, longueur = self._ecart(q)
        ex, ey = dx / longueur, dy / longueur
        ki, kj = self.i[0], self.j[0]
        vix, viy = vitesse_point(qd, ki, aix, aiy)
        vjx, vjy = vitesse_point(qd, kj, ajx, ajy)
        ddx, ddy = vjx - vix, vjy - viy
        wi = qd[3 * ki + 2] if ki >= 0 else 0.0
        wj = qd[3 * kj + 2] if kj >= 0 else 0.0
        cx = -ajx * wj * wj + aix * wi * wi
        cy = -ajy * wj * wj + aiy * wi * wi
        normal = ex * ddx + ey * ddy
        sortie[i] = -(ex * cx + ey * cy) - (ddx * ddx + ddy * ddy - normal * normal) / longueur

    def point_contact(self, q: np.ndarray) -> Tuple[float, float]:
        pix, piy, _, _, _, _, dx, dy, longueur = self._ecart(q)
        return pix + self.rayon_came * dx / longueur, piy + self.rayon_came * dy / longueur

    def normale(self, q: np.ndarray) -> Tuple[float, float]:
        """Normale extérieure au cercle au point de contact (de la came vers le poussoir)."""
        *_, dx, dy, longueur = self._ecart(q)
        return dx / longueur, dy / longueur


class PlateauTangent(PointSurDroite):
    """Plateau d'un poussoir tangent à une came circulaire : σ·n·(C − P) = R (1 équation).

    La droite du plateau est liée au poussoir (solide i, point P, direction
    ``angle_axe``) ; C est le centre du cercle (solide j). σ = ±1 indique de
    quel côté du plateau se trouve la came.
    """

    def __init__(self, attache_poussoir: Attache, angle_axe: float, attache_centre: Attache, rayon: float, q0: np.ndarray) -> None:
        super().__init__(attache_poussoir, angle_axe, attache_centre)
        self.rayon = rayon
        _, _, nx, ny, dx, dy, *_ = self._geometrie(q0)
        self.sigma = 1.0 if nx * dx + ny * dy >= 0.0 else -1.0

    def phi(self, q, t, sortie, i):
        PointSurDroite.phi(self, q, t, sortie, i)
        sortie[i] = self.sigma * sortie[i] - self.rayon

    def jac(self, q, t, J, i):
        ligne = np.zeros_like(J[i])
        PointSurDroite.jac(self, q, t, ligne[None, :], 0)
        J[i] += self.sigma * ligne

    def gamma(self, q, qd, t, sortie, i):
        PointSurDroite.gamma(self, q, qd, t, sortie, i)
        sortie[i] *= self.sigma

    def point_contact(self, q: np.ndarray) -> Tuple[float, float]:
        _, _, nx, ny, *_ = self._geometrie(q)
        cx, cy, _, _ = bras(q, self.j)
        return cx - self.sigma * self.rayon * nx, cy - self.sigma * self.rayon * ny

    def normale(self, q: np.ndarray) -> Tuple[float, float]:
        """Normale au contact, de la came vers le poussoir."""
        _, _, nx, ny, *_ = self._geometrie(q)
        return -self.sigma * nx, -self.sigma * ny


def _centre_de_gravite(q: np.ndarray, k: int) -> Tuple[float, float]:
    if k < 0:
        return 0.0, 0.0
    return q[3 * k], q[3 * k + 1]
