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

Deux liaisons de *contact* complètent la liste. Leur point de contact n'est
pas un point dessiné mais se déduit de la géométrie, à chaque instant :

- ``Engrenage`` : deux roues dentées (extérieur, intérieur) ou un pignon et
  une crémaillère ; contact au point primitif ;
- ``Came`` : un cercle (came excentrique) et un poussoir à pointe, à galet ou
  à plateau ; contact sur le cercle.

Chacune supprime une seule mobilité : comme une ponctuelle, elle transmet un
effort unique, porté par la normale au contact.

La classe ne contient que les données et les propriétés topologiques. Les
équations de contrainte utilisées par le solveur sont dans
``sikax.calcul.contraintes`` : c'est ce module qu'il faudra doubler d'une
version spatiale pour passer en 3D, sans toucher au modèle.
"""

from __future__ import annotations

import math
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
    "Engrenage",
    "Came",
    "NATURES_ENGRENAGE",
    "NATURES_CAME",
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
    OPTIONS: ClassVar[Tuple[Tuple[str, Tuple[str, ...]], ...]] = ()
    """Paramètres à valeurs choisies dans une liste : (nom, valeurs admises)."""
    REFERENCES: ClassVar[Tuple[str, ...]] = ()
    """Paramètres qui désignent un autre objet du modèle (un cercle du solide A)."""
    CONTACT: ClassVar[bool] = False
    """Vrai si le point de la liaison se déduit de la géométrie (engrenage, came)."""

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
        """Paramètres propres au type (``CHAMPS``, ``OPTIONS`` et ``REFERENCES``)."""
        valeurs: Dict[str, Any] = {nom: getattr(self, nom) for nom, _ in self.OPTIONS}
        valeurs.update({nom: getattr(self, nom) for nom in self.REFERENCES})
        valeurs.update({c.nom: getattr(self, c.nom) for c in self.CHAMPS})
        return valeurs

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


NATURES_ENGRENAGE = ("exterieur", "interieur", "cremaillere")
NATURES_CAME = ("pointe", "galet", "plat")


@dataclass
class Engrenage(Liaison):
    """Engrenage entre la roue A et la roue (ou la crémaillère) B.

    ``point_a`` et ``point_b`` sont les centres des roues, normalement les
    points de leurs liaisons pivots. Pour une crémaillère, ``point_b`` est un
    point de sa ligne primitive, de direction ``angle_axe`` (repère de B).

    - ``exterieur`` : les roues tournent en sens inverses, ω_b/ω_a = −Z_a/Z_b ;
    - ``interieur`` : B est une couronne à denture intérieure, même sens ;
    - ``cremaillere`` : B translate de r_a·Δθ_a (r_a = m·Z_a/2).

    Le contact a lieu au point primitif I ; l'effort de A sur B a une
    composante tangentielle Ft (qui transmet le couple) et une composante
    radiale Fr = |Ft|·tan α (qui écarte les roues). Le rendement η < 1 retire
    à la roue menée la fraction 1 − η de la puissance reçue.
    """

    nature: str = "exterieur"
    z_a: float = 20.0
    z_b: float = 40.0
    module: float = 0.002
    angle_pression: float = math.radians(20.0)
    rendement: float = 1.0
    angle_axe: float = 0.0

    TYPE: ClassVar[str] = "engrenage"
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (True, False, True)
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = ("lineaire_rectiligne_y", "ponctuelle_y")
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (
        Champ("z_a", "sans", 20.0, minimum=1.0, entier=True, cle="champ.z_a"),
        Champ("z_b", "sans", 40.0, minimum=1.0, entier=True, cle="champ.z_b"),
        Champ("module", "longueur", 0.002, minimum=0.0, strict=True),
        Champ("angle_pression", "angle", math.radians(20.0), minimum=0.0, maximum=math.radians(45.0)),
        Champ("rendement", "sans", 1.0, minimum=0.0, maximum=1.0, strict=True),
        Champ("angle_axe", "angle", 0.0),
    )
    OPTIONS: ClassVar[Tuple[Tuple[str, Tuple[str, ...]], ...]] = (("nature", NATURES_ENGRENAGE),)
    CONTACT: ClassVar[bool] = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.nature not in NATURES_ENGRENAGE:
            self.nature = "exterieur"

    @property
    def cremaillere(self) -> bool:
        return self.nature == "cremaillere"

    def rayon_primitif_a(self) -> float:
        return self.module * self.z_a / 2.0

    def rayon_primitif_b(self) -> float:
        """Rayon primitif de la roue B (infini pour une crémaillère : on rend 0)."""
        return 0.0 if self.cremaillere else self.module * self.z_b / 2.0

    def entraxe_theorique(self) -> float:
        """a = m·(Z_a + Z_b)/2 (extérieur), m·(Z_b − Z_a)/2 (intérieur), r_a (crémaillère)."""
        if self.nature == "interieur":
            return self.module * (self.z_b - self.z_a) / 2.0
        if self.cremaillere:
            return self.rayon_primitif_a()
        return self.module * (self.z_a + self.z_b) / 2.0

    def rapport(self) -> float:
        """Rapport de transmission r = ω_b/ω_a (roues), ou v_b/ω_a en m/rad (crémaillère)."""
        if self.cremaillere:
            return self.rayon_primitif_a()
        signe = 1.0 if self.nature == "interieur" else -1.0
        return signe * self.z_a / self.z_b

    def composantes_statiques(self) -> Tuple[str, ...]:
        return ("Ft",)

    def composantes_cinematiques(self) -> Tuple[str, ...]:
        return ("ωz", "Vr")


@dataclass
class Came(Liaison):
    """Contact came-poussoir : le cercle ``cercle`` du solide A touche le poussoir B.

    ``point_a`` est le centre du cercle, ``point_b`` le point du poussoir :

    - ``pointe`` : la pointe P reste sur le cercle, |CP| = R ;
    - ``galet``  : P est le centre d'un galet de rayon ``rayon_galet`` qui roule
      sur la came, |CP| = R + ρ ;
    - ``plat``   : le plateau du poussoir (droite par P de direction
      ``angle_axe``, repère de B) reste tangent au cercle.

    Le contact glisse librement : la came peut faire des tours complets. La
    liaison est bilatérale ; un effort normal qui change de signe signale un
    décollement que seul un ressort de rappel empêcherait.
    """

    nature: str = "pointe"
    cercle: str = ""
    rayon_galet: float = 0.0
    angle_axe: float = 0.0

    TYPE: ClassVar[str] = "came"
    MOBILITES: ClassVar[Tuple[bool, bool, bool]] = (True, False, True)
    MODELES_SPATIAUX: ClassVar[Tuple[str, ...]] = ("ponctuelle_y", "lineaire_rectiligne_y")
    CHAMPS: ClassVar[Tuple[Champ, ...]] = (
        Champ("rayon_galet", "longueur", 0.0, minimum=0.0),
        Champ("angle_axe", "angle", 0.0),
    )
    OPTIONS: ClassVar[Tuple[Tuple[str, Tuple[str, ...]], ...]] = (("nature", NATURES_CAME),)
    REFERENCES: ClassVar[Tuple[str, ...]] = ("cercle",)
    CONTACT: ClassVar[bool] = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.nature not in NATURES_CAME:
            self.nature = "pointe"

    def composantes_statiques(self) -> Tuple[str, ...]:
        return ("Fn",)

    def composantes_cinematiques(self) -> Tuple[str, ...]:
        return ("ωz", "Vt")


REGISTRE_LIAISONS: Dict[str, Type[Liaison]] = {
    cls.TYPE: cls for cls in (Pivot, Glissiere, Encastrement, Ponctuelle, Engrenage, Came)
}
TYPES_POINT: Tuple[str, ...] = ("pivot", "glissiere", "encastrement", "ponctuelle")
"""Liaisons entre deux points : on peut passer de l'une à l'autre sans rien perdre."""
TYPES_LIAISON: Tuple[str, ...] = tuple(REGISTRE_LIAISONS)


def classe_liaison(type_liaison: str) -> Type[Liaison]:
    try:
        return REGISTRE_LIAISONS[type_liaison]
    except KeyError:
        raise KeyError(f"type de liaison inconnu : « {type_liaison} »") from None


def creer_liaison(type_liaison: str, **attributs: Any) -> Liaison:
    """Construit une liaison du type demandé (les attributs inconnus sont refusés)."""
    return classe_liaison(type_liaison)(**attributs)
