"""Boîte « À propos »."""

from __future__ import annotations

import platform
from typing import Optional

import numpy
from PySide6 import __version__ as version_pyside
from PySide6.QtCore import Qt, qVersion
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ... import __app_name__, __version__
from ...chemins import trouver
from ...i18n import tr


class DialogueAPropos(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("a_propos.titre", nom=__app_name__))
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(22, 20, 22, 14)
        disposition.setSpacing(12)

        entete = QHBoxLayout()
        entete.setSpacing(16)
        logo = QLabel()
        image = QPixmap(str(trouver("resources", "icons", "sikax.png")))
        if not image.isNull():
            logo.setPixmap(image.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        entete.addWidget(logo)
        titres = QVBoxLayout()
        nom = QLabel(__app_name__)
        nom.setStyleSheet("font-size: 26px; font-weight: 700;")
        titres.addWidget(nom)
        version = QLabel(tr("a_propos.version", version=__version__))
        version.setProperty("role", "secondaire")
        titres.addWidget(version)
        entete.addLayout(titres, 1)
        disposition.addLayout(entete)

        description = QLabel(tr("a_propos.description"))
        description.setWordWrap(True)
        description.setMinimumWidth(420)
        disposition.addWidget(description)
        credits = QLabel(tr("a_propos.credits"))
        credits.setWordWrap(True)
        credits.setProperty("role", "secondaire")
        disposition.addWidget(credits)
        technique = QLabel(
            f"Python {platform.python_version()} · Qt {qVersion()} · PySide6 {version_pyside} · NumPy {numpy.__version__}"
        )
        technique.setProperty("role", "secondaire")
        technique.setTextInteractionFlags(Qt.TextSelectableByMouse)
        disposition.addWidget(technique)

        boutons = QDialogButtonBox()
        boutons.addButton(tr("commun.fermer"), QDialogButtonBox.AcceptRole)
        boutons.accepted.connect(self.accept)
        disposition.addWidget(boutons)
