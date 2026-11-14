"""Démonstrations animées du tutoriel.

Chaque démonstration est une fonction ``(scene, t)`` qui dessine l'état de
sa petite animation à l'instant ``t`` (en secondes, de 0 à sa durée) : un
pointeur de souris se déplace, clique, et l'élément apparaît sur une
mini-grille. L'animation boucle. Les symboles sont ceux du schéma de Sikax
(mêmes fonctions de dessin), pour que l'utilisateur les reconnaisse ensuite.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from ..schema.rendu import arc_fleche, fleche, hachures, zigzag

Point = Tuple[float, float]

FOND = QColor("#0F1115")
GRILLE = QColor("#1C2028")
GRILLE_FORTE = QColor("#262B36")
TRAIT = QColor("#DDE2EC")
ACCENT = QColor("#5B93FF")
SECONDAIRE = QColor("#98A1B3")
BLEU, ORANGE, VERT, ROSE, VIOLET = (QColor(c) for c in ("#3B82F6", "#F97316", "#22C55E", "#EC4899", "#A855F7"))
FORCE = QColor("#FF6B6B")
MOTEUR = QColor("#FACC15")
LARGEUR, HAUTEUR = 360.0, 200.0


def lisser(u: float) -> float:
    """Accélération puis freinage, comme une main qui déplace la souris."""
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def trajet(t: float, etapes: Sequence[Tuple[float, Point]]) -> Point:
    """Position interpolée sur une suite d'étapes (instant, position)."""
    if t <= etapes[0][0]:
        return etapes[0][1]
    for (t0, p0), (t1, p1) in zip(etapes, etapes[1:]):
        if t <= t1:
            u = lisser((t - t0) / max(t1 - t0, 1e-9))
            return (p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u)
    return etapes[-1][1]


def apparition(t: float, debut: float, duree: float = 0.25) -> float:
    return max(0.0, min(1.0, (t - debut) / duree))


