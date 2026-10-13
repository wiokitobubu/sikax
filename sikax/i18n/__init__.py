"""Localisation (français par défaut)."""

from .messages import texte_diagnostic, texte_erreur_calcul, texte_erreur_fichier, texte_message_calcul
from .traducteur import LANGUE_PAR_DEFAUT, Traducteur, tr, traducteur

__all__ = [
    "LANGUE_PAR_DEFAUT",
    "Traducteur",
    "texte_diagnostic",
    "texte_erreur_calcul",
    "texte_erreur_fichier",
    "texte_message_calcul",
    "tr",
    "traducteur",
]
