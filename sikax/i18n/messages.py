"""Mise en phrases des erreurs et des diagnostics.

Le moteur de calcul et le lecteur de fichiers ne produisent que des codes
accompagnés de paramètres. Ce module en fait des phrases dans la langue
active ; il est le seul endroit où codes et textes se rencontrent.
"""

from __future__ import annotations

from typing import Any, Dict

from .traducteur import tr, traducteur


def _formuler(cle: str, parametres: Dict[str, Any], repli: str) -> str:
    """Texte de la clé, ou un repli lisible si la clé n'est pas traduite."""
    if traducteur.existe(cle):
        return tr(cle, **parametres)
    details = ", ".join(f"{k} = {v}" for k, v in parametres.items())
    return f"{repli} ({details})" if details else repli


def texte_diagnostic(diagnostic) -> str:
    """Phrase d'un diagnostic de lecture, précédée de son emplacement dans le fichier."""
    message = _formuler(diagnostic.cle_i18n, diagnostic.parametres, diagnostic.code)
    return f"{diagnostic.chemin} : {message}" if diagnostic.chemin else message


def texte_erreur_fichier(erreur) -> str:
    """Phrase d'une ``ErreurLecture`` ou d'une ``ErreurEcriture``."""
    return _formuler(erreur.cle_i18n, erreur.parametres, erreur.code)


def texte_erreur_calcul(erreur) -> str:
    """Phrase d'une ``ErreurCalcul``."""
    parametres = dict(erreur.parametres)
    if erreur.code == "modele_invalide":
        probleme = str(parametres.get("probleme", ""))
        parametres["detail"] = _formuler(f"modele.probleme.{probleme}", {}, probleme)
    return _formuler(erreur.cle_i18n, parametres, erreur.code)


def texte_message_calcul(message) -> str:
    """Phrase d'un message attaché à des résultats (avertissement, information)."""
    parametres = dict(message.parametres)
    if "t" in parametres:
        parametres["t"] = f"{float(parametres['t']):.4g}"
    return _formuler(f"calcul.message.{message.code}", parametres, message.code)