class Scene:
    """Pinceaux de la mini-grille : solides, liaisons, pointeur et ondes de clic."""

    def __init__(self, p: QPainter, rect: QRectF) -> None:
        self.p = p
        self.rect = rect
        self.echelle = min(rect.width() / LARGEUR, rect.height() / HAUTEUR)
        self.dx = rect.left() + (rect.width() - LARGEUR * self.echelle) / 2.0
        self.dy = rect.top() + (rect.height() - HAUTEUR * self.echelle) / 2.0

    def q(self, point: Point) -> QPointF:
        return QPointF(self.dx + point[0] * self.echelle, self.dy + point[1] * self.echelle)

    def plume(self, couleur: QColor, largeur: float = 2.0, style=Qt.SolidLine) -> QPen:
        plume = QPen(couleur, largeur * self.echelle, style)
        plume.setCapStyle(Qt.RoundCap)
        plume.setJoinStyle(Qt.RoundJoin)
        return plume

    # -- décor ---------------------------------------------------------------
    def grille(self, zoom: float = 1.0, decalage: Point = (0.0, 0.0)) -> None:
        p = self.p
        p.fillRect(self.rect, FOND)
        pas = 20.0 * zoom
        p.setRenderHint(QPainter.Antialiasing, False)
        x0 = (decalage[0] % pas) - pas
        i = 0
        x = x0
        while x <= LARGEUR + pas:
            p.setPen(QPen(GRILLE_FORTE if i % 5 == 0 else GRILLE, 1.0))
            p.drawLine(self.q((x, 0.0)), self.q((x, HAUTEUR)))
            x += pas
            i += 1
        y = (decalage[1] % pas) - pas
        j = 0
        while y <= HAUTEUR + pas:
            p.setPen(QPen(GRILLE_FORTE if j % 5 == 0 else GRILLE, 1.0))
            p.drawLine(self.q((0.0, y)), self.q((LARGEUR, y)))
            y += pas
            j += 1
        p.setRenderHint(QPainter.Antialiasing, True)

    def texte(self, point: Point, texte: str, couleur: QColor = SECONDAIRE, taille: float = 9.0, gras: bool = False) -> None:
        police = QFont(self.p.font())
        police.setPointSizeF(taille * max(self.echelle, 0.7))
        police.setBold(gras)
        self.p.setFont(police)
        self.p.setPen(couleur)
        self.p.drawText(self.q(point), texte)

    # -- objets ----------------------------------------------------------------
    def barre(self, a: Point, b: Point, couleur: QColor, progres: float = 1.0, largeur: float = 5.0) -> None:
        if progres <= 0.0:
            return
        fin = (a[0] + (b[0] - a[0]) * progres, a[1] + (b[1] - a[1]) * progres)
        self.p.setPen(self.plume(couleur, largeur))
        self.p.drawLine(self.q(a), self.q(fin))

    def point(self, c: Point, couleur: QColor, rayon: float = 3.6) -> None:
        self.p.setPen(self.plume(FOND, 1.2))
        self.p.setBrush(couleur)
        self.p.drawEllipse(self.q(c), rayon * self.echelle, rayon * self.echelle)

    def pivot(self, c: Point, bati: bool = False, opacite: float = 1.0) -> None:
        if opacite <= 0.0:
            return
        p = self.p
        p.save()
        p.setOpacity(opacite)
        e = self.echelle
        centre = self.q(c)
        if bati:
            p.setPen(self.plume(TRAIT, 1.6))
            p.setBrush(FOND)
            p.drawPolygon(QPolygonF([centre, QPointF(centre.x() - 9 * e, centre.y() + 17 * e), QPointF(centre.x() + 9 * e, centre.y() + 17 * e)]))
            gauche, droite = QPointF(centre.x() - 13 * e, centre.y() + 17 * e), QPointF(centre.x() + 13 * e, centre.y() + 17 * e)
            p.drawLine(gauche, droite)
            hachures(p, gauche, droite, 1.0, TRAIT, 6.0 * e, 6.0 * e)
        p.setPen(self.plume(TRAIT, 2.0))
        p.setBrush(FOND)
        p.drawEllipse(centre, 6.0 * e, 6.0 * e)
        p.restore()

    def glissiere(self, c: Point, angle: float, opacite: float = 1.0) -> None:
        p = self.p
        p.save()
        p.setOpacity(opacite)
        e = self.echelle
        ux, uy = math.cos(angle), -math.sin(angle)
        a, b = self.q((c[0] - 60 * ux, c[1] - 60 * uy)), self.q((c[0] + 60 * ux, c[1] + 60 * uy))
        p.setPen(self.plume(TRAIT, 2.0))
        p.drawLine(a, b)
        hachures(p, a, b, 1.0, TRAIT, 8.0 * e, 6.0 * e)
        p.translate(self.q(c))
        p.rotate(-math.degrees(angle))
        p.setPen(self.plume(TRAIT, 2.0))
        p.setBrush(FOND)
        p.drawRect(QRectF(-14 * e, -7.5 * e, 28 * e, 15 * e))
        p.restore()

    def disque(self, c: Point, r: float, couleur: QColor, angle: float = 0.0, opacite: float = 1.0) -> None:
        p = self.p
        p.save()
        p.setOpacity(opacite)
        remplissage = QColor(couleur)
        remplissage.setAlpha(50)
        p.setPen(self.plume(couleur, 2.2))
        p.setBrush(remplissage)
        p.drawEllipse(self.q(c), r * self.echelle, r * self.echelle)
        p.setPen(self.plume(couleur, 1.4, Qt.DashLine))
        p.drawLine(self.q(c), self.q((c[0] + 0.72 * r * math.cos(angle), c[1] - 0.72 * r * math.sin(angle))))
        p.restore()

    def roue(self, c: Point, r: float, z: int, angle: float, couleur: QColor) -> None:
        """Roue dentée : z dents autour du cercle primitif de rayon r."""
        module = 2.0 * r / z
        tete, pied = r + module, r - 1.25 * module
        beta = 2.0 * math.pi / z
        points = []
        for i in range(z):
            phi = angle + i * beta
            for decalage, rayon in ((-0.30, pied), (-0.17, tete), (0.17, tete), (0.30, pied)):
                a = phi + decalage * beta
                points.append(self.q((c[0] + rayon * math.cos(a), c[1] - rayon * math.sin(a))))
        remplissage = QColor(couleur)
        remplissage.setAlpha(55)
        self.p.setPen(self.plume(couleur, 1.4))
        self.p.setBrush(remplissage)
        self.p.drawPolygon(QPolygonF(points))
        self.p.setPen(self.plume(couleur, 1.0, Qt.DashLine))
        self.p.setBrush(Qt.NoBrush)
        self.p.drawEllipse(self.q(c), r * self.echelle, r * self.echelle)
        self.p.setPen(self.plume(couleur, 1.6))
        self.p.drawLine(self.q(c), self.q((c[0] + 0.6 * r * math.cos(angle), c[1] - 0.6 * r * math.sin(angle))))

    def fleche(self, a: Point, b: Point, couleur: QColor) -> None:
        fleche(self.p, self.q(a), self.q(b), couleur, 2.4 * self.echelle, 10.0 * self.echelle)

    def moteur(self, c: Point, opacite: float = 1.0) -> None:
        if opacite <= 0.0:
            return
        self.p.save()
        self.p.setOpacity(opacite)
        arc_fleche(self.p, self.q(c), 13.5 * self.echelle, 1.0, MOTEUR, 2.0 * self.echelle)
        self.texte((c[0] + 15.0, c[1] + 20.0), "M", MOTEUR, 9.0, True)
        self.p.restore()

    def ressort(self, a: Point, b: Point, couleur: QColor) -> None:
        zigzag(self.p, self.q(a), self.q(b), couleur, 6.0 * self.echelle)

    def pointille(self, a: Point, b: Point, couleur: QColor = ACCENT) -> None:
        self.p.setPen(self.plume(couleur, 1.6, Qt.DashLine))
        self.p.drawLine(self.q(a), self.q(b))

    # -- souris ------------------------------------------------------------------
    def onde(self, c: Point, age: float) -> None:
        """Onde d'un clic, qui s'élargit et s'efface en un tiers de seconde."""
        if not 0.0 <= age <= 0.35:
            return
        u = age / 0.35
        couleur = QColor(ACCENT)
        couleur.setAlphaF(0.75 * (1.0 - u))
        self.p.setPen(self.plume(couleur, 2.2))
        self.p.setBrush(Qt.NoBrush)
        r = (6.0 + 16.0 * u) * self.echelle
        self.p.drawEllipse(self.q(c), r, r)

    def curseur(self, c: Point, appuye: bool = False) -> None:
        e = self.echelle * (0.92 if appuye else 1.0)
        x, y = self.q(c).x(), self.q(c).y()
        forme = [(0, 0), (0, 17), (4.2, 13.2), (7.4, 20), (10, 18.8), (6.9, 12.2), (12.2, 12.2)]
        polygone = QPolygonF([QPointF(x + px * e, y + py * e) for px, py in forme])
        self.p.setPen(QPen(QColor("#0B0D11"), 1.4 * self.echelle))
        self.p.setBrush(QColor("#FFFFFF"))
        self.p.drawPolygon(polygone)


