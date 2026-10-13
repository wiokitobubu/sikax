"""Torseur : résultante, moment et point de réduction.

La classe est écrite en 3D. Un problème plan (x, y) n'utilise que les
composantes (Rx, Ry) de la résultante et Mz du moment ; le constructeur
``Torseur.plan`` et les propriétés ``rx``, ``ry``, ``mz`` couvrent ce cas.

Le même objet représente un torseur statique (résultante = force, moment en
un point) ou un torseur cinématique (résultante = vitesse de rotation,
moment = vitesse du point).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]


def _vec3(v: Sequence[float]) -> Vec3:
    if len(v) == 2:
        return (float(v[0]), float(v[1]), 0.0)
    if len(v) == 3:
        return (float(v[0]), float(v[1]), float(v[2]))
    raise ValueError("un vecteur doit avoir 2 ou 3 composantes")


def _croix(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _scal(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@dataclass(frozen=True)
class Torseur:
    """Torseur réduit au point ``point``."""

    resultante: Vec3 = (0.0, 0.0, 0.0)
    moment: Vec3 = (0.0, 0.0, 0.0)
    point: Vec3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resultante", _vec3(self.resultante))
        object.__setattr__(self, "moment", _vec3(self.moment))
        object.__setattr__(self, "point", _vec3(self.point))

    # -- constructeurs -----------------------------------------------------
    @classmethod
    def plan(cls, rx: float, ry: float, mz: float, point: Sequence[float] = (0.0, 0.0)) -> "Torseur":
        """Torseur d'un problème plan : résultante (rx, ry), moment mz·z."""
        return cls((rx, ry, 0.0), (0.0, 0.0, mz), _vec3(point))

    @classmethod
    def glisseur(cls, force: Sequence[float], point: Sequence[float]) -> "Torseur":
        """Force appliquée en un point (moment nul en ce point)."""
        return cls(_vec3(force), (0.0, 0.0, 0.0), _vec3(point))

    @classmethod
    def couple(cls, moment: Sequence[float], point: Sequence[float] = (0.0, 0.0, 0.0)) -> "Torseur":
        """Couple pur (résultante nulle)."""
        return cls((0.0, 0.0, 0.0), _vec3(moment), _vec3(point))

    # -- accès plan --------------------------------------------------------
    @property
    def rx(self) -> float:
        return self.resultante[0]

    @property
    def ry(self) -> float:
        return self.resultante[1]

    @property
    def mz(self) -> float:
        return self.moment[2]

    @property
    def norme_resultante(self) -> float:
        return math.sqrt(_scal(self.resultante, self.resultante))

    @property
    def norme_moment(self) -> float:
        return math.sqrt(_scal(self.moment, self.moment))

    # -- algèbre -----------------------------------------------------------
    def deplacer(self, nouveau_point: Sequence[float]) -> "Torseur":
        """Transport du moment : M(B) = M(A) + BA ∧ R."""
        b = _vec3(nouveau_point)
        ba = (self.point[0] - b[0], self.point[1] - b[1], self.point[2] - b[2])
        c = _croix(ba, self.resultante)
        m = (self.moment[0] + c[0], self.moment[1] + c[1], self.moment[2] + c[2])
        return Torseur(self.resultante, m, b)

    def __add__(self, autre: "Torseur") -> "Torseur":
        if not isinstance(autre, Torseur):
            return NotImplemented
        o = autre.deplacer(self.point)
        return Torseur(
            tuple(a + b for a, b in zip(self.resultante, o.resultante)),
            tuple(a + b for a, b in zip(self.moment, o.moment)),
            self.point,
        )

    def __neg__(self) -> "Torseur":
        return Torseur(
            tuple(-a for a in self.resultante), tuple(-a for a in self.moment), self.point
        )

    def __sub__(self, autre: "Torseur") -> "Torseur":
        if not isinstance(autre, Torseur):
            return NotImplemented
        return self + (-autre)

    def __mul__(self, k: float) -> "Torseur":
        return Torseur(
            tuple(k * a for a in self.resultante), tuple(k * a for a in self.moment), self.point
        )

    __rmul__ = __mul__

    def comoment(self, autre: "Torseur") -> float:
        """Comoment de deux torseurs (puissance pour statique ⊗ cinématique)."""
        o = autre.deplacer(self.point)
        return _scal(self.resultante, o.moment) + _scal(self.moment, o.resultante)

    @property
    def automoment(self) -> float:
        """Invariant scalaire R·M, indépendant du point de réduction."""
        return _scal(self.resultante, self.moment)

    def point_axe_central(self) -> Optional[Vec3]:
        """Un point de l'axe central, ou ``None`` si la résultante est nulle."""
        r2 = _scal(self.resultante, self.resultante)
        if r2 <= 0.0:
            return None
        c = _croix(self.resultante, self.moment)
        return (
            self.point[0] + c[0] / r2,
            self.point[1] + c[1] / r2,
            self.point[2] + c[2] / r2,
        )

    def est_nul(self, tol: float = 1e-12) -> bool:
        return self.norme_resultante <= tol and self.norme_moment <= tol

    def proche_de(self, autre: "Torseur", tol: float = 1e-9) -> bool:
        return (self - autre).est_nul(tol)

    def __str__(self) -> str:
        r, m, p = self.resultante, self.moment, self.point
        return (
            f"{{R=({r[0]:.6g}, {r[1]:.6g}, {r[2]:.6g}) ; "
            f"M=({m[0]:.6g}, {m[1]:.6g}, {m[2]:.6g})}} en ({p[0]:.6g}, {p[1]:.6g}, {p[2]:.6g})"
        )
