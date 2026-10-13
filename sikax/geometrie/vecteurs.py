"""Opérations élémentaires sur les vecteurs du plan.

Conventions : repère direct (x vers la droite, y vers le haut), angles en
radians comptés positivement dans le sens trigonométrique.
"""

from __future__ import annotations

import math
from typing import Tuple

Vec2 = Tuple[float, float]

DEUX_PI = 2.0 * math.pi


def norme(v: Vec2) -> float:
    return math.hypot(v[0], v[1])


def distance(a: Vec2, b: Vec2) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def produit_scalaire(a: Vec2, b: Vec2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def produit_vectoriel_z(a: Vec2, b: Vec2) -> float:
    """Composante sur z du produit vectoriel de deux vecteurs du plan."""
    return a[0] * b[1] - a[1] * b[0]


def perpendiculaire(v: Vec2) -> Vec2:
    """Vecteur tourné de +90° (z ∧ v)."""
    return (-v[1], v[0])


def unitaire(angle: float) -> Vec2:
    """Vecteur unitaire faisant l'angle donné avec l'axe x."""
    return (math.cos(angle), math.sin(angle))


def tourner(v: Vec2, angle: float) -> Vec2:
    c, s = math.cos(angle), math.sin(angle)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])


def angle_de(v: Vec2) -> float:
    """Angle polaire d'un vecteur, dans ]-π, π]."""
    return math.atan2(v[1], v[0])


def normaliser_angle(angle: float) -> float:
    """Ramène un angle dans l'intervalle ]-π, π]."""
    a = math.fmod(angle, DEUX_PI)
    if a > math.pi:
        a -= DEUX_PI
    elif a <= -math.pi:
        a += DEUX_PI
    return a
