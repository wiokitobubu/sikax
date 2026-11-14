"""Courbes : tracé des grandeurs calculées en fonction du temps ou d'une autre grandeur.

Deux présentations :

- **Vue d'ensemble** : six graphiques liés en temps — position, vitesse et
  accélération de l'objet suivi (le point, le solide ou la liaison choisi
  sur le schéma), efforts dans les liaisons, couples, énergie — remplis dès
  la fin du calcul, sans rien cocher ;
- **Personnalisé** : l'arbre de toutes les grandeurs, à cocher, tracées en
  fonction du temps ou d'une autre grandeur.

Une valeur isolée démesurée (au voisinage d'un point mort) n'écrase pas
l'échelle : le graphique se règle sur l'essentiel des valeurs et signale le
pic. Les intervalles passés près d'un point mort sont grisés.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...calcul import Resultats
from ...fichiers.excel import Graphique
from ...i18n import tr, traducteur
from ..document import Document, Ref
from ..icones import icone
from ..theme import theme

ROLE_CLE = Qt.UserRole + 1
COULEURS = ("#3B82F6", "#F97316", "#22C55E", "#EC4899", "#A855F7", "#EAB308", "#14B8A6", "#EF4444")

# Ordre d'affichage des grandeurs dans l'arbre, par famille.
GRANDEURS = {
    "energie": ("mecanique", "cinetique", "potentielle"),
    "moteur": ("effort", "puissance", "position", "vitesse"),
    "liaison": ("X", "Y", "N", "R", "Fn", "Ft", "Fr", "couple_a", "couple_b", "angle", "vitesse_angulaire", "deplacement", "vitesse"),
    "point": ("x", "y", "vx", "vy", "v", "ax", "ay", "a"),
    "solide": ("x", "y", "angle", "vx", "vy", "v", "omega", "ax", "ay", "a", "alpha"),
    "action": ("fx", "fy", "f", "mz", "effort", "longueur"),
}
FAMILLES = ("moteur", "liaison", "point", "solide", "action", "energie")

VUES = ("position", "vitesse", "acceleration", "efforts", "couples", "energie")
"""Graphiques de la vue d'ensemble, dans l'ordre (deux lignes de trois)."""

PIC = 20.0
"""Une valeur plus de 20 fois au-dessus du 99e centile est un pic : elle ne règle pas l'échelle."""


def echelle_robuste(series: List[np.ndarray]) -> Optional[Tuple[float, float, float]]:
    """(bas, haut, pic) : plage d'affichage et valeur du pic écarté, ou ``None`` s'il n'y a pas de pic."""
    if not series:
        return None
    valeurs = np.concatenate([np.asarray(v, dtype=float).ravel() for v in series])
    valeurs = valeurs[np.isfinite(valeurs)]
    if valeurs.size < 8:
        return None
    absolues = np.abs(valeurs)
    ordinaire = float(np.percentile(absolues, 99.0))
    extreme = float(np.max(absolues))
    if extreme <= PIC * max(ordinaire, 1e-300):
        return None
    garde = valeurs[absolues <= 2.0 * ordinaire]
    bas, haut = float(np.min(garde)), float(np.max(garde))
    marge = 0.08 * max(haut - bas, ordinaire, 1e-300)
    return bas - marge, haut + marge, float(valeurs[np.argmax(absolues)])


