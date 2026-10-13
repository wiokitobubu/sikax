"""Actions mécaniques appliquées au mécanisme.

- ``Force``   : force appliquée en un point d'un solide ;
- ``Couple``  : moment pur appliqué à un solide ;
- ``Ressort`` : ressort-amortisseur linéaire entre deux points de deux solides.

La pesanteur est un réglage de l'étude (``sikax.modele.etude``). Les
composantes d'une force et la valeur d'un couple acceptent un nombre ou une
expression du temps, par exemple ``"50*sin(2*pi*t)"``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, ClassVar, Dict, Tuple, Type, Union

from .champs import Champ

Valeur = Union[float, str]

REPERES_FORCE = ("global", "local")

__all__ = [
    "ActionMecanique",
    "Force",
    "Couple",
    "Ressort",
    "REGISTRE_ACTIONS",
    "TYPES_ACTION",
    "REPERES_FORCE",
    "classe_action",
    "creer_action",
]


@dataclass
class ActionMecanique:
    id: str
    nom: str
    actif: bool = True

    TYPE: ClassVar[str] = ""
    CHAMPS: ClassVar[Tuple[Champ, ...]] = ()

    @property
    def type(self) -> str:
        return self.TYPE

    def solides_concernes(self) -> Tuple[str, ...]:
        return ()

    def concerne(self, solide_id: str) -> bool:
        return solide_id in self.solides_concernes()

    def utilise_point(self, solide_id: str, point_id: str) -> bool:
        return False

    def parametres(self) -> Dict[str, Any]:
        return {c.nom: getattr(self, c.nom) for c in self.CHAMPS}

    def copie(self) -> "ActionMecanique":
        return type(self)(**{f.name: getattr(self, f.name) for f in fields(self)})


@dataclass
class Force(ActionMecanique):
    """Force appliquée au point ``point`` du solide ``solide``.

    Avec ``repere == "local"`` les composantes sont données dans le repère du
    solide : la force tourne avec lui (force suiveuse).
    """

    solide: str = ""
    point: str = ""
    fx: Valeur = 0.0
    fy: Valeur = 0.0
    repere: str = "global"

    TYPE: ClassVar[str] = "force"
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (
        Champ("fx", "force", 0.0, expression=True),
        Champ("fy", "force", 0.0, expression=True),
    )

    def solides_concernes(self) -> Tuple[str, ...]:
        return (self.solide,)

    def utilise_point(self, solide_id: str, point_id: str) -> bool:
        return self.solide == solide_id and self.point == point_id


@dataclass
class Couple(ActionMecanique):
    """Moment pur (autour de z) appliqué au solide ``solide``."""

    solide: str = ""
    mz: Valeur = 0.0

    TYPE: ClassVar[str] = "couple"
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (Champ("mz", "moment", 0.0, expression=True),)

    def solides_concernes(self) -> Tuple[str, ...]:
        return (self.solide,)


@dataclass
class Ressort(ActionMecanique):
    """Ressort-amortisseur linéaire entre un point de A et un point de B.

    Effort de traction : F = raideur × (L − longueur_libre) + amortissement × dL/dt.
    """

    solide_a: str = ""
    point_a: str = ""
    solide_b: str = ""
    point_b: str = ""
    raideur: float = 0.0
    amortissement: float = 0.0
    longueur_libre: float = 0.0

    TYPE: ClassVar[str] = "ressort"
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (
        Champ("raideur", "raideur", 0.0, minimum=0.0),
        Champ("amortissement", "amortissement", 0.0, minimum=0.0),
        Champ("longueur_libre", "longueur", 0.0, minimum=0.0),
    )

    def solides_concernes(self) -> Tuple[str, ...]:
        return (self.solide_a, self.solide_b)

    def utilise_point(self, solide_id: str, point_id: str) -> bool:
        return (self.solide_a == solide_id and self.point_a == point_id) or (
            self.solide_b == solide_id and self.point_b == point_id
        )


REGISTRE_ACTIONS: Dict[str, Type[ActionMecanique]] = {
    cls.TYPE: cls for cls in (Force, Couple, Ressort)
}
TYPES_ACTION: Tuple[str, ...] = tuple(REGISTRE_ACTIONS)


def classe_action(type_action: str) -> Type[ActionMecanique]:
    try:
        return REGISTRE_ACTIONS[type_action]
    except KeyError:
        raise KeyError(f"type d'action inconnu : « {type_action} »") from None


def creer_action(type_action: str, **attributs: Any) -> ActionMecanique:
    return classe_action(type_action)(**attributs)
