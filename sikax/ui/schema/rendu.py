"""Dessin du schéma cinématique.

Tout est tracé avec ``QPainter`` en coordonnées écran : les symboles de
liaison gardent ainsi une taille constante quel que soit le zoom, comme sur
un schéma normalisé. La conversion monde → écran est fournie par la vue.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Optional, Set, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from ...modele import Couple, Force, Ressort
from ...modele.contacts import rayon_pied, rayon_tete
from ...modele.liaisons import Came, Encastrement, Engrenage, Glissiere, Liaison, Pivot, Ponctuelle
from ...modele.solide import ID_BATI
from ...util.expression import ErreurExpression, evaluer
from ..document import Document, Ref
from ..theme import theme

Ecran = Callable[[float, float], QPointF]

EPAISSEUR_SOLIDE = 5.0
RAYON_POINT = 3.6
RAYON_PIVOT = 6.0


def _plume(couleur: QColor, largeur: float = 1.6, style: Qt.PenStyle = Qt.SolidLine) -> QPen:
    plume = QPen(couleur, largeur, style)
    plume.setCapStyle(Qt.RoundCap)
    plume.setJoinStyle(Qt.RoundJoin)
    return plume


def fleche(p: QPainter, a: QPointF, b: QPointF, couleur: QColor, largeur: float = 2.0, pointe: float = 9.0) -> None:
    """Flèche de a vers b, pointe pleine."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    longueur = math.hypot(dx, dy)
    if longueur < 1e-6:
        return
    ux, uy = dx / longueur, dy / longueur
    pointe = min(pointe, longueur)
    base = QPointF(b.x() - ux * pointe, b.y() - uy * pointe)
    p.setPen(_plume(couleur, largeur))
    p.drawLine(a, base)
    demi = pointe * 0.42
    triangle = QPolygonF([b, QPointF(base.x() - uy * demi, base.y() + ux * demi), QPointF(base.x() + uy * demi, base.y() - ux * demi)])
    p.setPen(Qt.NoPen)
    p.setBrush(couleur)
    p.drawPolygon(triangle)


def hachures(p: QPainter, a: QPointF, b: QPointF, cote: float, couleur: QColor, pas: float = 6.0, longueur: float = 6.0) -> None:
    """Hachures de bâti le long du segment ab, du côté ``cote`` (+1 ou −1) de sa normale."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    total = math.hypot(dx, dy)
    if total < 1e-6:
        return
    ux, uy = dx / total, dy / total
    nx, ny = -uy * cote, ux * cote
    p.setPen(_plume(couleur, 1.2))
    nombre = max(1, int(total // pas))
    for i in range(nombre + 1):
        d = total * i / nombre
        x, y = a.x() + ux * d, a.y() + uy * d
        p.drawLine(QPointF(x, y), QPointF(x + (nx - ux) * longueur * 0.8, y + (ny - uy) * longueur * 0.8))


def arc_fleche(p: QPainter, centre: QPointF, rayon: float, sens: float, couleur: QColor, largeur: float = 2.0) -> None:
    """Arc de trois quarts de tour terminé par une pointe ; ``sens`` > 0 = sens trigonométrique."""
    rect = QRectF(centre.x() - rayon, centre.y() - rayon, 2 * rayon, 2 * rayon)
    depart, etendue = (-40.0, 270.0) if sens >= 0 else (220.0, -270.0)
    chemin = QPainterPath()
    chemin.arcMoveTo(rect, depart)
    chemin.arcTo(rect, depart, etendue)
    p.setPen(_plume(couleur, largeur))
    p.setBrush(Qt.NoBrush)
    p.drawPath(chemin)
    fin = math.radians(depart + etendue)
    bout = QPointF(centre.x() + rayon * math.cos(fin), centre.y() - rayon * math.sin(fin))
    # tangente dans le sens du parcours (repère écran : y vers le bas)
    signe = 1.0 if sens >= 0 else -1.0
    tx, ty = -math.sin(fin) * signe, -math.cos(fin) * signe
    taille = 8.0
    base = QPointF(bout.x() - tx * taille, bout.y() - ty * taille)
    demi = taille * 0.45
    p.setPen(Qt.NoPen)
    p.setBrush(couleur)
    p.drawPolygon(QPolygonF([
        QPointF(bout.x() + tx * 2, bout.y() + ty * 2),
        QPointF(base.x() - ty * demi, base.y() + tx * demi),
        QPointF(base.x() + ty * demi, base.y() - tx * demi),
    ]))


def zigzag(p: QPainter, a: QPointF, b: QPointF, couleur: QColor, largeur: float = 6.0) -> None:
    """Ressort entre a et b : le nombre de spires suit la longueur à l'écran."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    longueur = math.hypot(dx, dy)
    p.setPen(_plume(couleur, 1.8))
    if longueur < 24.0:
        p.drawLine(a, b)
        return
    ux, uy = dx / longueur, dy / longueur
    nx, ny = -uy, ux
    tete = min(12.0, longueur * 0.15)
    points = [a, QPointF(a.x() + ux * tete, a.y() + uy * tete)]
    utile = longueur - 2 * tete
    spires = max(4, min(40, int(utile / 9.0)))
    for i in range(2 * spires):
        d = tete + utile * (i + 0.5) / (2 * spires)
        cote = largeur if i % 2 == 0 else -largeur
        points.append(QPointF(a.x() + ux * d + nx * cote, a.y() + uy * d + ny * cote))
    points += [QPointF(b.x() - ux * tete, b.y() - uy * tete), b]
    p.setBrush(Qt.NoBrush)
    p.drawPolyline(QPolygonF(points))


