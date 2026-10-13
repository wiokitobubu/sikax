"""Validation topologique : mobilité, hyperstatisme et graphe des liaisons.

Le panneau se met à jour à chaque modification du modèle. Il présente côte à
côte l'analyse dans le plan (celle du mouvement simulé) et l'analyse dans
l'espace, qui dépend du modèle spatial choisi pour chaque liaison.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...calcul import BilanTopologique, analyser_topologie
from ...i18n import tr, traducteur
from ..document import Document, Ref
from ..theme import theme


COLONNES = ("liaison", "type", "plan", "espace", "modele")


class CarteBilan(QFrame):
    """Résumé d'une analyse : mobilité, hyperstatisme et verdict."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "carte")
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(14, 8, 14, 10)
        disposition.setSpacing(2)
        self.titre = QLabel()
        self.titre.setProperty("role", "rubrique")
        disposition.addWidget(self.titre)
        ligne = QHBoxLayout()
        ligne.setSpacing(18)
        self.mobilite = QLabel()
        self.mobilite.setProperty("role", "valeur")
        self.hyperstatisme = QLabel()
        self.hyperstatisme.setProperty("role", "valeur")
        ligne.addWidget(self.mobilite)
        ligne.addWidget(self.hyperstatisme)
        ligne.addStretch(1)
        disposition.addLayout(ligne)
        self.verdict = QLabel()
        self.verdict.setWordWrap(True)
        police = self.verdict.font()
        police.setBold(True)
        self.verdict.setFont(police)
        disposition.addWidget(self.verdict)

    def afficher(self, bilan: BilanTopologique) -> None:
        self.titre.setText(tr("validation.plan") if bilan.dimension == 2 else tr("validation.espace"))
        self.mobilite.setText(f"m = {bilan.mobilite}")
        self.hyperstatisme.setText(f"h = {bilan.hyperstatisme}")
        if bilan.nb_liaisons == 0:
            verdict, etat = tr("validation.verdict.vide"), ""
        elif bilan.isostatique:
            verdict, etat = tr("validation.verdict.isostatique"), "succes"
        else:
            verdict, etat = tr("validation.verdict.hyperstatique", h=bilan.hyperstatisme), "attention"
        self.verdict.setText(verdict)
        self.verdict.setProperty("etat", etat)
        self.verdict.style().unpolish(self.verdict)
        self.verdict.style().polish(self.verdict)


def detail_du_calcul(bilan: BilanTopologique) -> str:
    """Ligne qui justifie m et h : inconnues, équations, rang et vérification statique."""
    return tr(
        "validation.detail",
        nom=tr("validation.plan") if bilan.dimension == 2 else tr("validation.espace"),
        d=3 if bilan.dimension == 2 else 6,
        ic=bilan.ic,
        ec=bilan.ec,
        rang=bilan.rang,
        m=bilan.mobilite,
        h=bilan.hyperstatisme,
        is_=bilan.is_,
        es=bilan.es,
    )


