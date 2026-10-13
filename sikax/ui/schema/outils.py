"""Outils de la vue : chacun interprète la souris à sa manière.

La vue transmet les événements à l'outil actif avec la position du pointeur
dans le repère du modèle. Un outil ne modifie le modèle qu'à travers
``document.modification()`` : toutes ses actions sont donc annulables.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Type

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QPainter, QPen
from PySide6.QtWidgets import QMenu

from ...calcul import SystemeMecanique, glisser, refermer, residu_de_fermeture
from ...modele.liaisons import Encastrement, Pivot, classe_liaison
from ...modele.solide import ID_BATI
from ..document import Ref
from ..theme import theme
from .rendu import fleche

if TYPE_CHECKING:
    from .vue import VueSchema

SEUIL_GLISSER = 4.0  # pixels avant qu'un clic devienne un glisser
PAS_ANGULAIRE = math.radians(15.0)


class Outil:
    nom = ""
    curseur = Qt.ArrowCursor

    def __init__(self, vue: "VueSchema") -> None:
        self.vue = vue
        self.doc = vue.doc

    @property
    def cle_aide(self) -> str:
        return f"outil.{self.nom}.aide"

    def activer(self) -> None:
        pass

    def desactiver(self) -> None:
        self.annuler()

    def presse(self, evenement, x: float, y: float) -> None:
        pass

    def deplace(self, evenement, x: float, y: float) -> None:
        pass

    def relache(self, evenement, x: float, y: float) -> None:
        pass

    def double_clic(self, evenement, x: float, y: float) -> None:
        pass

    def clic_droit(self, evenement, x: float, y: float) -> bool:
        """Retourne vrai si l'outil a traité le clic droit (sinon : menu contextuel)."""
        return False

    def touche(self, evenement) -> bool:
        return False

    def valider(self) -> None:
        pass

    def annuler(self) -> bool:
        """Abandonne l'opération en cours. Retourne faux s'il n'y avait rien à abandonner."""
        return False

    def dessiner(self, p: QPainter) -> None:
        pass

    # -- aides communes ----------------------------------------------------------
    def _survoler(self, evenement) -> None:
        cibles = self.vue.objets_sous(evenement.position())
        self.vue.rendu.survol = cibles[0] if cibles else None

    def _apercu(self, p: QPainter, largeur: float = 2.0, pointille: bool = False) -> None:
        plume = QPen(theme.couleur("accent"), largeur, Qt.DashLine if pointille else Qt.SolidLine)
        plume.setCapStyle(Qt.RoundCap)
        p.setPen(plume)
        p.setBrush(Qt.NoBrush)


# --------------------------------------------------------------------- sélection