class Rendu:
    """Dessine le document dans un ``QPainter``."""

    def __init__(self, document: Document) -> None:
        self.doc = document
        self.options: Dict[str, bool] = {"reactions": True, "vitesses": False, "trajectoires": False}
        self.survol: Optional[Ref] = None

    # ------------------------------------------------------------- utilitaires
    def _police(self, p: QPainter, taille: float = 10.0, gras: bool = False) -> None:
        police = QFont(p.font())
        police.setPointSizeF(taille)
        police.setBold(gras)
        p.setFont(police)

    def _texte(self, p: QPainter, position: QPointF, texte: str, couleur: QColor, taille: float = 10.0, gras: bool = False) -> None:
        self._police(p, taille, gras)
        # liseré de la couleur du fond : le texte reste lisible par-dessus les traits
        fond = theme.couleur("canevas")
        chemin = QPainterPath()
        chemin.addText(position, p.font(), texte)
        p.setPen(QPen(fond, 3.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(chemin)
        p.setPen(Qt.NoPen)
        p.setBrush(couleur)
        p.drawPath(chemin)

    def _selectionne(self, genre: str, identifiant: str, sous: str = "") -> bool:
        s = self.doc.selection
        return s is not None and s.genre == genre and s.id == identifiant and s.sous == sous

    def _survole(self, genre: str, identifiant: str, sous: str = "") -> bool:
        s = self.survol
        return s is not None and s.genre == genre and s.id == identifiant and s.sous == sous

    # ------------------------------------------------------------------ dessin
    def dessiner(self, p: QPainter, ecran: Ecran, echelle: float) -> None:
        doc = self.doc
        m = doc.mecanisme
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        if doc.resultats is not None and self.options["trajectoires"]:
            self._trajectoires(p, ecran)
        elif doc.resultats is not None and doc.selection is not None and doc.selection.genre == "point":
            self._trajectoire(p, ecran, doc.selection.id, doc.selection.sous)
        self._cercles(p, ecran, echelle)
        self._solides(p, ecran)
        self._roues_dessinees: Set[Tuple[str, float]] = set()
        for liaison in m.liaisons.values():
            if isinstance(liaison, Engrenage):
                self._engrenage(p, ecran, echelle, liaison)
        for action in m.actions.values():
            if isinstance(action, Ressort):
                self._ressort(p, ecran, action)
        for liaison in m.liaisons.values():
            self._liaison(p, ecran, liaison, echelle)
        self._points(p, ecran)
        if m.affichage.get("centres_gravite", True):
            self._centres_gravite(p, ecran)
        self._actions(p, ecran)
        if doc.resultats is not None:
            if self.options["vitesses"]:
                self._vitesses(p, ecran)
            if self.options["reactions"]:
                self._reactions(p, ecran)

    # ----------------------------------------------------------------- solides
    def _solides(self, p: QPainter, ecran: Ecran) -> None:
        doc = self.doc
        accent = theme.couleur("accent")
        for solide in doc.mecanisme.solides.values():
            couleur = QColor(solide.couleur)
            choisi = self._selectionne("solide", solide.id)
            survole = self._survole("solide", solide.id)
            largeur = 3.0 if solide.bati else EPAISSEUR_SOLIDE
            segments = [(ecran(*doc.position(solide.id, a)), ecran(*doc.position(solide.id, b))) for a, b in solide.segments]
            if choisi or survole:
                p.setPen(_plume(QColor(accent.red(), accent.green(), accent.blue(), 150 if choisi else 70), largeur + 7.0))
                for a, b in segments:
                    p.drawLine(a, b)
                if not segments:
                    for point in solide.points.values():
                        p.drawPoint(ecran(*doc.position(solide.id, point.id)))
            p.setPen(_plume(couleur, largeur))
            for a, b in segments:
                p.drawLine(a, b)

    def _cercles(self, p: QPainter, ecran: Ecran, echelle: float) -> None:
        """Disques et cercles des solides, avec un rayon repère qui tourne avec eux."""
        doc = self.doc
        accent = theme.couleur("accent")
        for solide in doc.mecanisme.solides.values():
            if not solide.cercles:
                continue
            couleur = QColor(solide.couleur) if not solide.bati else theme.couleur("trait")
            choisi = self._selectionne("solide", solide.id)
            survole = self._survole("solide", solide.id)
            angle = doc.pose(solide.id)[2]
            for cercle in solide.cercles.values():
                if cercle.centre not in solide.points:
                    continue
                c = ecran(*doc.position(solide.id, cercle.centre))
                r = cercle.rayon * echelle
                if r < 0.5:
                    continue
                if choisi or survole:
                    p.setPen(_plume(QColor(accent.red(), accent.green(), accent.blue(), 150 if choisi else 70), 8.0))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(c, r, r)
                remplissage = QColor(couleur)
                remplissage.setAlpha(0 if solide.bati else (46 if theme.sombre else 34))
                p.setPen(_plume(couleur, 2.4 if solide.bati else 2.2))
                p.setBrush(remplissage)
                p.drawEllipse(c, r, r)
                if not solide.bati and r > 9.0:
                    bout = QPointF(c.x() + 0.72 * r * math.cos(angle), c.y() - 0.72 * r * math.sin(angle))
                    p.setPen(_plume(couleur, 1.4, Qt.DashLine))
                    p.drawLine(c, bout)

    # ------------------------------------------------------------- engrenages
    def _phase(self, liaison: Engrenage, solide_id: str, point_id: str, z: float, creux: bool) -> float:
        """Angle (repère du solide) d'une dent : dents en prise au point primitif dans la configuration du modèle."""
        m = self.doc.mecanisme
        contact = m.contact(liaison)
        centre = m.point_global(solide_id, point_id)
        direction = math.atan2(contact.point[1] - centre[1], contact.point[0] - centre[0])
        return direction - m.solide(solide_id).pose.angle + (math.pi / z if creux else 0.0)

    def _denture(self, p: QPainter, centre: QPointF, rayon_t: float, rayon_p: float, z: int, phase: float, couleur: QColor) -> None:
        """Couronne de z dents (rayons de tête et de pied à l'écran), la première à l'angle ``phase``."""
        beta = 2.0 * math.pi / z
        points = []
        for i in range(z):
            phi = phase + i * beta
            for decalage, rayon in ((-0.30, rayon_p), (-0.17, rayon_t), (0.17, rayon_t), (0.30, rayon_p)):
                a = phi + decalage * beta
                points.append(QPointF(centre.x() + rayon * math.cos(a), centre.y() - rayon * math.sin(a)))
        remplissage = QColor(couleur)
        remplissage.setAlpha(40 if theme.sombre else 30)
        p.setPen(_plume(couleur, 1.3))
        p.setBrush(remplissage)
        p.drawPolygon(QPolygonF(points))

    def _roue(self, p: QPainter, ecran: Ecran, echelle: float, liaison: Engrenage, solide_id: str, point_id: str, z: float, interieur: bool, creux: bool) -> None:
        doc = self.doc
        cle = (solide_id, round(liaison.module * z, 12))
        if cle in self._roues_dessinees:
            return
        self._roues_dessinees.add(cle)
        solide = doc.mecanisme.solides[solide_id]
        couleur = theme.couleur("trait") if solide.bati else QColor(solide.couleur)
        centre = ecran(*doc.position(solide_id, point_id))
        primitif = liaison.module * z / 2.0 * echelle
        p.setPen(_plume(couleur, 1.0, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(centre, primitif, primitif)
        nombre = int(round(z))
        if primitif < 6.0 or nombre < 3 or 2.0 * math.pi * primitif / nombre < 2.5:
            return  # dents trop petites à l'écran : le cercle primitif suffit
        angle = doc.pose(solide_id)[2] + self._phase(liaison, solide_id, point_id, z, creux)
        self._denture(
            p,
            centre,
            rayon_tete(liaison.module, z, interieur) * echelle,
            rayon_pied(liaison.module, z, interieur) * echelle,
            nombre,
            angle,
            couleur,
        )

    def _cremaillere(self, p: QPainter, ecran: Ecran, echelle: float, liaison: Engrenage) -> None:
        """Dents de la crémaillère, le long de sa ligne primitive, du côté du pignon."""
        doc = self.doc
        m = doc.mecanisme
        solide = m.solides[liaison.solide_b]
        couleur = theme.couleur("trait") if solide.bati else QColor(solide.couleur)
        ob = doc.position(liaison.solide_b, liaison.point_b)
        direction = doc.pose(liaison.solide_b)[2] + liaison.angle_axe
        ux, uy = math.cos(direction), math.sin(direction)
        contact = m.contact(liaison, doc.position, lambda sid: doc.pose(sid)[2])
        nx, ny = contact.glissement  # normale orientée vers le pignon
        pas = math.pi * liaison.module
        # abscisses (repère de la crémaillère) de ses points, et premier creux en prise dans le modèle
        abscisses = [(px - ob[0]) * ux + (py - ob[1]) * uy for px, py in (doc.position(solide.id, pid) for pid in solide.points)]
        debut, fin = min(abscisses + [-4.0 * pas]), max(abscisses + [4.0 * pas])
        modele = m.contact(liaison)
        mob = m.point_global(liaison.solide_b, liaison.point_b)
        mdir = solide.pose.angle + liaison.angle_axe
        s0 = (modele.point[0] - mob[0]) * math.cos(mdir) + (modele.point[1] - mob[1]) * math.sin(mdir) + pas / 2.0
        k0, k1 = math.ceil((debut - s0) / pas), math.floor((fin - s0) / pas)
        if (k1 - k0) > 400 or pas * echelle < 3.0:
            k0 = k1 + 1
        tete, pied = liaison.module, -1.25 * liaison.module
        points = []
        for k in range(k0, k1 + 1):
            s = s0 + k * pas
            for ds, h in ((-0.30, pied), (-0.17, tete), (0.17, tete), (0.30, pied)):
                x = ob[0] + (s + ds * pas) * ux + h * nx
                y = ob[1] + (s + ds * pas) * uy + h * ny
                points.append(ecran(x, y))
        a = ecran(ob[0] + debut * ux, ob[1] + debut * uy)
        b = ecran(ob[0] + fin * ux, ob[1] + fin * uy)
        p.setPen(_plume(couleur, 1.0, Qt.DashLine))
        p.drawLine(a, b)
        if points:
            remplissage = QColor(couleur)
            remplissage.setAlpha(40 if theme.sombre else 30)
            p.setPen(_plume(couleur, 1.3))
            p.setBrush(remplissage)
            p.drawPolyline(QPolygonF(points))

    def _engrenage(self, p: QPainter, ecran: Ecran, echelle: float, liaison: Engrenage) -> None:
        m = self.doc.mecanisme
        if liaison.solide_a not in m.solides or liaison.solide_b not in m.solides:
            return
        try:
            self._roue(p, ecran, echelle, liaison, liaison.solide_a, liaison.point_a, liaison.z_a, False, False)
            if liaison.cremaillere:
                self._cremaillere(p, ecran, echelle, liaison)
            else:
                self._roue(p, ecran, echelle, liaison, liaison.solide_b, liaison.point_b, liaison.z_b, liaison.nature == "interieur", True)
        except (KeyError, ValueError):
            return

    def _points(self, p: QPainter, ecran: Ecran) -> None:
        doc = self.doc
        m = doc.mecanisme
        fond = theme.couleur("canevas")
        accent = theme.couleur("accent")
        secondaire = theme.couleur("texte_secondaire")
        lies: Set[Tuple[str, str]] = set()
        for liaison in m.liaisons.values():
            lies.add((liaison.solide_a, liaison.point_a))
            lies.add((liaison.solide_b, liaison.point_b))
        noms_dessines: Set[Tuple[int, int, str]] = set()
        afficher_noms = m.affichage.get("noms_points", True)
        for solide in m.solides.values():
            couleur = QColor(solide.couleur)
            for point in solide.points.values():
                c = ecran(*doc.position(solide.id, point.id))
                choisi = self._selectionne("point", solide.id, point.id)
                survole = self._survole("point", solide.id, point.id)
                if solide.bati and (solide.id, point.id) not in lies:
                    self._ancrage(p, c)
                if choisi or survole:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 150 if choisi else 80))
                    p.drawEllipse(c, RAYON_POINT + 5.0, RAYON_POINT + 5.0)
                if (solide.id, point.id) not in lies or choisi:
                    p.setPen(_plume(fond, 1.4))
                    p.setBrush(couleur)
                    p.drawEllipse(c, RAYON_POINT, RAYON_POINT)
                if afficher_noms:
                    cle = (int(round(c.x() / 4.0)), int(round(c.y() / 4.0)), point.nom)
                    if cle not in noms_dessines:
                        noms_dessines.add(cle)
                        ecart = 13.0 if (solide.id, point.id) in lies else 9.0
                        self._texte(p, QPointF(c.x() + ecart, c.y() - ecart), point.nom, secondaire, 10.0, True)

    def _ancrage(self, p: QPainter, c: QPointF) -> None:
        """Petit symbole de bâti sous un point fixe libre."""
        trait = theme.couleur("trait")
        gauche, droite = QPointF(c.x() - 9.0, c.y() + 6.0), QPointF(c.x() + 9.0, c.y() + 6.0)
        p.setPen(_plume(trait, 1.6))
        p.drawLine(gauche, droite)
        hachures(p, gauche, droite, 1.0, trait, 4.5, 5.0)

    def _centres_gravite(self, p: QPainter, ecran: Ecran) -> None:
        doc = self.doc
        trait = theme.couleur("trait")
        fond = theme.couleur("canevas")
        for solide in doc.mecanisme.solides_mobiles():
            if solide.inertie.masse <= 0.0:
                continue
            c = ecran(*doc.vers_global(solide.id, solide.inertie.gx, solide.inertie.gy))
            r = 5.0
            rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            p.setPen(_plume(trait, 1.2))
            p.setBrush(fond)
            p.drawEllipse(rect)
            p.setPen(Qt.NoPen)
            p.setBrush(trait)
            p.drawPie(rect, 0, 90 * 16)
            p.drawPie(rect, 180 * 16, 90 * 16)

    # ---------------------------------------------------------------- liaisons
    def _liaison(self, p: QPainter, ecran: Ecran, liaison: Liaison, echelle: float = 1.0) -> None:
        doc = self.doc
        m = doc.mecanisme
        if liaison.solide_a not in m.solides or liaison.solide_b not in m.solides:
            return
        try:
            pa = ecran(*doc.position(liaison.solide_a, liaison.point_a))
            pb = ecran(*doc.position(liaison.solide_b, liaison.point_b))
        except KeyError:
            return
        if liaison.CONTACT:
            self._contact(p, ecran, echelle, liaison)
            return
        choisi = self._selectionne("liaison", liaison.id)
        survole = self._survole("liaison", liaison.id)
        trait = theme.couleur("trait")
        fond = theme.couleur("canevas")
        accent = theme.couleur("accent")
        avec_bati = ID_BATI in (liaison.solide_a, liaison.solide_b)
        if choisi or survole:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 110 if choisi else 55))
            p.drawEllipse(pb, 17.0, 17.0)
        contour = accent if choisi else trait

        # direction de l'axe à l'écran (y vers le bas)
        beta = doc.pose(liaison.solide_a)[2] + getattr(liaison, "angle_axe", 0.0)
        ux, uy = math.cos(beta), -math.sin(beta)
        nx, ny = -uy, ux  # normale à l'axe, à l'écran

        if isinstance(liaison, Pivot):
            if avec_bati:
                base_g, base_d = QPointF(pb.x() - 13.0, pb.y() + 17.0), QPointF(pb.x() + 13.0, pb.y() + 17.0)
                p.setPen(_plume(trait, 1.6))
                p.setBrush(fond)
                p.drawPolygon(QPolygonF([pb, QPointF(pb.x() - 9.0, pb.y() + 17.0), QPointF(pb.x() + 9.0, pb.y() + 17.0)]))
                p.drawLine(base_g, base_d)
                hachures(p, base_g, base_d, 1.0, trait)
            p.setPen(_plume(contour, 2.0))
            p.setBrush(fond)
            p.drawEllipse(pb, RAYON_PIVOT, RAYON_PIVOT)

        elif isinstance(liaison, Glissiere):
            couleur_a = QColor(m.solides[liaison.solide_a].couleur) if not avec_bati or liaison.solide_a != ID_BATI else trait
            # la glissière passe par le point de A et s'étend au-delà du coulisseau
            s = (pb.x() - pa.x()) * ux + (pb.y() - pa.y()) * uy
            debut, fin = min(0.0, s) - 34.0, max(0.0, s) + 34.0
            g1 = QPointF(pa.x() + ux * debut, pa.y() + uy * debut)
            g2 = QPointF(pa.x() + ux * fin, pa.y() + uy * fin)
            p.setPen(_plume(couleur_a, 2.0))
            p.drawLine(g1, g2)
            if liaison.solide_a == ID_BATI:
                hachures(p, g1, g2, 1.0 if ny >= 0 else -1.0, trait, 7.0, 6.0)
            p.save()
            p.translate(pb)
            p.rotate(math.degrees(math.atan2(uy, ux)))
            p.setPen(_plume(contour, 2.0))
            p.setBrush(fond)
            p.drawRect(QRectF(-14.0, -7.5, 28.0, 15.0))
            p.restore()

        elif isinstance(liaison, Encastrement):
            if avec_bati:
                base_g, base_d = QPointF(pb.x() - 13.0, pb.y() + 7.0), QPointF(pb.x() + 13.0, pb.y() + 7.0)
                p.setPen(_plume(trait, 1.8))
                p.drawLine(base_g, base_d)
                hachures(p, base_g, base_d, 1.0, trait)
            p.setPen(_plume(contour, 1.6))
            p.setBrush(contour)
            p.drawRect(QRectF(pb.x() - 5.5, pb.y() - 5.5, 11.0, 11.0))

        elif isinstance(liaison, Ponctuelle):
            couleur_a = trait if liaison.solide_a == ID_BATI else QColor(m.solides[liaison.solide_a].couleur)
            s = (pb.x() - pa.x()) * ux + (pb.y() - pa.y()) * uy
            debut, fin = min(0.0, s) - 26.0, max(0.0, s) + 26.0
            g1 = QPointF(pa.x() + ux * debut, pa.y() + uy * debut)
            g2 = QPointF(pa.x() + ux * fin, pa.y() + uy * fin)
            cote = 1.0 if ny >= 0 else -1.0  # côté « bas » de l'écran : la matière de A
            p.setPen(_plume(couleur_a, 2.0))
            p.drawLine(g1, g2)
            if liaison.solide_a == ID_BATI:
                hachures(p, g1, g2, cote, trait, 7.0, 6.0)
            # sphère tangente au plan, du côté opposé à la matière
            r = 5.5
            centre = QPointF(pb.x() - nx * cote * r, pb.y() - ny * cote * r)
            p.setPen(_plume(contour, 2.0))
            p.setBrush(fond)
            p.drawEllipse(centre, r, r)

        moteur = m.moteur_de_liaison(liaison.id)
        if moteur is not None:
            couleur = theme.couleur("moteur") if moteur.actif else theme.couleur("texte_inactif")
            if self._selectionne("moteur", moteur.id):
                couleur = accent
            if liaison.PILOTAGE == "rotation":
                arc_fleche(p, pb, 13.5, 1.0, couleur, 2.0)
                self._texte(p, QPointF(pb.x() + 15.0, pb.y() + 18.0), "M", couleur, 9.0, True)
            else:
                decalage = QPointF(nx * 17.0, ny * 17.0)
                a = QPointF(pb.x() - ux * 16.0, pb.y() - uy * 16.0) - decalage
                b = QPointF(pb.x() + ux * 16.0, pb.y() + uy * 16.0) - decalage
                fleche(p, a, b, couleur, 2.0, 8.0)
                milieu = QPointF((a.x() + b.x()) / 2.0 - nx * 11.0 - 4.0, (a.y() + b.y()) / 2.0 - ny * 11.0 + 4.0)
                self._texte(p, milieu, "M", couleur, 9.0, True)

        if m.affichage.get("noms_liaisons", False) or choisi:
            self._texte(p, QPointF(pb.x() + 12.0, pb.y() + 30.0), liaison.nom, theme.couleur("texte_secondaire"), 9.0)

    def position_contact(self, liaison: Liaison) -> Optional[Tuple[float, float]]:
        """Point de contact d'un engrenage ou d'une came dans la configuration affichée."""
        doc = self.doc
        try:
            return doc.mecanisme.contact(liaison, doc.position, lambda sid: doc.pose(sid)[2]).point
        except (KeyError, ValueError):
            return None

    def _contact(self, p: QPainter, ecran: Ecran, echelle: float, liaison: Liaison) -> None:
        """Symbole d'un engrenage (point primitif) ou d'une came (poussoir et point de contact)."""
        doc = self.doc
        m = doc.mecanisme
        try:
            contact = m.contact(liaison, doc.position, lambda sid: doc.pose(sid)[2])
        except (KeyError, ValueError):
            return
        choisi = self._selectionne("liaison", liaison.id)
        survole = self._survole("liaison", liaison.id)
        accent = theme.couleur("accent")
        trait = theme.couleur("trait")
        fond = theme.couleur("canevas")
        k = ecran(*contact.point)
        if choisi or survole:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 110 if choisi else 55))
            p.drawEllipse(k, 14.0, 14.0)
        if isinstance(liaison, Came):
            poussoir = m.solides[liaison.solide_b]
            couleur = QColor(poussoir.couleur) if not poussoir.bati else trait
            centre_p = ecran(*doc.position(liaison.solide_b, liaison.point_b))
            if liaison.nature == "galet":
                rayon = max(4.0, liaison.rayon_galet * echelle)
                p.setPen(_plume(couleur, 2.0))
                p.setBrush(fond)
                p.drawEllipse(centre_p, rayon, rayon)
                p.setBrush(couleur)
                p.setPen(Qt.NoPen)
                p.drawEllipse(centre_p, 2.2, 2.2)
            elif liaison.nature == "plat":
                ux, uy = contact.glissement
                cercle = m.solide(liaison.solide_a).cercle(liaison.cercle)
                demi = max(26.0, 1.15 * cercle.rayon * echelle)
                pied = QPointF(centre_p.x() + (k.x() - centre_p.x()), centre_p.y() + (k.y() - centre_p.y()))
                a = QPointF(pied.x() - ux * demi, pied.y() + uy * demi)
                b = QPointF(pied.x() + ux * demi, pied.y() - uy * demi)
                p.setPen(_plume(couleur, 3.2))
                p.drawLine(a, b)
            else:
                ex, ey = contact.normale
                base = QPointF(centre_p.x() + ex * 11.0, centre_p.y() - ey * 11.0)
                nx, ny = -ey, ex
                p.setPen(_plume(couleur, 1.8))
                p.setBrush(fond)
                p.drawPolygon(QPolygonF([centre_p, QPointF(base.x() + nx * 5.0, base.y() - ny * 5.0), QPointF(base.x() - nx * 5.0, base.y() + ny * 5.0)]))
        # point de contact (point primitif d'un engrenage)
        p.setPen(_plume(accent if choisi else trait, 1.6))
        p.setBrush(fond)
        p.drawEllipse(k, 3.6, 3.6)
        if m.affichage.get("noms_liaisons", False) or choisi:
            self._texte(p, QPointF(k.x() + 12.0, k.y() + 26.0), liaison.nom, theme.couleur("texte_secondaire"), 9.0)

    # ----------------------------------------------------------------- actions
    def echelle_forces(self) -> float:
        """Pixels par newton : la plus grande force du modèle mesure 80 px."""
        maximum = 0.0
        t = self.doc.temps
        for action in self.doc.mecanisme.actions.values():
            if isinstance(action, Force) and action.actif:
                try:
                    maximum = max(maximum, math.hypot(evaluer(action.fx, t), evaluer(action.fy, t)))
                except ErreurExpression:
                    continue
        return 80.0 / maximum if maximum > 0.0 else 1.0

    def extremite_force(self, ecran: Ecran, action: Force) -> Optional[Tuple[QPointF, QPointF, float]]:
        """(origine, extrémité, norme) de la flèche d'une force, ou ``None`` si elle est indéfinie."""
        doc = self.doc
        m = doc.mecanisme
        if action.solide not in m.solides or action.point not in m.solides[action.solide].points:
            return None
        try:
            fx, fy = evaluer(action.fx, doc.temps), evaluer(action.fy, doc.temps)
        except ErreurExpression:
            return None
        if action.repere == "local":
            angle = doc.pose(action.solide)[2]
            c, s = math.cos(angle), math.sin(angle)
            fx, fy = c * fx - s * fy, s * fx + c * fy
        norme = math.hypot(fx, fy)
        origine = ecran(*doc.position(action.solide, action.point))
        if norme <= 0.0:
            return origine, origine, 0.0
        longueur = max(26.0, norme * self.echelle_forces())
        return origine, QPointF(origine.x() + fx / norme * longueur, origine.y() - fy / norme * longueur), norme

    def centre_couple(self, ecran: Ecran, action: Couple) -> Optional[QPointF]:
        doc = self.doc
        solide = doc.mecanisme.solides.get(action.solide)
        if solide is None:
            return None
        if solide.points:
            xs = [p.x for p in solide.points.values()]
            ys = [p.y for p in solide.points.values()]
            return ecran(*doc.vers_global(solide.id, sum(xs) / len(xs), sum(ys) / len(ys)))
        return ecran(*doc.vers_global(solide.id, 0.0, 0.0))

    def _actions(self, p: QPainter, ecran: Ecran) -> None:
        doc = self.doc
        unites = doc.mecanisme.unites
        accent = theme.couleur("accent")
        for action in doc.mecanisme.actions.values():
            choisi = self._selectionne("action", action.id)
            inactif = theme.couleur("texte_inactif")
            if isinstance(action, Force):
                geometrie = self.extremite_force(ecran, action)
                if geometrie is None:
                    continue
                a, b, norme = geometrie
                couleur = accent if choisi else (theme.couleur("force") if action.actif else inactif)
                if norme > 0.0:
                    fleche(p, a, b, couleur, 2.4 if choisi else 2.0, 10.0)
                texte = f"{action.nom} = {unites.formater(norme, 'force', 4)}"
                # étiquette au milieu de la flèche, décalée du côté « haut » de l'écran
                dx, dy = b.x() - a.x(), b.y() - a.y()
                longueur = math.hypot(dx, dy) or 1.0
                nx, ny = -dy / longueur, dx / longueur
                if ny > 0:
                    nx, ny = -nx, -ny
                milieu = QPointF((a.x() + b.x()) / 2.0 + nx * 12.0 - 20.0, (a.y() + b.y()) / 2.0 + ny * 12.0)
                self._texte(p, milieu, texte, couleur, 9.5)
            elif isinstance(action, Couple):
                centre = self.centre_couple(ecran, action)
                if centre is None:
                    continue
                try:
                    valeur = evaluer(action.mz, doc.temps)
                except ErreurExpression:
                    continue
                couleur = accent if choisi else (theme.couleur("couple") if action.actif else inactif)
                arc_fleche(p, centre, 15.0, 1.0 if valeur >= 0 else -1.0, couleur, 2.4 if choisi else 2.0)
                texte = f"{action.nom} = {unites.formater(valeur, 'moment', 4)}"
                self._texte(p, QPointF(centre.x() + 19.0, centre.y() - 12.0), texte, couleur, 9.5)

    def _ressort(self, p: QPainter, ecran: Ecran, action: Ressort) -> None:
        doc = self.doc
        try:
            a = ecran(*doc.position(action.solide_a, action.point_a))
            b = ecran(*doc.position(action.solide_b, action.point_b))
        except KeyError:
            return
        choisi = self._selectionne("action", action.id)
        couleur = theme.couleur("accent") if choisi else (theme.couleur("ressort") if action.actif else theme.couleur("texte_inactif"))
        zigzag(p, a, b, couleur)

    # --------------------------------------------------------------- résultats
    def _polyligne(self, p: QPainter, ecran: Ecran, xs, ys, couleur: QColor) -> None:
        pas = max(1, len(xs) // 4000)
        points = QPolygonF([ecran(float(xs[i]), float(ys[i])) for i in range(0, len(xs), pas)])
        p.setPen(_plume(couleur, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(points)

    def _trajectoire(self, p: QPainter, ecran: Ecran, solide_id: str, point_id: str) -> None:
        resultats = self.doc.resultats
        base = f"point/{solide_id}/{point_id}/"
        if resultats is None or base + "x" not in resultats.canaux:
            return
        self._polyligne(p, ecran, resultats.valeurs(base + "x"), resultats.valeurs(base + "y"), theme.couleur("trajectoire"))

    def _trajectoires(self, p: QPainter, ecran: Ecran) -> None:
        for solide in self.doc.mecanisme.solides_mobiles():
            for point_id in solide.points:
                self._trajectoire(p, ecran, solide.id, point_id)

    def _maximum(self, suffixe: str, prefixe: str) -> float:
        resultats = self.doc.resultats
        maximum = 0.0
        for cle, canal in resultats.canaux.items():
            if cle.startswith(prefixe) and cle.endswith(suffixe) and canal.valeurs.size:
                maximum = max(maximum, float(abs(canal.valeurs).max()))
        return maximum

    def _reactions(self, p: QPainter, ecran: Ecran) -> None:
        doc = self.doc
        resultats = doc.resultats
        maximum = self._maximum("/R", "liaison/")
        if maximum <= 0.0:
            return
        couleur = theme.couleur("reaction")
        unites = doc.mecanisme.unites
        for liaison in doc.mecanisme.liaisons.values():
            torseur = resultats.torseur_liaison(liaison.id, doc.indice)
            if torseur is None:
                continue
            norme = torseur.norme_resultante
            if norme <= 1e-9 * maximum:
                continue
            origine = ecran(torseur.point[0], torseur.point[1])
            longueur = 14.0 + 66.0 * norme / maximum
            bout = QPointF(origine.x() + torseur.rx / norme * longueur, origine.y() - torseur.ry / norme * longueur)
            fleche(p, origine, bout, couleur, 2.0, 9.0)
            if self._selectionne("liaison", liaison.id):
                self._texte(p, QPointF(bout.x() + 6.0, bout.y() - 4.0), unites.formater(norme, "force", 4), couleur, 9.5)

    def _vitesses(self, p: QPainter, ecran: Ecran) -> None:
        doc = self.doc
        resultats = doc.resultats
        maximum = self._maximum("/v", "point/")
        if maximum <= 0.0:
            return
        couleur = theme.couleur("vitesse")
        for solide in doc.mecanisme.solides_mobiles():
            for point_id in solide.points:
                base = f"point/{solide.id}/{point_id}/"
                if base + "vx" not in resultats.canaux:
                    continue
                vx, vy = resultats.valeur(base + "vx", doc.indice), resultats.valeur(base + "vy", doc.indice)
                norme = math.hypot(vx, vy)
                if norme <= 1e-9 * maximum:
                    continue
                origine = ecran(resultats.valeur(base + "x", doc.indice), resultats.valeur(base + "y", doc.indice))
                longueur = 10.0 + 55.0 * norme / maximum
                fleche(p, origine, QPointF(origine.x() + vx / norme * longueur, origine.y() - vy / norme * longueur), couleur, 1.6, 7.0)
