"""Barre de lecture : parcourt dans le temps les résultats d'une étude."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSlider, QToolButton, QWidget

from ...i18n import tr, traducteur
from ..document import Document
from ..icones import icone
from ..theme import theme

VITESSES = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0)


class BarreLecture(QFrame):
    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self.setProperty("role", "barre")
        self._depart_reel = 0.0
        self._depart_simule = 0.0

        self.debut = QToolButton()
        self.lecture = QToolButton()
        self.fin = QToolButton()
        self.boucle = QToolButton()
        self.boucle.setCheckable(True)
        self.boucle.setChecked(True)
        for bouton in (self.debut, self.lecture, self.fin, self.boucle):
            bouton.setIconSize(QSize(18, 18))
            bouton.setAutoRaise(True)
        self.curseur = QSlider(Qt.Horizontal)
        self.curseur.setRange(0, 0)
        self.temps = QLabel("t = 0.000 s")
        self.temps.setMinimumWidth(150)
        self.vitesse = QComboBox()
        for v in VITESSES:
            self.vitesse.addItem(f"× {v:g}", v)
        self.vitesse.setCurrentIndex(VITESSES.index(1.0))

        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(10, 5, 10, 5)
        disposition.setSpacing(4)
        for composant in (self.debut, self.lecture, self.fin, self.boucle):
            disposition.addWidget(composant)
        disposition.addSpacing(6)
        disposition.addWidget(self.curseur, 1)
        disposition.addSpacing(6)
        disposition.addWidget(self.temps)
        disposition.addWidget(self.vitesse)

        self._minuteur = QTimer(self)
        self._minuteur.setInterval(16)
        self._minuteur.timeout.connect(self._avancer)

        self.lecture.clicked.connect(self.basculer)
        self.debut.clicked.connect(lambda: self._aller(0))
        self.fin.clicked.connect(lambda: self._aller(self.curseur.maximum()))
        self.curseur.valueChanged.connect(self._sur_curseur)
        self.vitesse.activated.connect(lambda _: self._recaler())
        document.resultats_change.connect(self._sur_resultats)
        document.temps_change.connect(self._sur_temps)
        traducteur.abonner(self.traduire)
        theme.change.connect(self._sur_theme)  # méthode liée : déconnectée d'office à la destruction
        self.traduire()
        self._sur_resultats()

    def _sur_theme(self, _nom: str) -> None:
        self._icones()

    @property
    def en_lecture(self) -> bool:
        return self._minuteur.isActive()

    def traduire(self) -> None:
        self.debut.setToolTip(tr("lecteur.debut"))
        self.fin.setToolTip(tr("lecteur.fin"))
        self.boucle.setToolTip(tr("lecteur.boucle"))
        self.vitesse.setToolTip(tr("lecteur.vitesse"))
        self._icones()

    def _icones(self) -> None:
        self.debut.setIcon(icone("debut"))
        self.fin.setIcon(icone("fin"))
        self.boucle.setIcon(icone("boucle"))
        self.lecture.setIcon(icone("pause" if self.en_lecture else "lancer"))
        self.lecture.setToolTip(tr("lecteur.pause") if self.en_lecture else tr("lecteur.lire"))

    def _sur_resultats(self) -> None:
        self.arreter()
        resultats = self.doc.resultats
        anime = resultats is not None and resultats.nb_instants > 1
        self.setVisible(anime)
        self.curseur.blockSignals(True)
        self.curseur.setRange(0, resultats.nb_instants - 1 if anime else 0)
        self.curseur.setValue(0)
        self.curseur.blockSignals(False)
        self._sur_temps(0)

    def _sur_temps(self, indice: int) -> None:
        resultats = self.doc.resultats
        if resultats is None or resultats.nb_instants == 0:
            return
        if self.curseur.value() != indice:
            self.curseur.blockSignals(True)
            self.curseur.setValue(indice)
            self.curseur.blockSignals(False)
        self.temps.setText(f"t = {self.doc.temps:.3f} s  /  {float(resultats.temps[-1]):.3f} s")

    def _sur_curseur(self, valeur: int) -> None:
        self.doc.definir_indice(valeur)
        self._recaler()

    def _aller(self, indice: int) -> None:
        self.doc.definir_indice(indice)
        self._recaler()

    def _recaler(self) -> None:
        """Repart de l'instant affiché (après un saut ou un changement de vitesse)."""
        self._depart_reel = time.perf_counter()
        self._depart_simule = self.doc.temps

    def basculer(self) -> None:
        if self.en_lecture:
            self.arreter()
        else:
            self.lire()

    def lire(self) -> None:
        resultats = self.doc.resultats
        if resultats is None or resultats.nb_instants < 2:
            return
        if self.doc.indice >= resultats.nb_instants - 1:
            self.doc.definir_indice(0)
        self._recaler()
        self._minuteur.start()
        self._icones()

    def arreter(self) -> None:
        self._minuteur.stop()
        self._icones()

    def _avancer(self) -> None:
        resultats = self.doc.resultats
        if resultats is None or resultats.nb_instants < 2:
            self.arreter()
            return
        fin = float(resultats.temps[-1])
        t = self._depart_simule + (time.perf_counter() - self._depart_reel) * float(self.vitesse.currentData())
        if t >= fin:
            if self.boucle.isChecked() and fin > 0.0:
                debut = float(resultats.temps[0])
                t = debut + (t - debut) % (fin - debut)
                self._depart_reel = time.perf_counter()
                self._depart_simule = t
            else:
                self.doc.definir_indice(resultats.nb_instants - 1)
                self.arreter()
                return
        self.doc.definir_indice(resultats.indice_du_temps(t))
