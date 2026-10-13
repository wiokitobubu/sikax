"""Erreurs du moteur de calcul.

Une ``ErreurCalcul`` porte un code et des paramètres plutôt qu'un texte : le
message affiché est construit par la couche de traduction (clé
``calcul.erreur.<code>``), le moteur reste indépendant de la langue.
"""

from __future__ import annotations

from typing import Any, Dict


class ErreurCalcul(Exception):
    def __init__(self, code: str, /, **parametres: Any) -> None:
        self.code = code
        self.parametres: Dict[str, Any] = parametres
        details = ", ".join(f"{k}={v}" for k, v in parametres.items())
        super().__init__(f"{code} ({details})" if details else code)

    @property
    def cle_i18n(self) -> str:
        return f"calcul.erreur.{self.code}"


class CalculInterrompu(Exception):
    """Levée quand l'utilisateur annule un calcul en cours."""