class OutilSelection(Outil):
    """Sélectionne les objets ; glisser un point ou une liaison modifie la géométrie."""

    nom = "selection"

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self._depart: Optional[QPointF] = None
        self._cibles: List[Ref] = []
        self._deja_choisi = False
        self._groupe: Set[Tuple[str, str]] = set()
        self._glisse = False

    def presse(self, evenement, x, y):
        self._depart = evenement.position()
        self._cibles = self.vue.objets_sous(self._depart)
        self._glisse = False
        self._groupe = set()
        self._deja_choisi = self.doc.selection in self._cibles
        if not self._cibles:
            self.doc.selectionner(None)
            return
        if not self._deja_choisi:
            self.doc.selectionner(self._cibles[0])
        self._groupe = self._points_a_deplacer(self.doc.selection)

    def _points_a_deplacer(self, ref: Optional[Ref]) -> Set[Tuple[str, str]]:
        """Points qui suivent le glisser : le point visé et ceux qui lui sont articulés."""
        m = self.doc.mecanisme
        if ref is None:
            return set()
        if ref.genre == "point":
            depart = {(ref.id, ref.sous)}
        elif ref.genre == "liaison":
            liaison = m.liaisons[ref.id]
            depart = {(liaison.solide_b, liaison.point_b)}
            pa = self.doc.position(liaison.solide_a, liaison.point_a)
            pb = self.doc.position(liaison.solide_b, liaison.point_b)
            if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= 1e-7 * m.longueur_caracteristique():
                depart.add((liaison.solide_a, liaison.point_a))
        else:
            return set()
        groupe = set(depart)
        change = True
        while change:
            change = False
            for liaison in m.liaisons.values():
                if not isinstance(liaison, (Pivot, Encastrement)):
                    continue
                a, b = (liaison.solide_a, liaison.point_a), (liaison.solide_b, liaison.point_b)
                if (a in groupe) != (b in groupe):
                    groupe |= {a, b}
                    change = True
        return groupe

    def deplace(self, evenement, x, y):
        if self._depart is None or not (evenement.buttons() & Qt.LeftButton):
            self._survoler(evenement)
            return
        position = evenement.position()
        if not self._glisse:
            if math.hypot(position.x() - self._depart.x(), position.y() - self._depart.y()) < SEUIL_GLISSER:
                return
            if not self._groupe:
                return
            self._glisse = True
        cx, cy = self.vue.aimanter(x, y, exclure=self._groupe)
        with self.doc.modification(fusion="geometrie") as m:
            for solide_id, point_id in self._groupe:
                if solide_id in m.solides and point_id in m.solides[solide_id].points:
                    m.solides[solide_id].placer_point_global(point_id, cx, cy)

    def relache(self, evenement, x, y):
        if self._glisse:
            self.doc.terminer_fusion()
            # une géométrie modifiée peut ouvrir des liaisons : on referme le mécanisme
            m = self.doc.mecanisme
            if residu_de_fermeture(m) > 1e-9 * m.longueur_caracteristique():
                with self.doc.modification(fusion="geometrie"):
                    if not refermer(m):
                        self.vue.signaler("outil.message.fermeture_impossible")
                self.doc.terminer_fusion()
        elif self._cibles and self._deja_choisi and len(self._cibles) > 1:
            # second clic au même endroit : objet suivant sous le pointeur
            suivant = (self._cibles.index(self.doc.selection) + 1) % len(self._cibles)
            self.doc.selectionner(self._cibles[suivant])
        self._depart = None
        self._glisse = False
        self._groupe = set()

    def annuler(self) -> bool:
        actif = self._depart is not None
        self._depart = None
        self._glisse = False
        return actif


class OutilManipuler(Outil):
    """Déplace le mécanisme en respectant ses liaisons : règle la configuration initiale."""

    nom = "manipuler"
    curseur = Qt.OpenHandCursor

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self._systeme: Optional[SystemeMecanique] = None
        self._attache = None
        self._q = None

    def presse(self, evenement, x, y):
        self._systeme = None
        m = self.doc.mecanisme
        for ref in self.vue.objets_sous(evenement.position()):
            if ref.genre == "liaison":
                liaison = m.liaisons[ref.id]
                solide_id = liaison.solide_b if liaison.solide_b != ID_BATI else liaison.solide_a
            elif ref.genre in ("point", "solide"):
                solide_id = ref.id
            else:
                continue
            if solide_id == ID_BATI:
                continue
            if self.doc.resultats is not None:
                # on manipule le modèle, pas l'animation : retour à la configuration initiale
                self.doc.definir_resultats(None)
            systeme = SystemeMecanique(m, avec_moteurs=False)
            local = m.solides[solide_id].pose.vers_local(x, y)
            self._systeme = systeme
            self._attache = systeme.attache_locale(solide_id, *local)
            self._q = systeme.q0
            self.doc.selectionner(Ref("solide", solide_id))
            self.vue.setCursor(Qt.ClosedHandCursor)
            return
        self.vue.signaler("outil.manipuler.rien")

    def deplace(self, evenement, x, y):
        if self._systeme is None or not (evenement.buttons() & Qt.LeftButton):
            self._survoler(evenement)
            return
        self._q = glisser(self._systeme, self._q, self._attache, (x, y))
        with self.doc.modification(fusion="manipulation"):
            self._systeme.appliquer_au_modele(self._q)

    def relache(self, evenement, x, y):
        if self._systeme is not None:
            self.doc.terminer_fusion()
        self._systeme = None
        self.vue.setCursor(self.curseur)

    def annuler(self) -> bool:
        actif = self._systeme is not None
        self._systeme = None
        return actif


