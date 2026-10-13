"""Lois de mouvement des moteurs.

Une loi fournit, à l'instant ``t``, le déplacement imposé à une liaison ainsi
que ses dérivées première et seconde : ``(f, df/dt, d²f/dt²)``. Le déplacement
est un angle (rad) pour une pivot, une longueur (m) pour une glissière.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Tuple, Union

from ..util.expression import ErreurExpression, compiler

Valeur = Union[float, str]

# Pour chaque loi : (paramètre, rôle, valeur par défaut). Le rôle donne la
# dimension : « position », « vitesse » et « acceleration » sont angulaires ou
# linéaires selon la liaison pilotée.
LOIS: Dict[str, Tuple[Tuple[str, str, Valeur], ...]] = {
    "vitesse_constante": (
        ("vitesse", "vitesse", 1.0),
        ("position_initiale", "position", 0.0),
    ),
    "uniformement_accelere": (
        ("acceleration", "acceleration", 1.0),
        ("vitesse_initiale", "vitesse", 0.0),
        ("position_initiale", "position", 0.0),
    ),
    "sinusoidale": (
        ("amplitude", "position", 0.1),
        ("frequence", "frequence", 1.0),
        ("phase", "phase", 0.0),
        ("decalage", "position", 0.0),
    ),
    "trapeze": (
        ("course", "position", 1.0),
        ("vitesse_max", "vitesse", 1.0),
        ("acceleration", "acceleration", 2.0),
        ("depart", "temps", 0.0),
    ),
    "blocage": (("position", "position", 0.0),),
    "expression": (("expression", "expression", "0"),),
}
TYPES_LOI: Tuple[str, ...] = tuple(LOIS)

_DIMENSIONS = {
    "rotation": {"position": "angle", "vitesse": "vitesse_angulaire", "acceleration": "acceleration_angulaire"},
    "translation": {"position": "longueur", "vitesse": "vitesse", "acceleration": "acceleration"},
}


def dimension_du_role(role: str, pilotage: str) -> str:
    """Dimension physique d'un paramètre de loi selon la nature du moteur."""
    if role in ("position", "vitesse", "acceleration"):
        return _DIMENSIONS.get(pilotage, _DIMENSIONS["rotation"])[role]
    return {"frequence": "frequence", "phase": "angle", "temps": "temps"}.get(role, "sans")


def parametres_par_defaut(type_loi: str) -> Dict[str, Valeur]:
    return {nom: defaut for nom, _, defaut in LOIS[type_loi]}


@dataclass
class LoiMouvement:
    type: str = "vitesse_constante"
    parametres: Dict[str, Valeur] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in LOIS:
            raise ValueError(f"loi de mouvement inconnue : « {self.type} »")
        complets = parametres_par_defaut(self.type)
        complets.update({k: v for k, v in self.parametres.items() if k in complets})
        self.parametres = complets

    def _p(self, nom: str) -> float:
        return float(self.parametres[nom])

    def evaluer(self, t: float) -> Tuple[float, float, float]:
        """Déplacement imposé et ses deux premières dérivées à l'instant ``t``."""
        nature = self.type
        if nature == "vitesse_constante":
            v = self._p("vitesse")
            return (self._p("position_initiale") + v * t, v, 0.0)
        if nature == "uniformement_accelere":
            a, v0 = self._p("acceleration"), self._p("vitesse_initiale")
            return (self._p("position_initiale") + v0 * t + 0.5 * a * t * t, v0 + a * t, a)
        if nature == "sinusoidale":
            amp, w = self._p("amplitude"), 2.0 * math.pi * self._p("frequence")
            arg = w * t + self._p("phase")
            s, c = math.sin(arg), math.cos(arg)
            return (self._p("decalage") + amp * s, amp * w * c, -amp * w * w * s)
        if nature == "trapeze":
            return _trapeze(t, self._p("course"), self._p("vitesse_max"), self._p("acceleration"), self._p("depart"))
        if nature == "blocage":
            return (self._p("position"), 0.0, 0.0)
        return compiler(str(self.parametres["expression"])).jet(t).tuple()

    def verifier(self) -> None:
        """Lève ``ValueError`` si les paramètres sont incohérents."""
        if self.type == "expression":
            try:
                compiler(str(self.parametres["expression"]))
            except ErreurExpression as exc:
                raise ValueError(str(exc)) from exc
            return
        for nom, _, _ in LOIS[self.type]:
            valeur = self.parametres[nom]
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur):
                raise ValueError(f"paramètre « {nom} » invalide")
        if self.type == "trapeze":
            if self._p("vitesse_max") <= 0.0 or self._p("acceleration") <= 0.0:
                raise ValueError("vitesse maximale et accélération doivent être strictement positives")

    def duree_caracteristique(self) -> float:
        """Durée « naturelle » de la loi (une période, la fin du trapèze…), ou 0."""
        if self.type == "sinusoidale" and self._p("frequence") > 0.0:
            return 1.0 / self._p("frequence")
        if self.type == "vitesse_constante" and self._p("vitesse") != 0.0:
            return abs(2.0 * math.pi / self._p("vitesse"))
        if self.type == "trapeze":
            return self._p("depart") + _duree_trapeze(abs(self._p("course")), self._p("vitesse_max"), self._p("acceleration"))
        return 0.0

    def copie(self) -> "LoiMouvement":
        return LoiMouvement(self.type, dict(self.parametres))


def _phases_trapeze(course: float, v_max: float, acc: float) -> Tuple[float, float, float]:
    """(durée d'accélération, durée à vitesse constante, vitesse atteinte)."""
    if course <= 0.0 or v_max <= 0.0 or acc <= 0.0:
        return (0.0, 0.0, 0.0)
    t_acc = v_max / acc
    if acc * t_acc * t_acc >= course:  # profil triangulaire : v_max jamais atteinte
        t_acc = math.sqrt(course / acc)
        return (t_acc, 0.0, acc * t_acc)
    return (t_acc, (course - acc * t_acc * t_acc) / v_max, v_max)


def _duree_trapeze(course: float, v_max: float, acc: float) -> float:
    t_acc, t_const, _ = _phases_trapeze(course, v_max, acc)
    return 2.0 * t_acc + t_const


def _trapeze(t: float, course: float, v_max: float, acc: float, depart: float) -> Tuple[float, float, float]:
    sens = -1.0 if course < 0.0 else 1.0
    d = abs(course)
    t_acc, t_const, v = _phases_trapeze(d, v_max, acc)
    tau = t - depart
    total = 2.0 * t_acc + t_const
    if tau <= 0.0 or total <= 0.0:
        return (0.0, 0.0, 0.0)
    if tau < t_acc:
        return (sens * 0.5 * acc * tau * tau, sens * acc * tau, sens * acc)
    if tau < t_acc + t_const:
        return (sens * (0.5 * acc * t_acc * t_acc + v * (tau - t_acc)), sens * v, 0.0)
    if tau < total:
        reste = total - tau
        return (sens * (d - 0.5 * acc * reste * reste), sens * acc * reste, -sens * acc)
    return (sens * d, 0.0, 0.0)
