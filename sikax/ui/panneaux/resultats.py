"""Tableau des efforts à l'instant affiché : torseurs de liaison et efforts moteurs."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ...i18n import tr, traducteur
from ..document import Document, Ref
from ..widgets.champs import formater

COLONNES = ("element", "nature", "solides", "X", "Y", "N", "R", "")

# Une composante un milliard de fois plus petite que la plus grande est du bruit d'arrondi.
BRUIT = 1e-9


class PanneauResultats(QWidget):
    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self._silence = False
        self.entete = QLabel()
        self.entete.setProperty("role", "secondaire")
        self.entete.setWordWrap(True)
        self.entete.setContentsMargins(10, 8, 10, 4)
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
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self.entete)
        disposition.addWidget(self.table)

        document.resultats_change.connect(self.reconstruire)
        document.temps_change.connect(lambda _: self.actualiser())
        document.modele_change.connect(self.reconstruire)
        traducteur.abonner(self.reconstruire)
        self.reconstruire()

    def reconstruire(self) -> None:
        doc = self.doc
        m = doc.mecanisme
        unites = m.unites
        resultats = doc.resultats
        force, moment = unites.symbole("force"), unites.symbole("moment")
        titres = {
            "element": tr("resultats.colonne.element"),
            "nature": tr("resultats.colonne.nature"),
            "solides": tr("resultats.colonne.solides"),
            "X": f"X ({force})",
            "Y": f"Y ({force})",
            "N": f"N ({moment})",
            "R": f"‖R‖ ({force})",
            "": "",
        }
        self.table.setHorizontalHeaderLabels([titres[c] for c in COLONNES])
        self._lignes = []
        if resultats is None or not any(c.endswith("/X") for c in resultats.canaux):
            self.table.setRowCount(0)
            self.entete.setText(tr("resultats.vide"))
            return
        for liaison in m.liaisons.values():
            if f"liaison/{liaison.id}/X" in resultats.canaux:
                a, b = m.solides[liaison.solide_a].nom, m.solides[liaison.solide_b].nom
                self._lignes.append(("liaison", liaison.id, liaison.nom, tr(f"liaison.type.{liaison.type}"), f"{a} → {b}"))
        for moteur in m.moteurs.values():
            if f"moteur/{moteur.id}/effort" in resultats.canaux:
                liaison = m.liaisons.get(moteur.liaison)
                self._lignes.append(("moteur", moteur.id, moteur.nom, tr("resultats.moteur"), liaison.nom if liaison else ""))
        self._silence = True
        self.table.setRowCount(len(self._lignes))
        for ligne, (genre, identifiant, nom, nature, solides) in enumerate(self._lignes):
            for colonne, texte in enumerate((nom, nature, solides, "", "", "", "", "")):
                element = QTableWidgetItem(texte)
                element.setData(Qt.UserRole, (genre, identifiant))
                if 3 <= colonne <= 6:
                    element.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(ligne, colonne, element)
        self._silence = False
        self.actualiser()

    def actualiser(self) -> None:
        doc = self.doc
        resultats = doc.resultats
        if resultats is None or not getattr(self, "_lignes", None):
            return
        m = doc.mecanisme
        i = doc.indice
        if resultats.nb_instants > 1:
            self.entete.setText(tr("resultats.entete_instant", t=f"{doc.temps:.4g}"))
        else:
            self.entete.setText(tr("resultats.entete_statique"))
        lignes = []
        for genre, identifiant, *_reste in self._lignes:
            if genre == "liaison":
                base = f"liaison/{identifiant}/"
                lignes.append([resultats.valeur(base + g, i) for g in ("X", "Y", "N", "R")])
            else:
                moteur = m.moteurs.get(identifiant)
                liaison = m.liaisons.get(moteur.liaison) if moteur else None
                effort = resultats.valeur(f"moteur/{identifiant}/effort", i)
                rotation = liaison is None or liaison.PILOTAGE == "rotation"
                lignes.append([None, None, effort, None] if rotation else [None, None, None, effort])
        # forces et moments n'ont pas la même unité : un plancher de bruit pour chacun
        plancher_force = BRUIT * max((abs(v) for l in lignes for v in (l[0], l[1], l[3]) if v is not None), default=0.0)
        plancher_moment = BRUIT * max((abs(l[2]) for l in lignes if l[2] is not None), default=0.0)
        for ligne, valeurs in enumerate(lignes):
            for colonne, valeur in zip((3, 4, 5, 6), valeurs):
                element = self.table.item(ligne, colonne)
                if element is None:
                    continue
                if valeur is None:
                    element.setText("")
                    continue
                plancher = plancher_moment if colonne == 5 else plancher_force
                element.setText(formater(float(f"{(0.0 if abs(valeur) <= plancher else valeur):.5g}")))

    def _sur_ligne(self) -> None:
        if self._silence:
            return
        elements = self.table.selectedItems()
        if elements:
            genre, identifiant = elements[0].data(Qt.UserRole)
            self.doc.selectionner(Ref(genre, identifiant))
