"""Description déclarative des paramètres d'un objet du modèle.

Chaque classe (liaison, action, loi de mouvement…) liste ses paramètres
numériques sous forme de ``Champ``. Cette description unique sert à la fois :

- au lecteur et à l'écrivain de fichiers (nom, valeur par défaut, validation) ;
- au panneau de propriétés (libellé, dimension physique donc unité affichée).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Champ:
    nom: str
    """Nom de l'attribut Python et de la clé dans le fichier."""

    dimension: str = "sans"
    """Dimension physique (voir ``sikax.physique.unites``)."""

    defaut: float = 0.0

    expression: bool = False
    """Vrai si le champ accepte une expression du temps (``"10*sin(t)"``)."""

    minimum: Optional[float] = None
    """Borne inférieure admise (en SI), ``None`` s'il n'y en a pas."""

    maximum: Optional[float] = None
    """Borne supérieure admise (en SI), ``None`` s'il n'y en a pas."""

    entier: bool = False
    """Vrai si la valeur doit être un nombre entier (nombre de dents)."""

    strict: bool = False
    """Vrai si la borne inférieure est exclue (module, rayon strictement positifs)."""

    cle: str = ""
    """Clé de traduction du libellé ; par défaut ``champ.<nom>``."""

    @property
    def cle_i18n(self) -> str:
        return self.cle or f"champ.{self.nom}"

    def admet(self, valeur: float) -> bool:
        """Vrai si la valeur respecte les bornes et le caractère entier du champ."""
        if self.minimum is not None and (valeur < self.minimum or (self.strict and valeur <= self.minimum)):
            return False
        if self.maximum is not None and valeur > self.maximum:
            return False
        return not self.entier or float(valeur).is_integer()