def _clics(s: Scene, t: float, clics: Sequence[Tuple[float, Point]]) -> bool:
    """Dessine les ondes des clics ; vrai si le bouton est enfoncé à l'instant t."""
    appuye = False
    for instant, lieu in clics:
        s.onde(lieu, t - instant)
        appuye = appuye or 0.0 <= t - instant <= 0.12
    return appuye


# ---------------------------------------------------------------- démonstrations

def _bielle_manivelle(s: Scene, o: Point, angle: float, rayon: float = 32.0, bielle: float = 100.0) -> Point:
    b = (o[0] + rayon * math.cos(angle), o[1] - rayon * math.sin(angle))
    cx = b[0] + math.sqrt(max(bielle * bielle - (o[1] - b[1]) ** 2, 0.0))
    c = (cx, o[1])
    s.barre(o, b, BLEU)
    s.barre(b, c, ORANGE)
    s.p.setPen(s.plume(TRAIT, 2.0))
    s.p.setBrush(VERT.darker(140))
    s.p.drawRect(QRectF(s.q((c[0] - 4, c[1] - 9)), s.q((c[0] + 28, c[1] + 9))))
    gauche, droite = s.q((o[0] + 40, o[1] + 12)), s.q((o[0] + 190, o[1] + 12))
    s.p.setPen(s.plume(TRAIT, 1.6))
    s.p.drawLine(gauche, droite)
    hachures(s.p, gauche, droite, 1.0, TRAIT, 7.0 * s.echelle, 5.0 * s.echelle)
    s.pivot(o, bati=True)
    s.pivot(b)
    s.pivot(c)
    return c


