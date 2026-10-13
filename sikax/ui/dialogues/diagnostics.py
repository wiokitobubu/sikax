"""Compte rendu de lecture d'un fichier : liste des anomalies rencontrées."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ...fichiers import Rapport
from ...i18n import texte_diagnostic, tr
from ..theme import theme

SYMBOLES = {"erreur": "✕", "avertissement": "⚠", "info": "ℹ"}
JETONS = {"erreur": "erreur", "avertissement": "attention", "info": "texte_secondaire"}


class DialogueDiagnostics(QDialog):
    """Affiche le rapport ; peut proposer d'ouvrir malgré les erreurs."""

    def __init__(self, rapport: Rapport, fichier: str, proposer_ouverture: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("diagnostics.titre"))
        self.resize(720, 440)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(16, 14, 16, 12)
        disposition.setSpacing(10)

        erreurs, avertissements = len(rapport.erreurs), len(rapport.avertissements)
        titre = QLabel(fichier)
        titre.setProperty("role", "titre")
        disposition.addWidget(titre)
        resume = QLabel(tr("diagnostics.resume", erreurs=erreurs, avertissements=avertissements))
        resume.setProperty("role", "secondaire")
        resume.setWordWrap(True)
        disposition.addWidget(resume)

        liste = QListWidget()
        liste.setWordWrap(True)
        ordre = {"erreur": 0, "avertissement": 1, "info": 2}
        for diagnostic in sorted(rapport.diagnostics, key=lambda d: ordre.get(d.niveau, 3)):
            element = QListWidgetItem(f"{SYMBOLES.get(diagnostic.niveau, '•')}  {texte_diagnostic(diagnostic)}")
            element.setForeground(theme.couleur(JETONS.get(diagnostic.niveau, "texte")))
            liste.addItem(element)
        disposition.addWidget(liste, 1)

        if proposer_ouverture:
            explication = QLabel(tr("diagnostics.ouvrir_quand_meme_aide"))
            explication.setWordWrap(True)
            disposition.addWidget(explication)
            boutons = QDialogButtonBox()
            ouvrir = boutons.addButton(tr("diagnostics.ouvrir_quand_meme"), QDialogButtonBox.AcceptRole)
            annuler = boutons.addButton(tr("commun.annuler"), QDialogButtonBox.RejectRole)
            annuler.setDefault(True)
            ouvrir.setAutoDefault(False)
        else:
            boutons = QDialogButtonBox()
            fermer = boutons.addButton(tr("commun.fermer"), QDialogButtonBox.AcceptRole)
            fermer.setDefault(True)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        disposition.addWidget(boutons)
        self.setWindowModality(Qt.WindowModal)
