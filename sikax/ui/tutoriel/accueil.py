"""Fenêtre de bienvenue : « Es-tu nouveau sur Sikax ? »

Deux grands boutons : découvrir l'application avec le tutoriel, ou aller
directement au travail. Une case permet de ne plus poser la question ; le
tutoriel reste accessible dans Aide → Tutoriel (F1).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import __app_name__, __version__
from ...chemins import icone_application
from ...i18n import tr
from ..icones import icone
from ..theme import theme


class DialogueAccueil(QDialog):
    NOUVEAU = "nouveau"
    HABITUE = "habitue"

    def __init__(self, parent: Optional[QWidget] = None, deja_masque: bool = False) -> None:
        super().__init__(parent)
        self.choix: Optional[str] = None
        self.setWindowTitle(tr("accueil_dialogue.fenetre", nom=__app_name__))
        self.setModal(True)
        self.setMinimumWidth(560)

        logo = QLabel()
        logo.setPixmap(QIcon(str(icone_application())).pixmap(64, 64))
        titre = QLabel(tr("accueil_dialogue.titre", nom=__app_name__))
        police = titre.font()
        police.setPointSizeF(police.pointSizeF() + 7.0)
        police.setBold(True)
        titre.setFont(police)
        version = QLabel(tr("accueil_dialogue.version", version=__version__))
        version.setProperty("role", "secondaire")
        question = QLabel(tr("accueil_dialogue.question"))
        police = question.font()
        police.setPointSizeF(police.pointSizeF() + 3.0)
        question.setFont(police)

        self.bouton_nouveau = self._grand_bouton("tutoriel", tr("accueil_dialogue.nouveau"), tr("accueil_dialogue.nouveau_detail"))
        self.bouton_nouveau.setProperty("principal", True)
        self.bouton_habitue = self._grand_bouton("selection", tr("accueil_dialogue.habitue"), tr("accueil_dialogue.habitue_detail"))
        self.bouton_nouveau.clicked.connect(lambda: self._choisir(self.NOUVEAU))
        self.bouton_habitue.clicked.connect(lambda: self._choisir(self.HABITUE))
        self.case = QCheckBox(tr("accueil_dialogue.ne_plus_demander"))
        self.case.setChecked(deja_masque)
        note = QLabel(tr("accueil_dialogue.note"))
        note.setProperty("role", "secondaire")
        note.setWordWrap(True)

        entete = QHBoxLayout()
        entete.setSpacing(14)
        entete.addWidget(logo, 0, Qt.AlignTop)
        textes = QVBoxLayout()
        textes.setSpacing(2)
        textes.addWidget(titre)
        textes.addWidget(version)
        entete.addLayout(textes, 1)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(26, 24, 26, 20)
        disposition.setSpacing(14)
        disposition.addLayout(entete)
        disposition.addSpacing(4)
        disposition.addWidget(question)
        disposition.addWidget(self.bouton_nouveau)
        disposition.addWidget(self.bouton_habitue)
        disposition.addSpacing(4)
        disposition.addWidget(self.case)
        disposition.addWidget(note)
        self.bouton_nouveau.setFocus()

    @property
    def ne_plus_demander(self) -> bool:
        return self.case.isChecked()

    def _grand_bouton(self, pictogramme: str, texte: str, detail: str) -> QPushButton:
        bouton = QPushButton(f"{texte}\n{detail}")
        bouton.setIcon(icone(pictogramme, couleur=theme.hex("accent_texte") if pictogramme == "tutoriel" else None, taille=28))
        bouton.setIconSize(QSize(28, 28))
        bouton.setMinimumHeight(64)
        bouton.setStyleSheet("QPushButton { text-align: left; padding: 10px 16px; }")
        bouton.setCursor(Qt.PointingHandCursor)
        return bouton

    def _choisir(self, choix: str) -> None:
        self.choix = choix
        self.accept()
