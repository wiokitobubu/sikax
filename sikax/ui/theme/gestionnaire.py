"""Thèmes clair et sombre.

Un thème est une *palette* de couleurs nommées (``fenetre``, ``accent``,
``canevas``, ``force``…). Elle alimente trois choses à la fois :

- la feuille de style Qt, générée depuis ``resources/themes/style.qss`` en
  remplaçant chaque jeton ``{{nom}}`` par sa couleur ;
- la ``QPalette`` de l'application (couleurs des composants natifs) ;
- les dessins faits à la main (schéma cinématique, courbes), qui demandent
  leurs couleurs avec ``theme.couleur("force")``.

Les palettes par défaut sont ci-dessous ; un fichier ``clair.json`` ou
``sombre.json`` présent dans ``resources/themes`` les remplace, ce qui permet
de retoucher les couleurs sans modifier le code.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from ...chemins import dossier_icones, dossier_themes

PALETTES: Dict[str, Dict[str, str]] = {
    "clair": {
        "fenetre": "#EEF0F4", "surface": "#FFFFFF", "surface_haute": "#F3F5F9", "survol": "#E6EAF2",
        "bordure": "#D5DAE4", "texte": "#1A1F2B", "texte_secondaire": "#5A6478", "texte_inactif": "#A3ABBB",
        "accent": "#2563EB", "accent_survol": "#1D4FD7", "accent_texte": "#FFFFFF", "selection": "#D3E2FF",
        "succes": "#0F9D58", "attention": "#C77700", "erreur": "#D92D50",
        "canevas": "#FBFCFE", "grille": "#EEF1F6", "grille_forte": "#DDE2EB", "axes": "#B9C1CF", "trait": "#232B3A",
        "force": "#DC2626", "couple": "#EA580C", "reaction": "#7C3AED", "vitesse": "#16A34A",
        "trajectoire": "#0891B2", "ressort": "#4D7C0F", "moteur": "#B45309", "gravite": "#BE185D",
    },
    "sombre": {
        "fenetre": "#14161B", "surface": "#1B1E25", "surface_haute": "#242833", "survol": "#2C3140",
        "bordure": "#2E3442", "texte": "#E7EAF0", "texte_secondaire": "#98A1B3", "texte_inactif": "#5C6475",
        "accent": "#5B93FF", "accent_survol": "#77A6FF", "accent_texte": "#FFFFFF", "selection": "#27406F",
        "succes": "#3DD68C", "attention": "#F5B13D", "erreur": "#FF5C7A",
        "canevas": "#0F1115", "grille": "#1A1D24", "grille_forte": "#262B36", "axes": "#3A4254", "trait": "#DDE2EC",
        "force": "#FF6B6B", "couple": "#FFA94D", "reaction": "#B79CFF", "vitesse": "#4ADE80",
        "trajectoire": "#22D3EE", "ressort": "#A3E635", "moteur": "#FACC15", "gravite": "#F472B6",
    },
}
THEMES = tuple(PALETTES)
THEME_PAR_DEFAUT = "sombre"
"""Thème du premier démarrage ; ensuite, le choix de l'utilisateur est mémorisé."""

_JETON = re.compile(r"\{\{(\w+)\}\}")
_COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def charger_palette(nom: str) -> Dict[str, str]:
    """Palette du thème : valeurs par défaut, complétées par le fichier JSON s'il existe."""
    palette = dict(PALETTES.get(nom, PALETTES[THEME_PAR_DEFAUT]))
    fichier = dossier_themes() / f"{nom}.json"
    try:
        donnees = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return palette
    if isinstance(donnees, dict):
        for cle, valeur in donnees.items():
            if cle in palette and isinstance(valeur, str) and _COULEUR.match(valeur):
                palette[cle] = valeur
    return palette


def feuille_de_style(palette: Dict[str, str], nom: str = THEME_PAR_DEFAUT) -> str:
    """Feuille de style Qt du thème (chaîne vide si le modèle est introuvable)."""
    try:
        modele = (dossier_themes() / "style.qss").read_text(encoding="utf-8")
    except OSError:
        return ""
    jetons = dict(palette)
    jetons["coche"] = (dossier_icones() / "coche.svg").as_posix()
    jetons["chevron"] = (dossier_icones() / f"chevron_{nom}.svg").as_posix()
    return _JETON.sub(lambda m: jetons.get(m.group(1), "#FF00FF"), modele)


class GestionnaireTheme(QObject):
    change = Signal(str)
    """Émis après un changement de thème, avec son nom."""

    def __init__(self) -> None:
        super().__init__()
        self.nom = THEME_PAR_DEFAUT
        self.couleurs: Dict[str, str] = dict(PALETTES[THEME_PAR_DEFAUT])

    @property
    def sombre(self) -> bool:
        return self.nom == "sombre"

    def couleur(self, jeton: str, alpha: Optional[int] = None) -> QColor:
        couleur = QColor(self.couleurs.get(jeton, "#FF00FF"))
        if alpha is not None:
            couleur.setAlpha(alpha)
        return couleur

    def hex(self, jeton: str) -> str:
        return self.couleurs.get(jeton, "#FF00FF")

    def appliquer(self, nom: str) -> None:
        """Active le thème pour toute l'application."""
        if nom not in PALETTES:
            nom = THEME_PAR_DEFAUT
        self.nom = nom
        self.couleurs = charger_palette(nom)
        application = QApplication.instance()
        if application is not None:
            application.setPalette(self._palette_qt())
            application.setStyleSheet(feuille_de_style(self.couleurs, nom))
        self.change.emit(nom)

    def basculer(self) -> str:
        self.appliquer("clair" if self.sombre else "sombre")
        return self.nom

    def _palette_qt(self) -> QPalette:
        c = self.couleur
        palette = QPalette()
        roles = {
            QPalette.Window: "fenetre",
            QPalette.WindowText: "texte",
            QPalette.Base: "surface",
            QPalette.AlternateBase: "surface_haute",
            QPalette.ToolTipBase: "surface_haute",
            QPalette.ToolTipText: "texte",
            QPalette.Text: "texte",
            QPalette.Button: "surface_haute",
            QPalette.ButtonText: "texte",
            QPalette.BrightText: "accent_texte",
            QPalette.Highlight: "accent",
            QPalette.HighlightedText: "accent_texte",
            QPalette.Link: "accent",
            QPalette.PlaceholderText: "texte_inactif",
            QPalette.Mid: "bordure",
            QPalette.Dark: "bordure",
            QPalette.Shadow: "fenetre",
        }
        for role, jeton in roles.items():
            palette.setColor(role, c(jeton))
        for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, c("texte_inactif"))
        return palette


theme = GestionnaireTheme()