def demo_bienvenue(s: Scene, t: float) -> None:
    s.grille()
    o = (80.0, 110.0)
    angle = 2.0 * math.pi * 0.5 * max(0.0, t - 2.4)
    if t < 2.4:
        s.barre(o, (o[0] + 32.0, o[1]), BLEU, lisser(t / 0.8))
        s.barre((o[0] + 32.0, o[1]), (o[0] + 132.0, o[1]), ORANGE, lisser((t - 0.8) / 0.8))
        s.pivot(o, bati=True, opacite=apparition(t, 1.7))
        s.moteur(o, apparition(t, 2.0))
    else:
        _bielle_manivelle(s, o, angle)
        s.moteur(o)
    for i, (debut, mot) in enumerate(((0.2, "1. Dessiner"), (1.6, "2. Relier"), (2.4, "3. Calculer"))):
        couleur = QColor(TRAIT if t >= debut else SECONDAIRE)
        couleur.setAlphaF(0.35 + 0.65 * apparition(t, debut))
        s.texte((20.0 + 112.0 * i, 30.0), mot, couleur, 10.5, True)


def demo_barre(s: Scene, t: float) -> None:
    s.grille()
    p1, p2, p3 = (70.0, 140.0), (170.0, 80.0), (290.0, 110.0)
    clics = [(0.7, p1), (1.7, p2), (2.7, p3), (2.95, p3)]
    souris = trajet(t, [(0.0, (40.0, 170.0)), (0.6, p1), (1.6, p2), (2.6, p3), (5.0, p3)])
    if 0.7 <= t:
        s.point(p1, BLEU)
    if 1.7 <= t:
        s.barre(p1, p2, BLEU)
        s.point(p2, BLEU)
    elif 0.7 < t:
        s.pointille(p1, souris)
    if 2.7 <= t:
        s.barre(p2, p3, BLEU)
        s.point(p3, BLEU)
    elif 1.7 < t:
        s.pointille(p2, souris)
        longueur = math.hypot(souris[0] - p2[0], souris[1] - p2[1])
        s.texte((souris[0] + 14, souris[1] + 20), f"{longueur / 2:.0f} mm", TRAIT, 8.5)
    if t >= 3.0:
        s.texte((205.0, 30.0), "Solide terminé", ACCENT, 10.0, True)
    s.curseur(souris, _clics(s, t, clics))


def demo_pivot(s: Scene, t: float) -> None:
    s.grille()
    a, b = (110.0, 120.0), (250.0, 70.0)
    s.barre(a, b, BLEU)
    s.point(a, BLEU)
    s.point(b, BLEU)
    souris = trajet(t, [(0.0, (300.0, 170.0)), (1.0, a), (5.0, a)])
    s.pivot(a, bati=True, opacite=apparition(t, 1.15))
    if t >= 1.3:
        s.texte((150.0, 165.0), "Pivot avec le bâti", ACCENT, 10.0, True)
    s.curseur(souris, _clics(s, t, [(1.1, a)]))


