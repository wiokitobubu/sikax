"""Détection des formes d'une photo de schéma : aperçu réglable, puis création des solides."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from ...modele.fond import FondPlan
from ...vision import Detection, detecter


class Apercu(QLabel):
    """La photo, réduite, avec les traits (orange) et les cercles (bleu) détectés par-dessus."""

    def __init__(self, image: QImage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.image = image
        self.detection: Optional[Detection] = None
        self.setMinimumSize(560, 360)
        self.setAlignment(Qt.AlignCenter)

    def afficher(self, detection: Optional[Detection]) -> None:
        self.detection = detection
        self._dessiner()

    def resizeEvent(self, evenement) -> None:
        self._dessiner()
        super().resizeEvent(evenement)

    def _dessiner(self) -> None:
        if self.image.isNull():
            return
        cible = self.size()
        image = self.image.scaled(cible, Qt.KeepAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_ARGB32)
        facteur = image.width() / max(self.image.width(), 1)
        p = QPainter(image)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(image.rect(), QColor(255, 255, 255, 60))
        if self.detection is not None:
            p.setPen(QPen(QColor("#F97316"), 3.0))
            for segment in self.detection.segments:
                p.drawLine(QPointF(segment.a[0] * facteur, segment.a[1] * facteur), QPointF(segment.b[0] * facteur, segment.b[1] * facteur))
            for cercle in self.detection.cercles:
                disque = cercle.rayon > self.detection.seuil_disque()
                p.setPen(QPen(QColor("#2563EB" if disque else "#16A34A"), 2.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cercle.centre[0] * facteur, cercle.centre[1] * facteur), cercle.rayon * facteur, cercle.rayon * facteur)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#DC2626"))
            for segment in self.detection.segments:
                for x, y in (segment.a, segment.b):
                    p.drawEllipse(QPointF(x * facteur, y * facteur), 3.5, 3.5)
        p.end()
        self.setPixmap(QPixmap.fromImage(image))


class DialogueDetection(QDialog):
    """Réglage de la détection ; ``accept`` signifie : créer les solides cochés."""

    def __init__(self, fond: FondPlan, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.fond = fond
        self.detection: Optional[Detection] = None
        self.setWindowTitle(tr("detection.titre"))
        image = QImage()
        image.loadFromData(fond.donnees)
        self.apercu = Apercu(image)
        self.sensibilite = QSlider(Qt.Horizontal)
        self.sensibilite.setRange(0, 100)
        self.sensibilite.setValue(40)
        self.longueur = QSlider(Qt.Horizontal)
        self.longueur.setRange(2, 30)
        self.longueur.setValue(6)
        self.barres = QCheckBox(tr("detection.barres"))
        self.barres.setChecked(True)
        self.disques = QCheckBox(tr("detection.disques"))
        self.disques.setChecked(True)
        self.pivots = QCheckBox(tr("detection.pivots"))
        self.pivots.setToolTip(tr("detection.pivots_aide"))
        self.bilan = QLabel()
        self.bilan.setProperty("role", "secondaire")
        self.bilan.setWordWrap(True)
        explication = QLabel(tr("detection.explication"))
        explication.setWordWrap(True)
        explication.setProperty("role", "secondaire")

        formulaire = QFormLayout()
        formulaire.addRow(tr("detection.sensibilite"), self.sensibilite)
        formulaire.addRow(tr("detection.longueur_min"), self.longueur)
        cases = QHBoxLayout()
        for case in (self.barres, self.disques, self.pivots):
            cases.addWidget(case)
        cases.addStretch(1)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.button(QDialogButtonBox.Ok).setText(tr("detection.creer"))
        boutons.button(QDialogButtonBox.Cancel).setText(tr("commun.annuler"))
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        self._ok = boutons.button(QDialogButtonBox.Ok)

        disposition = QVBoxLayout(self)
        disposition.addWidget(explication)
        disposition.addWidget(self.apercu, 1)
        disposition.addLayout(formulaire)
        disposition.addLayout(cases)
        disposition.addWidget(self.bilan)
        disposition.addWidget(boutons)

        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(180)
        self._minuteur.timeout.connect(self.analyser)
        self.sensibilite.valueChanged.connect(lambda _: self._minuteur.start())
        self.longueur.valueChanged.connect(lambda _: self._minuteur.start())
        self.analyser()

    def analyser(self) -> None:
        """Relance la détection avec les réglages courants et met l'aperçu à jour."""
        try:
            self.detection = detecter(self.fond.donnees, self.sensibilite.value() / 100.0, self.longueur.value() / 100.0)
        except (ValueError, ImportError) as erreur:
            self.detection = None
            self.bilan.setText(tr("detection.echec", message=str(erreur)))
            self._ok.setEnabled(False)
            self.apercu.afficher(None)
            return
        d = self.detection
        self.bilan.setText(tr("detection.bilan", traits=len(d.segments), disques=len(d.disques()), articulations=len(d.articulations())))
        self._ok.setEnabled(bool(d.segments or d.cercles))
        self.apercu.afficher(d)
