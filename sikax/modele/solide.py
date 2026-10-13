"""Solides indéformables, points et paramètres d'inertie."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..geometrie import Pose
from ..geometrie.vecteurs import Vec2

ID_BATI = "S0"

# Couleurs attribuées tour à tour aux nouveaux solides (lisibles en clair et en sombre).
COULEURS_SOLIDES = (
    "#3B82F6",
    "#F97316",
    "#22C55E",
    "#EC4899",
    "#A855F7",
    "#EAB308",
    "#14B8A6",
    "#EF4444",
)
COULEUR_BATI = "#7C8696"


@dataclass
class Point:
    """Point lié à un solide, repéré dans le repère de ce solide."""

    id: str
    nom: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class Inertie:
    """Caractéristiques d'inertie d'un solide plan."""

    masse: float = 0.0
    gx: float = 0.0
    """Abscisse du centre de gravité G dans le repère du solide (m)."""
    gy: float = 0.0
    jz: float = 0.0
    """Moment d'inertie autour de l'axe (G, z), en kg·m²."""

    def est_nulle(self) -> bool:
        return self.masse == 0.0 and self.jz == 0.0


@dataclass
class Solide:
    """Solide indéformable. Le bâti est le solide d'identifiant ``S0``."""

    id: str
    nom: str
    bati: bool = False
    couleur: str = COULEURS_SOLIDES[0]
    pose: Pose = field(default_factory=Pose)
    points: Dict[str, Point] = field(default_factory=dict)
    segments: List[Tuple[str, str]] = field(default_factory=list)
    inertie: Inertie = field(default_factory=Inertie)

    # -- points ------------------------------------------------------------
    def point(self, point_id: str) -> Point:
        try:
            return self.points[point_id]
        except KeyError:
            raise KeyError(f"point « {point_id} » inconnu dans le solide « {self.id} »") from None

    def prochain_id_point(self) -> str:
        numeros = [int(p[1:]) for p in self.points if p[:1] == "P" and p[1:].isdigit()]
        return f"P{max(numeros, default=0) + 1}"

    def ajouter_point(self, nom: str, x_local: float, y_local: float, point_id: Optional[str] = None) -> Point:
        pid = point_id or self.prochain_id_point()
        if pid in self.points:
            raise ValueError(f"le point « {pid} » existe déjà dans « {self.id} »")
        point = Point(pid, nom, float(x_local), float(y_local))
        self.points[pid] = point
        return point

    def supprimer_point(self, point_id: str) -> None:
        self.points.pop(point_id, None)
        self.segments = [s for s in self.segments if point_id not in s]

    def position_globale(self, point_id: str) -> Vec2:
        p = self.point(point_id)
        return self.pose.vers_global(p.x, p.y)

    def placer_point_global(self, point_id: str, gx: float, gy: float) -> None:
        """Modifie la géométrie : le point passe en (gx, gy) dans la pose actuelle."""
        p = self.point(point_id)
        p.x, p.y = self.pose.vers_local(gx, gy)

    def point_proche(self, gx: float, gy: float, rayon: float) -> Optional[Point]:
        meilleur, d_min = None, rayon
        for p in self.points.values():
            X, Y = self.pose.vers_global(p.x, p.y)
            d = math.hypot(X - gx, Y - gy)
            if d <= d_min:
                meilleur, d_min = p, d
        return meilleur

    # -- segments ----------------------------------------------------------
    def ajouter_segment(self, a: str, b: str) -> bool:
        if a == b or a not in self.points or b not in self.points:
            return False
        if (a, b) in self.segments or (b, a) in self.segments:
            return False
        self.segments.append((a, b))
        return True

    def segments_globaux(self) -> List[Tuple[Vec2, Vec2]]:
        return [(self.position_globale(a), self.position_globale(b)) for a, b in self.segments]

    # -- inertie -----------------------------------------------------------
    def centre_gravite_global(self) -> Vec2:
        return self.pose.vers_global(self.inertie.gx, self.inertie.gy)

    def longueur_totale(self) -> float:
        total = 0.0
        for a, b in self.segments:
            pa, pb = self.points[a], self.points[b]
            total += math.hypot(pb.x - pa.x, pb.y - pa.y)
        return total

    def inertie_barres_homogenes(self, masse: float) -> Inertie:
        """Inertie du solide vu comme un assemblage de barres minces homogènes.

        La masse totale est répartie sur les segments au prorata de leur
        longueur. Sans segment, la masse est concentrée au barycentre des
        points (moment d'inertie nul).
        """
        longueurs = []
        for a, b in self.segments:
            pa, pb = self.points[a], self.points[b]
            longueur = math.hypot(pb.x - pa.x, pb.y - pa.y)
            if longueur > 0.0:
                longueurs.append((longueur, (pa.x + pb.x) / 2.0, (pa.y + pb.y) / 2.0))
        total = sum(l for l, _, _ in longueurs)
        if total <= 0.0:
            if not self.points:
                return Inertie(masse, 0.0, 0.0, 0.0)
            n = len(self.points)
            gx = sum(p.x for p in self.points.values()) / n
            gy = sum(p.y for p in self.points.values()) / n
            return Inertie(masse, gx, gy, 0.0)
        gx = sum(l * cx for l, cx, _ in longueurs) / total
        gy = sum(l * cy for l, _, cy in longueurs) / total
        jz = 0.0
        for longueur, cx, cy in longueurs:
            m = masse * longueur / total
            jz += m * longueur * longueur / 12.0 + m * ((cx - gx) ** 2 + (cy - gy) ** 2)
        return Inertie(masse, gx, gy, jz)
