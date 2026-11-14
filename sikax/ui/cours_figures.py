"""Figures des fiches de cours, dessinées aux couleurs du thème.

Chaque fonction dessine une figure dans une image deux fois plus fine que sa
taille d'affichage (écrans à haute densité). Les fiches les appellent par
``<img src="figure:<nom>" width="...">``.
"""

from __future__ import annotations

import math
from typing import Callable, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF

from .schema.rendu import arc_fleche, fleche, hachures
from .theme import theme

LARGEUR, HAUTEUR = 360, 210
FACTEUR = 2.0


def _image(dessiner: Callable[[QPainter], None], largeur: int = LARGEUR, hauteur: int = HAUTEUR) -> QImage:
    image = QImage(int(largeur * FACTEUR), int(hauteur * FACTEUR), QImage.Format_ARGB32)
    image.fill(theme.couleur("surface_haute"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.scale(FACTEUR, FACTEUR)
    dessiner(p)
    p.end()
    image.setDevicePixelRatio(FACTEUR)
    return image


def _texte(p: QPainter, x: float, y: float, texte: str, couleur: QColor, taille: float = 10.0, gras: bool = False, italique: bool = True) -> None:
    police = QFont(p.font())
    police.setPointSizeF(taille)
    police.setBold(gras)
    police.setItalic(italique)
    p.setFont(police)
    p.setPen(couleur)
    p.drawText(QPointF(x, y), texte)


def _plume(couleur: QColor, largeur: float = 2.0, style=Qt.SolidLine) -> QPen:
    plume = QPen(couleur, largeur, style)
    plume.setCapStyle(Qt.RoundCap)
    return plume


def _moment(p: QPainter) -> None:
    trait, force, accent, texte = theme.couleur("trait"), theme.couleur("force"), theme.couleur("accent"), theme.couleur("texte_secondaire")
    a, pt = QPointF(70.0, 150.0), QPointF(230.0, 70.0)
    p.setPen(_plume(trait, 5.0))
    p.drawLine(a, pt)
    p.setPen(Qt.NoPen)
    p.setBrush(trait)
    p.drawEllipse(a, 4.0, 4.0)
    bout = QPointF(pt.x() + 30.0, pt.y() + 95.0)
    fleche(p, pt, bout, force, 2.4, 11.0)
    # bras de levier : distance de A à la droite d'action
    dx, dy = bout.x() - pt.x(), bout.y() - pt.y()
    longueur = math.hypot(dx, dy)
    ux, uy = dx / longueur, dy / longueur
    t = (a.x() - pt.x()) * ux + (a.y() - pt.y()) * uy
    pied = QPointF(pt.x() + t * ux, pt.y() + t * uy)
    p.setPen(_plume(trait, 1.0, Qt.DashLine))
    p.drawLine(QPointF(pt.x() - 1.6 * longueur * ux, pt.y() - 1.6 * longueur * uy), QPointF(pt.x() + 1.4 * longueur * ux, pt.y() + 1.4 * longueur * uy))
    p.setPen(_plume(accent, 1.8))
    p.drawLine(a, pied)
    arc_fleche(p, a, 22.0, -1.0, accent, 1.8)
    _texte(p, a.x() - 18.0, a.y() + 22.0, "A", trait, 11.0, True, False)
    _texte(p, pt.x() + 8.0, pt.y() - 6.0, "P", trait, 11.0, True, False)
    _texte(p, bout.x() + 6.0, bout.y(), "F", force, 12.0, True)
    _texte(p, (a.x() + pied.x()) / 2.0 - 20.0, (a.y() + pied.y()) / 2.0 - 6.0, "d", accent, 12.0, True)
    _texte(p, 18.0, 30.0, "M_A(F) = AP ∧ F    |M_A| = F · d", texte, 10.5)


def _torseur(p: QPainter) -> None:
    trait, force, couple, texte = theme.couleur("trait"), theme.couleur("force"), theme.couleur("couple"), theme.couleur("texte_secondaire")
    corps = QPolygonF([QPointF(60, 150), QPointF(120, 60), QPointF(260, 80), QPointF(290, 160), QPointF(170, 180)])
    remplissage = QColor(theme.couleur("accent"))
    remplissage.setAlpha(38)
    p.setPen(_plume(trait, 1.6))
    p.setBrush(remplissage)
    p.drawPolygon(corps)
    a, b = QPointF(150.0, 125.0), QPointF(250.0, 135.0)
    for point, nom in ((a, "A"), (b, "B")):
        p.setPen(Qt.NoPen)
        p.setBrush(trait)
        p.drawEllipse(point, 3.6, 3.6)
        _texte(p, point.x() - 14.0, point.y() + 18.0, nom, trait, 11.0, True, False)
    fleche(p, a, QPointF(a.x() + 60.0, a.y() - 70.0), force, 2.4, 11.0)
    arc_fleche(p, a, 20.0, 1.0, couple, 2.0)
    _texte(p, a.x() + 52.0, a.y() - 74.0, "R", force, 12.0, True)
    _texte(p, a.x() - 50.0, a.y() - 22.0, "M_A", couple, 11.0, True)
    _texte(p, 18.0, 30.0, "{T} = { R ; M_A }    M_B = M_A + BA ∧ R", texte, 10.5)


def _engrenage(p: QPainter) -> None:
    trait, force, accent, texte = theme.couleur("trait"), theme.couleur("force"), theme.couleur("accent"), theme.couleur("texte_secondaire")
    o1, o2 = QPointF(110.0, 118.0), QPointF(258.0, 118.0)
    r1, r2 = 56.0, 92.0
    o2 = QPointF(o1.x() + r1 + r2, o1.y())
    i = QPointF(o1.x() + r1, o1.y())
    for centre, r, couleur in ((o1, r1, QColor("#3B82F6")), (o2, r2, QColor("#F97316"))):
        p.setPen(_plume(couleur, 1.4, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(centre, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(couleur)
        p.drawEllipse(centre, 3.4, 3.4)
    p.setPen(_plume(trait, 1.0))
    p.drawLine(o1, QPointF(o2.x(), o2.y()))
    alpha = math.radians(20.0)
    # ligne d'action, inclinée de α sur la tangente commune (verticale)
    ux, uy = math.sin(alpha), -math.cos(alpha)
    p.setPen(_plume(accent, 1.4, Qt.DashDotLine))
    p.drawLine(QPointF(i.x() - 90 * ux, i.y() - 90 * uy), QPointF(i.x() + 90 * ux, i.y() + 90 * uy))
    fleche(p, i, QPointF(i.x(), i.y() - 62.0), force, 2.2, 10.0)
    fleche(p, i, QPointF(i.x() + 62.0 * math.tan(alpha), i.y()), force, 2.2, 9.0)
    fleche(p, i, QPointF(i.x() + 62.0 * ux / math.cos(alpha), i.y() + 62.0 * uy / math.cos(alpha)), accent, 2.0, 10.0)
    _texte(p, o1.x() - 16.0, o1.y() + 20.0, "O₁", trait, 10.5, True, False)
    _texte(p, o2.x() + 6.0, o2.y() + 20.0, "O₂", trait, 10.5, True, False)
    _texte(p, i.x() - 14.0, i.y() + 18.0, "I", trait, 10.5, True, False)
    _texte(p, i.x() - 26.0, i.y() - 64.0, "Ft", force, 10.5, True)
    _texte(p, i.x() + 28.0, i.y() + 16.0, "Fr", force, 10.5, True)
    _texte(p, i.x() + 26.0, i.y() - 56.0, "Fn", accent, 10.5, True)
    _texte(p, i.x() + 8.0, i.y() - 26.0, "α", accent, 11.0, True)
    _texte(p, 14.0, 22.0, "d = m·Z   a = (d₁ + d₂)/2   Fr = Ft·tan α", texte, 10.0)


def _came(p: QPainter) -> None:
    trait, accent, texte = theme.couleur("trait"), theme.couleur("accent"), theme.couleur("texte_secondaire")
    o = QPointF(150.0, 140.0)
    e, r = 22.0, 52.0
    c = QPointF(o.x() + e * math.cos(math.radians(60)), o.y() - e * math.sin(math.radians(60)))
    remplissage = QColor("#3B82F6")
    remplissage.setAlpha(40)
    p.setPen(_plume(QColor("#3B82F6"), 2.0))
    p.setBrush(remplissage)
    p.drawEllipse(c, r, r)
    p.setPen(Qt.NoPen)
    p.setBrush(trait)
    p.drawEllipse(o, 3.6, 3.6)
    p.setBrush(QColor("#3B82F6"))
    p.drawEllipse(c, 3.0, 3.0)
    p.setPen(_plume(accent, 1.8))
    p.drawLine(o, c)
    # poussoir à galet, guidé verticalement au-dessus de O
    hauteur = c.y() - math.sqrt((r + 11.0) ** 2 - (o.x() - c.x()) ** 2)
    galet = QPointF(o.x(), hauteur)
    p.setPen(_plume(QColor("#F97316"), 4.0))
    p.drawLine(QPointF(galet.x(), galet.y() - 11.0), QPointF(galet.x(), 20.0))
    p.setPen(_plume(QColor("#F97316"), 2.0))
    p.setBrush(theme.couleur("surface_haute"))
    p.drawEllipse(galet, 11.0, 11.0)
    p.setPen(_plume(trait, 1.4))
    for x in (o.x() - 14.0, o.x() + 14.0):
        p.drawLine(QPointF(x, 26.0), QPointF(x, 56.0))
    hachures(p, QPointF(o.x() - 30.0, o.y() + 20.0), QPointF(o.x() + 30.0, o.y() + 20.0), 1.0, trait)
    p.drawLine(QPointF(o.x() - 30.0, o.y() + 20.0), QPointF(o.x() + 30.0, o.y() + 20.0))
    _texte(p, o.x() - 18.0, o.y() + 14.0, "O", trait, 10.5, True, False)
    _texte(p, c.x() + 6.0, c.y() + 14.0, "C", trait, 10.5, True, False)
    _texte(p, (o.x() + c.x()) / 2.0 + 6.0, (o.y() + c.y()) / 2.0 + 4.0, "e", accent, 12.0, True)
    _texte(p, 210.0, 60.0, "course = 2·e", texte, 10.5)
    _texte(p, 210.0, 80.0, "y = e·sin θ + √((R+ρ)² − e²cos²θ)", texte, 9.5)


def _point_mort(p: QPainter) -> None:
    trait, accent, texte = theme.couleur("trait"), theme.couleur("attention"), theme.couleur("texte_secondaire")
    o = QPointF(70.0, 120.0)
    b = QPointF(o.x() + 50.0, o.y())
    c = QPointF(b.x() + 150.0, o.y())
    p.setPen(_plume(QColor("#3B82F6"), 5.0))
    p.drawLine(o, b)
    p.setPen(_plume(QColor("#F97316"), 5.0))
    p.drawLine(b, c)
    p.setPen(_plume(trait, 2.0))
    p.setBrush(theme.couleur("surface_haute"))
    p.drawRect(QRectF(c.x() - 4.0, c.y() - 14.0, 40.0, 28.0))
    for point in (o, b, c):
        p.drawEllipse(point, 5.0, 5.0)
    p.drawLine(QPointF(c.x() - 30.0, c.y() + 18.0), QPointF(c.x() + 70.0, c.y() + 18.0))
    hachures(p, QPointF(c.x() - 30.0, c.y() + 18.0), QPointF(c.x() + 70.0, c.y() + 18.0), 1.0, trait)
    p.setPen(_plume(accent, 1.4, Qt.DashLine))
    p.drawLine(QPointF(o.x() - 30.0, o.y()), QPointF(c.x() + 70.0, c.y()))
    fleche(p, QPointF(c.x() + 60.0, c.y() - 34.0), QPointF(c.x() + 10.0, c.y() - 34.0), theme.couleur("force"), 2.2, 10.0)
    _texte(p, c.x() + 18.0, c.y() - 42.0, "F", theme.couleur("force"), 11.0, True)
    _texte(p, 20.0, 40.0, "Point mort haut : manivelle et bielle alignées.", texte, 10.0, False, False)
    _texte(p, 20.0, 58.0, "La force du piston ne produit aucun couple sur la manivelle.", texte, 9.5, False, False)


def _inertie(p: QPainter) -> None:
    trait, texte = theme.couleur("trait"), theme.couleur("texte_secondaire")
    centre = QPointF(85.0, 115.0)
    remplissage = QColor("#22C55E")
    remplissage.setAlpha(46)
    p.setPen(_plume(QColor("#22C55E"), 2.0))
    p.setBrush(remplissage)
    p.drawEllipse(centre, 50.0, 50.0)
    p.setPen(_plume(trait, 1.4))
    p.drawLine(centre, QPointF(centre.x() + 50.0, centre.y()))
    _texte(p, centre.x() + 18.0, centre.y() - 6.0, "R", trait, 11.0, True)
    _texte(p, 40.0, 190.0, "J = m·R²/2", texte, 11.0)
    a, b = QPointF(190.0, 115.0), QPointF(330.0, 115.0)
    p.setPen(_plume(QColor("#3B82F6"), 6.0))
    p.drawLine(a, b)
    p.setPen(_plume(trait, 1.0, Qt.DashLine))
    milieu = QPointF((a.x() + b.x()) / 2.0, a.y())
    p.drawLine(QPointF(milieu.x(), milieu.y() - 40.0), QPointF(milieu.x(), milieu.y() + 40.0))
    _texte(p, milieu.x() - 6.0, milieu.y() - 46.0, "G", trait, 11.0, True, False)
    _texte(p, 200.0, 170.0, "J_G = m·L²/12", texte, 11.0)
    _texte(p, 200.0, 190.0, "J_A = J_G + m·d²  (Huygens)", texte, 10.0)


FIGURES: Dict[str, Callable[[QPainter], None]] = {
    "moment": _moment,
    "torseur": _torseur,
    "engrenage": _engrenage,
    "came": _came,
    "point_mort": _point_mort,
    "inertie": _inertie,
}


def figures() -> Dict[str, QImage]:
    """Toutes les figures, dessinées avec la palette du thème courant."""
    return {nom: _image(dessiner) for nom, dessiner in FIGURES.items()}