def demo_relier(s: Scene, t: float) -> None:
    s.grille()
    a1, a2 = (60.0, 120.0), (230.0, 120.0)
    b1, b2 = (150.0, 120.0), (290.0, 50.0)
    lieu = (150.0, 120.0)
    s.barre(a1, a2, BLEU)
    s.barre(b1, b2, ORANGE)
    for point, couleur in ((a1, BLEU), (a2, BLEU), (b2, ORANGE)):
        s.point(point, couleur)
    souris = trajet(t, [(0.0, (60.0, 175.0)), (0.9, (152.0, 122.0)), (1.3, (152.0, 122.0)), (2.3, (260.0, 66.0)), (6.0, (260.0, 66.0))])
    if 1.0 <= t < 2.4:
        s.point(lieu, ACCENT, 4.5)
        s.pointille(lieu, souris)
        s.texte((180.0, 172.0), "Cliquez le second solide", SECONDAIRE, 9.0)
    s.pivot(lieu, opacite=apparition(t, 2.4))
    if t >= 2.6:
        s.texte((172.0, 172.0), "Points ajoutés aux deux barres", ACCENT, 9.5, True)
    s.curseur(souris, _clics(s, t, [(1.0, (152.0, 122.0)), (2.4, (260.0, 66.0))]))


def demo_glissiere(s: Scene, t: float) -> None:
    s.grille()
    c = (180.0, 110.0)
    s.point(c, ORANGE)
    souris = trajet(t, [(0.0, (60.0, 170.0)), (0.8, c), (1.0, c), (2.4, (270.0, 60.0)), (5.0, (270.0, 60.0))])
    if 1.0 <= t < 2.5:
        angle = math.atan2(c[1] - souris[1], souris[0] - c[0])
        angle = round(angle / math.radians(15.0)) * math.radians(15.0)
        ux, uy = math.cos(angle), -math.sin(angle)
        s.pointille((c[0] - 60 * ux, c[1] - 60 * uy), (c[0] + 60 * ux, c[1] + 60 * uy))
        s.texte((c[0] + 14, c[1] - 14), f"{math.degrees(angle):.0f}°", TRAIT, 9.0)
    if t >= 2.5:
        s.glissiere(c, math.radians(30.0), apparition(t, 2.5))
    appuye = 1.0 <= t <= 2.5
    s.onde(c, t - 0.9)
    s.curseur(souris, appuye)


def demo_cercle(s: Scene, t: float) -> None:
    s.grille()
    c = (170.0, 105.0)
    souris = trajet(t, [(0.0, (70.0, 175.0)), (0.8, c), (1.0, c), (2.4, (225.0, 70.0)), (5.0, (225.0, 70.0))])
    rayon = math.hypot(souris[0] - c[0], souris[1] - c[1]) if t >= 1.0 else 0.0
    if 1.0 <= t < 2.5:
        s.p.setPen(s.plume(ACCENT, 2.0, Qt.DashLine))
        s.p.setBrush(Qt.NoBrush)
        s.p.drawEllipse(s.q(c), rayon * s.echelle, rayon * s.echelle)
        s.texte((souris[0] + 12, souris[1] + 18), f"R = {rayon / 2:.0f} mm", TRAIT, 8.5)
    if t >= 2.5:
        s.disque(c, 65.3, VERT, 0.0, apparition(t, 2.5))
    s.point(c, VERT)
    s.onde(c, t - 0.9)
    s.curseur(souris, 1.0 <= t <= 2.5)


def demo_engrenage(s: Scene, t: float) -> None:
    s.grille()
    c1, c2 = (120.0, 110.0), (120.0 + 40.0 + 60.0, 110.0)
    actif = t >= 2.2
    angle = 1.4 * max(0.0, t - 2.2)
    if actif:
        s.roue(c1, 40.0, 16, angle, BLEU)
        s.roue(c2, 60.0, 24, -angle * 40.0 / 60.0 + math.pi / 24.0 + math.pi, ORANGE)
    else:
        s.disque(c1, 40.0, BLEU)
        s.disque(c2, 60.0, ORANGE)
    s.pivot(c1, bati=True)
    s.pivot(c2, bati=True)
    souris = trajet(t, [(0.0, (40.0, 30.0)), (0.9, (110.0, 90.0)), (1.1, (110.0, 90.0)), (1.9, (240.0, 80.0)), (6.5, (240.0, 80.0))])
    if 1.0 <= t < 2.0:
        s.pointille((110.0, 90.0), souris)
    if actif:
        s.texte((30.0, 30.0), "Z₁ = 16   Z₂ = 24   r = −2/3", ACCENT, 10.0, True)
    s.curseur(souris, _clics(s, t, [(1.0, (110.0, 90.0)), (2.0, (240.0, 80.0))]))


