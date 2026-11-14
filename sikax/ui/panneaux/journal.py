"""Journal : messages du calcul et de la lecture des fichiers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..theme import theme

SYMBOLES = {"info": "ℹ", "succes": "✓", "avertissement": "⚠", "erreur": "✕"}
JETONS = {"info": "texte_secondaire", "succes": "succes", "avertissement": "attention", "erreur": "erreur"}


class PanneauJournal(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.liste = QListWidget()
        self.liste.setWordWrap(True)
        self.liste.setUniformItemSizes(False)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(4, 4, 4, 4)
        disposition.addWidget(self.liste)
        theme.change.connect(self._sur_theme)  # méthode liée : déconnectée d'office à la destruction

    def _sur_theme(self, _nom: str) -> None:
        self._recolorer()

    def ajouter(self, niveau: str, texte: str) -> None:
        heure = datetime.now().strftime("%H:%M:%S")
        element = QListWidgetItem(f"{SYMBOLES.get(niveau, '•')}  {heure}   {texte}")
        element.setData(256, niveau)
        element.setForeground(theme.couleur(JETONS.get(niveau, "texte")))
        self.liste.addItem(element)
        while self.liste.count() > 500:
            self.liste.takeItem(0)
        self.liste.scrollToBottom()

    def _recolorer(self) -> None:
        for i in range(self.liste.count()):
            element = self.liste.item(i)
            element.setForeground(theme.couleur(JETONS.get(element.data(256), "texte")))

    def vider(self) -> None:
        self.liste.clear()

    def textes(self):
        return [self.liste.item(i).text() for i in range(self.liste.count())]
