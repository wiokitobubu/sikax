"""Collecte des états calculés et construction des grandeurs de résultat."""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from ..util.expression import evaluer
from .resultats import Message, Resultats
from .systeme import SystemeMecanique


class Enregistreur:
    """Mémorise, instant par instant, l'état du système et les efforts de liaison."""

    def __init__(self, systeme: SystemeMecanique, nb_instants: int) -> None:
        self.systeme = systeme
        n, nl, nm = systeme.n, len(systeme.liaisons), len(systeme.moteurs)
        self.t = np.zeros(nb_instants)
        self.q = np.zeros((nb_instants, n))
        self.qd = np.zeros((nb_instants, n))
        self.qdd = np.zeros((nb_instants, n))
        self.torseurs = np.zeros((nb_instants, nl, 5))
        self.efforts_moteurs = np.zeros((nb_instants, nm))
        self.contacts: Dict[str, Dict[str, np.ndarray]] = {}
        """Grandeurs propres aux engrenages et aux cames, par liaison."""
        self.avec_efforts = False
        self.nb = 0

    def noter(
        self,
        t: float,
        q: np.ndarray,
        qd: np.ndarray,
        qdd: np.ndarray,
        multiplicateurs: Optional[np.ndarray] = None,
        J: Optional[np.ndarray] = None,
    ) -> None:
        i = self.nb
        self.t[i] = t
        self.q[i] = q
        self.qd[i] = qd
        self.qdd[i] = qdd
        systeme = self.systeme
        if multiplicateurs is not None and J is not None:
            self.avec_efforts = True
            for j, info in enumerate(systeme.liaisons.values()):
                self.torseurs[i, j] = systeme.torseur_liaison(q, J, multiplicateurs, info)
                if info.bloc is not None:
                    grandeurs = self.contacts.setdefault(info.liaison.id, {})
                    for nom, valeur in systeme.grandeurs_contact(q, qd, multiplicateurs, info).items():
                        grandeurs.setdefault(nom, np.zeros(self.t.size))[i] = valeur
            for j, info in enumerate(systeme.moteurs.values()):
                self.efforts_moteurs[i, j] = systeme.effort_moteur(multiplicateurs, info)
        else:
            for j, info in enumerate(systeme.liaisons.values()):
                px, py = info.bloc.point_contact(q) if info.bloc is not None else systeme.position(q, info.attache_b)
                self.torseurs[i, j, 3:] = (px, py)
        self.nb += 1

    # ------------------------------------------------------------------
    def resultats(self, type_etude: str) -> Resultats:
        systeme = self.systeme
        modele = systeme.mecanisme
        nb = self.nb
        t, Q, QD, QDD = self.t[:nb], self.q[:nb], self.qd[:nb], self.qdd[:nb]

        poses = np.zeros((nb, systeme.n))
        res = Resultats(type_etude, t.copy(), list(systeme.corps), poses)

        for k, sid in enumerate(systeme.corps):
            solide = modele.solides[sid]
            i = 3 * k
            theta, omega, alpha = Q[:, i + 2], QD[:, i + 2], QDD[:, i + 2]
            c, s = np.cos(theta), np.sin(theta)
            gx, gy = solide.inertie.gx, solide.inertie.gy
            poses[:, i] = Q[:, i] - (c * gx - s * gy)
            poses[:, i + 1] = Q[:, i + 1] - (s * gx + c * gy)
            poses[:, i + 2] = theta

            base = f"solide/{sid}/"
            nom = solide.nom
            res.ajouter(base + "x", "longueur", Q[:, i], nom)
            res.ajouter(base + "y", "longueur", Q[:, i + 1], nom)
            res.ajouter(base + "angle", "angle", theta, nom)
            res.ajouter(base + "vx", "vitesse", QD[:, i], nom)
            res.ajouter(base + "vy", "vitesse", QD[:, i + 1], nom)
            res.ajouter(base + "v", "vitesse", np.hypot(QD[:, i], QD[:, i + 1]), nom)
            res.ajouter(base + "omega", "vitesse_angulaire", omega, nom)
            res.ajouter(base + "ax", "acceleration", QDD[:, i], nom)
            res.ajouter(base + "ay", "acceleration", QDD[:, i + 1], nom)
            res.ajouter(base + "a", "acceleration", np.hypot(QDD[:, i], QDD[:, i + 1]), nom)
            res.ajouter(base + "alpha", "acceleration_angulaire", alpha, nom)

            for point in solide.points.values():
                sx, sy = point.x - gx, point.y - gy
                bx, by = c * sx - s * sy, s * sx + c * sy
                vx, vy = QD[:, i] - by * omega, QD[:, i + 1] + bx * omega
                ax = QDD[:, i] - by * alpha - bx * omega * omega
                ay = QDD[:, i + 1] + bx * alpha - by * omega * omega
                bp = f"point/{sid}/{point.id}/"
                etiquette = f"{point.nom} ({nom})"
                res.ajouter(bp + "x", "longueur", Q[:, i] + bx, etiquette)
                res.ajouter(bp + "y", "longueur", Q[:, i + 1] + by, etiquette)
                res.ajouter(bp + "vx", "vitesse", vx, etiquette)
                res.ajouter(bp + "vy", "vitesse", vy, etiquette)
                res.ajouter(bp + "v", "vitesse", np.hypot(vx, vy), etiquette)
                res.ajouter(bp + "ax", "acceleration", ax, etiquette)
                res.ajouter(bp + "ay", "acceleration", ay, etiquette)
                res.ajouter(bp + "a", "acceleration", np.hypot(ax, ay), etiquette)

        for j, info in enumerate(systeme.liaisons.values()):
            liaison = info.liaison
            base = f"liaison/{liaison.id}/"
            tx, _, rz = liaison.MOBILITES
            deplacement = np.zeros(nb)
            angle = np.zeros(nb)
            vitesse = np.zeros(nb)
            rotation = np.zeros(nb)
            if liaison.CONTACT:
                tx = rz = False  # le mouvement relatif au contact se lit sur les solides
            for i in range(nb):
                deplacement[i], angle[i] = systeme.coordonnee_liaison(Q[i], info)
                vitesse[i], rotation[i] = systeme.vitesse_liaison(Q[i], QD[i], info)
            if rz:
                res.ajouter(base + "angle", "angle", angle, liaison.nom)
                res.ajouter(base + "vitesse_angulaire", "vitesse_angulaire", rotation, liaison.nom)
            if tx:
                res.ajouter(base + "deplacement", "longueur", deplacement, liaison.nom)
                res.ajouter(base + "vitesse", "vitesse", vitesse, liaison.nom)
            X, Y, N = self.torseurs[:nb, j, 0], self.torseurs[:nb, j, 1], self.torseurs[:nb, j, 2]
            res.ajouter(base + "px", "longueur", self.torseurs[:nb, j, 3], liaison.nom)
            res.ajouter(base + "py", "longueur", self.torseurs[:nb, j, 4], liaison.nom)
            if self.avec_efforts:
                res.ajouter(base + "X", "force", X, liaison.nom)
                res.ajouter(base + "Y", "force", Y, liaison.nom)
                res.ajouter(base + "N", "moment", N, liaison.nom)
                res.ajouter(base + "R", "force", np.hypot(X, Y), liaison.nom)
                if liaison.A_UN_AXE:
                    ka = info.attache_a[0]
                    beta = (Q[:, 3 * ka + 2] if ka >= 0 else 0.0) + info.angle_axe
                    normal = -np.sin(beta) * X + np.cos(beta) * Y
                    res.ajouter(base + "Fn", "force", normal, liaison.nom)
                    if liaison.type == "ponctuelle":
                        self._signaler_decollement(res, liaison.nom, t, normal)
                for nom, valeurs in self.contacts.get(liaison.id, {}).items():
                    res.ajouter(base + nom, "moment" if nom.startswith("couple") else "force", valeurs[:nb], liaison.nom)
                if liaison.type == "came" and base + "Fn" in res.canaux:
                    self._signaler_decollement(res, liaison.nom, t, res.valeurs(base + "Fn"))

        for j, info in enumerate(systeme.moteurs.values()):
            moteur = info.moteur
            base = f"moteur/{moteur.id}/"
            rotation = info.pilotage == "rotation"
            consigne = np.array([moteur.loi.evaluer(float(ti)) for ti in t]).reshape(nb, 3)
            res.ajouter(base + "position", "angle" if rotation else "longueur", info.reference + consigne[:, 0], moteur.nom)
            res.ajouter(base + "vitesse", "vitesse_angulaire" if rotation else "vitesse", consigne[:, 1], moteur.nom)
            if self.avec_efforts:
                effort = self.efforts_moteurs[:nb, j]
                res.ajouter(base + "effort", "moment" if rotation else "force", effort, moteur.nom)
                res.ajouter(base + "puissance", "puissance", effort * consigne[:, 1], moteur.nom)

        self._actions(res, t, Q, QD)

        cinetique = np.zeros(nb)
        potentielle = np.zeros(nb)
        for i in range(nb):
            cinetique[i], potentielle[i] = systeme.energies(Q[i], QD[i])
        res.ajouter("energie/cinetique", "energie", cinetique)
        res.ajouter("energie/potentielle", "energie", potentielle)
        res.ajouter("energie/mecanique", "energie", cinetique + potentielle)
        return res

    @staticmethod
    def _signaler_decollement(res: Resultats, nom: str, t: np.ndarray, normal: np.ndarray) -> None:
        """Un appui réel ne retient pas : si l'effort normal change de signe, il décollerait."""
        seuil = 1e-6 * float(np.max(np.abs(normal))) if normal.size else 0.0
        significatif = np.where(np.abs(normal) > seuil)[0]
        if significatif.size < 2:
            return
        signes = np.sign(normal[significatif])
        bascules = np.where(signes[1:] != signes[:-1])[0]
        if bascules.size:
            instant = float(t[significatif[bascules[0] + 1]])
            res.messages.append(Message("avertissement", "decollement", {"liaison": nom, "t": instant}))

    def _actions(self, res: Resultats, t: np.ndarray, Q: np.ndarray, QD: np.ndarray) -> None:
        systeme = self.systeme
        modele = systeme.mecanisme
        nb = t.size
        for attache, fx, fy, local, action_id in systeme._forces:
            composantes = np.array(
                [systeme.composantes_force(Q[i], float(t[i]), attache, fx, fy, local, action_id) for i in range(nb)]
            ).reshape(nb, 2)
            nom = modele.actions[action_id].nom
            res.ajouter(f"action/{action_id}/fx", "force", composantes[:, 0], nom)
            res.ajouter(f"action/{action_id}/fy", "force", composantes[:, 1], nom)
            res.ajouter(f"action/{action_id}/f", "force", np.hypot(composantes[:, 0], composantes[:, 1]), nom)
        for _, mz, action_id in systeme._couples:
            nom = modele.actions[action_id].nom
            res.ajouter(f"action/{action_id}/mz", "moment", [evaluer(mz, float(ti)) for ti in t], nom)
        for ressort in systeme._ressorts:
            action_id = ressort[5]
            nom = modele.actions[action_id].nom
            valeurs = np.array([systeme.effort_ressort(Q[i], QD[i], ressort)[:2] for i in range(nb)]).reshape(nb, 2)
            res.ajouter(f"action/{action_id}/effort", "force", valeurs[:, 0], nom)
            res.ajouter(f"action/{action_id}/longueur", "longueur", valeurs[:, 1], nom)


def instants(duree: float, pas: float) -> np.ndarray:
    """Instants d'échantillonnage 0, pas, 2·pas, … sans dépasser la durée.

    Un pas plus grand que la durée est ramené à la durée : il y a toujours au
    moins l'instant initial et un instant final.
    """
    if duree <= 0.0 or pas <= 0.0:
        return np.zeros(1)
    pas = min(pas, duree)
    nombre = max(1, int(math.floor(duree / pas + 1e-9)))
    return np.arange(nombre + 1) * pas


def liste_ids(objets) -> List[str]:
    return [o.id for o in objets]
