"""Diagnostics de lecture et d'écriture des fichiers.

Le lecteur ne s'arrête pas à la première anomalie : il les consigne toutes
dans un ``Rapport``, chacune avec son emplacement dans le fichier. Un
diagnostic porte un code et des paramètres ; son texte est produit par la
couche de traduction (clé ``fichier.diag.<code>``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

ERREUR = "erreur"
AVERTISSEMENT = "avertissement"
INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    niveau: str
    code: str
    chemin: str = ""
    """Emplacement dans le document, par exemple ``liaisons[2] (L3)``."""
    parametres: Dict[str, Any] = field(default_factory=dict)

    @property
    def cle_i18n(self) -> str:
        return f"fichier.diag.{self.code}"

    def __str__(self) -> str:
        details = ", ".join(f"{k}={v}" for k, v in self.parametres.items())
        lieu = f" [{self.chemin}]" if self.chemin else ""
        return f"{self.niveau}: {self.code}{lieu}" + (f" ({details})" if details else "")


@dataclass
class Rapport:
    diagnostics: List[Diagnostic] = field(default_factory=list)

    def ajouter(self, niveau: str, code: str, chemin: str = "", /, **parametres: Any) -> None:
        self.diagnostics.append(Diagnostic(niveau, code, chemin, parametres))

    def erreur(self, code: str, chemin: str = "", /, **parametres: Any) -> None:
        self.ajouter(ERREUR, code, chemin, **parametres)

    def avertissement(self, code: str, chemin: str = "", /, **parametres: Any) -> None:
        self.ajouter(AVERTISSEMENT, code, chemin, **parametres)

    def info(self, code: str, chemin: str = "", /, **parametres: Any) -> None:
        self.ajouter(INFO, code, chemin, **parametres)

    @property
    def erreurs(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.niveau == ERREUR]

    @property
    def avertissements(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.niveau == AVERTISSEMENT]

    @property
    def a_des_erreurs(self) -> bool:
        return any(d.niveau == ERREUR for d in self.diagnostics)

    def codes(self) -> List[str]:
        return [d.code for d in self.diagnostics]

    def __len__(self) -> int:
        return len(self.diagnostics)

    def __iter__(self):
        return iter(self.diagnostics)


class ErreurFichier(Exception):
    """Erreur de lecture ou d'écriture, accompagnée du rapport complet."""

    def __init__(self, code: str, rapport: Rapport = None, /, **parametres: Any) -> None:
        self.code = code
        self.parametres: Dict[str, Any] = parametres
        self.rapport = rapport if rapport is not None else Rapport()
        details = ", ".join(f"{k}={v}" for k, v in parametres.items())
        super().__init__(f"{code} ({details})" if details else code)

    @property
    def cle_i18n(self) -> str:
        return f"fichier.erreur.{self.code}"


class ErreurLecture(ErreurFichier):
    pass


class ErreurEcriture(ErreurFichier):
    pass
