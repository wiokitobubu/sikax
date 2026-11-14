"""Aide contextuelle : boutons « ? » et ouverture des fiches de cours.

Chaque option importante de l'interface porte un petit bouton « ? ». Son
infobulle donne la définition en deux lignes ; un clic ouvre la fiche de
cours correspondante dans le panneau « Cours », à la bonne section.

Les panneaux ne connaissent pas le panneau des cours : ils émettent
``aide.ouvrir(fiche, section)`` et la fenêtre principale fait le reste.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtWidgets import QToolButton

from ..i18n import tr, traducteur
from .icones import icone


class _Aide(QObject):
    ouvrir = Signal(str, str)
    """Demande d'affichage d'une fiche de cours : (identifiant de fiche, section)."""


aide = _Aide()


def bouton_aide(fiche: str, section: str = "") -> QToolButton:
    """Bouton « ? » : infobulle ``aide.<fiche>.<section>`` (ou le résumé de la fiche), clic → fiche."""
    bouton = QToolButton()
    bouton.setProperty("role", "aide")
    bouton.setAutoRaise(True)
    bouton.setCursor(Qt.PointingHandCursor)
    bouton.setFocusPolicy(Qt.NoFocus)
    bouton.setIconSize(QSize(15, 15))
    bouton.setIcon(icone("aide", "accent", 15))

    def traduire() -> None:
        cle = f"aide.{fiche}.{section}" if section else ""
        texte = tr(cle) if cle and traducteur.existe(cle) else tr(f"cours.resume.{fiche}")
        bouton.setToolTip(f"<p style='max-width: 320px'>{texte}</p><p><i>{tr('aide.clic_pour_le_cours')}</i></p>")

    traduire()
    bouton.clicked.connect(lambda: aide.ouvrir.emit(fiche, section))
    bouton.setObjectName(f"aide_{fiche}_{section}" if section else f"aide_{fiche}")
    return bouton
