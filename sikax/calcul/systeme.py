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
from ..modele.liaisons import Came, Encastrement, Engrenage, Glissiere, Liaison, Pivot, Ponctuelle
from ..modele.mecanisme import Mecanisme
from ..modele.moteur import Moteur
from ..util.expression import ErreurExpression, evaluer
from .contraintes import (
    AngleRelatif,
    Attache,
    Coincidence,
    Contrainte,
    DistanceConstante,
    EngrenageCremaillere,
    EngrenageRoues,
    PlateauTangent,
    PointSurDroite,
    TranslationPilotee,
    bras,
    coordonnee_translation,
    vitesse_point,
    vitesse_translation,
)
from .algebre import TOL_RANG, resoudre
from .erreurs import ErreurCalcul


@dataclass
class InfoLiaison:
    """Place d'une liaison dans le système d'équations."""

    liaison: Liaison
    lignes: slice
    attache_a: Attache
    attache_b: Attache
    angle_axe: float = 0.0
    bloc: Optional[Contrainte] = None
    """Contrainte de contact (engrenage, came) qui calcule elle-même ses efforts physiques."""


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
                blocs[0] if liaison.CONTACT else None,
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
        if isinstance(liaison, Engrenage):
            return [self._engrenage(liaison, a, b)]
        if isinstance(liaison, Came):
            return [self._came(liaison, b)]
        raise ErreurCalcul("liaison_non_geree", type=liaison.type)

    def _engrenage(self, liaison: Engrenage, a: Attache, b: Attache) -> Contrainte:
        if liaison.cremaillere:
            return EngrenageCremaillere(b, liaison.angle_axe, a, liaison.rayon_primitif_a(), self.q0, liaison.angle_pression, liaison.rendement)
        signe = -1.0 if liaison.nature == "interieur" else 1.0
        pax, pay, _, _ = bras(self.q0, a)
        pbx, pby, _, _ = bras(self.q0, b)
        entraxe = math.hypot(pbx - pax, pby - pay)
        somme = abs(liaison.z_a + signe * liaison.z_b)
        if entraxe > 1e-12 * self.mecanisme.longueur_caracteristique() and somme > 0.0:
            # rayons primitifs de fonctionnement : rapport Za/Zb, et ra + s·rb = entraxe réel
            ra, rb = entraxe * liaison.z_a / somme, entraxe * liaison.z_b / somme
        else:
            ra, rb = liaison.rayon_primitif_a(), liaison.rayon_primitif_b()
        return EngrenageRoues(a, b, ra, rb, signe, self.q0, liaison.angle_pression, liaison.rendement, self._porte_train(liaison))

    def _came(self, liaison: Came, b: Attache) -> Contrainte:
        solide = self.mecanisme.solide(liaison.solide_a)
        cercle = solide.cercle(liaison.cercle)
        centre = self.attache(liaison.solide_a, cercle.centre)
        if liaison.nature == "plat":
            return PlateauTangent(b, liaison.angle_axe, centre, cercle.rayon, self.q0)
        galet = liaison.rayon_galet if liaison.nature == "galet" else 0.0
        return DistanceConstante(centre, b, cercle.rayon + galet, cercle.rayon)

    def _porte_train(self, liaison: Engrenage) -> int:
        """Indice du solide qui porte les axes des deux roues (−1 pour le bâti).

        C'est le solide par rapport auquel se mesure la puissance transmise
        par la denture : le bâti pour des axes fixes, le porte-satellites d'un
        train épicycloïdal.
        """
        m = self.mecanisme
        tolerance = 1e-7 * m.longueur_caracteristique()

        def partenaire(solide_id: str, point_id: str) -> Optional[str]:
            centre = m.point_global(solide_id, point_id)
            for autre in m.liaisons.values():
                if isinstance(autre, Pivot) and autre.concerne(solide_id):
                    point = autre.point_a if autre.solide_a == solide_id else autre.point_b
                    lieu = m.point_global(solide_id, point)
                    if math.hypot(lieu[0] - centre[0], lieu[1] - centre[1]) <= tolerance:
                        return autre.autre_solide(solide_id)
            return None

        def pivot_en(s1: str, s2: str, lieu) -> bool:
            for autre in m.liaisons.values():
                if isinstance(autre, Pivot) and {autre.solide_a, autre.solide_b} == {s1, s2}:
                    p = m.position_liaison(autre)
                    if math.hypot(p[0] - lieu[0], p[1] - lieu[1]) <= tolerance:
                        return True
            return False

        ya = partenaire(liaison.solide_a, liaison.point_a)
        yb = partenaire(liaison.solide_b, liaison.point_b)
        porteur = ya or yb
        if ya is not None and yb is not None and ya != yb:
            if pivot_en(ya, yb, m.point_global(liaison.solide_a, liaison.point_a)):
                porteur = yb
            elif pivot_en(ya, yb, m.point_global(liaison.solide_b, liaison.point_b)):
                porteur = ya
        return self.indice.get(porteur, -1) if porteur is not None else -1

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
        self._pertes = [info for info in self.liaisons.values() if info.bloc is not None and info.bloc.dissipe()]
        self._radiaux = [info for info in self.liaisons.values() if info.bloc is not None and info.bloc.a_effort_radial()]

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

    def multiplicateurs(self, q: np.ndarray, qd: np.ndarray, J: np.ndarray, second_membre: np.ndarray, tol: float = TOL_RANG) -> np.ndarray:
        """Inconnues de liaison λ telles que (Φq − G)ᵀ·λ = second membre.

        G regroupe le frottement des engrenages de rendement η < 1, qui est
        proportionnel à l'effort transmis : le système reste linéaire et se
        résout exactement, une fois connu le sens de passage de la puissance
        (déterminé sur la solution sans frottement, puis vérifié).
        """
        multiplicateurs, _, _ = resoudre(J.T, second_membre, tol)
        for _ in range(3):
            G = self.matrice_pertes(q, qd, multiplicateurs)
            if G is None:
                break
            corriges, _, _ = resoudre(J.T - G, second_membre, tol)
            G_corrige = self.matrice_pertes(q, qd, corriges)
            stable = G_corrige is not None and np.allclose(G_corrige, G, rtol=1e-9, atol=0.0)
            multiplicateurs = corriges
            if stable:
                break
        return self.completer_multiplicateurs(q, J, multiplicateurs, second_membre + self.pertes(q, qd, multiplicateurs), tol)

    def matrice_pertes(self, q: np.ndarray, qd: np.ndarray, multiplicateurs: np.ndarray) -> Optional[np.ndarray]:
        """G (n × nc) : force généralisée de frottement des engrenages par unité de λ, ou ``None``."""
        G = None
        for info in self._pertes:
            g = info.bloc.vecteur_pertes(q, qd, float(multiplicateurs[info.lignes.start]))
            if g is not None:
                if G is None:
                    G = np.zeros((self.n, self.nc))
                G[:, info.lignes.start] = g
        return G

    def completer_multiplicateurs(self, q: np.ndarray, J: np.ndarray, multiplicateurs: np.ndarray, second_membre: np.ndarray, tol: float = TOL_RANG) -> np.ndarray:
        """Ajoute l'effort radial des engrenages aux efforts de liaison calculés.

        La liaison engrenage ne transmet par construction que l'effort
        tangentiel Ft. L'effort radial Fr = |Ft|·tan α, qui sépare les roues,
        ne travaille pas : il ne change pas le mouvement mais charge les pivots
        des roues. On l'applique comme une action connue et on résout de nouveau
        pour les autres liaisons ; l'effort tangentiel, lui, est inchangé.
        """
        if not self._radiaux:
            return multiplicateurs
        radial = np.zeros(self.n)
        for info in self._radiaux:
            info.bloc.ajouter_effort_radial(q, multiplicateurs[info.lignes.start], radial)
        complets, _, _ = resoudre(J.T, second_membre + radial, tol)
        for info in self._radiaux:
            complets[info.lignes] = multiplicateurs[info.lignes]
        return complets

    @property
    def avec_pertes(self) -> bool:
        """Vrai si un engrenage frotte (rendement inférieur à 1)."""
        return bool(self._pertes)

    def pertes(self, q: np.ndarray, qd: np.ndarray, multiplicateurs: np.ndarray) -> np.ndarray:
        """Forces généralisées de frottement des engrenages, d'après les efforts de liaison."""
        Q = np.zeros(self.n)
        for info in self._pertes:
            lam = float(multiplicateurs[info.lignes.start])
            g = info.bloc.vecteur_pertes(q, qd, lam)
            if g is not None:
                Q += g * lam
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
        le point de liaison porté par B, ou le point de contact d'un engrenage
        ou d'une came (le moment y est nul).
        """
        if info.bloc is not None:
            fx, fy = self.effort_de_contact(q, multiplicateurs, info)
            px, py = info.bloc.point_contact(q)
            return fx, fy, 0.0, px, py
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

    def effort_de_contact(self, q: np.ndarray, multiplicateurs: np.ndarray, info: InfoLiaison) -> Tuple[float, float]:
        """Force de A sur B au contact d'un engrenage (Ft et Fr) ou d'une came (effort normal)."""
        lam = float(multiplicateurs[info.lignes.start])
        bloc = info.bloc
        if isinstance(bloc, (EngrenageRoues, EngrenageCremaillere)):
            return bloc.efforts(q, lam)[2]
        nx, ny = bloc.normale(q)
        return -lam * nx, -lam * ny

    def grandeurs_contact(self, q: np.ndarray, qd: np.ndarray, multiplicateurs: np.ndarray, info: InfoLiaison) -> Dict[str, float]:
        """Grandeurs propres à une liaison de contact, pour les résultats."""
        lam = float(multiplicateurs[info.lignes.start])
        bloc = info.bloc
        if isinstance(bloc, (EngrenageRoues, EngrenageCremaillere)):
            ft, fr, _ = bloc.efforts(q, lam)
            ca, cb = bloc.couples(q, lam)
            grandeurs = {"Ft": ft, "Fr": fr, "Fn": math.hypot(ft, fr), "couple_a": ca}
            if isinstance(bloc, EngrenageRoues):
                grandeurs["couple_b"] = cb
            return grandeurs
        return {"Fn": -lam}

    def effort_moteur(self, multiplicateurs: np.ndarray, info: InfoMoteur) -> float:
        """Couple (N·m) ou force (N) exercé par le moteur de A sur B."""
        return -float(multiplicateurs[info.ligne])
