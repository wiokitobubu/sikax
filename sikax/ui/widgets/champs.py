"""Champs de saisie conscients des unités.

``ChampNombre`` affiche une grandeur dans l'unité choisie par l'utilisateur
(mm, degrés…) alors que le modèle la conserve en SI. Il accepte la virgule
ou le point décimal et, si on l'y autorise, une expression du temps.
"""

from __future__ import annotations

from typing import Callable, Optional, Union

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

from ...i18n import tr
from ...physique.unites import Unites
from ...util.expression import ErreurExpression, vers_nombre_ou_expression

Valeur = Union[float, str]


def formater(valeur: float) -> str:
    """Écriture courte d'un nombre : jusqu'à 7 chiffres significatifs, sans zéros inutiles."""
    if valeur == 0.0:
        return "0"
    return f"{valeur:.7g}"


class ChampNombre(QLineEdit):
    """Champ numérique. Émet ``modifie`` avec la valeur en SI (ou le texte d'une expression)."""

    modifie = Signal(object)

    def __init__(
        self,
        dimension: str,
        unites: Callable[[], Unites],
        expression: bool = False,
        minimum: Optional[float] = None,
        strict: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.dimension = dimension
        self._unites = unites
        self._expression = expression
        self._minimum = minimum
        self._strict = strict
        self._valeur: Valeur = 0.0
        self.editingFinished.connect(self._valider)
        if expression:
            self.setPlaceholderText(tr("champ.expression_admise"))

    def symbole(self) -> str:
        return self._unites().symbole(self.dimension)

    def definir(self, valeur: Valeur) -> None:
        """Affiche une valeur du modèle (SI) sans émettre de signal."""
        self._valeur = valeur
        if isinstance(valeur, str):
            texte = valeur
        else:
            texte = formater(self._unites().vers_affichage(float(valeur), self.dimension))
        if texte != self.text():
            self.setText(texte)
        self._marquer(False)

    def valeur(self) -> Valeur:
        return self._valeur

    def _marquer(self, invalide: bool, message: str = "") -> None:
        if bool(self.property("invalide")) != invalide:
            self.setProperty("invalide", invalide)
            self.style().unpolish(self)
            self.style().polish(self)
        self.setToolTip(message)

    def _valider(self) -> None:
        texte = self.text().strip()
        try:
            saisie = vers_nombre_ou_expression(texte)
        except ErreurExpression as exc:
            self._marquer(True, str(exc))
            return
        if isinstance(saisie, str):
            if not self._expression:
                self._marquer(True, tr("champ.nombre_attendu"))
                return
            nouvelle: Valeur = saisie
        else:
            nouvelle = self._unites().depuis_affichage(saisie, self.dimension)
            if self._minimum is not None and (nouvelle < self._minimum or (self._strict and nouvelle <= self._minimum)):
                self._marquer(True, tr("champ.valeur_trop_petite"))
                return
        self._marquer(False)
        if nouvelle != self._valeur:
            self._valeur = nouvelle
            self.modifie.emit(nouvelle)
        elif isinstance(nouvelle, float):
            self.definir(nouvelle)  # remet en forme la saisie (« 1,50 » → « 1.5 »)


class ChampTexte(QLineEdit):
    """Champ de texte qui émet ``modifie`` à la validation, seulement si le texte a changé."""

    modifie = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._valeur = ""
        self.editingFinished.connect(self._valider)

    def definir(self, texte: str) -> None:
        self._valeur = texte
        if texte != self.text():
            self.setText(texte)

    def _valider(self) -> None:
        texte = self.text().strip()
        if texte != self._valeur:
            self._valeur = texte
            self.modifie.emit(texte)


class ZoneTexte(QPlainTextEdit):
    """Texte sur plusieurs lignes ; émet ``modifie`` quand on quitte la zone après un changement."""

    modifie = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._valeur = ""

    def definir(self, texte: str) -> None:
        self._valeur = texte
        if texte != self.toPlainText():
            self.setPlainText(texte)

    def focusOutEvent(self, evenement) -> None:
        texte = self.toPlainText().strip()
        if texte != self._valeur:
            self._valeur = texte
            self.modifie.emit(texte)
        super().focusOutEvent(evenement)