class GrapheLiaisons(QWidget):
    """Graphe des liaisons : un sommet par solide, une arête par liaison."""

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self.bilan: Optional[BilanTopologique] = None
        self._sommets: Dict[str, QPointF] = {}
        self._aretes: List[Tuple[str, QPointF]] = []
        self.setMinimumSize(220, 160)
        self.setMouseTracking(True)
        document.selection_change.connect(self.update)
        theme.change.connect(lambda _: self.update())

    def sizeHint(self) -> QSize:
        return QSize(320, 220)

    def afficher(self, bilan: BilanTopologique) -> None:
        self.bilan = bilan
        self.update()

    def _placer(self) -> None:
        """Dispose les solides sur un cercle, le bâti en bas."""
        solides = list(self.doc.mecanisme.solides)
        self._sommets = {}
        n = len(solides)
        centre = QPointF(self.width() / 2.0, self.height() / 2.0)
        rx = max(self.width() / 2.0 - 70.0, 20.0)
        ry = max(self.height() / 2.0 - 40.0, 16.0)
        centre = QPointF(centre.x(), centre.y() + 8.0)  # place pour la légende
        if n == 1:
            self._sommets[solides[0]] = centre
            return
        for i, solide_id in enumerate(solides):
            angle = math.pi / 2.0 + 2.0 * math.pi * i / n  # le bâti (premier) en bas
            self._sommets[solide_id] = QPointF(centre.x() + rx * math.cos(angle), centre.y() + ry * math.sin(angle))

    def paintEvent(self, evenement) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.couleur("surface"))
        m = self.doc.mecanisme
        self._placer()
        self._aretes = []
        hyperstatiques = set(self.bilan.liaisons_hyperstatiques()) if self.bilan is not None else set()
        selection = self.doc.selection
        police = QFont(p.font())
        police.setPointSizeF(9.0)
        p.setFont(police)

        # plusieurs liaisons entre deux mêmes solides : arêtes de courbures différentes
        compte: Dict[Tuple[str, str], int] = {}
        for liaison in m.liaisons.values():
            if liaison.solide_a not in self._sommets or liaison.solide_b not in self._sommets:
                continue
            paire = tuple(sorted((liaison.solide_a, liaison.solide_b)))
            rang = compte.get(paire, 0)
            compte[paire] = rang + 1
            a, b = self._sommets[paire[0]], self._sommets[paire[1]]
            milieu = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            longueur = math.hypot(dx, dy) or 1.0
            decalage = 26.0 * ((rang + 1) // 2) * (1 if rang % 2 else -1)
            controle = QPointF(milieu.x() - dy / longueur * decalage, milieu.y() + dx / longueur * decalage)
            chemin = QPainterPath(a)
            chemin.quadTo(controle, b)
            choisie = selection is not None and selection.genre == "liaison" and selection.id == liaison.id
            if choisie:
                couleur = theme.couleur("accent")
            elif liaison.id in hyperstatiques:
                couleur = theme.couleur("attention")
            else:
                couleur = theme.couleur("texte_secondaire")
            p.setPen(QPen(couleur, 2.6 if choisie else 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawPath(chemin)
            etiquette = QPointF((milieu.x() + controle.x()) / 2.0, (milieu.y() + controle.y()) / 2.0)
            self._aretes.append((liaison.id, etiquette))
            if choisie or len(m.liaisons) <= 4:
                texte = liaison.nom
                largeur = p.fontMetrics().horizontalAdvance(texte) + 10.0
                cadre = QRectF(etiquette.x() - largeur / 2.0, etiquette.y() - 9.0, largeur, 18.0)
                p.setPen(Qt.NoPen)
                p.setBrush(theme.couleur("surface"))
                p.drawRoundedRect(cadre, 4.0, 4.0)
                p.setPen(couleur)
                p.drawText(cadre, Qt.AlignCenter, texte)
            else:  # graphe chargé : une pastille, le nom apparaît à la sélection ou au survol
                p.setPen(QPen(couleur, 1.6))
                p.setBrush(theme.couleur("surface"))
                p.drawEllipse(etiquette, 4.5, 4.5)

        if self.bilan is not None and self.bilan.nb_liaisons:
            p.setPen(theme.couleur("texte_secondaire"))
            legende = tr("validation.graphe", solides=self.bilan.nb_solides, liaisons=self.bilan.nb_liaisons, boucles=self.bilan.nb_boucles)
            p.drawText(QRectF(8.0, 4.0, self.width() - 16.0, 18.0), Qt.AlignLeft | Qt.AlignVCenter, legende)
        police.setBold(True)
        p.setFont(police)
        for solide_id, centre in self._sommets.items():
            solide = m.solides[solide_id]
            texte = solide.nom
            largeur = max(p.fontMetrics().horizontalAdvance(texte) + 20.0, 44.0)
            cadre = QRectF(centre.x() - largeur / 2.0, centre.y() - 13.0, largeur, 26.0)
            choisi = selection is not None and selection.genre == "solide" and selection.id == solide_id
            couleur = QColor(solide.couleur)
            p.setPen(QPen(theme.couleur("accent") if choisi else couleur, 2.4 if choisi else 1.6))
            fond = QColor(couleur)
            fond.setAlpha(46)
            p.setBrush(theme.couleur("surface"))
            p.drawRoundedRect(cadre, 13.0, 13.0)
            p.setBrush(fond)
            p.drawRoundedRect(cadre, 13.0, 13.0)
            p.setPen(theme.couleur("texte"))
            p.drawText(cadre, Qt.AlignCenter, texte)
        p.end()

    def mouseMoveEvent(self, evenement) -> None:
        position = evenement.position()
        m = self.doc.mecanisme
        for liaison_id, centre in self._aretes:
            if abs(position.x() - centre.x()) <= 12.0 and abs(position.y() - centre.y()) <= 12.0 and liaison_id in m.liaisons:
                liaison = m.liaisons[liaison_id]
                self.setToolTip(f"{liaison.nom} : {m.solides[liaison.solide_a].nom} – {m.solides[liaison.solide_b].nom}")
                return
        self.setToolTip("")

    def mousePressEvent(self, evenement) -> None:
        position = evenement.position()
        for solide_id, centre in self._sommets.items():
            if abs(position.x() - centre.x()) <= 40.0 and abs(position.y() - centre.y()) <= 14.0:
                self.doc.selectionner(Ref("solide", solide_id))
                return
        for liaison_id, centre in self._aretes:
            if abs(position.x() - centre.x()) <= 36.0 and abs(position.y() - centre.y()) <= 11.0:
                self.doc.selectionner(Ref("liaison", liaison_id))
                return


class PanneauValidation(QWidget):
    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self.bilan_plan: Optional[BilanTopologique] = None
        self.bilan_espace: Optional[BilanTopologique] = None
        self._silence = False

        self.carte_plan = CarteBilan()
        self.carte_espace = CarteBilan()
        self.moteurs = QLabel()
        self.moteurs.setWordWrap(True)
        self.avertissements = QLabel()
        self.avertissements.setWordWrap(True)
        self.avertissements.setProperty("etat", "attention")

        gauche = QWidget()
        colonne = QVBoxLayout(gauche)
        colonne.setContentsMargins(10, 10, 6, 10)
        colonne.setSpacing(8)
        cartes = QHBoxLayout()
        cartes.setSpacing(8)
        cartes.addWidget(self.carte_plan)
        cartes.addWidget(self.carte_espace)
        colonne.addLayout(cartes)
        self.detail = QLabel()
        self.detail.setProperty("role", "secondaire")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        colonne.addWidget(self.detail)
        colonne.addWidget(self.moteurs)
        colonne.addWidget(self.avertissements)
        colonne.addStretch(1)

        self.table = QTableWidget(0, len(COLONNES))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._sur_ligne)

        self.graphe = GrapheLiaisons(document)

        defilement = QScrollArea()
        defilement.setWidgetResizable(True)
        defilement.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        defilement.setWidget(gauche)
        separateur = QSplitter(Qt.Horizontal)
        separateur.addWidget(defilement)
        separateur.addWidget(self.table)
        separateur.addWidget(self.graphe)
        separateur.setStretchFactor(0, 4)
        separateur.setStretchFactor(1, 5)
        separateur.setStretchFactor(2, 3)
        separateur.setSizes([400, 420, 340])
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(separateur)

        self._en_attente = False
        document.modele_change.connect(self._planifier)
        document.selection_change.connect(self._suivre_selection)
        traducteur.abonner(self._planifier)
        self.actualiser()

    def _planifier(self) -> None:
        """Met à jour au prochain tour de boucle (jamais pendant le signal d'une liste du tableau)."""
        if not self._en_attente:
            self._en_attente = True
            QTimer.singleShot(0, self.actualiser)

    def actualiser(self) -> None:
        self._en_attente = False
        m = self.doc.mecanisme
        with np.errstate(all="ignore"):
            self.bilan_plan = analyser_topologie(m, 2)
            self.bilan_espace = analyser_topologie(m, 3)
        plan, espace = self.bilan_plan, self.bilan_espace
        self.carte_plan.afficher(plan)
        self.carte_espace.afficher(espace)
        self.graphe.afficher(plan)
        if plan.nb_liaisons:
            self.detail.setText(detail_du_calcul(plan) + "\n" + detail_du_calcul(espace))
        self.detail.setVisible(plan.nb_liaisons > 0)

        if plan.nb_liaisons == 0:
            self.moteurs.setText(tr("validation.aide_vide"))
        elif plan.mobilite_libre == 0 and plan.mobilite > 0:
            self.moteurs.setText(tr("validation.moteurs.complet", moteurs=plan.nb_moteurs, m=plan.mobilite))
        elif plan.mobilite == 0:
            self.moteurs.setText(tr("validation.moteurs.structure"))
        else:
            self.moteurs.setText(tr("validation.moteurs.libre", moteurs=plan.nb_moteurs, pilotees=plan.mobilite_pilotee, libres=plan.mobilite_libre))

        lignes = []
        for code, parametres in plan.avertissements:
            if code == "aucun_solide" and plan.nb_liaisons == 0:
                continue  # projet vide : le texte d'accueil suffit
            if "solides" in parametres:
                parametres = dict(parametres, solides=", ".join(m.solides[s].nom for s in parametres["solides"] if s in m.solides))
            lignes.append("⚠ " + tr(f"topologie.avertissement.{code}", **parametres))
        if plan.hyperstatisme > 0:
            noms = ", ".join(m.liaisons[l].nom for l in plan.liaisons_hyperstatiques() if l in m.liaisons)
            lignes.append("⚠ " + tr("validation.boucles_hyperstatiques", liaisons=noms))
        self.avertissements.setText("\n".join(lignes))
        self.avertissements.setVisible(bool(lignes))
        self._remplir_table()
        self._suivre_selection()

    def _remplir_table(self) -> None:
        m = self.doc.mecanisme
        plan, espace = self.bilan_plan, self.bilan_espace
        self._silence = True
        self.table.setHorizontalHeaderLabels([tr(f"validation.colonne.{c}") for c in COLONNES])
        for colonne, cle in enumerate(COLONNES):
            self.table.horizontalHeaderItem(colonne).setToolTip(tr(f"validation.colonne_aide.{cle}"))
        self.table.setRowCount(len(plan.liaisons))
        hyperstatiques = set(plan.liaisons_hyperstatiques())
        for ligne, (detail, spatial) in enumerate(zip(plan.liaisons, espace.liaisons)):
            liaison = m.liaisons[detail.id]
            solides = f"{m.solides[detail.solide_a].nom} – {m.solides[detail.solide_b].nom}"
            textes = [
                detail.nom,
                tr(f"liaison.type.{detail.type}"),
                f"{detail.ddl} / {detail.inconnues_statiques}",
                f"{spatial.ddl} / {spatial.inconnues_statiques}",
                "",
            ]
            for colonne, texte in enumerate(textes):
                element = QTableWidgetItem(texte)
                element.setData(Qt.UserRole, detail.id)
                element.setToolTip(solides)
                if colonne in (2, 3):
                    element.setTextAlignment(Qt.AlignCenter)
                if detail.id in hyperstatiques and colonne == 0:
                    element.setForeground(theme.couleur("attention"))
                    element.setToolTip(f"{solides}\n{tr('validation.liaison_hyperstatique')}")
                self.table.setItem(ligne, colonne, element)
            choix = QComboBox()
            for cle in liaison.MODELES_SPATIAUX:
                choix.addItem(tr(f"spatial.{cle}"), cle)
            choix.setCurrentIndex(max(0, choix.findData(liaison.modele_spatial)))
            choix.activated.connect(lambda _, lid=detail.id, c=choix: self._changer_modele(lid, c.currentData()))
            self.table.setCellWidget(ligne, 4, choix)
        self._silence = False

    def _changer_modele(self, liaison_id: str, modele: str) -> None:
        if liaison_id in self.doc.mecanisme.liaisons and self.doc.mecanisme.liaisons[liaison_id].modele_spatial != modele:
            with self.doc.modification():
                self.doc.mecanisme.liaisons[liaison_id].modele_spatial = modele

    def _sur_ligne(self) -> None:
        if self._silence:
            return
        elements = self.table.selectedItems()
        if elements:
            self.doc.selectionner(Ref("liaison", elements[0].data(Qt.UserRole)))

    def _suivre_selection(self) -> None:
        selection = self.doc.selection
        self._silence = True
        self.table.clearSelection()
        if selection is not None and selection.genre == "liaison":
            for ligne in range(self.table.rowCount()):
                element = self.table.item(ligne, 0)
                if element is not None and element.data(Qt.UserRole) == selection.id:
                    self.table.selectRow(ligne)
                    break
        self._silence = False

    def resume(self) -> str:
        """Phrase de synthèse pour la barre d'état."""
        plan = self.bilan_plan
        if plan is None or plan.nb_liaisons == 0:
            return ""
        return tr("validation.resume", m=plan.mobilite, h=plan.hyperstatisme, h3=self.bilan_espace.hyperstatisme)
