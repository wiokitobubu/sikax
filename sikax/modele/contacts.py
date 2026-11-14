"""Géométrie des liaisons de contact : point primitif d'un engrenage, point de contact d'une came.

Ces fonctions ne connaissent que des positions globales : le modèle les
appelle avec la configuration enregistrée, la vue avec la configuration
animée. Le moteur de calcul refait les mêmes calculs à partir de l'état q.

Formules usuelles des engrenages droits à denture droite (module m, nombre
de dents Z, angle de pression α) :

- diamètre primitif   d = m·Z
- pas                 p = π·m
- diamètre de tête    da = d + 2·m     (saillie ha = m)
- diamètre de pied    df = d − 2,5·m   (creux hf = 1,25·m)
- entraxe             a = (d1 + d2)/2 (extérieur), (d2 − d1)/2 (intérieur)
- effort radial       Fr = Ft·tan α ;  effort normal Fn = Ft / cos α
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from ..geometrie.vecteurs import Vec2

SAILLIE = 1.0
CREUX = 1.25


@dataclass(frozen=True)
class Contact:
    point: Vec2
    """Point de contact : point primitif I (engrenage), point de la came (came)."""
    normale: Vec2
    """Direction unitaire de l'effort transmis (pour un engrenage : la tangente)."""
    glissement: Vec2
    """Direction unitaire du mouvement relatif libre au contact."""

    @property
    def angle_glissement(self) -> float:
        return math.atan2(self.glissement[1], self.glissement[0])


def pas(module: float) -> float:
    return math.pi * module


def rayon_tete(module: float, z: float, interieur: bool = False) -> float:
    """Rayon de tête (la denture d'une couronne est tournée vers l'intérieur)."""
    return module * z / 2.0 + (-SAILLIE if interieur else SAILLIE) * module


def rayon_pied(module: float, z: float, interieur: bool = False) -> float:
    return module * z / 2.0 + (CREUX if interieur else -CREUX) * module


def rayons_de_fonctionnement(z_a: float, z_b: float, interieur: bool, entraxe: float, module: float) -> Tuple[float, float]:
    """Rayons primitifs qui roulent réellement : rapport Za/Zb, somme (ou différence) = entraxe."""
    somme = abs(z_a - z_b) if interieur else z_a + z_b
    if entraxe > 0.0 and somme > 0.0:
        return entraxe * z_a / somme, entraxe * z_b / somme
    return module * z_a / 2.0, module * z_b / 2.0


def contact_roues(z_a: float, z_b: float, interieur: bool, module: float, oa: Vec2, ob: Vec2) -> Contact:
    """Point primitif de deux roues de centres oa et ob (B est la couronne si ``interieur``)."""
    dx, dy = ob[0] - oa[0], ob[1] - oa[1]
    entraxe = math.hypot(dx, dy)
    if entraxe <= 0.0:
        return Contact(oa, (0.0, 1.0), (1.0, 0.0))
    nx, ny = dx / entraxe, dy / entraxe
    ra, _ = rayons_de_fonctionnement(z_a, z_b, interieur, entraxe, module)
    signe = -1.0 if interieur else 1.0  # le point primitif d'une couronne est au-delà du pignon
    point = (oa[0] + signe * ra * nx, oa[1] + signe * ra * ny)
    return Contact(point, (-ny, nx), (nx, ny))


def contact_cremaillere(rayon: float, oa: Vec2, pb: Vec2, direction: float) -> Contact:
    """Point primitif d'un pignon (centre oa, rayon primitif r) et d'une crémaillère.

    La ligne primitive de la crémaillère passe par pb avec la direction donnée.
    """
    ux, uy = math.cos(direction), math.sin(direction)
    nx, ny = -uy, ux
    if nx * (oa[0] - pb[0]) + ny * (oa[1] - pb[1]) < 0.0:
        nx, ny = -nx, -ny  # normale orientée de la crémaillère vers le pignon
    point = (oa[0] - rayon * nx, oa[1] - rayon * ny)
    return Contact(point, (ux, uy), (nx, ny))


def contact_came_point(centre: Vec2, rayon: float, p: Vec2) -> Contact:
    """Came circulaire (centre, rayon) et poussoir à pointe ou à galet de centre p."""
    dx, dy = p[0] - centre[0], p[1] - centre[1]
    distance = math.hypot(dx, dy)
    if distance <= 0.0:
        return Contact(centre, (0.0, 1.0), (1.0, 0.0))
    ex, ey = dx / distance, dy / distance
    return Contact((centre[0] + rayon * ex, centre[1] + rayon * ey), (ex, ey), (-ey, ex))


def contact_came_plateau(centre: Vec2, rayon: float, p: Vec2, direction: float) -> Contact:
    """Came circulaire et poussoir à plateau (droite par p, de direction donnée)."""
    ux, uy = math.cos(direction), math.sin(direction)
    nx, ny = -uy, ux
    if nx * (centre[0] - p[0]) + ny * (centre[1] - p[1]) < 0.0:
        nx, ny = -nx, -ny  # normale orientée du plateau vers la came
    return Contact((centre[0] - rayon * nx, centre[1] - rayon * ny), (-nx, -ny), (ux, uy))
