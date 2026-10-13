"""Liaisons mécaniques du plan.

``Liaison`` est la classe de base ; chaque liaison relie un point du solide A
à un point du solide B. Les quatre liaisons planes élémentaires sont :

=============  ==========================  ===================  =====================
Classe         Mobilités de B / A          Inconnues statiques  Équations de liaison
=============  ==========================  ===================  =====================
Encastrement   aucune                      X, Y, N              3
Pivot          rotation Rz                 X, Y                 2
Glissiere      translation Tx              Y, N                 2
Ponctuelle     translation Tx, rotation Rz Y                    1
=============  ==========================  ===================  =====================

Les composantes sont exprimées dans le repère local de la liaison : ``x`` est
l'axe de la liaison (direction de glissement), ``y`` sa normale.

La classe ne contient que les données et les propriétés topologiques. Les
équations de contrainte utilisées par le solveur sont dans
``sikax.calcul.contraintes`` : c'est ce module qu'il faudra doubler d'une
version spatiale pour passer en 3D, sans toucher au modèle.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, ClassVar, Dict, Optional, Tuple, Type

from .catalogue_spatial import CATALOGUE, ModeleSpatial
from .champs import Champ

__all__ = [
    "Liaison",
    "Pivot",
    "Glissiere",
    "Encastrement",
    "Ponctuelle",
    "REGISTRE_LIAISONS",
    "TYPES_LIAISON",
    "classe_liaison",
    "creer_liaison",
]


@dataclass
class Liaison:
    """Liaison entre le solide A et le solide B.

    Le torseur statique calculé par Sikax est celui de l'action de A sur B,
    réduit au point de liaison ; le torseur cinématique est celui de B par
    rapport à A.
    """

    id: str
    nom: str
    solide_a: str
    point_a: str
    solide_b: str
    point_b: str
    modele_spatial: str = ""

    # -- description du type (redéfinie par les sous-classes) -----------------
    TYPE: ClassVar[str] = ""
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (False, False, False)
    """Mobilités planes dans le repère local : (Tx, Ty, Rz)."""
    A_UN_AXE: ClassVar[bool] = False
    """Vrai si la liaison possède une direction (attribut ``angle_axe``)."""
    PILOTAGE: ClassVar[Optional[str]] = None
    """``"rotation"`` ou ``"translation"`` si un moteur peut piloter la liaison."""
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = ()
    """Modèles 3D compatibles ; le premier est le modèle par défaut."""
    CHAMPS: ClassVar[Tuple[Champ, ...]] = ()

    def __post_init__(self) -> None:
        if not self.modele_spatial:
            self.modele_spatial = self.MODELES_SPATIAUX[0] if self.MODELES_SPATIAUX else ""

    # -- topologie ----------------------------------------------------------
    @property
    def type(self) -> str:
        return self.TYPE

    def ddl(self, dimension: int = 2) -> int:
        """Nombre de degrés de liberté (inconnues cinématiques)."""
        if dimension == 2:
            return sum(self.MOBILITES)
        return self.modele_3d().ddl

    def inconnues_statiques(self, dimension: int = 2) -> int:
        """Nombre d'inconnues de liaison (composantes du torseur statique)."""
        return (3 if dimension == 2 else 6) - self.ddl(dimension)

    def modele_3d(self) -> ModeleSpatial:
        cle = self.modele_spatial if self.modele_spatial in self.MODELES_SPATIAUX else self.MODELES_SPATIAUX[0]
        return CATALOGUE[cle]

    def composantes_statiques(self) -> Tuple[str, ...]:
        """Noms des composantes non nulles du torseur statique (repère local)."""
        tx, ty, rz = self.MOBILITES
        return tuple(nom for nom, libre in (("X", tx), ("Y", ty), ("N", rz)) if not libre)

    def composantes_cinematiques(self) -> Tuple[str, ...]:
        """Noms des composantes non nulles du torseur cinématique (repère local)."""
        tx, ty, rz = self.MOBILITES
        return tuple(nom for nom, libre in (("ωz", rz), ("Vx", tx), ("Vy", ty)) if libre)

    # -- relations ----------------------------------------------------------
    def concerne(self, solide_id: str) -> bool:
        return solide_id in (self.solide_a, self.solide_b)

    def autre_solide(self, solide_id: str) -> str:
        return self.solide_b if solide_id == self.solide_a else self.solide_a

    def utilise_point(self, solide_id: str, point_id: str) -> bool:
        return (self.solide_a == solide_id and self.point_a == point_id) or (
            self.solide_b == solide_id and self.point_b == point_id
        )

    # -- paramètres ---------------------------------------------------------
    def parametres(self) -> Dict[str, Any]:
        """Paramètres propres au type (ceux de ``CHAMPS``)."""
        return {c.nom: getattr(self, c.nom) for c in self.CHAMPS}

    def copie(self) -> "Liaison":
        return type(self)(**{f.name: getattr(self, f.name) for f in fields(self)})


