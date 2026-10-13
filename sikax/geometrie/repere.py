"""Pose d'un solide : position de l'origine de son repère et orientation.

En 2D une pose est le triplet (x, y, angle). Le passage à la 3D se fera en
remplaçant ``angle`` par une orientation complète (quaternion) : tout le reste
du modèle ne manipule les poses qu'à travers ``vers_global`` / ``vers_local``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .vecteurs import Vec2


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0

    def vers_global(self, px: float, py: float) -> Vec2:
        """Coordonnées globales d'un point donné dans le repère du solide."""
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (self.x + c * px - s * py, self.y + s * px + c * py)

    def vers_local(self, gx: float, gy: float) -> Vec2:
        """Coordonnées locales d'un point donné dans le repère global."""
        c, s = math.cos(self.angle), math.sin(self.angle)
        dx, dy = gx - self.x, gy - self.y
        return (c * dx + s * dy, -s * dx + c * dy)

    def direction_globale(self, angle_local: float) -> float:
        return self.angle + angle_local

    def copie(self) -> "Pose":
        return Pose(self.x, self.y, self.angle)

    def est_identite(self, tol: float = 0.0) -> bool:
        return abs(self.x) <= tol and abs(self.y) <= tol and abs(self.angle) <= tol
