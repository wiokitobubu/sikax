"""Mise en équations d'un mécanisme plan.

``SystemeMecanique`` traduit un ``Mecanisme`` en système algébro-différentiel :

    M·q̈ + Φqᵀ·λ = Q(q, q̇, t)        (PFD, une équation par mobilité de solide)
    Φ(q, t) = 0                       (liaisons et moteurs)

Les multiplicateurs de Lagrange λ sont les inconnues de liaison : on en
déduit le torseur transmis par chaque liaison et l'effort de chaque moteur.

Le système garde une référence sur le mécanisme reçu : passer une copie si
le modèle peut être modifié pendant le calcul.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..modele.actions import Couple, Force, Ressort
from ..modele.liaisons import Encastrement, Glissiere, Liaison, Pivot, Ponctuelle
from ..modele.mecanisme import Mecanisme
from ..modele.moteur import Moteur
from ..util.expression import ErreurExpression, evaluer
from .contraintes import (
    AngleRelatif,
    Attache,
    Coincidence,
    Contrainte,
    PointSurDroite,
    TranslationPilotee,
    bras,
    coordonnee_translation,
    vitesse_point,
    vitesse_translation,
)
from .erreurs import ErreurCalcul


@dataclass
class InfoLiaison:
    """Place d'une liaison dans le système d'équations."""

    liaison: Liaison
    lignes: slice
    attache_a: Attache
    attache_b: Attache
    angle_axe: float = 0.0


@dataclass
class InfoMoteur:
    moteur: Moteur
    liaison: Liaison
    ligne: int
    pilotage: str
    reference: float
    """Valeur de la coordonnée pilotée ajoutée à la loi (0 si moteur absolu)."""


class SystemeMecanique:
    def __init__(self, mecanisme: Mecanisme, avec_moteurs: bool = True) -> None:
        self.mecanisme = mecanisme
        self.corps: List[str] = [s.id for s in mecanisme.solides_mobiles()]
        self.indice: Dict[str, int] = {sid: k for k, sid in enumerate(self.corps)}
        self.nb = len(self.corps)
        self.n = 3 * self.nb

        self._g_local: List[Tuple[float, float]] = []
        masses = np.zeros(self.n)
        for k, sid in enumerate(self.corps):
            inertie = mecanisme.solides[sid].inertie
            self._g_local.append((inertie.gx, inertie.gy))
            masses[3 * k] = masses[3 * k + 1] = inertie.masse
            masses[3 * k + 2] = inertie.jz
        self.masses = masses
        self.masse_definie_positive = bool(self.n == 0 or np.all(masses > 0.0))

        etude = mecanisme.etude
        self.gravite = (etude.gx, etude.gy) if etude.pesanteur else (0.0, 0.0)
        self._poids = np.zeros(self.n)
        self._poids[0::3] = masses[0::3] * self.gravite[0]
        self._poids[1::3] = masses[1::3] * self.gravite[1]

        self.q0 = self.q_depuis_modele()

        # -- liaisons ---------------------------------------------------------
        self.contraintes: List[Tuple[int, Contrainte]] = []
        self.liaisons: Dict[str, InfoLiaison] = {}
        ligne = 0
        for liaison in mecanisme.liaisons.values():
            blocs = self._contraintes_de(liaison)
            debut = ligne
            for bloc in blocs:
                self.contraintes.append((ligne, bloc))
                ligne += bloc.n_eq
            self.liaisons[liaison.id] = InfoLiaison(
                liaison,
                slice(debut, ligne),
                self.attache(liaison.solide_a, liaison.point_a),
                self.attache(liaison.solide_b, liaison.point_b),
                getattr(liaison, "angle_axe", 0.0),
            )
        self.nc_liaisons = ligne

        # -- moteurs ----------------------------------------------------------
        self.moteurs: Dict[str, InfoMoteur] = {}
        if avec_moteurs:
            for moteur in mecanisme.moteurs.values():
                if not moteur.actif or moteur.liaison not in self.liaisons:
                    continue
                info = self.liaisons[moteur.liaison]
                pilotage = info.liaison.PILOTAGE
                if pilotage is None:
                    continue
                reference = self.coordonnee_liaison(self.q0, info)[0 if pilotage == "translation" else 1] if moteur.relatif else 0.0
                ki, kj = info.attache_a[0], info.attache_b[0]
                loi = self._loi(moteur)
                if pilotage == "rotation":
                    bloc: Contrainte = AngleRelatif(ki, kj, reference, loi)
                else:
                    bloc = TranslationPilotee(info.attache_a, info.angle_axe, info.attache_b, reference, loi)
                self.contraintes.append((ligne, bloc))
                self.moteurs[moteur.id] = InfoMoteur(moteur, info.liaison, ligne, pilotage, reference)
                ligne += 1
        self.nc = ligne

        self._preparer_actions()

    @staticmethod
    def _loi(moteur: Moteur):
        """Loi du moteur, dont les erreurs d'évaluation deviennent des ``ErreurCalcul``."""
        evaluer_loi = moteur.loi.evaluer

        def loi(t: float) -> Tuple[float, float, float]:
            try:
                return evaluer_loi(t)
            except ErreurExpression as exc:
                raise ErreurCalcul("expression", objet=moteur.nom, message=str(exc)) from exc

        return loi

    # ------------------------------------------------------------ géométrie
    def attache(self, solide_id: str, point_id: str) -> Attache:
        """Attache d'un point du modèle (indice du solide et vecteur G→P local)."""
        solide = self.mecanisme.solide(solide_id)
        point = solide.point(point_id)
        return self.attache_locale(solide_id, point.x, point.y)

    def attache_locale(self, solide_id: str, x: float, y: float) -> Attache:
        k = self.indice.get(solide_id, -1)
        if k < 0:
            X, Y = self.mecanisme.solide(solide_id).pose.vers_global(x, y)
            return (-1, X, Y)
        gx, gy = self._g_local[k]
        return (k, x - gx, y - gy)

    def q_depuis_modele(self, mecanisme: Optional[Mecanisme] = None) -> np.ndarray:
        """Vecteur q correspondant aux poses du modèle."""
        modele = mecanisme or self.mecanisme
        q = np.zeros(self.n)
        for k, sid in enumerate(self.corps):
            solide = modele.solides[sid]
            gx, gy = self._g_local[k]
            q[3 * k], q[3 * k + 1] = solide.pose.vers_global(gx, gy)
            q[3 * k + 2] = solide.pose.angle
        return q

    def pose_solide(self, q: np.ndarray, solide_id: str) -> Tuple[float, float, float]:
        """Pose (x, y, angle) de l'origine du repère du solide pour l'état q."""
        k = self.indice.get(solide_id, -1)
        if k < 0:
            pose = self.mecanisme.solide(solide_id).pose
            return (pose.x, pose.y, pose.angle)
        gx, gy = self._g_local[k]
        angle = q[3 * k + 2]
        c, s = math.cos(angle), math.sin(angle)
        return (q[3 * k] - (c * gx - s * gy), q[3 * k + 1] - (s * gx + c * gy), angle)

    def appliquer_au_modele(self, q: np.ndarray, mecanisme: Optional[Mecanisme] = None) -> None:
        """Reporte l'état q dans les poses des solides du modèle."""
        modele = mecanisme or self.mecanisme
        for sid in self.corps:
            pose = modele.solides[sid].pose
            pose.x, pose.y, pose.angle = (float(v) for v in self.pose_solide(q, sid))

    def position(self, q: np.ndarray, attache: Attache) -> Tuple[float, float]:
        x, y, _, _ = bras(q, attache)
        return x, y

    def vitesse(self, q: np.ndarray, qd: np.ndarray, attache: Attache) -> Tuple[float, float]:
        _, _, ax, ay = bras(q, attache)
        return vitesse_point(qd, attache[0], ax, ay)

    def acceleration(self, q: np.ndarray, qd: np.ndarray, qdd: np.ndarray, attache: Attache) -> Tuple[float, float]:
        k = attache[0]
        if k < 0:
            return 0.0, 0.0
        _, _, ax, ay = bras(q, attache)
        i = 3 * k
        w, dw = qd[i + 2], qdd[i + 2]
        return qdd[i] - ay * dw - ax * w * w, qdd[i + 1] + ax * dw - ay * w * w

    # ---------------------------------------------------------- contraintes
    def _contraintes_de(self, liaison: Liaison) -> List[Contrainte]:
        a = self.attache(liaison.solide_a, liaison.point_a)
        b = self.attache(liaison.solide_b, liaison.point_b)
        if isinstance(liaison, Pivot):
            return [Coincidence(a, b)]
        if isinstance(liaison, Glissiere):
            return [PointSurDroite(a, liaison.angle_axe, b), AngleRelatif(a[0], b[0], liaison.angle_relatif)]
        if isinstance(liaison, Encastrement):
            return [Coincidence(a, b), AngleRelatif(a[0], b[0], liaison.angle_relatif)]
        if isinstance(liaison, Ponctuelle):
            return [PointSurDroite(a, liaison.angle_axe, b)]
        raise ErreurCalcul("liaison_non_geree", type=liaison.type)

    def _blocs(self, moteurs: bool):
        if moteurs:
            return self.contraintes
        return [(i, c) for i, c in self.contraintes if i < self.nc_liaisons]

    def taille(self, moteurs: bool = True) -> int:
        return self.nc if moteurs else self.nc_liaisons

    def phi(self, q: np.ndarray, t: float = 0.0, moteurs: bool = True) -> np.ndarray:
        sortie = np.zeros(self.taille(moteurs))
        for i, bloc in self._blocs(moteurs):
            bloc.phi(q, t, sortie, i)
        return sortie

    def jacobienne(self, q: np.ndarray, t: float = 0.0, moteurs: bool = True) -> np.ndarray:
        J = np.zeros((self.taille(moteurs), self.n))
        for i, bloc in self._blocs(moteurs):
            bloc.jac(q, t, J, i)
        return J

    def phi_t(self, q: np.ndarray, t: float = 0.0, moteurs: bool = True) -> np.ndarray:
        sortie = np.zeros(self.taille(moteurs))
        for i, bloc in self._blocs(moteurs):
            bloc.phi_t(q, t, sortie, i)
        return sortie

    def gamma(self, q: np.ndarray, qd: np.ndarray, t: float = 0.0, moteurs: bool = True) -> np.ndarray:
        sortie = np.zeros(self.taille(moteurs))
        for i, bloc in self._blocs(moteurs):
            bloc.gamma(q, qd, t, sortie, i)
        return sortie

    # --------------------------------------------- coordonnées articulaires
    def coordonnee_liaison(self, q: np.ndarray, info: InfoLiaison) -> Tuple[float, float]:
        """(déplacement le long de l'axe, angle de B par rapport à A)."""
        ki, kj = info.attache_a[0], info.attache_b[0]
        angle = (q[3 * kj + 2] if kj >= 0 else 0.0) - (q[3 * ki + 2] if ki >= 0 else 0.0)
        if info.liaison.A_UN_AXE:
            return coordonnee_translation(q, info.attache_a, info.angle_axe, info.attache_b), angle
        return 0.0, angle

    def vitesse_liaison(self, q: np.ndarray, qd: np.ndarray, info: InfoLiaison) -> Tuple[float, float]:
        ki, kj = info.attache_a[0], info.attache_b[0]
        omega = (qd[3 * kj + 2] if kj >= 0 else 0.0) - (qd[3 * ki + 2] if ki >= 0 else 0.0)
        if info.liaison.A_UN_AXE:
            return vitesse_translation(q, qd, info.attache_a, info.angle_axe, info.attache_b), omega
        return 0.0, omega

    def lignes_vitesse_liaison(self, q: np.ndarray, info: InfoLiaison) -> np.ndarray:
        """Ligne L telle que L·q̇ = vitesse relative de la mobilité pilotable."""
        ligne = np.zeros((1, self.n))
        ki, kj = info.attache_a[0], info.attache_b[0]
        if info.liaison.PILOTAGE == "translation":
            TranslationPilotee(info.attache_a, info.angle_axe, info.attache_b, 0.0, lambda t: (0.0, 0.0, 0.0)).jac(q, 0.0, ligne, 0)
        else:
            AngleRelatif(ki, kj, 0.0).jac(q, 0.0, ligne, 0)
        return ligne[0]

    # ----------------------------------------------------------------- forces
    def _preparer_actions(self) -> None:
        self._forces = []
        self._couples = []
        self._ressorts = []
        self._amortisseurs = []
        for action in self.mecanisme.actions.values():
            if not action.actif:
                continue
            if isinstance(action, Force):
                attache = self.attache(action.solide, action.point)
                if attache[0] >= 0:
                    self._forces.append((attache, action.fx, action.fy, action.repere == "local", action.id))
            elif isinstance(action, Couple):
                k = self.indice.get(action.solide, -1)
                if k >= 0:
                    self._couples.append((k, action.mz, action.id))
            elif isinstance(action, Ressort):
                self._ressorts.append(
                    (
                        self.attache(action.solide_a, action.point_a),
                        self.attache(action.solide_b, action.point_b),
                        action.raideur,
                        action.amortissement,
                        action.longueur_libre,
                        action.id,
                    )
                )
        for info in self.liaisons.values():
            coefficient = getattr(info.liaison, "amortissement", 0.0)
            if coefficient > 0.0:
                self._amortisseurs.append((info, coefficient))

    def _nom_action(self, action_id: str) -> str:
        action = self.mecanisme.actions.get(action_id)
        return action.nom if action is not None else action_id

    def composantes_force(self, q: np.ndarray, t: float, attache: Attache, fx, fy, local: bool, action_id: str = "") -> Tuple[float, float]:
        """Composantes globales d'une force à l'instant t."""
        try:
            x, y = evaluer(fx, t), evaluer(fy, t)
        except ErreurExpression as exc:
            raise ErreurCalcul("expression", objet=self._nom_action(action_id), message=str(exc)) from exc
        if local and attache[0] >= 0:
            angle = q[3 * attache[0] + 2]
            c, s = math.cos(angle), math.sin(angle)
            return c * x - s * y, s * x + c * y
        return x, y

    def effort_ressort(self, q: np.ndarray, qd: np.ndarray, ressort) -> Tuple[float, float, float, float]:
        """(effort de traction, longueur, ex, ey) d'un ressort préparé."""
        a, b, raideur, amortissement, libre, _ = ressort
        pax, pay, aax, aay = bras(q, a)
        pbx, pby, abx, aby = bras(q, b)
        dx, dy = pbx - pax, pby - pay
        longueur = math.hypot(dx, dy)
        if longueur < 1e-12:
            return 0.0, longueur, 1.0, 0.0
        ex, ey = dx / longueur, dy / longueur
        vax, vay = vitesse_point(qd, a[0], aax, aay)
        vbx, vby = vitesse_point(qd, b[0], abx, aby)
        allongement = ex * (vbx - vax) + ey * (vby - vay)
        return raideur * (longueur - libre) + amortissement * allongement, longueur, ex, ey

    @staticmethod
    def _ajouter_force(Q: np.ndarray, attache: Attache, bx: float, by: float, fx: float, fy: float) -> None:
        """Ajoute la force (fx, fy) de bras de levier (bx, by) par rapport à G."""
        k = attache[0]
        if k < 0:
            return
        i = 3 * k
        Q[i] += fx
        Q[i + 1] += fy
        Q[i + 2] += bx * fy - by * fx

    def forces(self, q: np.ndarray, qd: np.ndarray, t: float = 0.0) -> np.ndarray:
        """Forces généralisées des actions extérieures et intérieures connues."""
        Q = self._poids.copy()
        for attache, fx, fy, local, action_id in self._forces:
            x, y = self.composantes_force(q, t, attache, fx, fy, local, action_id)
            _, _, ax, ay = bras(q, attache)
            self._ajouter_force(Q, attache, ax, ay, x, y)
        for k, mz, action_id in self._couples:
            try:
                Q[3 * k + 2] += evaluer(mz, t)
            except ErreurExpression as exc:
                raise ErreurCalcul("expression", objet=self._nom_action(action_id), message=str(exc)) from exc
        for ressort in self._ressorts:
            a, b = ressort[0], ressort[1]
            effort, _, ex, ey = self.effort_ressort(q, qd, ressort)
            _, _, aax, aay = bras(q, a)
            _, _, abx, aby = bras(q, b)
            self._ajouter_force(Q, a, aax, aay, effort * ex, effort * ey)
            self._ajouter_force(Q, b, abx, aby, -effort * ex, -effort * ey)
        for info, coefficient in self._amortisseurs:
            glissement, rotation = self.vitesse_liaison(q, qd, info)
            ki, kj = info.attache_a[0], info.attache_b[0]
            if info.liaison.PILOTAGE == "rotation":
                couple = -coefficient * rotation
                if kj >= 0:
                    Q[3 * kj + 2] += couple
                if ki >= 0:
                    Q[3 * ki + 2] -= couple
            else:
                beta = (q[3 * ki + 2] if ki >= 0 else 0.0) + info.angle_axe
                fx, fy = -coefficient * glissement * math.cos(beta), -coefficient * glissement * math.sin(beta)
                px, py, abx, aby = bras(q, info.attache_b)
                self._ajouter_force(Q, info.attache_b, abx, aby, fx, fy)
                if ki >= 0:
                    self._ajouter_force(Q, info.attache_a, px - q[3 * ki], py - q[3 * ki + 1], -fx, -fy)
        return Q

    def energies(self, q: np.ndarray, qd: np.ndarray) -> Tuple[float, float]:
        """(énergie cinétique, énergie potentielle de pesanteur et des ressorts)."""
        cinetique = 0.5 * float(np.dot(self.masses, qd * qd))
        gx, gy = self.gravite
        potentielle = -float(np.dot(self.masses[0::3], gx * q[0::3] + gy * q[1::3])) if self.n else 0.0
        nul = np.zeros(self.n)
        for ressort in self._ressorts:
            _, longueur, _, _ = self.effort_ressort(q, nul, ressort)
            potentielle += 0.5 * ressort[2] * (longueur - ressort[4]) ** 2
        return cinetique, potentielle

    # ------------------------------------------------------ efforts de liaison
    def torseur_liaison(self, q: np.ndarray, J: np.ndarray, multiplicateurs: np.ndarray, info: InfoLiaison) -> Tuple[float, float, float, float, float]:
        """Action de A sur B : (X, Y, N, px, py), moment N réduit au point (px, py).

        Les composantes sont dans la base globale ; le point de réduction est
        le point de liaison porté par B.
        """
        lam = multiplicateurs[info.lignes]
        lignes = J[info.lignes]
        px, py, bx, by = bras(q, info.attache_b)
        ka, kb = info.attache_a[0], info.attache_b[0]
        if kb >= 0:
            c = 3 * kb
            rx = -float(lam @ lignes[:, c])
            ry = -float(lam @ lignes[:, c + 1])
            mg = -float(lam @ lignes[:, c + 2])
            return rx, ry, mg - (bx * ry - by * rx), px, py
        if ka >= 0:
            c = 3 * ka
            rx = -float(lam @ lignes[:, c])
            ry = -float(lam @ lignes[:, c + 1])
            mg = -float(lam @ lignes[:, c + 2])
            lx, ly = px - q[c], py - q[c + 1]
            return -rx, -ry, -(mg - (lx * ry - ly * rx)), px, py
        return 0.0, 0.0, 0.0, px, py

    def effort_moteur(self, multiplicateurs: np.ndarray, info: InfoMoteur) -> float:
        """Couple (N·m) ou force (N) exercé par le moteur de A sur B."""
        return -float(multiplicateurs[info.ligne])