def demo_came(s: Scene, t: float) -> None:
    s.grille()
    o = (150.0, 135.0)
    rayon, excentricite, galet = 38.0, 14.0, 8.0
    angle = 2.0 * math.pi * 0.45 * max(0.0, t - 2.0)
    c = (o[0] + excentricite * math.cos(angle + math.pi / 2), o[1] - excentricite * math.sin(angle + math.pi / 2))
    s.disque(c, rayon, BLEU, angle)
    s.point(c, BLEU)
    s.barre(o, c, BLEU, 1.0, 2.5)
    dx = o[0] - c[0]
    hauteur = c[1] - math.sqrt(max((rayon + galet) ** 2 - dx * dx, 0.0))
    galet_c = (o[0], hauteur)
    s.barre((o[0], hauteur - galet), (o[0], 18.0), ORANGE)
    s.p.setPen(s.plume(ORANGE, 2.0))
    s.p.setBrush(FOND)
    s.p.drawEllipse(s.q(galet_c), galet * s.echelle, galet * s.echelle)
    for x in (o[0] - 13.0, o[0] + 13.0):
        s.p.setPen(s.plume(TRAIT, 1.6))
        s.p.drawLine(s.q((x, 20.0)), s.q((x, 52.0)))
    s.pivot(o, bati=True)
    s.moteur(o, apparition(t, 1.9))
    souris = trajet(t, [(0.0, (300.0, 175.0)), (0.7, (178.0, 140.0)), (0.9, (178.0, 140.0)), (1.5, galet_c), (6.5, galet_c)])
    if t >= 2.2:
        s.texte((215.0, 40.0), "course = 2·e", ACCENT, 10.0, True)
    s.curseur(souris, _clics(s, t, [(0.8, (178.0, 140.0)), (1.6, galet_c)]))


def demo_moteur(s: Scene, t: float) -> None:
    s.grille()
    o = (130.0, 115.0)
    angle = 2.0 * math.pi * 0.4 * max(0.0, t - 1.6)
    b = (o[0] + 70.0 * math.cos(angle), o[1] - 70.0 * math.sin(angle))
    s.barre(o, b, BLEU)
    s.point(b, BLEU)
    s.pivot(o, bati=True)
    s.moteur(o, apparition(t, 1.15))
    souris = trajet(t, [(0.0, (290.0, 170.0)), (1.0, o), (5.0, o)])
    if t >= 1.6:
        s.texte((205.0, 40.0), "ω = 2,5 rad/s", ACCENT, 10.0, True)
    s.curseur(souris, _clics(s, t, [(1.1, o)]))


def demo_force(s: Scene, t: float) -> None:
    s.grille()
    a, b = (90.0, 130.0), (230.0, 130.0)
    s.barre(a, b, BLEU)
    s.point(a, BLEU)
    s.point(b, BLEU)
    s.pivot(a, bati=True)
    souris = trajet(t, [(0.0, (300.0, 40.0)), (0.9, b), (1.1, b), (2.3, (236.0, 50.0)), (5.0, (236.0, 50.0))])
    if 1.1 <= t:
        fin = souris if t < 2.4 else (236.0, 50.0)
        s.fleche(b, fin, FORCE)
        s.texte((fin[0] + 10, fin[1] + 4), f"{math.hypot(fin[0] - b[0], fin[1] - b[1]) * 1.25:.0f} N", FORCE, 9.5, True)
    s.onde(b, t - 1.0)
    s.curseur(souris, 1.1 <= t <= 2.4)


