"""Photo d'un schéma affichée sous le mécanisme.

On importe la photo (ou le scan) d'un schéma cinématique, on l'étalonne en
donnant une longueur connue, puis on trace le mécanisme par-dessus. L'image
est enregistrée *dans* le projet : un fichier envoyé à quelqu'un d'autre
garde son fond.

Repère : l'image est un rectangle de largeur ``largeur`` (m) dont le coin
inférieur gauche est en (x, y) et qui est tourné de ``angle`` autour de ce
coin. Sa hauteur suit les proportions de l'image.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional, Tuple

from ..geometrie.vecteurs import Vec2

FORMATS = {"png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff"}


def format_image(donnees: bytes) -> Optional[str]:
    """``"png"`` ou ``"jpeg"`` d'après la signature des données, ``None`` sinon."""
    for nom, signature in FORMATS.items():
        if donnees.startswith(signature):
            return nom
    return None


@dataclass
class FondPlan:
    donnees: bytes
    """Contenu du fichier image (PNG ou JPEG), tel quel."""
    format: str = "png"
    largeur_px: int = 1
    hauteur_px: int = 1
    x: float = 0.0
    y: float = 0.0
    largeur: float = 0.2
    """Largeur de l'image dans le repère du modèle (m)."""
    angle: float = 0.0
    opacite: float = 0.45
    visible: bool = True
    nom: str = ""

    @property
    def hauteur(self) -> float:
        return self.largeur * self.hauteur_px / max(self.largeur_px, 1)

    @property
    def metres_par_pixel(self) -> float:
        return self.largeur / max(self.largeur_px, 1)

    def vers_modele(self, u: float, v: float) -> Vec2:
        """Position dans le modèle du pixel (u, v), v compté depuis le haut de l'image."""
        echelle = self.metres_par_pixel
        lx, ly = u * echelle, (self.hauteur_px - v) * echelle
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (self.x + c * lx - s * ly, self.y + s * lx + c * ly)

    def vers_pixels(self, gx: float, gy: float) -> Tuple[float, float]:
        echelle = self.metres_par_pixel
        c, s = math.cos(self.angle), math.sin(self.angle)
        dx, dy = gx - self.x, gy - self.y
        lx, ly = c * dx + s * dy, -s * dx + c * dy
        return lx / echelle, self.hauteur_px - ly / echelle

    def etalonner(self, a: Vec2, b: Vec2, longueur: float) -> None:
        """Change l'échelle pour que les points a et b (pris sur l'image) soient à ``longueur``.

        Le point a reste en place : on trace l'étalon sans que l'image ne fuie.
        """
        mesure = math.hypot(b[0] - a[0], b[1] - a[1])
        if mesure <= 0.0 or not (longueur > 0.0 and math.isfinite(longueur)):
            raise ValueError("étalonnage impossible : deux points distincts et une longueur positive sont nécessaires")
        u, v = self.vers_pixels(*a)
        self.largeur *= longueur / mesure
        apres = self.vers_modele(u, v)
        self.x += a[0] - apres[0]
        self.y += a[1] - apres[1]

    def copie(self) -> "FondPlan":
        return replace(self)