# ---------------------------------------------------------------------- création

class OutilBarre(Outil):
    """Dessine un solide : chaque clic ajoute un point, Entrée ou double-clic termine."""

    nom = "barre"
    curseur = Qt.CrossCursor

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self.sommets: List[Tuple[float, float]] = []
        self._pointeur: Optional[Tuple[float, float]] = None

    def presse(self, evenement, x, y):
        position = self.vue.aimanter(x, y)
        if self.sommets and math.hypot(position[0] - self.sommets[-1][0], position[1] - self.sommets[-1][1]) < self.vue.pixels(3.0):
            return
        self.sommets.append(position)
        self.vue.signaler("outil.barre.suite")

    def deplace(self, evenement, x, y):
        self._pointeur = self.vue.aimanter(x, y)

    def double_clic(self, evenement, x, y):
        self.valider()

    def clic_droit(self, evenement, x, y) -> bool:
        if self.sommets:
            self.valider()
            return True
        return False

    def valider(self) -> None:
        if len(self.sommets) < 2:
            self.sommets = []
            return
        sommets, self.sommets = self.sommets, []
        vue = self.vue
        tolerance = vue.pixels(2.0)
        with self.doc.modification() as m:
            # points déjà présents sous chaque sommet, relevés avant la création
            voisins = [[(s.id, p.id) for s, p in m.points_en(x, y, tolerance)] for x, y in sommets]
            solide = m.creer_barre(sommets)
            if vue.pivots_automatiques:
                for point_id, autres in zip(list(solide.points), voisins):
                    if not autres:
                        continue
                    autre = next((a for a in autres if a[0] == ID_BATI), autres[0])
                    m.creer_liaison("pivot", autre[0], autre[1], solide.id, point_id)
        self.doc.selectionner(Ref("solide", solide.id))
        vue.signaler(self.cle_aide)

    def annuler(self) -> bool:
        actif = bool(self.sommets)
        self.sommets = []
        return actif

    def dessiner(self, p: QPainter) -> None:
        vue = self.vue
        if self._pointeur is not None:
            c = vue.ecran(*self._pointeur)
            self._apercu(p, 1.4)
            p.drawEllipse(c, 5.0, 5.0)
        if not self.sommets:
            return
        points = [vue.ecran(*s) for s in self.sommets]
        self._apercu(p, 4.0)
        for a, b in zip(points, points[1:]):
            p.drawLine(a, b)
        if self._pointeur is not None:
            fin = vue.ecran(*self._pointeur)
            self._apercu(p, 2.0, pointille=True)
            p.drawLine(points[-1], fin)
            dx, dy = self._pointeur[0] - self.sommets[-1][0], self._pointeur[1] - self.sommets[-1][1]
            unites = self.doc.mecanisme.unites
            texte = f"{unites.formater(math.hypot(dx, dy), 'longueur', 4)}   {math.degrees(math.atan2(dy, dx)):.1f}°"
            p.setPen(theme.couleur("texte"))
            p.drawText(QPointF(fin.x() + 14.0, fin.y() + 18.0), texte)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.couleur("accent"))
        for point in points:
            p.drawEllipse(point, 4.0, 4.0)


class OutilPoint(Outil):
    """Ajoute un point au solide sélectionné (au bâti si rien n'est sélectionné)."""

    nom = "point"
    curseur = Qt.CrossCursor

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self._pointeur: Optional[Tuple[float, float]] = None

    def _cible(self) -> Tuple[str, Optional[str]]:
        """(solide qui reçoit le point, point auquel le relier)."""
        selection = self.doc.selection
        if selection is not None and selection.genre == "point":
            return selection.id, (selection.sous if selection.id != ID_BATI else None)
        if selection is not None and selection.genre == "solide":
            return selection.id, None
        return ID_BATI, None

    def presse(self, evenement, x, y):
        gx, gy = self.vue.aimanter(x, y)
        solide_id, relier = self._cible()
        with self.doc.modification() as m:
            solide = m.solides[solide_id]
            if relier is None and not solide.bati and solide.points:
                # garder le squelette d'un seul tenant : relier au point le plus proche
                relier = min(
                    solide.points,
                    key=lambda pid: math.hypot(solide.position_globale(pid)[0] - gx, solide.position_globale(pid)[1] - gy),
                )
            point = m.creer_point(solide_id, gx, gy, relier_a=relier)
        self.doc.selectionner(Ref("point", solide_id, point.id))

    def deplace(self, evenement, x, y):
        self._pointeur = self.vue.aimanter(x, y)

    def dessiner(self, p: QPainter) -> None:
        if self._pointeur is not None:
            self._apercu(p, 1.4)
            p.drawEllipse(self.vue.ecran(*self._pointeur), 5.0, 5.0)


