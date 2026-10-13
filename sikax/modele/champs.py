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

    cle: str = ""
    """Clé de traduction du libellé ; par défaut ``champ.<nom>``."""

    @property
    def cle_i18n(self) -> str:
        return self.cle or f"champ.{self.nom}"
