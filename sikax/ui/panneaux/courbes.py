"""Courbes : tracé des grandeurs calculées en fonction du temps ou d'une autre grandeur."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...calcul import Resultats
from ...i18n import tr, traducteur
from ..document import Document
from ..icones import icone
from ..theme import theme

ROLE_CLE = Qt.UserRole + 1
COULEURS = ("#3B82F6", "#F97316", "#22C55E", "#EC4899", "#A855F7", "#EAB308", "#14B8A6", "#EF4444")

# Ordre d'affichage des grandeurs dans l'arbre, par famille.
GRANDEURS = {
    "energie": ("mecanique", "cinetique", "potentielle"),
    "moteur": ("effort", "puissance", "position", "vitesse"),
    "liaison": ("X", "Y", "N", "R", "Fn", "angle", "vitesse_angulaire", "deplacement", "vitesse"),
    "point": ("x", "y", "vx", "vy", "v", "ax", "ay", "a"),
    "solide": ("x", "y", "angle", "vx", "vy", "v", "omega", "ax", "ay", "a", "alpha"),
    "action": ("fx", "fy", "f", "mz", "effort", "longueur"),
}
FAMILLES = ("moteur", "liaison", "point", "solide", "action", "energie")


class PanneauCourbes(QWidget):
    exporter_csv = Signal(list)
    """Demande d'export des grandeurs données (liste de clés)."""

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self.coches: Set[str] = set()
        self.abscisse: Optional[str] = None
        self._courbes: Dict[str, pg.PlotDataItem] = {}
        self._silence = False

        self.arbre = QTreeWidget()
        self.arbre.setHeaderHidden(True)
        self.arbre.setIndentation(14)
        self.arbre.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbre.itemChanged.connect(self._sur_coche)
        self.arbre.customContextMenuRequested.connect(self._sur_menu)

        self.graphe = pg.PlotWidget()
        self.graphe.setMenuEnabled(False)
        self.graphe.showGrid(x=True, y=True, alpha=0.25)
        self.legende = self.graphe.addLegend(offset=(-10, 10))
        self.ligne_temps = pg.InfiniteLine(angle=90, movable=True)
        self.ligne_temps.sigPositionChanged.connect(self._sur_ligne)
        self.graphe.addItem(self.ligne_temps, ignoreBounds=True)
        self.reperes = pg.ScatterPlotItem(size=9)
        self.graphe.addItem(self.reperes, ignoreBounds=True)

        self.etiquette_abscisse = QLabel()
        self.etiquette_abscisse.setProperty("role", "secondaire")
        self.bouton_temps = QToolButton()
        self.bouton_temps.clicked.connect(lambda: self.definir_abscisse(None))
        self.bouton_effacer = QToolButton()
        self.bouton_effacer.clicked.connect(self.tout_decocher)
        self.bouton_csv = QToolButton()
        self.bouton_csv.clicked.connect(lambda: self.exporter_csv.emit(self.cles_tracees()))
        self.message = QLabel()
        self.message.setProperty("role", "secondaire")
        barre = QHBoxLayout()
        barre.setContentsMargins(10, 6, 10, 2)
        barre.setSpacing(6)
        barre.addWidget(self.etiquette_abscisse)
        barre.addWidget(self.bouton_temps)
        barre.addStretch(1)
        barre.addWidget(self.message)
        barre.addStretch(1)
        barre.addWidget(self.bouton_effacer)
        barre.addWidget(self.bouton_csv)
        droite = QWidget()
        colonne = QVBoxLayout(droite)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(0)
        colonne.addLayout(barre)
        colonne.addWidget(self.graphe, 1)

        separateur = QSplitter(Qt.Horizontal)
        separateur.addWidget(self.arbre)
        separateur.addWidget(droite)
        separateur.setStretchFactor(0, 0)
        separateur.setStretchFactor(1, 1)
        separateur.setSizes([270, 900])
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(separateur)

        document.resultats_change.connect(self.reconstruire)
        document.temps_change.connect(lambda _: self._placer_reperes())
        traducteur.abonner(self.reconstruire)
        theme.change.connect(lambda _: self._habiller())
        self._habiller()
        self.reconstruire()

    # ---------------------------------------------------------------- libellés
    def libelle(self, cle: str, avec_unite: bool = True) -> str:
        resultats = self.doc.resultats
        parties = cle.split("/")
        if parties[0] == "energie":
            texte = tr(f"grandeur.energie_{parties[-1]}")
        else:
            objet = resultats.canaux[cle].objet if resultats is not None and cle in resultats.canaux else parties[1]
            texte = f"{objet} · {tr('grandeur.' + parties[-1])}"
        if avec_unite and resultats is not None and cle in resultats.canaux:
            symbole = self.doc.mecanisme.unites.symbole(resultats.canaux[cle].dimension)
            if symbole:
                texte += f" ({symbole})"
        return texte

    def _valeurs(self, cle: str) -> np.ndarray:
        canal = self.doc.resultats.canaux[cle]
        facteur, _ = self.doc.mecanisme.unites.facteur(canal.dimension)
        return canal.valeurs * facteur

    # ------------------------------------------------------------------- arbre
    def reconstruire(self) -> None:
        resultats = self.doc.resultats
        self._silence = True
        self.arbre.clear()
        self._feuilles: Dict[str, QTreeWidgetItem] = {}
        if resultats is not None:
            if self.abscisse is not None and self.abscisse not in resultats.canaux:
                self.abscisse = None
            self.coches = {c for c in self.coches if c in resultats.canaux}
            if not self.coches:
                self.coches = self._choix_initial(resultats)
            self._remplir(resultats)
        self._silence = False
        self.traduire()
        self.tracer()

    @staticmethod
    def _choix_initial(resultats: Resultats) -> Set[str]:
        """Première grandeur tracée : l'effort moteur s'il y en a un, sinon l'angle du premier solide."""
        for prefixe, suffixe in (("moteur/", "/effort"), ("liaison/", "/R"), ("solide/", "/angle")):
            for cle in resultats.canaux:
                if cle.startswith(prefixe) and cle.endswith(suffixe):
                    return {cle}
        return set()

    def _remplir(self, resultats: Resultats) -> None:
        par_famille: Dict[str, Dict[Tuple[str, ...], List[str]]] = {f: {} for f in FAMILLES}
        for cle in resultats.canaux:
            parties = cle.split("/")
            famille, grandeur = parties[0], parties[-1]
            if famille not in par_famille or grandeur not in GRANDEURS[famille]:
                continue
            par_famille[famille].setdefault(tuple(parties[1:-1]), []).append(cle)

        for famille in FAMILLES:
            groupes = par_famille[famille]
            if not groupes:
                continue
            racine = QTreeWidgetItem(self.arbre, [tr(f"courbes.famille.{famille}")])
            police = racine.font(0)
            police.setBold(True)
            racine.setFont(0, police)
            racine.setFlags(Qt.ItemIsEnabled)
            ouvert = False
            intermediaires: Dict[str, QTreeWidgetItem] = {}
            for objet, cles in groupes.items():
                parent = racine
                if objet:
                    if famille == "point":  # un niveau par solide, puis un par point
                        solide_id = objet[0]
                        if solide_id not in intermediaires:
                            nom = self.doc.mecanisme.solides[solide_id].nom if solide_id in self.doc.mecanisme.solides else solide_id
                            intermediaires[solide_id] = QTreeWidgetItem(racine, [nom])
                            intermediaires[solide_id].setFlags(Qt.ItemIsEnabled)
                        parent = intermediaires[solide_id]
                        nom_objet = resultats.canaux[cles[0]].objet.split(" (")[0]
                    else:
                        nom_objet = resultats.canaux[cles[0]].objet or objet[-1]
                    parent = QTreeWidgetItem(parent, [nom_objet])
                    parent.setFlags(Qt.ItemIsEnabled)
                cles.sort(key=lambda c: GRANDEURS[famille].index(c.rsplit("/", 1)[-1]))
                for cle in cles:
                    grandeur = cle.rsplit("/", 1)[-1]
                    texte = tr(f"grandeur.energie_{grandeur}") if famille == "energie" else tr(f"grandeur.{grandeur}")
                    feuille = QTreeWidgetItem(parent, [texte])
                    feuille.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                    feuille.setCheckState(0, Qt.Checked if cle in self.coches else Qt.Unchecked)
                    feuille.setData(0, ROLE_CLE, cle)
                    self._feuilles[cle] = feuille
                    if cle in self.coches:
                        ouvert = True
                        ancetre = feuille.parent()
                        while ancetre is not None:
                            ancetre.setExpanded(True)
                            ancetre = ancetre.parent()
            racine.setExpanded(ouvert or famille in ("moteur", "energie"))

    def _sur_coche(self, element: QTreeWidgetItem, _colonne: int) -> None:
        if self._silence:
            return
        cle = element.data(0, ROLE_CLE)
        if cle is None:
            return
        if element.checkState(0) == Qt.Checked:
            self.coches.add(cle)
        else:
            self.coches.discard(cle)
        self.tracer()

    def _sur_menu(self, position: QPoint) -> None:
        element = self.arbre.itemAt(position)
        cle = element.data(0, ROLE_CLE) if element is not None else None
        if cle is None:
            return
        menu = QMenu(self)
        action = QAction(tr("courbes.utiliser_abscisse"), menu)
        action.triggered.connect(lambda: self.definir_abscisse(cle))
        menu.addAction(action)
        menu.exec(self.arbre.viewport().mapToGlobal(position))

    def cocher(self, cles) -> None:
        """Remplace les grandeurs tracées (utilisé par les tests et les exemples)."""
        self.coches = set(cles)
        self.reconstruire()

    def tout_decocher(self) -> None:
        self.coches = set()
        self.reconstruire()

    def definir_abscisse(self, cle: Optional[str]) -> None:
        self.abscisse = cle
        self.traduire()
        self.tracer()

    def cles_tracees(self) -> List[str]:
        resultats = self.doc.resultats
        if resultats is None:
            return []
        return [c for c in resultats.canaux if c in self.coches]

    # ------------------------------------------------------------------- tracé
    def traduire(self) -> None:
        self.bouton_temps.setText(tr("courbes.revenir_au_temps"))
        self.bouton_temps.setVisible(self.abscisse is not None)
        self.bouton_effacer.setText(tr("courbes.tout_decocher"))
        self.bouton_csv.setText(tr("courbes.exporter_csv"))
        self.bouton_csv.setIcon(icone("exporter", taille=16))
        self.bouton_csv.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        nom = tr("courbes.temps") if self.abscisse is None else self.libelle(self.abscisse)
        self.etiquette_abscisse.setText(tr("courbes.abscisse", nom=nom))

    def _habiller(self) -> None:
        self.graphe.setBackground(theme.couleur("surface"))
        plume = pg.mkPen(theme.couleur("bordure"))
        texte = pg.mkPen(theme.couleur("texte_secondaire"))
        for nom in ("left", "bottom"):
            axe = self.graphe.getAxis(nom)
            axe.setPen(plume)
            axe.setTextPen(texte)
        self.ligne_temps.setPen(pg.mkPen(theme.couleur("accent"), width=1.4))
        self.legende.setLabelTextColor(theme.couleur("texte"))
        self.legende.setBrush(pg.mkBrush(theme.couleur("surface_haute", 220)))
        self.legende.setPen(pg.mkPen(theme.couleur("bordure")))
        self.tracer()

    def tracer(self) -> None:
        resultats = self.doc.resultats
        for courbe in self._courbes.values():
            self.graphe.removeItem(courbe)
        self._courbes = {}
        self.legende.clear()
        cles = self.cles_tracees()
        disponible = resultats is not None and resultats.nb_instants > 0
        self.ligne_temps.setVisible(disponible and self.abscisse is None and resultats.nb_instants > 1)
        self.bouton_csv.setEnabled(disponible)
        if not disponible:
            self.message.setText(tr("courbes.aucun_resultat"))
            self.reperes.setData([], [])
            self.graphe.setLabel("bottom", "")
            self.graphe.setLabel("left", "")
            return
        self.message.setText(tr("courbes.etude_statique") if resultats.nb_instants == 1 else ("" if cles else tr("courbes.aucune_grandeur")))
        x = resultats.temps if self.abscisse is None else self._valeurs(self.abscisse)
        ponctuel = resultats.nb_instants == 1
        for i, cle in enumerate(cles):
            couleur = COULEURS[i % len(COULEURS)]
            options = dict(pen=pg.mkPen(couleur, width=2), name=self.libelle(cle))
            if ponctuel:
                options.update(symbol="o", symbolBrush=couleur, symbolSize=9)
            self._courbes[cle] = self.graphe.plot(x, self._valeurs(cle), **options)
        self.graphe.setLabel("bottom", tr("courbes.axe_temps") if self.abscisse is None else self.libelle(self.abscisse))
        dimensions = {resultats.canaux[c].dimension for c in cles}
        unique = self.doc.mecanisme.unites.symbole(dimensions.pop()) if len(dimensions) == 1 else ""
        self.graphe.setLabel("left", unique)
        self.graphe.enableAutoRange()
        self._placer_reperes()

    def _placer_reperes(self) -> None:
        resultats = self.doc.resultats
        if resultats is None or resultats.nb_instants == 0:
            return
        i = self.doc.indice
        if self.abscisse is None:
            self._silence = True
            self.ligne_temps.setValue(float(resultats.temps[i]))
            self._silence = False
            x = float(resultats.temps[i])
        else:
            x = float(self._valeurs(self.abscisse)[i])
        points = []
        for n, cle in enumerate(self.cles_tracees()):
            couleur = COULEURS[n % len(COULEURS)]
            points.append({"pos": (x, float(self._valeurs(cle)[i])), "brush": pg.mkBrush(couleur), "pen": pg.mkPen(theme.couleur("surface"), width=1.5)})
        self.reperes.setData(points)

    def _sur_ligne(self) -> None:
        if self._silence or self.doc.resultats is None:
            return
        self.doc.definir_indice(self.doc.resultats.indice_du_temps(float(self.ligne_temps.value())))