class OutilLiaison(Outil):
    """Pose une liaison sur un point : entre les deux solides présents, ou avec le bâti."""

    curseur = Qt.CrossCursor
    type_liaison = "pivot"

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self._attente: Optional[Tuple[float, float, str, str]] = None  # x, y, solide A, solide B
        self._depart: Optional[QPointF] = None
        self._angle = 0.0
        self._pointeur: Optional[Tuple[float, float]] = None

    @property
    def nom(self) -> str:  # type: ignore[override]
        return self.type_liaison

    @property
    def cle_aide(self) -> str:
        return f"outil.liaison.aide_{'axe' if classe_liaison(self.type_liaison).A_UN_AXE else 'point'}"

    def _paire(self, x: float, y: float, position_globale) -> Optional[Tuple[float, float, str, str]]:
        vue = self.vue
        proches = vue.points_proches(x, y)
        if not proches:
            vue.signaler("outil.liaison.aucun_point")
            return None
        px, py = proches[0][2], proches[0][3]
        tolerance = vue.pixels(2.0)
        solides: List[str] = []
        for solide_id, _, qx, qy in proches:
            if solide_id not in solides and math.hypot(qx - px, qy - py) <= tolerance:
                solides.append(solide_id)
        if len(solides) == 1:
            if solides[0] == ID_BATI:
                vue.signaler("outil.liaison.bati_seul")
                return None
            return (px, py, ID_BATI, solides[0])
        if len(solides) == 2:
            a, b = solides
            if b == ID_BATI:
                a, b = b, a
            return (px, py, a, b)
        # plus de deux solides ici : l'utilisateur choisit la paire
        paires = []
        for i, a in enumerate(solides):
            for b in solides[i + 1:]:
                paires.append((b, a) if b == ID_BATI else (a, b))
        choix = self.choisir_paire(paires, position_globale)
        if choix is None:
            return None
        return (px, py, choix[0], choix[1])

    def choisir_paire(self, paires: List[Tuple[str, str]], position_globale) -> Optional[Tuple[str, str]]:
        """Demande, par un menu, quels solides relier quand plus de deux se rejoignent en un point."""
        m = self.doc.mecanisme
        menu = QMenu(self.vue)
        for a, b in paires:
            action = QAction(f"{m.solides[a].nom}  –  {m.solides[b].nom}", menu)
            action.setData((a, b))
            menu.addAction(action)
        choix = menu.exec(position_globale)
        return tuple(choix.data()) if choix is not None else None

    def presse(self, evenement, x, y):
        self._attente = self._paire(x, y, evenement.globalPosition().toPoint())
        self._depart = evenement.position()
        self._angle = 0.0
        if self._attente is not None and not classe_liaison(self.type_liaison).A_UN_AXE:
            self._creer()

    def deplace(self, evenement, x, y):
        self._pointeur = (x, y)
        if self._attente is None or self._depart is None or not (evenement.buttons() & Qt.LeftButton):
            self._survoler(evenement)
            return
        position = evenement.position()
        dx, dy = position.x() - self._depart.x(), position.y() - self._depart.y()
        if math.hypot(dx, dy) >= 12.0:
            angle = math.atan2(-dy, dx)
            if not (evenement.modifiers() & Qt.ShiftModifier):
                angle = round(angle / PAS_ANGULAIRE) * PAS_ANGULAIRE
            self._angle = angle

    def relache(self, evenement, x, y):
        if self._attente is not None:
            self._creer()

    def _creer(self) -> None:
        x, y, a, b = self._attente
        self._attente = None
        self._depart = None
        m = self.doc.mecanisme
        tolerance = self.vue.pixels(2.0)
        for existante in m.liaisons.values():
            if {existante.solide_a, existante.solide_b} == {a, b}:
                ex, ey = self.doc.position(existante.solide_b, existante.point_b)
                if math.hypot(ex - x, ey - y) <= tolerance:
                    self.vue.signaler("outil.liaison.deja_liee", nom=existante.nom)
                    self.doc.selectionner(Ref("liaison", existante.id))
                    return
        with self.doc.modification() as m:
            liaison = m.creer_liaison_en(self.type_liaison, x, y, a, b, angle_axe_global=self._angle, rayon=tolerance)
        self.doc.selectionner(Ref("liaison", liaison.id))

    def annuler(self) -> bool:
        actif = self._attente is not None
        self._attente = None
        self._depart = None
        return actif

    def dessiner(self, p: QPainter) -> None:
        if self._attente is None:
            return
        x, y = self._attente[0], self._attente[1]
        c = self.vue.ecran(x, y)
        ux, uy = math.cos(self._angle), -math.sin(self._angle)
        self._apercu(p, 2.0, pointille=True)
        p.drawLine(QPointF(c.x() - ux * 60.0, c.y() - uy * 60.0), QPointF(c.x() + ux * 60.0, c.y() + uy * 60.0))
        p.setPen(theme.couleur("texte"))
        p.drawText(QPointF(c.x() + 14.0, c.y() - 14.0), f"{math.degrees(self._angle):.0f}°")