class PanneauCourbes(QWidget):
    exporter_demande = Signal(list)
    """Demande d'export Excel des grandeurs données (liste de clés)."""

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self.coches: Set[str] = set()
        self.abscisse: Optional[str] = None
        self._courbes: Dict[str, pg.PlotDataItem] = {}
        self._silence = False
        self.suivi: Optional[Ref] = None
        """Objet suivi par la vue d'ensemble ; ``None`` : la sélection du schéma."""
        self.series: Dict[str, List[str]] = {vue: [] for vue in VUES}
        """Grandeurs tracées dans chaque graphique de la vue d'ensemble."""

        # -- personnalisé : arbre des grandeurs et graphique unique --------------------
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

        # -- barre commune ----------------------------------------------------------------
        self.etiquette_abscisse = QLabel()
        self.etiquette_abscisse.setProperty("role", "secondaire")
        self.bouton_temps = QToolButton()
        self.bouton_temps.clicked.connect(lambda: self.definir_abscisse(None))
        self.bouton_effacer = QToolButton()
        self.bouton_effacer.clicked.connect(self.tout_decocher)
        self.bouton_excel = QToolButton()
        self.bouton_excel.clicked.connect(lambda: self.exporter_demande.emit(self.cles_affichees()))
        self.message = QLabel()
        self.message.setProperty("role", "secondaire")
        self.bouton_ensemble = QToolButton()
        self.bouton_personnalise = QToolButton()
        self._modes = QButtonGroup(self)
        for i, bouton in enumerate((self.bouton_ensemble, self.bouton_personnalise)):
            bouton.setCheckable(True)
            bouton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self._modes.addButton(bouton, i)
        self.bouton_ensemble.setChecked(True)
        self._modes.idClicked.connect(self.choisir_mode)
        self.etiquette_suivi = QLabel()
        self.etiquette_suivi.setProperty("role", "secondaire")
        self.choix_suivi = QComboBox()
        self.choix_suivi.setMinimumWidth(200)
        self.choix_suivi.activated.connect(self._sur_suivi)

        barre = QHBoxLayout()
        barre.setContentsMargins(10, 6, 10, 2)
        barre.setSpacing(6)
        barre.addWidget(self.bouton_ensemble)
        barre.addWidget(self.bouton_personnalise)
        barre.addSpacing(10)
        barre.addWidget(self.etiquette_suivi)
        barre.addWidget(self.choix_suivi)
        barre.addWidget(self.etiquette_abscisse)
        barre.addWidget(self.bouton_temps)
        barre.addStretch(1)
        barre.addWidget(self.message)
        barre.addStretch(1)
        barre.addWidget(self.bouton_effacer)
        barre.addWidget(self.bouton_excel)

        # -- vue d'ensemble : six graphiques liés en temps ------------------------------
        self.ensemble = pg.GraphicsLayoutWidget()
        self.graphes: Dict[str, pg.PlotItem] = {}
        self.lignes: Dict[str, pg.InfiniteLine] = {}
        self._courbes_ensemble: Dict[str, List[pg.PlotDataItem]] = {vue: [] for vue in VUES}
        self._zones: List[Tuple[pg.PlotItem, pg.LinearRegionItem]] = []
        for i, vue in enumerate(VUES):
            graphe = self.ensemble.addPlot(row=i // 3, col=i % 3)
            graphe.setMenuEnabled(False)
            graphe.showGrid(x=True, y=True, alpha=0.22)
            # Pas de titre : le nom du graphique est porté par l'axe vertical. Un titre de
            # pyqtgraph est un élément de la mise en page dont la taille minimale suit le texte ;
            # dans un panneau étroit ou masqué, la mise en page peut alors boucler sans fin.
            # La légende, elle, est en surimpression et n'y participe pas.
            graphe.addLegend(offset=(4, 2), labelTextSize="7.5pt", verSpacing=-8, horSpacing=8, colCount=1)
            if i:
                graphe.setXLink(self.graphes[VUES[0]])
            ligne = pg.InfiniteLine(angle=90, movable=True)
            ligne.sigPositionChanged.connect(self._sur_ligne_ensemble)
            graphe.addItem(ligne, ignoreBounds=True)
            self.graphes[vue] = graphe
            self.lignes[vue] = ligne

        self.personnalise = QSplitter(Qt.Horizontal)
        self.personnalise.addWidget(self.arbre)
        self.personnalise.addWidget(self.graphe)
        self.personnalise.setStretchFactor(0, 0)
        self.personnalise.setStretchFactor(1, 1)
        self.personnalise.setSizes([270, 900])

        self.pages = QStackedWidget()
        self.pages.addWidget(self.ensemble)
        self.pages.addWidget(self.personnalise)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addLayout(barre)
        disposition.addWidget(self.pages, 1)

        document.resultats_change.connect(self.reconstruire)
        document.selection_change.connect(self._sur_selection)
        document.temps_change.connect(lambda _: self._placer_reperes())
        traducteur.abonner(self.reconstruire)
        theme.change.connect(self._sur_theme)  # méthode liée : déconnectée d'office à la destruction
        self._habiller()
        self.reconstruire()

    # ------------------------------------------------------------ présentation
    def _sur_theme(self, _nom: str) -> None:
        self._habiller()

    @property
    def mode(self) -> str:
        return "ensemble" if self.pages.currentIndex() == 0 else "personnalise"

    def choisir_mode(self, indice: int) -> None:
        """0 : vue d'ensemble ; 1 : courbes personnalisées."""
        self.pages.setCurrentIndex(indice)
        bouton = self._modes.button(indice)
        if not bouton.isChecked():
            bouton.setChecked(True)
        ensemble = indice == 0
        for composant in (self.etiquette_suivi, self.choix_suivi):
            composant.setVisible(ensemble)
        for composant in (self.etiquette_abscisse, self.bouton_effacer):
            composant.setVisible(not ensemble)
        self.bouton_temps.setVisible(not ensemble and self.abscisse is not None)
        self.tracer()

    def cles_affichees(self) -> List[str]:
        """Grandeurs visibles dans la présentation courante (celles qu'exporte le bouton Excel)."""
        if self.mode == "personnalise":
            return self.cles_tracees()
        return list(dict.fromkeys(c for vue in VUES for c in self.series.get(vue, [])))

    def graphiques_excel(self) -> List[Graphique]:
        """Graphiques du classeur Excel : ceux de la vue d'ensemble."""
        resultats = self.doc.resultats
        sortie: List[Graphique] = []
        if resultats is None:
            return sortie
        for vue in VUES:
            cles = [c for c in self.series.get(vue, []) if c in resultats.canaux]
            if cles:
                dimensions = {resultats.canaux[c].dimension for c in cles}
                unite = self.doc.mecanisme.unites.symbole(dimensions.pop()) if len(dimensions) == 1 else ""
                sortie.append(Graphique(tr(f"courbes.vue.{vue}"), unite, cles))
        return sortie

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
        if self.suivi is not None and self.doc.objet(self.suivi) is None:
            self.suivi = None
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
        """Remplace les grandeurs tracées en mode personnalisé (utilisé par les tests et les exemples)."""
        self.coches = set(cles)
        self.choisir_mode(1)
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
        self.bouton_temps.setVisible(self.mode == "personnalise" and self.abscisse is not None)
        self.bouton_effacer.setText(tr("courbes.tout_decocher"))
        self.bouton_excel.setText(tr("courbes.exporter_excel"))
        self.bouton_excel.setToolTip(tr("courbes.exporter_excel_aide"))
        self.bouton_excel.setIcon(icone("tableur", taille=16))
        self.bouton_excel.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.bouton_ensemble.setText(tr("courbes.mode.ensemble"))
        self.bouton_ensemble.setIcon(icone("ensemble", taille=16))
        self.bouton_personnalise.setText(tr("courbes.mode.personnalise"))
        self.bouton_personnalise.setIcon(icone("courbes", taille=16))
        self.etiquette_suivi.setText(tr("courbes.objet_suivi"))
        nom = tr("courbes.temps") if self.abscisse is None else self.libelle(self.abscisse)
        self.etiquette_abscisse.setText(tr("courbes.abscisse", nom=nom))
        self._remplir_suivi()

    def _habiller(self) -> None:
        plume = pg.mkPen(theme.couleur("bordure"))
        texte = pg.mkPen(theme.couleur("texte_secondaire"))
        self.graphe.setBackground(theme.couleur("surface"))
        self.ensemble.setBackground(theme.couleur("surface"))
        axes = [self.graphe.getAxis(nom) for nom in ("left", "bottom")]
        axes += [graphe.getAxis(nom) for graphe in self.graphes.values() for nom in ("left", "bottom")]
        for axe in axes:
            axe.setPen(plume)
            axe.setTextPen(texte)
        self.ligne_temps.setPen(pg.mkPen(theme.couleur("accent"), width=1.4))
        for ligne in self.lignes.values():
            ligne.setPen(pg.mkPen(theme.couleur("accent"), width=1.2))
        legendes = [self.legende] + [graphe.legend for graphe in self.graphes.values() if graphe.legend is not None]
        for legende in legendes:
            legende.setLabelTextColor(theme.couleur("texte"))
            legende.setBrush(pg.mkBrush(theme.couleur("surface_haute", 210)))
            legende.setPen(pg.mkPen(theme.couleur("bordure")))
        self.tracer()

    def tracer(self) -> None:
        if self.mode == "ensemble":
            self._tracer_ensemble()
        else:
            self._tracer_personnalise()

    def _tracer_personnalise(self) -> None:
        resultats = self.doc.resultats
        for courbe in self._courbes.values():
            self.graphe.removeItem(courbe)
        self._courbes = {}
        self.legende.clear()
        cles = self.cles_tracees()
        disponible = resultats is not None and resultats.nb_instants > 0
        self.ligne_temps.setVisible(disponible and self.abscisse is None and resultats.nb_instants > 1)
        self.bouton_excel.setEnabled(disponible)
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
            options = dict(pen=pg.mkPen(couleur, width=2), name=self.libelle(cle), connect="finite")
            if ponctuel:
                options.update(symbol="o", symbolBrush=couleur, symbolSize=9)
            self._courbes[cle] = self.graphe.plot(x, self._valeurs(cle), **options)
        self.graphe.setLabel("bottom", tr("courbes.axe_temps") if self.abscisse is None else self.libelle(self.abscisse))
        dimensions = {resultats.canaux[c].dimension for c in cles}
        unique = self.doc.mecanisme.unites.symbole(dimensions.pop()) if len(dimensions) == 1 else ""
        self.graphe.setLabel("left", unique)
        plage = echelle_robuste([self._valeurs(c) for c in cles]) if self.abscisse is None and not ponctuel else None
        if plage is not None:
            self.graphe.enableAutoRange(axis="x")
            self.graphe.setYRange(plage[0], plage[1], padding=0.0)
            self.message.setText(tr("courbes.pic", valeur=f"{plage[2]:.3g}", unite=unique))
        else:
            self.graphe.enableAutoRange()
        self._placer_reperes()

    def _placer_reperes(self) -> None:
        resultats = self.doc.resultats
        if resultats is None or resultats.nb_instants == 0:
            return
        i = self.doc.indice
        self._silence = True
        instant = float(resultats.temps[i])
        for ligne in self.lignes.values():
            ligne.setValue(instant)
        if self.abscisse is None:
            self.ligne_temps.setValue(instant)
        self._silence = False
        x = instant if self.abscisse is None else float(self._valeurs(self.abscisse)[i])
        points = []
        for n, cle in enumerate(self.cles_tracees()):
            y = float(self._valeurs(cle)[i])
            if np.isfinite(y):
                couleur = COULEURS[n % len(COULEURS)]
                points.append({"pos": (x, y), "brush": pg.mkBrush(couleur), "pen": pg.mkPen(theme.couleur("surface"), width=1.5)})
        self.reperes.setData(points)

    def _sur_ligne(self) -> None:
        if self._silence or self.doc.resultats is None:
            return
        self.doc.definir_indice(self.doc.resultats.indice_du_temps(float(self.ligne_temps.value())))

    def _sur_ligne_ensemble(self, ligne: pg.InfiniteLine) -> None:
        if self._silence or self.doc.resultats is None:
            return
        self.doc.definir_indice(self.doc.resultats.indice_du_temps(float(ligne.value())))

    # ---------------------------------------------------------- vue d'ensemble
    def _remplir_suivi(self) -> None:
        """Liste des objets que la vue d'ensemble peut suivre."""
        m = self.doc.mecanisme
        self.choix_suivi.blockSignals(True)
        self.choix_suivi.clear()
        self.choix_suivi.addItem(icone("selection", taille=14), tr("courbes.suivi_selection"), None)
        for solide in m.solides_mobiles():
            self.choix_suivi.addItem(icone("solide", taille=14), solide.nom, Ref("solide", solide.id))
            for point in solide.points.values():
                self.choix_suivi.addItem(icone("point", taille=14), f"    {point.nom} ({solide.nom})", Ref("point", solide.id, point.id))
        for liaison in m.liaisons.values():
            self.choix_suivi.addItem(icone(liaison.type, taille=14), liaison.nom, Ref("liaison", liaison.id))
        indice = self.choix_suivi.findData(self.suivi) if self.suivi is not None else 0
        self.choix_suivi.setCurrentIndex(max(0, indice))
        self.choix_suivi.blockSignals(False)

    def suivre(self, ref: Optional[Ref]) -> None:
        """Fixe l'objet suivi par la vue d'ensemble (``None`` : suivre la sélection du schéma)."""
        self.suivi = ref
        self._remplir_suivi()
        self.tracer()

    def _sur_suivi(self, indice: int) -> None:
        self.suivi = self.choix_suivi.itemData(indice)
        self._tracer_ensemble()

    def _sur_selection(self) -> None:
        if self.suivi is None and self.mode == "ensemble":
            self._tracer_ensemble()

    def objet_suivi(self) -> Optional[Ref]:
        """Objet de la vue d'ensemble : choisi dans la liste, sinon la sélection, sinon le point qui bouge le plus."""
        resultats = self.doc.resultats
        if resultats is None:
            return None
        for ref in (self.suivi, self.doc.selection):
            if ref is None:
                continue
            if ref.genre == "point" and f"point/{ref.id}/{ref.sous}/x" in resultats.canaux:
                return ref
            if ref.genre == "solide" and f"solide/{ref.id}/angle" in resultats.canaux:
                return ref
            if ref.genre == "liaison" and f"liaison/{ref.id}/px" in resultats.canaux:
                return ref
            if ref.genre == "moteur" and ref.id in self.doc.mecanisme.moteurs:
                return Ref("liaison", self.doc.mecanisme.moteurs[ref.id].liaison)
        # Rien de choisi : ce qui bouge le plus, point qui se déplace ou solide qui tourne
        # (une roue qui tourne sur place a un centre immobile : on suit alors la roue).
        meilleur, ampleur = None, 0.0
        longueur = self.doc.mecanisme.longueur_caracteristique()
        for cle in resultats.canaux:
            if cle.startswith("point/") and cle.endswith("/x"):
                base = cle[:-1]
                etendue = float(np.ptp(resultats.valeurs(base + "x")) + np.ptp(resultats.valeurs(base + "y")))
                if etendue > ampleur:
                    _, sid, pid, _ = cle.split("/")
                    meilleur, ampleur = Ref("point", sid, pid), etendue
        for cle in resultats.canaux:
            if cle.startswith("solide/") and cle.endswith("/angle"):
                rotation = float(np.ptp(resultats.valeurs(cle))) * 0.25 * longueur
                if rotation > 2.0 * ampleur:
                    meilleur, ampleur = Ref("solide", cle.split("/")[1]), rotation
        return meilleur

    def _series_ensemble(self) -> Dict[str, List[str]]:
        """Grandeurs de chaque graphique, pour l'objet suivi."""
        resultats = self.doc.resultats
        m = self.doc.mecanisme
        series: Dict[str, List[str]] = {vue: [] for vue in VUES}
        if resultats is None:
            return series
        canaux = resultats.canaux

        def ajouter(vue: str, *cles: str) -> None:
            series[vue].extend(c for c in cles if c in canaux and c not in series[vue])

        suivi = self.objet_suivi()
        if suivi is not None and suivi.genre == "point":
            base = f"point/{suivi.id}/{suivi.sous}/"
            ajouter("position", base + "x", base + "y")
            ajouter("vitesse", base + "vx", base + "vy", base + "v")
            ajouter("acceleration", base + "ax", base + "ay", base + "a")
        elif suivi is not None and suivi.genre == "solide":
            base = f"solide/{suivi.id}/"
            ajouter("position", base + "angle")
            ajouter("vitesse", base + "omega")
            ajouter("acceleration", base + "alpha")
        elif suivi is not None and suivi.genre == "liaison":
            base = f"liaison/{suivi.id}/"
            liaison = m.liaisons.get(suivi.id)
            ajouter("position", base + "angle", base + "deplacement")
            ajouter("vitesse", base + "vitesse_angulaire", base + "vitesse")
            if liaison is not None:
                if not series["position"]:
                    ajouter("position", f"solide/{liaison.solide_a}/angle", f"solide/{liaison.solide_b}/angle")
                    ajouter("vitesse", f"solide/{liaison.solide_a}/omega", f"solide/{liaison.solide_b}/omega")
                ajouter("acceleration", f"solide/{liaison.solide_b}/alpha", f"solide/{liaison.solide_a}/alpha")
            ajouter("efforts", base + "X", base + "Y", base + "R", base + "Ft", base + "Fr", base + "Fn")
            ajouter("couples", base + "couple_a", base + "couple_b")
        if not series["efforts"]:
            ajouter("efforts", *[c for c in canaux if c.startswith("liaison/") and c.endswith("/R")])
        for cle, canal in canaux.items():
            if cle.startswith("moteur/") and cle.endswith("/effort"):
                ajouter("couples" if canal.dimension == "moment" else "efforts", cle)
            elif cle.startswith("action/") and cle.endswith("/mz"):
                ajouter("couples", cle)
            elif cle.startswith("liaison/") and cle.endswith(("/couple_a", "/couple_b")) and (suivi is None or suivi.genre != "liaison"):
                ajouter("couples", cle)
        ajouter("energie", "energie/mecanique", "energie/cinetique", "energie/potentielle")
        return series

    def _tracer_ensemble(self) -> None:
        resultats = self.doc.resultats
        disponible = resultats is not None and resultats.nb_instants > 0
        self.bouton_excel.setEnabled(disponible)
        for graphe, zone in self._zones:
            graphe.removeItem(zone)
        self._zones = []
        for vue, graphe in self.graphes.items():
            for courbe in self._courbes_ensemble[vue]:
                graphe.removeItem(courbe)
            self._courbes_ensemble[vue] = []
            if graphe.legend is not None:
                graphe.legend.clear()
        self.series = self._series_ensemble() if disponible else {vue: [] for vue in VUES}
        if not disponible:
            self.message.setText(tr("courbes.aucun_resultat"))
            for vue, graphe in self.graphes.items():
                graphe.setLabel("left", tr(f"courbes.vue.{vue}"), **{"font-size": "8pt"})
                self.lignes[vue].setVisible(False)
            return
        suivi = self.objet_suivi()
        nom_suivi = self._nom(suivi)
        self.message.setText(tr("courbes.etude_statique") if resultats.nb_instants == 1 else "")
        ponctuel = resultats.nb_instants == 1
        unites = self.doc.mecanisme.unites
        pics = []
        for vue, graphe in self.graphes.items():
            cles = self.series[vue]
            donnees = []
            if graphe.legend is not None:
                graphe.legend.setColumnCount(max(1, min(len(cles), 4)))
            for n, cle in enumerate(cles):
                couleur = COULEURS[n % len(COULEURS)]
                options = dict(pen=pg.mkPen(couleur, width=1.8), connect="finite")
                if ponctuel:
                    options.update(symbol="o", symbolBrush=couleur, symbolSize=8)
                valeurs = self._valeurs(cle)
                donnees.append(valeurs)
                courbe = graphe.plot(resultats.temps, valeurs, **options)
                self._courbes_ensemble[vue].append(courbe)
                if graphe.legend is not None:
                    graphe.legend.addItem(courbe, self._court(cle, suivi))
            dimensions = {resultats.canaux[c].dimension for c in cles}
            symbole = unites.symbole(dimensions.pop()) if len(dimensions) == 1 else ""
            graphe.setLabel("bottom", tr("courbes.axe_temps") if vue in VUES[3:] else "")
            plage = echelle_robuste(donnees) if not ponctuel else None
            if plage is not None:
                graphe.enableAutoRange(axis="x")
                graphe.setYRange(plage[0], plage[1], padding=0.0)
                pics.append(f"{tr(f'courbes.vue.{vue}')} {tr('courbes.pic', valeur=f'{plage[2]:.3g}', unite=symbole)}")
            elif donnees and self._negligeable(donnees, vue):
                graphe.enableAutoRange(axis="x")
                graphe.setYRange(-1.0, 1.0, padding=0.0)
            else:
                graphe.enableAutoRange()
            nom = tr(f"courbes.vue.{vue}") + ("" if cles else " " + tr("courbes.vue_vide"))
            graphe.setLabel("left", f"{nom} ({symbole})" if symbole else nom, **{"font-size": "8pt"})
            self.lignes[vue].setVisible(not ponctuel)
            for debut, fin in resultats.zones_singulieres:
                zone = pg.LinearRegionItem(values=(debut, max(fin, debut + 1e-9)), movable=False, brush=pg.mkBrush(theme.couleur("attention", 45)))
                zone.setToolTip(tr("courbes.zone_point_mort"))
                graphe.addItem(zone, ignoreBounds=True)
                self._zones.append((graphe, zone))
        if nom_suivi and not ponctuel:
            self.message.setText(" ".join([tr("courbes.suivi", nom=nom_suivi)] + pics))
        self._placer_reperes()

    def _negligeable(self, donnees: List[np.ndarray], vue: str) -> bool:
        """Vrai si toutes les valeurs ne sont que du bruit d'arrondi autour de zéro.

        Sans cela, l'échelle automatique grossit ce bruit (10⁻¹² mm/s) jusqu'à
        remplir le graphique, et un point immobile semble trembler.
        """
        resultats = self.doc.resultats
        echelle = 0.0
        for cle in self.series.get(vue, []):
            canal = resultats.canaux[cle]
            facteur, _ = self.doc.mecanisme.unites.facteur(canal.dimension)
            echelle = max(echelle, float(np.nanmax(np.abs(canal.valeurs))) * facteur if canal.valeurs.size else 0.0)
        longueur = self.doc.mecanisme.longueur_caracteristique()
        seuil = 1e-9 * max(1.0, self.doc.mecanisme.unites.facteur("longueur")[0] * longueur)
        return echelle <= seuil

    def _court(self, cle: str, suivi: Optional[Ref]) -> str:
        """Nom court d'une courbe dans un titre : la grandeur seule si l'objet est déjà dans le titre."""
        parties = cle.split("/")
        grandeur = parties[-1]
        if parties[0] == "energie":
            return tr(f"grandeur.energie_{grandeur}")
        if suivi is not None and len(parties) >= 3 and parties[1] == suivi.id and parties[0] in ("point", "solide"):
            return tr(f"grandeur.{grandeur}")
        return self.libelle(cle, avec_unite=False)

    def _nom(self, ref: Optional[Ref]) -> str:
        if ref is None:
            return ""
        m = self.doc.mecanisme
        objet = self.doc.objet(ref)
        if objet is None:
            return ""
        if ref.genre == "point":
            return f"{objet.nom} ({m.solides[ref.id].nom})"
        return getattr(objet, "nom", "")