def demo_calcul(s: Scene, t: float) -> None:
    s.grille()
    o = (50.0, 120.0)
    angle = 2.0 * math.pi * 0.5 * max(0.0, t - 0.8)
    piston = _bielle_manivelle(s, o, angle, 22.0, 70.0)
    s.moteur(o)
    # courbe de la position du piston, tracée au fur et à mesure
    cadre = QRectF(s.q((205.0, 40.0)), s.q((345.0, 170.0)))
    s.p.setPen(s.plume(GRILLE_FORTE, 1.0))
    s.p.setBrush(QColor(20, 23, 30))
    s.p.drawRoundedRect(cadre, 5.0, 5.0)
    chemin = QPainterPath()
    duree = max(0.0, t - 0.8)
    for i in range(0, 141):
        u = i / 140.0
        if u * 5.5 > duree:
            break
        a = 2.0 * math.pi * 0.5 * u * 5.5
        x = 22.0 * math.cos(a) + math.sqrt(70.0 ** 2 - (22.0 * math.sin(a)) ** 2)
        point = s.q((210.0 + 130.0 * u, 105.0 - (x - 70.0) * 2.2))
        chemin.lineTo(point) if i else chemin.moveTo(point)
    s.p.setPen(s.plume(ACCENT, 1.8))
    s.p.setBrush(Qt.NoBrush)
    s.p.drawPath(chemin)
    s.texte((212.0, 56.0), "x piston (mm)", SECONDAIRE, 8.0)
    if t < 0.8:
        s.texte((60.0, 40.0), "F5", MOTEUR, 14.0, True)


def demo_vue(s: Scene, t: float) -> None:
    zoom = 1.0 + 0.6 * math.sin(min(t, 3.0) / 3.0 * math.pi)
    decalage = (-40.0 * lisser((t - 3.2) / 1.5), 0.0) if t > 3.2 else (0.0, 0.0)
    s.grille(zoom, decalage)
    centre = (180.0 + decalage[0], 105.0)

    def ici(x: float, y: float) -> Point:
        return (centre[0] + (x - 180.0) * zoom, centre[1] + (y - 105.0) * zoom)

    s.barre(ici(130, 120), ici(170, 85), BLEU)
    s.barre(ici(170, 85), ici(240, 120), ORANGE)
    s.pivot(ici(130, 120), bati=True)
    s.pivot(ici(170, 85))
    s.pivot(ici(240, 120))
    s.texte((20.0, 30.0), "molette : zoom" if t < 3.2 else "clic droit maintenu : déplacer", ACCENT, 10.0, True)
    s.curseur((200.0 + decalage[0], 100.0), t > 3.2)


def demo_photo(s: Scene, t: float) -> None:
    s.grille()
    # « photo » d'un schéma dessiné à la main, estompée
    s.p.save()
    s.p.setOpacity(0.45)
    s.p.fillRect(QRectF(s.q((30.0, 25.0)), s.q((330.0, 185.0))), QColor("#E8E2D0"))
    crayon = QColor("#5B5548")
    for a, b in (((80, 140), (130, 90)), ((130, 90), (240, 120)), ((240, 120), (240, 160))):
        s.p.setPen(s.plume(crayon, 2.0))
        s.p.drawLine(s.q(a), s.q(b))
    for c in ((80, 140), (130, 90), (240, 120)):
        s.p.setPen(s.plume(crayon, 1.6))
        s.p.setBrush(Qt.NoBrush)
        s.p.drawEllipse(s.q(c), 5 * s.echelle, 5 * s.echelle)
    s.p.restore()
    a, b = (80.0, 140.0), (130.0, 90.0)
    souris = trajet(t, [(0.0, (300.0, 170.0)), (0.8, a), (1.6, b), (7.0, b)])
    if 0.9 <= t < 2.8:
        s.pointille(a, souris if t < 1.7 else b, MOTEUR)
    if 1.8 <= t < 2.8:
        s.texte((140.0, 60.0), "Longueur réelle : 50 mm", MOTEUR, 9.5, True)
    if t >= 2.9:
        s.barre((80, 140), (130, 90), BLEU, lisser((t - 2.9) / 0.6))
        s.barre((130, 90), (240, 120), ORANGE, lisser((t - 3.5) / 0.6))
        s.barre((240, 120), (240, 160), VERT, lisser((t - 4.1) / 0.6))
        s.texte((215.0, 40.0), "Tracé par-dessus", ACCENT, 10.0, True)
    s.curseur(souris, _clics(s, t, [(0.9, a), (1.7, b)]))