def _outil_liaison(type_liaison: str) -> Type[OutilLiaison]:
    return type(f"OutilLiaison_{type_liaison}", (OutilLiaison,), {"type_liaison": type_liaison})


class OutilForce(Outil):
    """Applique une force à un point : cliquer le point puis tirer pour donner direction et norme."""

    nom = "force"
    curseur = Qt.CrossCursor

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self._point: Optional[Tuple[str, str, float, float]] = None
        self._depart: Optional[QPointF] = None
        self._fin: Optional[QPointF] = None

    def presse(self, evenement, x, y):
        mobiles = [c for c in self.vue.points_proches(x, y) if c[0] != ID_BATI]
        if not mobiles:
            self.vue.signaler("outil.force.aucun_point")
            self._point = None
            return
        self._point = mobiles[0]
        self._depart = evenement.position()
        self._fin = None

    def deplace(self, evenement, x, y):
        if self._point is not None and (evenement.buttons() & Qt.LeftButton):
            self._fin = evenement.position()
        else:
            self._survoler(evenement)

    @staticmethod
    def _arrondir(valeur: float) -> float:
        """Deux chiffres significatifs : 87,3 → 87 ; 143 → 140."""
        if valeur == 0.0:
            return 0.0
        ordre = 10.0 ** (math.floor(math.log10(abs(valeur))) - 1)
        return round(valeur / ordre) * ordre

    def _composantes(self) -> Tuple[float, float]:
        if self._fin is None or self._depart is None:
            return (0.0, -100.0)
        dx, dy = self._fin.x() - self._depart.x(), -(self._fin.y() - self._depart.y())
        if math.hypot(dx, dy) < 8.0:
            return (0.0, -100.0)
        return (self._arrondir(dx), self._arrondir(dy))  # 1 pixel = 1 newton

    def relache(self, evenement, x, y):
        if self._point is None:
            return
        solide_id, point_id, _, _ = self._point
        fx, fy = self._composantes()
        self._point = None
        self._fin = None
        with self.doc.modification() as m:
            force = m.creer_force(solide_id, point_id, fx, fy)
        self.doc.selectionner(Ref("action", force.id))

    def annuler(self) -> bool:
        actif = self._point is not None
        self._point = None
        self._fin = None
        return actif

    def dessiner(self, p: QPainter) -> None:
        if self._point is None or self._fin is None:
            return
        origine = self.vue.ecran(self._point[2], self._point[3])
        fleche(p, origine, self._fin, theme.couleur("force"), 2.0, 10.0)
        fx, fy = self._composantes()
        p.setPen(theme.couleur("texte"))
        p.drawText(QPointF(self._fin.x() + 12.0, self._fin.y() - 8.0), f"{math.hypot(fx, fy):.4g} N")


