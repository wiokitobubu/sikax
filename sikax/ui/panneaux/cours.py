"""Fiches de cours intégrées : les notions de mécanique utiles pour comprendre Sikax.

Les fiches sont des pages HTML de ``resources/cours/<langue>/`` (à défaut,
celles en français) : on peut les corriger ou les compléter sans toucher au
programme. Les figures sont dessinées par ``sikax.ui.cours_figures`` et
insérées dans le document sous les adresses ``figure:<nom>``, aux couleurs du
thème. Chaque section d'une fiche porte une ancre (``<a name="...">``) : le
bouton « ? » d'une option ouvre la fiche à la bonne section.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from ...chemins import dossier_cours
from ...i18n import tr, traducteur
from ..icones import icone
from ..theme import theme
from .. import cours_figures

FICHES = (
    "etudes",
    "moment",
    "couple_moteur",
    "torseur",
    "centre_gravite",
    "inertie",
    "excentricite",
    "ddl",
    "isostatisme",
    "engrenages",
    "points_morts",
    "methodes",
)
"""Fiches de cours, dans l'ordre du sommaire."""

ROLE_FICHE = Qt.UserRole + 1


def fichier_de_fiche(fiche: str, langue: str) -> Optional[Path]:
    """Page HTML d'une fiche dans la langue demandée, sinon en français."""
    for code in (langue, "fr"):
        chemin = dossier_cours() / code / f"{fiche}.html"
        if chemin.is_file():
            return chemin
    return None


class PanneauCours(QWidget):
    """Sommaire des fiches et lecteur de la fiche choisie."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.fiche = FICHES[0]
        self.sommaire = QListWidget()
        self.sommaire.setMaximumHeight(170)
        self.sommaire.currentItemChanged.connect(self._sur_choix)
        self.lecteur = QTextBrowser()
        self.lecteur.setOpenExternalLinks(False)
        self.lecteur.setOpenLinks(False)
        self.lecteur.anchorClicked.connect(self._sur_lien)
        self.lecteur.setProperty("role", "cours")
        self.introduction = QLabel()
        self.introduction.setProperty("role", "secondaire")
        self.introduction.setWordWrap(True)

        separateur = QSplitter(Qt.Vertical)
        separateur.addWidget(self.sommaire)
        separateur.addWidget(self.lecteur)
        separateur.setStretchFactor(1, 1)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(8, 8, 8, 8)
        disposition.setSpacing(6)
        disposition.addWidget(self.introduction)
        disposition.addWidget(separateur, 1)

        traducteur.abonner(self.traduire)
        theme.change.connect(lambda _: self.afficher(self.fiche))
        self.traduire()

    def traduire(self) -> None:
        self.introduction.setText(tr("cours.introduction"))
        self.sommaire.blockSignals(True)
        self.sommaire.clear()
        for fiche in FICHES:
            element = QListWidgetItem(icone("cours", taille=16), tr(f"cours.fiche.{fiche}"))
            element.setData(ROLE_FICHE, fiche)
            element.setToolTip(tr(f"cours.resume.{fiche}"))
            self.sommaire.addItem(element)
        self.sommaire.blockSignals(False)
        self.afficher(self.fiche)

    def _sur_choix(self, courant: Optional[QListWidgetItem], _precedent) -> None:
        if courant is not None:
            self.afficher(courant.data(ROLE_FICHE))

    def _sur_lien(self, url: QUrl) -> None:
        """Lien interne ``fiche:<nom>#<section>`` vers une autre fiche, ou ancre de la page."""
        if url.scheme() == "fiche":
            self.afficher(url.path(), url.fragment())
        elif url.hasFragment() and not url.path():
            self.lecteur.scrollToAnchor(url.fragment())

    def afficher(self, fiche: str, section: str = "") -> None:
        """Montre une fiche, à la section demandée s'il y en a une."""
        if fiche not in FICHES:
            fiche = FICHES[0]
        self.fiche = fiche
        for i in range(self.sommaire.count()):
            if self.sommaire.item(i).data(ROLE_FICHE) == fiche and self.sommaire.currentRow() != i:
                self.sommaire.blockSignals(True)
                self.sommaire.setCurrentRow(i)
                self.sommaire.blockSignals(False)
        document = QTextDocument(self.lecteur)
        document.setDefaultStyleSheet(self._style())
        for nom, image in cours_figures.figures().items():
            document.addResource(QTextDocument.ImageResource, QUrl(f"figure:{nom}"), image)
        chemin = fichier_de_fiche(fiche, traducteur.langue)
        texte = chemin.read_text(encoding="utf-8") if chemin is not None else f"<h1>{tr(f'cours.fiche.{fiche}')}</h1>"
        document.setHtml(texte)
        self.lecteur.setDocument(document)
        if section:
            self.lecteur.scrollToAnchor(section)
        else:
            self.lecteur.verticalScrollBar().setValue(0)

    def sections(self, fiche: str) -> List[str]:
        """Ancres présentes dans une fiche (pour les tests de cohérence)."""
        chemin = fichier_de_fiche(fiche, traducteur.langue)
        if chemin is None:
            return []
        import re

        return re.findall(r'<a name="([^"]+)"', chemin.read_text(encoding="utf-8"))

    @staticmethod
    def _style() -> str:
        c = theme.hex
        return f"""
            body {{ color: {c('texte')}; font-size: 10.5pt; }}
            h1 {{ color: {c('accent')}; font-size: 15pt; margin-bottom: 4px; }}
            h2 {{ color: {c('texte')}; font-size: 12pt; margin-top: 14px; margin-bottom: 3px; border-bottom: 1px solid {c('bordure')}; }}
            h3 {{ color: {c('texte_secondaire')}; font-size: 10.5pt; margin-top: 8px; }}
            p, li {{ line-height: 135%; }}
            .formule {{ background-color: {c('surface_haute')}; color: {c('texte')}; padding: 6px; font-family: 'Cambria Math', 'STIX Two Math', 'DejaVu Serif', serif; font-size: 11.5pt; }}
            .remarque {{ color: {c('texte_secondaire')}; }}
            .sikax {{ background-color: {c('selection')}; color: {c('texte')}; padding: 6px; }}
            table {{ border-collapse: collapse; }}
            th {{ background-color: {c('surface_haute')}; color: {c('texte')}; padding: 3px 6px; border: 1px solid {c('bordure')}; }}
            td {{ padding: 3px 6px; border: 1px solid {c('bordure')}; }}
            a {{ color: {c('accent')}; }}
        """
