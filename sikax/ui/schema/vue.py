"""Vue du schéma cinématique : zoom, déplacement, grille, sélection et outils.

Repère du modèle : x vers la droite, y vers le haut, longueurs en mètres.
``echelle`` est le nombre de pixels par mètre ; ``ecran`` et ``monde``
convertissent dans les deux sens.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from ...i18n import tr
from ...modele import Couple, Force, Ressort
from ..document import Document, Ref
from ..theme import theme
from .outils import OUTILS, Outil
from .rendu import Rendu, fleche

ECHELLE_MIN = 5.0
ECHELLE_MAX = 5.0e6
RAYON_CAPTURE = 10.0  # pixels


def _distance_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    longueur2 = dx * dx + dy * dy
    if longueur2 <= 1e-12:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / longueur2))
    return math.hypot(p.x() - (a.x() + t * dx), p.y() - (a.y() + t * dy))


class VueSchema(QWidget):
    coordonnees = Signal(float, float)
    """Position du pointeur dans le repère du modèle."""
    aide = Signal(str)
    """Indication à afficher dans la barre d'état."""
    outil_change = Signal(str)
    menu_demande = Signal(object, QPoint)
    """Clic droit sur un objet (référence ou ``None``) à la position globale donnée."""

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self.rendu = Rendu(document)
        self.cx = 0.0
        self.cy = 0.0
        self.echelle = 2500.0
        self.pivots_automatiques = True
        self._panoramique: Optional[QPointF] = None
        self._clic_droit: Optional[QPointF] = None
        self._espace = False
        self._pointeur = QPointF()
        self._a_ajuster = True
        self.outils: Dict[str, Outil] = {nom: classe(self) for nom, classe in OUTILS.items()}
        self.outil: Outil = self.outils["selection"]

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.setCursor(self.outil.curseur)

        document.modele_change.connect(self.update)
        document.selection_change.connect(self.update)
        document.resultats_change.connect(self.update)
        document.temps_change.connect(self.update)
        theme.change.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(900, 600)

    # ----------------------------------------------------------- conversions
    def ecran(self, x: float, y: float) -> QPointF:
        return QPointF(self.width() / 2.0 + (x - self.cx) * self.echelle, self.height() / 2.0 - (y - self.cy) * self.echelle)

    def monde(self, position: QPointF) -> Tuple[float, float]:
        return (
            self.cx + (position.x() - self.width() / 2.0) / self.echelle,
            self.cy - (position.y() - self.height() / 2.0) / self.echelle,
        )

    def pixels(self, nombre: float) -> float:
        """Longueur, dans le modèle, d'un nombre de pixels à l'écran."""
        return nombre / self.echelle

    # ------------------------------------------------------------------ cadrage
    def ajuster(self) -> None:
        """Cadre la vue sur l'ensemble du mécanisme."""
        boite = self._boite()
        if boite is None:
            self.cx, self.cy, self.echelle = 0.0, 0.0, 2500.0
        else:
            xmin, ymin, xmax, ymax = boite
            largeur, hauteur = max(xmax - xmin, 1e-9), max(ymax - ymin, 1e-9)
            marge = 90.0
            libre_x = max(self.width() - 2 * marge, 50.0)
            libre_y = max(self.height() - 2 * marge, 50.0)
            echelle = min(libre_x / largeur, libre_y / hauteur)
            if xmax - xmin < 1e-9 and ymax - ymin < 1e-9:
                echelle = 2500.0
            self.echelle = max(ECHELLE_MIN, min(ECHELLE_MAX, echelle))
            self.cx, self.cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
        self._a_ajuster = False
        self.update()

    def demander_ajustement(self) -> None:
        """Recadrera au prochain affichage (quand la taille du composant est connue)."""
        self._a_ajuster = True
        self.update()

    def _boite(self) -> Optional[Tuple[float, float, float, float]]:
        doc = self.doc
        xs: List[float] = []
        ys: List[float] = []
        for solide in doc.mecanisme.solides.values():
            for point_id in solide.points:
                x, y = doc.position(solide.id, point_id)
                xs.append(x)
                ys.append(y)
        resultats = doc.resultats
        if resultats is not None:
            for cle, canal in resultats.canaux.items():
                if cle.startswith("point/") and canal.valeurs.size:
                    if cle.endswith("/x"):
                        xs += [float(canal.valeurs.min()), float(canal.valeurs.max())]
                    elif cle.endswith("/y"):
                        ys += [float(canal.valeurs.min()), float(canal.valeurs.max())]
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def zoomer(self, facteur: float, autour: Optional[QPointF] = None) -> None:
        autour = autour if autour is not None else QPointF(self.width() / 2.0, self.height() / 2.0)
        avant = self.monde(autour)
        self.echelle = max(ECHELLE_MIN, min(ECHELLE_MAX, self.echelle * facteur))
        apres = self.monde(autour)
        self.cx += avant[0] - apres[0]
        self.cy += avant[1] - apres[1]
        self.update()

    # ------------------------------------------------------------- aimantation
    def pas_grille(self) -> float:
        """Pas de la grille affichée : le pas du projet, élargi tant qu'il serait trop serré."""
        base = float(self.doc.mecanisme.affichage.get("pas_grille", 0.01)) or 0.01
        pas = base
        facteurs = (2.0, 2.5, 2.0)
        i = 0
        while pas * self.echelle < 11.0 and i < 60:
            pas *= facteurs[i % 3]
            i += 1
        return pas

    def points_proches(self, x: float, y: float, rayon_px: float = RAYON_CAPTURE, exclure=()) -> List[Tuple[str, str, float, float]]:
        """Points du modèle proches de (x, y) : (solide, point, x, y), du plus proche au plus lointain."""
        doc = self.doc
        rayon = self.pixels(rayon_px)
        trouves = []
        for solide in doc.mecanisme.solides.values():
            for point_id in solide.points:
                if (solide.id, point_id) in exclure:
                    continue
                px, py = doc.position(solide.id, point_id)
                d = math.hypot(px - x, py - y)
                if d <= rayon:
                    trouves.append((d, solide.id, point_id, px, py))
        trouves.sort()
        return [(s, p, px, py) for _, s, p, px, py in trouves]

    def aimanter(self, x: float, y: float, exclure=(), grille: bool = True) -> Tuple[float, float]:
        """Position accrochée : sur un point existant, sinon sur la grille si elle est active."""
        proches = self.points_proches(x, y, RAYON_CAPTURE, exclure)
        if proches:
            return proches[0][2], proches[0][3]
        if grille and self.doc.mecanisme.affichage.get("aimantation", True):
            pas = self.pas_grille()
            return round(x / pas) * pas, round(y / pas) * pas
        return x, y

    # ---------------------------------------------------------------- sélection
    def objets_sous(self, position: QPointF) -> List[Ref]:
        """Objets situés sous le pointeur : liaisons, actions, points puis solides."""
        doc = self.doc
        m = doc.mecanisme
        liaisons: List[Tuple[float, Ref]] = []
        actions: List[Tuple[float, Ref]] = []
        points: List[Tuple[float, Ref]] = []
        solides: List[Tuple[float, Ref]] = []

        def ecart(q: QPointF) -> float:
            return math.hypot(q.x() - position.x(), q.y() - position.y())

        for liaison in m.liaisons.values():
            try:
                d = ecart(self.ecran(*doc.position(liaison.solide_b, liaison.point_b)))
            except KeyError:
                continue
            if d <= 11.0:
                liaisons.append((d, Ref("liaison", liaison.id)))
        for action in m.actions.values():
            if isinstance(action, Force):
                geometrie = self.rendu.extremite_force(self.ecran, action)
                if geometrie is not None:
                    a, b, _ = geometrie
                    d = _distance_segment(position, a, b)
                    # près de l'origine, le point d'application garde la priorité
                    if d <= 6.0 and ecart(a) > 9.0:
                        actions.append((d, Ref("action", action.id)))
            elif isinstance(action, Couple):
                centre = self.rendu.centre_couple(self.ecran, action)
                if centre is not None and abs(ecart(centre) - 15.0) <= 6.0:
                    actions.append((abs(ecart(centre) - 15.0), Ref("action", action.id)))
            elif isinstance(action, Ressort):
                try:
                    a = self.ecran(*doc.position(action.solide_a, action.point_a))
                    b = self.ecran(*doc.position(action.solide_b, action.point_b))
                except KeyError:
                    continue
                d = _distance_segment(position, a, b)
                if d <= 8.0 and ecart(a) > 9.0 and ecart(b) > 9.0:
                    actions.append((d, Ref("action", action.id)))
        for solide in m.solides.values():
            for point_id in solide.points:
                d = ecart(self.ecran(*doc.position(solide.id, point_id)))
                if d <= 9.0:
                    points.append((d, Ref("point", solide.id, point_id)))
            for a, b in solide.segments:
                d = _distance_segment(position, self.ecran(*doc.position(solide.id, a)), self.ecran(*doc.position(solide.id, b)))
                if d <= 6.0:
                    solides.append((d, Ref("solide", solide.id)))
                    break
        resultat: List[Ref] = []
        for groupe in (liaisons, actions, points, solides):
            groupe.sort(key=lambda element: element[0])
            for _, ref in groupe:
                if ref not in resultat:
                    resultat.append(ref)
        return resultat

    # ------------------------------------------------------------------ outils
    def choisir_outil(self, nom: str) -> None:
        if nom not in self.outils:
            nom = "selection"
        if self.outil is not self.outils[nom]:
            self.outil.desactiver()
            self.outil = self.outils[nom]
            self.outil.activer()
        self.rendu.survol = None
        self.setCursor(self.outil.curseur)
        self.aide.emit(tr(self.outil.cle_aide))
        self.outil_change.emit(nom)
        self.update()

    def signaler(self, cle: str, /, **parametres) -> None:
        """Affiche un message d'outil dans la barre d'état."""
        self.aide.emit(tr(cle, **parametres))

    # --------------------------------------------------------------- événements
    def _position(self, evenement: QMouseEvent) -> QPointF:
        return evenement.position()

    def mousePressEvent(self, evenement: QMouseEvent) -> None:
        self.setFocus()
        position = self._position(evenement)
        bouton = evenement.button()
        if bouton == Qt.MiddleButton or (bouton == Qt.LeftButton and self._espace):
            self._panoramique = position
            self.setCursor(Qt.ClosedHandCursor)
            return
        if bouton == Qt.RightButton:
            self._clic_droit = position
            self._panoramique = position
            return
        if bouton == Qt.LeftButton:
            x, y = self.monde(position)
            self.outil.presse(evenement, x, y)
            self.update()

    def mouseMoveEvent(self, evenement: QMouseEvent) -> None:
        position = self._position(evenement)
        self._pointeur = position
        x, y = self.monde(position)
        self.coordonnees.emit(x, y)
        if self._panoramique is not None:
            if self._clic_droit is not None:
                if math.hypot(position.x() - self._clic_droit.x(), position.y() - self._clic_droit.y()) < 5.0:
                    return
                self._clic_droit = None  # c'est un glisser : déplacement de la vue
                self.setCursor(Qt.ClosedHandCursor)
            self.cx -= (position.x() - self._panoramique.x()) / self.echelle
            self.cy += (position.y() - self._panoramique.y()) / self.echelle
            self._panoramique = position
            self.update()
            return
        self.outil.deplace(evenement, x, y)
        self.update()

    def mouseReleaseEvent(self, evenement: QMouseEvent) -> None:
        position = self._position(evenement)
        bouton = evenement.button()
        if bouton == Qt.RightButton:
            clic = self._clic_droit is not None
            self._clic_droit = None
            self._panoramique = None
            self.setCursor(self.outil.curseur)
            if clic and not self.outil.clic_droit(evenement, *self.monde(position)):
                cibles = self.objets_sous(position)
                self.menu_demande.emit(cibles[0] if cibles else None, evenement.globalPosition().toPoint())
            self.update()
            return
        if self._panoramique is not None and bouton in (Qt.MiddleButton, Qt.LeftButton):
            self._panoramique = None
            self.setCursor(Qt.OpenHandCursor if self._espace else self.outil.curseur)
            return
        if bouton == Qt.LeftButton:
            x, y = self.monde(position)
            self.outil.relache(evenement, x, y)
            self.update()

    def mouseDoubleClickEvent(self, evenement: QMouseEvent) -> None:
        if evenement.button() == Qt.MiddleButton:
            self.ajuster()
        elif evenement.button() == Qt.LeftButton:
            x, y = self.monde(self._position(evenement))
            self.outil.double_clic(evenement, x, y)
            self.update()

    def wheelEvent(self, evenement: QWheelEvent) -> None:
        delta = evenement.angleDelta().y()
        if delta:
            self.zoomer(1.0015 ** delta, evenement.position())

    def keyPressEvent(self, evenement: QKeyEvent) -> None:
        touche = evenement.key()
        if touche == Qt.Key_Space and not evenement.isAutoRepeat():
            self._espace = True
            self.setCursor(Qt.OpenHandCursor)
            return
        if self.outil.touche(evenement):
            self.update()
            return
        if touche == Qt.Key_Escape:
            if not self.outil.annuler():
                if self.outil.nom != "selection":
                    self.choisir_outil("selection")
                else:
                    self.doc.selectionner(None)
            self.update()
        elif touche in (Qt.Key_Delete, Qt.Key_Backspace):
            self.doc.supprimer(self.doc.selection)
        elif touche in (Qt.Key_Return, Qt.Key_Enter):
            self.outil.valider()
            self.update()
        else:
            super().keyPressEvent(evenement)

    def keyReleaseEvent(self, evenement: QKeyEvent) -> None:
        if evenement.key() == Qt.Key_Space and not evenement.isAutoRepeat():
            self._espace = False
            if self._panoramique is None:
                self.setCursor(self.outil.curseur)
            return
        super().keyReleaseEvent(evenement)

    def leaveEvent(self, evenement) -> None:
        if self.rendu.survol is not None:
            self.rendu.survol = None
            self.update()

    # ------------------------------------------------------------------- dessin
    def paintEvent(self, evenement) -> None:
        if self._a_ajuster and self.width() > 50:
            self.ajuster()
        p = QPainter(self)
        self.peindre(p)
        p.end()

    def peindre(self, p: QPainter, decor: bool = True) -> None:
        p.fillRect(self.rect(), theme.couleur("canevas"))
        if decor and self.doc.mecanisme.affichage.get("grille", True):
            self._grille(p)
        if decor:
            self._axes(p)
        self.rendu.dessiner(p, self.ecran, self.echelle)
        self.outil.dessiner(p)
        if decor:
            self._habillage(p)
            if self.doc.mecanisme.est_vide() and self.outil.nom == "selection":
                self._accueil(p)

    def _grille(self, p: QPainter) -> None:
        pas = self.pas_grille()
        x0, y1 = self.monde(QPointF(0.0, 0.0))
        x1, y0 = self.monde(QPointF(float(self.width()), float(self.height())))
        fine = QPen(theme.couleur("grille"), 1.0)
        forte = QPen(theme.couleur("grille_forte"), 1.0)
        p.setRenderHint(QPainter.Antialiasing, False)
        premier = math.floor(x0 / pas)
        for i in range(int(premier), int(math.ceil(x1 / pas)) + 1):
            x = self.ecran(i * pas, 0.0).x()
            p.setPen(forte if i % 5 == 0 else fine)
            p.drawLine(QPointF(x, 0.0), QPointF(x, float(self.height())))
        premier = math.floor(y0 / pas)
        for j in range(int(premier), int(math.ceil(y1 / pas)) + 1):
            y = self.ecran(0.0, j * pas).y()
            p.setPen(forte if j % 5 == 0 else fine)
            p.drawLine(QPointF(0.0, y), QPointF(float(self.width()), y))
        p.setRenderHint(QPainter.Antialiasing, True)

    def _axes(self, p: QPainter) -> None:
        origine = self.ecran(0.0, 0.0)
        couleur = theme.couleur("axes")
        fleche(p, origine, QPointF(origine.x() + 34.0, origine.y()), couleur, 1.6, 7.0)
        fleche(p, origine, QPointF(origine.x(), origine.y() - 34.0), couleur, 1.6, 7.0)
        p.setPen(couleur)
        police = p.font()
        police.setPointSizeF(9.0)
        police.setBold(False)
        p.setFont(police)
        p.drawText(QPointF(origine.x() + 38.0, origine.y() + 4.0), "x")
        p.drawText(QPointF(origine.x() - 3.0, origine.y() - 39.0), "y")

    def _accueil(self, p: QPainter) -> None:
        """Sur une page blanche, indique par où commencer."""
        police = p.font()
        police.setPointSizeF(15.0)
        police.setBold(True)
        p.setFont(police)
        p.setPen(theme.couleur("texte_secondaire"))
        centre_y = self.height() / 2.0 + 70.0
        p.drawText(QRectF(0.0, centre_y, float(self.width()), 30.0), Qt.AlignHCenter | Qt.AlignVCenter, tr("accueil.titre"))
        police.setPointSizeF(11.0)
        police.setBold(False)
        p.setFont(police)
        p.setPen(theme.couleur("texte_inactif") if theme.sombre else theme.couleur("texte_secondaire"))
        p.drawText(
            QRectF(40.0, centre_y + 34.0, float(self.width()) - 80.0, 80.0),
            Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
            tr("accueil.texte"),
        )

    def _habillage(self, p: QPainter) -> None:
        """Échelle graphique, pesanteur et instant affiché."""
        unites = self.doc.mecanisme.unites
        secondaire = theme.couleur("texte_secondaire")
        police = p.font()
        police.setPointSizeF(9.5)
        police.setBold(False)
        p.setFont(police)

        # échelle : une longueur « ronde » d'environ 110 pixels
        cible = 110.0 / self.echelle
        puissance = 10.0 ** math.floor(math.log10(cible)) if cible > 0 else 1.0
        longueur = next((k * puissance for k in (5.0, 2.0, 1.0) if k * puissance <= cible), puissance)
        largeur = longueur * self.echelle
        x0, y0 = 18.0, self.height() - 20.0
        p.setPen(QPen(secondaire, 1.4))
        p.drawLine(QPointF(x0, y0), QPointF(x0 + largeur, y0))
        p.drawLine(QPointF(x0, y0 - 4.0), QPointF(x0, y0 + 4.0))
        p.drawLine(QPointF(x0 + largeur, y0 - 4.0), QPointF(x0 + largeur, y0 + 4.0))
        p.drawText(QPointF(x0 + largeur + 8.0, y0 + 4.0), unites.formater(longueur, "longueur", 4))

        etude = self.doc.mecanisme.etude
        if etude.pesanteur and (etude.gx or etude.gy):
            norme = math.hypot(etude.gx, etude.gy)
            a = QPointF(self.width() - 34.0, 22.0)
            b = QPointF(a.x() + etude.gx / norme * 30.0, a.y() - etude.gy / norme * 30.0)
            couleur = theme.couleur("gravite")
            fleche(p, a, b, couleur, 1.8, 8.0)
            p.setPen(couleur)
            p.drawText(QPointF(a.x() - 16.0, a.y() + 14.0), "g")

        if self.doc.resultats is not None and self.doc.resultats.nb_instants > 1:
            p.setPen(secondaire)
            p.drawText(QPointF(18.0, 26.0), f"t = {self.doc.temps:.3f} s")

    # ------------------------------------------------------------------- export
    def image(self, facteur: float = 2.0, decor: bool = True) -> QImage:
        """Image du schéma à la résolution demandée (``facteur`` × la taille à l'écran)."""
        image = QImage(int(self.width() * facteur), int(self.height() * facteur), QImage.Format_ARGB32)
        image.fill(theme.couleur("canevas"))
        p = QPainter(image)
        p.scale(facteur, facteur)
        outil, survol = self.outil, self.rendu.survol
        self.outil, self.rendu.survol = self.outils["selection"], None
        try:
            self.peindre(p, decor)
        finally:
            self.outil, self.rendu.survol = outil, survol
            p.end()
        return image
