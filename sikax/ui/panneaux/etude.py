"""Panneau de l'étude : type d'analyse, durée, pesanteur et lancement du calcul."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr, traducteur
from ...modele.etude import METHODES, TYPES_ETUDE
from ..aide import bouton_aide
from ..document import Document
from ..icones import icone
from ..theme import theme
from ..widgets.champs import ChampNombre


class PanneauEtude(QWidget):
    lancer = Signal()
    annuler = Signal()
    equilibre = Signal()

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self._en_cours = False

        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.addWidget(zone)
        contenu = QWidget()
        zone.setWidget(contenu)
        disposition = QVBoxLayout(contenu)
        disposition.setContentsMargins(12, 10, 12, 12)
        disposition.setSpacing(8)

        self.titre = QLabel()
        self.titre.setProperty("role", "titre")
        disposition.addWidget(self.titre)

        formulaire = QFormLayout()
        formulaire.setHorizontalSpacing(10)
        formulaire.setVerticalSpacing(6)
        formulaire.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.type = QComboBox()
        self.e_type = QLabel()
        formulaire.addRow(self.e_type, self._avec_aide(self.type, "etudes", "nature"))
        unites = lambda: self.doc.mecanisme.unites  # noqa: E731
        self.duree = ChampNombre("temps", unites, minimum=0.0, strict=True)
        self.e_duree = QLabel()
        formulaire.addRow(self.e_duree, self.duree)
        self.pas = ChampNombre("temps", unites, minimum=0.0, strict=True)
        self.e_pas = QLabel()
        formulaire.addRow(self.e_pas, self.pas)
        self.methode = QComboBox()
        self.e_methode = QLabel()
        self._rangee_methode = self._avec_aide(self.methode, "methodes", "methode")
        formulaire.addRow(self.e_methode, self._rangee_methode)
        self.precision = ChampNombre("sans", unites, minimum=0.0, strict=True)
        self.e_precision = QLabel()
        self._rangee_precision = self._avec_aide(self.precision, "methodes", "precision")
        formulaire.addRow(self.e_precision, self._rangee_precision)
        self._formulaire = formulaire
        disposition.addLayout(formulaire)

        self.description = QLabel()
        self.description.setProperty("role", "secondaire")
        self.description.setWordWrap(True)
        disposition.addWidget(self.description)

        self.inertie = QCheckBox()
        disposition.addWidget(self.inertie)

        self.rubrique_pesanteur = QLabel()
        self.rubrique_pesanteur.setProperty("role", "rubrique")
        disposition.addWidget(self.rubrique_pesanteur)
        self.pesanteur = QCheckBox()
        disposition.addWidget(self.pesanteur)
        gravite = QFormLayout()
        gravite.setHorizontalSpacing(10)
        gravite.setVerticalSpacing(6)
        gravite.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.gx = ChampNombre("sans", unites)  # toujours en m/s², quelle que soit l'unité de longueur
        self.gy = ChampNombre("sans", unites)
        self.e_gx, self.e_gy = QLabel("gx (m/s²)"), QLabel("gy (m/s²)")
        gravite.addRow(self.e_gx, self.gx)
        gravite.addRow(self.e_gy, self.gy)
        disposition.addLayout(gravite)

        self.bouton = QPushButton()
        self.bouton.setProperty("principal", True)
        self.bouton.setMinimumHeight(34)
        disposition.addSpacing(6)
        disposition.addWidget(self.bouton)
        self.progression = QProgressBar()
        self.progression.setRange(0, 1000)
        self.progression.setTextVisible(False)
        self.progression.setVisible(False)
        disposition.addWidget(self.progression)
        self.bouton_equilibre = QPushButton()
        disposition.addWidget(self.bouton_equilibre)

        self.bilan = QLabel()
        self.bilan.setWordWrap(True)
        self.bilan.setTextInteractionFlags(Qt.TextSelectableByMouse)
        disposition.addWidget(self.bilan)
        disposition.addStretch(1)

        for etiquette in (self.e_type, self.e_duree, self.e_pas, self.e_gx, self.e_gy, self.e_methode, self.e_precision):
            etiquette.setProperty("role", "secondaire")

        etude = lambda: self.doc.mecanisme.etude  # noqa: E731
        self.type.activated.connect(lambda _: self._ecrire(lambda: setattr(etude(), "type", self.type.currentData())))
        self.methode.activated.connect(lambda _: self._ecrire(lambda: setattr(etude(), "methode", self.methode.currentData())))
        self.precision.modifie.connect(lambda v: self._ecrire(lambda: setattr(etude(), "precision", min(max(v, 1e-12), 1e-2))))
        self.duree.modifie.connect(lambda v: self._ecrire(lambda: setattr(etude(), "duree", v)))
        self.pas.modifie.connect(lambda v: self._ecrire(lambda: setattr(etude(), "pas", v)))
        self.gx.modifie.connect(lambda v: self._ecrire(lambda: setattr(etude(), "gx", v)))
        self.gy.modifie.connect(lambda v: self._ecrire(lambda: setattr(etude(), "gy", v)))
        self.pesanteur.clicked.connect(lambda etat: self._ecrire(lambda: setattr(etude(), "pesanteur", bool(etat))))
        self.inertie.clicked.connect(lambda etat: self._ecrire(lambda: setattr(etude(), "inertie", bool(etat))))
        self.bouton.clicked.connect(self._sur_bouton)
        self.bouton_equilibre.clicked.connect(lambda: self.equilibre.emit())

        document.modele_change.connect(self.actualiser)
        traducteur.abonner(self.traduire)
        theme.change.connect(lambda _: self._icones())
        self.traduire()

    @staticmethod
    def _avec_aide(composant: QWidget, fiche: str, section: str) -> QWidget:
        rangee = QWidget()
        boite = QHBoxLayout(rangee)
        boite.setContentsMargins(0, 0, 0, 0)
        boite.setSpacing(2)
        boite.addWidget(composant, 1)
        boite.addWidget(bouton_aide(fiche, section))
        return rangee

    def _ecrire(self, operation) -> None:
        with self.doc.modification():
            operation()

    def _sur_bouton(self) -> None:
        if self._en_cours:
            self.annuler.emit()
        else:
            self.lancer.emit()

    def traduire(self) -> None:
        self.titre.setText(tr("etude.titre"))
        self.e_type.setText(tr("etude.nature"))
        self.e_duree.setText(f"{tr('etude.duree')} (s)")
        self.e_pas.setText(f"{tr('etude.pas')} (s)")
        self.inertie.setText(tr("etude.inertie"))
        self.inertie.setToolTip(tr("etude.inertie_aide"))
        self.rubrique_pesanteur.setText(tr("etude.pesanteur"))
        self.pesanteur.setText(tr("etude.pesanteur_active"))
        self.bouton_equilibre.setText(tr("etude.equilibre"))
        self.bouton_equilibre.setToolTip(tr("etude.equilibre_aide"))
        self.e_methode.setText(tr("etude.methode"))
        self.e_precision.setText(tr("etude.precision"))
        self.precision.setToolTip(tr("etude.precision_aide"))
        choisie = self.methode.currentData()
        self.methode.clear()
        for methode in METHODES:
            self.methode.addItem(tr(f"etude.methodes.{methode}"), methode)
        if choisie is not None:
            self.methode.setCurrentIndex(max(0, self.methode.findData(choisie)))
        courant = self.type.currentData()
        self.type.clear()
        for nature in TYPES_ETUDE:
            self.type.addItem(tr(f"etude.type.{nature}"), nature)
        if courant is not None:
            self.type.setCurrentIndex(max(0, self.type.findData(courant)))
        self._icones()
        self.actualiser()

    def _icones(self) -> None:
        self.bouton.setIcon(icone("stop" if self._en_cours else "lancer", couleur=theme.hex("accent_texte")))
        self.bouton_equilibre.setIcon(icone("equilibre"))

    def actualiser(self) -> None:
        etude = self.doc.mecanisme.etude
        indice = self.type.findData(etude.type)
        if indice >= 0 and indice != self.type.currentIndex():
            self.type.setCurrentIndex(indice)
        for champ, valeur in ((self.duree, etude.duree), (self.pas, etude.pas), (self.gx, etude.gx), (self.gy, etude.gy), (self.precision, etude.precision)):
            if not (champ.hasFocus() and champ.isModified()):
                champ.definir(valeur)
        indice = self.methode.findData(etude.methode)
        if indice >= 0 and indice != self.methode.currentIndex():
            self.methode.setCurrentIndex(indice)
        dynamique = etude.type == "dynamique"
        for composant in (self.e_methode, self._rangee_methode, self.e_precision, self._rangee_precision):
            composant.setVisible(dynamique)
        self.pesanteur.setChecked(etude.pesanteur)
        self.inertie.setChecked(etude.inertie)
        temporel = etude.type != "statique"
        self.duree.setEnabled(temporel)
        self.pas.setEnabled(temporel)
        self.inertie.setVisible(etude.type == "cinematique")
        self.gx.setEnabled(etude.pesanteur)
        self.gy.setEnabled(etude.pesanteur)
        self.description.setText(tr(f"etude.description.{etude.type}"))
        if not self._en_cours:
            self.bouton.setText(tr("etude.lancer"))

    # ------------------------------------------------------------ état du calcul
    def calcul_en_cours(self, en_cours: bool) -> None:
        self._en_cours = en_cours
        self.progression.setVisible(en_cours)
        self.progression.setValue(0)
        self.bouton.setText(tr("etude.arreter") if en_cours else tr("etude.lancer"))
        self.bouton.setProperty("principal", not en_cours)
        self.bouton.style().unpolish(self.bouton)
        self.bouton.style().polish(self.bouton)
        self.bouton_equilibre.setEnabled(not en_cours)
        self._icones()

    def avancement(self, fraction: float) -> None:
        self.progression.setValue(int(1000 * max(0.0, min(1.0, fraction))))

    def afficher_bilan(self, texte: str, etat: str = "") -> None:
        self.bilan.setText(texte)
        self.bilan.setProperty("etat", etat)
        self.bilan.style().unpolish(self.bilan)
        self.bilan.style().polish(self.bilan)