def demo_cours(s: Scene, t: float) -> None:
    s.grille()
    panneau = QRectF(s.q((30.0, 30.0)), s.q((170.0, 175.0)))
    s.p.setPen(s.plume(GRILLE_FORTE, 1.0))
    s.p.setBrush(QColor(27, 30, 37))
    s.p.drawRoundedRect(panneau, 6.0, 6.0)
    for i, (libelle, valeur) in enumerate((("Module m", "2 mm"), ("Dents Z₁", "20"), ("Angle α", "20°"))):
        y = 60.0 + 34.0 * i
        s.texte((42.0, y), libelle, SECONDAIRE, 8.5)
        s.texte((112.0, y), valeur, TRAIT, 8.5)
    aide = (158.0, 56.0)
    lueur = 0.5 + 0.5 * math.sin(6.0 * t)
    couleur = QColor(ACCENT)
    couleur.setAlphaF(0.35 + 0.65 * lueur if t < 1.2 else 1.0)
    s.p.setPen(s.plume(couleur, 1.6))
    s.p.setBrush(Qt.NoBrush)
    s.p.drawEllipse(s.q(aide), 7.0 * s.echelle, 7.0 * s.echelle)
    s.texte((aide[0] - 3.0, aide[1] + 4.0), "?", couleur, 9.0, True)
    souris = trajet(t, [(0.0, (300.0, 170.0)), (1.0, aide), (5.0, aide)])
    if t >= 1.3:
        u = lisser((t - 1.3) / 0.5)
        fiche = QRectF(s.q((190.0 + 30.0 * (1.0 - u), 30.0)), s.q((340.0, 175.0)))
        s.p.save()
        s.p.setOpacity(u)
        s.p.setPen(s.plume(GRILLE_FORTE, 1.0))
        s.p.setBrush(QColor(27, 30, 37))
        s.p.drawRoundedRect(fiche, 6.0, 6.0)
        s.texte((200.0, 52.0), "Engrenages", ACCENT, 10.5, True)
        s.texte((200.0, 82.0), "d = m · Z", TRAIT, 10.0)
        s.texte((200.0, 108.0), "Ft = 2·C / d", TRAIT, 10.0)
        s.texte((200.0, 134.0), "Fr = Ft · tan α", TRAIT, 10.0)
        s.p.restore()
    s.curseur(souris, _clics(s, t, [(1.1, aide)]))


DEMOS: Dict[str, Tuple[float, Callable[[Scene, float], None]]] = {
    "bienvenue": (6.5, demo_bienvenue),
    "barre": (5.0, demo_barre),
    "pivot": (4.0, demo_pivot),
    "relier": (5.5, demo_relier),
    "glissiere": (4.5, demo_glissiere),
    "cercle": (4.5, demo_cercle),
    "engrenage": (6.5, demo_engrenage),
    "came": (6.5, demo_came),
    "moteur": (5.0, demo_moteur),
    "force": (4.5, demo_force),
    "calcul": (6.5, demo_calcul),
    "vue": (6.0, demo_vue),
    "photo": (7.0, demo_photo),
    "cours": (5.0, demo_cours),
}
"""Démonstration de chaque étape : (durée d'une boucle en secondes, fonction de dessin)."""


def dessiner(nom: str, p: QPainter, rect: QRectF, t: float) -> None:
    """Dessine l'image de la démonstration ``nom`` à l'instant t (bouclé sur sa durée)."""
    duree, fonction = DEMOS[nom]
    p.save()
    p.setClipRect(rect)
    p.setRenderHint(QPainter.Antialiasing, True)
    fonction(Scene(p, rect), t % duree)
    p.restore()