@dataclass
class Pivot(Liaison):
    """Articulation : B tourne autour du point de liaison par rapport à A."""

    amortissement: float = 0.0
    vitesse_initiale: float = 0.0

    TYPE: ClassVar[str] = "pivot"
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (False, False, True)
    PILOTAGE: ClassVar[Optional[str]] = "rotation"
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = (
        "pivot_z",
        "pivot_glissant_z",
        "rotule",
        "lineaire_annulaire_z",
    )
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (
        Champ("amortissement", "amortissement_angulaire", 0.0, minimum=0.0),
        Champ("vitesse_initiale", "vitesse_angulaire", 0.0),
    )


@dataclass
class Glissiere(Liaison):
    """Guidage en translation de B par rapport à A le long d'un axe lié à A.

    ``angle_axe`` est la direction de l'axe dans le repère de A ;
    ``angle_relatif`` est l'orientation, constante, de B par rapport à A.
    """

    angle_axe: float = 0.0
    angle_relatif: float = 0.0
    amortissement: float = 0.0
    vitesse_initiale: float = 0.0

    TYPE: ClassVar[str] = "glissiere"
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (True, False, False)
    A_UN_AXE: ClassVar[bool] = True
    PILOTAGE: ClassVar[Optional[str]] = "translation"
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = ("glissiere_x", "pivot_glissant_x", "appui_plan_y")
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (
        Champ("angle_axe", "angle", 0.0),
        Champ("angle_relatif", "angle", 0.0),
        Champ("amortissement", "amortissement", 0.0, minimum=0.0),
        Champ("vitesse_initiale", "vitesse", 0.0),
    )


@dataclass
class Encastrement(Liaison):
    """Liaison complète : B est immobile par rapport à A."""

    angle_relatif: float = 0.0

    TYPE: ClassVar[str] = "encastrement"
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (False, False, False)
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = ("encastrement",)
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (Champ("angle_relatif", "angle", 0.0),)


@dataclass
class Ponctuelle(Liaison):
    """Appui simple : le point de B reste sur une droite liée à A.

    La droite passe par le point de A et a pour direction ``angle_axe`` (dans
    le repère de A). L'action transmise est portée par la normale à la droite.
    La liaison est bilatérale : un effort normal négatif signale un décollement
    que le modèle n'autorise pas.
    """

    angle_axe: float = 0.0

    TYPE: ClassVar[str] = "ponctuelle"
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (True, False, True)
    A_UN_AXE: ClassVar[bool] = True
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = (
        "ponctuelle_y",
        "lineaire_annulaire_x",
        "lineaire_rectiligne_y",
    )
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (Champ("angle_axe", "angle", 0.0),)


REGISTRE_LIAISONS: Dict[str, Type[Liaison]] = {
    cls.TYPE: cls for cls in (Pivot, Glissiere, Encastrement, Ponctuelle)
}
TYPES_LIAISON: Tuple[str, ...] = tuple(REGISTRE_LIAISONS)


def classe_liaison(type_liaison: str) -> Type[Liaison]:
    try:
        return REGISTRE_LIAISONS[type_liaison]
    except KeyError:
        raise KeyError(f"type de liaison inconnu : « {type_liaison} »") from None


def creer_liaison(type_liaison: str, **attributs: Any) -> Liaison:
    """Construit une liaison du type demandé (les attributs inconnus sont refusés)."""
    return classe_liaison(type_liaison)(**attributs)