class OutilCouple(Outil):
    """Applique un couple au solide cliqué."""

    nom = "couple"
    curseur = Qt.CrossCursor

    def presse(self, evenement, x, y):
        for ref in self.vue.objets_sous(evenement.position()):
            if ref.genre in ("point", "solide") and ref.id != ID_BATI:
                with self.doc.modification() as m:
                    couple = m.creer_couple(ref.id, 10.0)
                self.doc.selectionner(Ref("action", couple.id))
                return
        self.vue.signaler("outil.couple.aucun_solide")

    def deplace(self, evenement, x, y):
        self._survoler(evenement)


class OutilRessort(Outil):
    """Tend un ressort entre deux points de deux solides différents."""

    nom = "ressort"
    curseur = Qt.CrossCursor

    def __init__(self, vue: "VueSchema") -> None:
        super().__init__(vue)
        self._premier: Optional[Tuple[str, str, float, float]] = None
        self._pointeur: Optional[Tuple[float, float]] = None

    def presse(self, evenement, x, y):
        proches = self.vue.points_proches(x, y)
        if not proches:
            self.vue.signaler("outil.ressort.aucun_point")
            return
        if self._premier is None:
            self._premier = proches[0]
            self.vue.signaler("outil.ressort.second")
            return
        autres = [c for c in proches if c[0] != self._premier[0]]
        if not autres:
            self.vue.signaler("outil.ressort.meme_solide")
            return
        premier, second = self._premier, autres[0]
        self._premier = None
        with self.doc.modification() as m:
            ressort = m.creer_ressort(premier[0], premier[1], second[0], second[1], 1000.0)
        self.doc.selectionner(Ref("action", ressort.id))
        self.vue.signaler(self.cle_aide)

    def deplace(self, evenement, x, y):
        self._pointeur = (x, y)
        self._survoler(evenement)

    def annuler(self) -> bool:
        actif = self._premier is not None
        self._premier = None
        return actif

    def dessiner(self, p: QPainter) -> None:
        if self._premier is None or self._pointeur is None:
            return
        self._apercu(p, 2.0, pointille=True)
        p.drawLine(self.vue.ecran(self._premier[2], self._premier[3]), self.vue.ecran(*self._pointeur))


class OutilMoteur(Outil):
    """Motorise la liaison pivot ou glissière cliquée."""

    nom = "moteur"
    curseur = Qt.PointingHandCursor

    def presse(self, evenement, x, y):
        m = self.doc.mecanisme
        for ref in self.vue.objets_sous(evenement.position()):
            if ref.genre != "liaison":
                continue
            liaison = m.liaisons[ref.id]
            if liaison.PILOTAGE is None:
                self.vue.signaler("outil.moteur.non_pilotable", nom=liaison.nom)
                return
            existant = m.moteur_de_liaison(liaison.id)
            if existant is not None:
                self.doc.selectionner(Ref("moteur", existant.id))
                return
            with self.doc.modification() as modele:
                moteur = modele.creer_moteur(liaison.id)
            self.doc.selectionner(Ref("moteur", moteur.id))
            return
        self.vue.signaler("outil.moteur.aucune_liaison")

    def deplace(self, evenement, x, y):
        self._survoler(evenement)


OUTILS: Dict[str, Type[Outil]] = {
    "selection": OutilSelection,
    "manipuler": OutilManipuler,
    "barre": OutilBarre,
    "point": OutilPoint,
    "pivot": _outil_liaison("pivot"),
    "glissiere": _outil_liaison("glissiere"),
    "encastrement": _outil_liaison("encastrement"),
    "ponctuelle": _outil_liaison("ponctuelle"),
    "force": OutilForce,
    "couple": OutilCouple,
    "ressort": OutilRessort,
    "moteur": OutilMoteur,
}
