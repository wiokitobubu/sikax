"""Catalogue des liaisons normalisées dans l'espace (3D).

Un schéma plan ne dit pas tout : une articulation dessinée dans le plan peut
être réalisée par une pivot, une pivot glissant ou une rotule. Ce choix ne
change pas le mouvement plan mais change le degré d'hyperstatisme réel du
mécanisme. Chaque liaison plane de Sikax porte donc un *modèle spatial* pris
dans ce catalogue, utilisé par l'analyse d'hyperstatisme « dans l'espace ».

Repère local de la liaison : ``x`` est l'axe de la liaison dans le plan du
schéma, ``y`` la normale dans le plan, ``z`` la normale au plan.

C'est aussi la table de départ du futur moteur 3D : une mobilité est un
couple (nature, axe) avec nature ``"R"`` (rotation) ou ``"T"`` (translation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

Mobilite = Tuple[str, str]


@dataclass(frozen=True)
class ModeleSpatial:
    cle: str
    mobilites: Tuple[Mobilite, ...]

    @property
    def ddl(self) -> int:
        return len(self.mobilites)

    @property
    def inconnues_statiques(self) -> int:
        return 6 - len(self.mobilites)

    @property
    def cle_i18n(self) -> str:
        return f"spatial.{self.cle}"

    def mobilites_planes(self) -> Tuple[bool, bool, bool]:
        """Mobilités conservées dans le plan : (Tx, Ty, Rz)."""
        return (("T", "x") in self.mobilites, ("T", "y") in self.mobilites, ("R", "z") in self.mobilites)


def _m(*mobilites: str) -> Tuple[Mobilite, ...]:
    return tuple((m[0], m[1]) for m in mobilites)


CATALOGUE: Dict[str, ModeleSpatial] = {
    m.cle: m
    for m in (
        ModeleSpatial("encastrement", _m()),
        # Articulations du plan (rotation autour de z)
        ModeleSpatial("pivot_z", _m("Rz")),
        ModeleSpatial("pivot_glissant_z", _m("Rz", "Tz")),
        ModeleSpatial("rotule", _m("Rx", "Ry", "Rz")),
        ModeleSpatial("lineaire_annulaire_z", _m("Rx", "Ry", "Rz", "Tz")),
        # Guidages en translation le long de x
        ModeleSpatial("glissiere_x", _m("Tx")),
        ModeleSpatial("pivot_glissant_x", _m("Rx", "Tx")),
        ModeleSpatial("appui_plan_y", _m("Ry", "Tx", "Tz")),
        # Contacts : rotation autour de z et translation le long de x
        ModeleSpatial("ponctuelle_y", _m("Rx", "Ry", "Rz", "Tx", "Tz")),
        ModeleSpatial("lineaire_annulaire_x", _m("Rx", "Ry", "Rz", "Tx")),
        ModeleSpatial("lineaire_rectiligne_y", _m("Ry", "Rz", "Tx", "Tz")),
    )
}


def modele_spatial(cle: str) -> ModeleSpatial:
    try:
        return CATALOGUE[cle]
    except KeyError:
        raise KeyError(f"modèle spatial inconnu : « {cle} »") from None
