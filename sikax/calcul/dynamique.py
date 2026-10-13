"""Étude dynamique : intégration du principe fondamental de la dynamique (PFD).

Équations du mouvement sous contraintes :

    M·q̈ + Φqᵀ·λ = Q(q, q̇, t)
    Φq·q̈ = γ(q, q̇, t)

Résolution par la méthode du noyau, valable aussi pour un mécanisme
hyperstatique (lignes de Φq liées) ou comportant des solides sans masse :

    q̈ = q̈p + N·z     avec  Φq·q̈p = γ  (solution de norme minimale)
                            N = base du noyau de Φq (mouvements permis)
    (Nᵀ·M·N)·z = Nᵀ·(Q − M·q̈p)
    Φqᵀ·λ = Q − M·q̈

L'intégration en temps utilise Dormand-Prince 5(4). Après chaque pas, la
position et la vitesse sont reprojetées sur les liaisons, ce qui supprime la
dérive numérique sans stabilisation artificielle.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np

from .algebre import decomposer, resoudre
from .assemblage import assembler
from .cinematique import assembler_ou_echouer
from .enregistreur import Enregistreur
from .erreurs import CalculInterrompu, ErreurCalcul
from .integrateur import facteur_de_pas, norme_erreur, pas_dopri
from .resultats import Resultats
from .systeme import SystemeMecanique

Progression = Optional[Callable[[float], None]]
Annulation = Optional[Callable[[], bool]]

PAS_MINIMAL = 1e-12
ESSAIS_MAX_PAR_INTERVALLE = 200000
TOL_DYNAMIQUE = 1e-6
"""Seuil relatif sous lequel une direction de liaison est tenue pour dégénérée."""


class _Dynamique:
    def __init__(self, systeme: SystemeMecanique) -> None:
        self.s = systeme
        self.w = np.ones(systeme.n)
        self.w[2::3] = systeme.mecanisme.longueur_caracteristique()
        self.masses_s = systeme.masses / (self.w * self.w)
        self.hyperstatisme = 0
        self.mobilite = 0

    def accelerations(self, q: np.ndarray, qd: np.ndarray, t: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(q̈, λ, Φq, q̇ cohérente) à l'état donné.

        La vitesse est d'abord ramenée sur les liaisons (Φq·q̇ = −Φt) : les
        écarts de vitesse des étapes intermédiaires de l'intégrateur ne sont
        ainsi jamais réinjectés dans les accélérations.
        """
        s, w = self.s, self.w
        J = s.jacobienne(q, t)
        if s.nc == 0:
            self.hyperstatisme, self.mobilite = 0, s.n
            return s.forces(q, qd, t) / w / self.masses_s / w, np.zeros(0), J, qd
        Js = J / w
        U, sv, Vt, r_exact = decomposer(Js)
        # Près d'une configuration singulière, une direction de liaison devient
        # presque dégénérée : on la laisse à la projection en position plutôt
        # que de diviser par une valeur singulière minuscule.
        r = int(np.sum(sv > TOL_DYNAMIQUE * sv[0])) if sv.size and sv[0] > 0.0 else 0
        Ur, Vr, sr = U[:, :r], Vt[:r].T, sv[:r]
        vitesse = qd * w
        if r:
            vitesse = vitesse - Vr @ ((Ur.T @ (Js @ vitesse + s.phi_t(q, t))) / sr)
        qd = vitesse / w
        Q = s.forces(q, qd, t) / w
        particuliere = Vr @ ((Ur.T @ s.gamma(q, qd, t)) / sr) if r else np.zeros(s.n)
        N = Vt[r:].T
        acc = particuliere
        if N.shape[1]:
            reduite = (N.T * self.masses_s) @ N
            second = N.T @ (Q - self.masses_s * particuliere)
            try:
                z = np.linalg.solve(reduite, second)
            except np.linalg.LinAlgError as exc:
                raise ErreurCalcul("inertie_insuffisante") from exc
            acc = particuliere + N @ z
        multiplicateurs = Ur @ ((Vr.T @ (Q - self.masses_s * acc)) / sr) if r else np.zeros(s.nc)
        self.hyperstatisme = s.nc - r_exact
        self.mobilite = s.n - r_exact
        return acc / w, multiplicateurs, J, qd

    def verifier_inertie(self, q: np.ndarray, t: float) -> None:
        """Refuse le calcul si une mobilité libre n'entraîne aucune inertie."""
        s = self.s
        _, _, Vt, r = decomposer(s.jacobienne(q, t) / self.w) if s.nc else (None, None, np.eye(s.n), 0)
        N = Vt[r:].T
        if N.shape[1] == 0:
            return
        reduite = (N.T * self.masses_s) @ N
        valeurs = np.linalg.eigvalsh(reduite)
        if valeurs[0] <= 1e-12 * max(float(valeurs[-1]), 1e-300):
            sans_inertie = [
                s.mecanisme.solides[sid].nom
                for k, sid in enumerate(s.corps)
                if s.masses[3 * k] <= 0.0 or s.masses[3 * k + 2] <= 0.0
            ]
            raise ErreurCalcul("inertie_insuffisante", solides=", ".join(sans_inertie))

    def projeter_vitesse(self, q: np.ndarray, qd: np.ndarray, t: float) -> np.ndarray:
        """Vitesse la plus proche de q̇ qui respecte Φq·q̇ = −Φt."""
        s, w = self.s, self.w
        if s.nc == 0:
            return qd
        J = s.jacobienne(q, t) / w
        correction, _, _ = resoudre(J, J @ (qd * w) + s.phi_t(q, t), TOL_DYNAMIQUE)
        return qd - correction / w

    def vitesses_initiales(self, q: np.ndarray, t: float) -> np.ndarray:
        """Vitesses compatibles avec les liaisons et les vitesses initiales demandées."""
        s, w = self.s, self.w
        lignes: List[np.ndarray] = []
        cibles: List[float] = []
        for info in s.liaisons.values():
            vitesse = getattr(info.liaison, "vitesse_initiale", 0.0)
            if vitesse != 0.0 and info.liaison.PILOTAGE is not None:
                lignes.append(s.lignes_vitesse_liaison(q, info))
                cibles.append(vitesse)
        if not lignes:
            return self.projeter_vitesse(q, np.zeros(s.n), t)
        A = np.vstack([s.jacobienne(q, t)] + lignes) / w
        b = np.concatenate([-s.phi_t(q, t), np.array(cibles)])
        qd_s, _, _ = resoudre(A, b)
        return self.projeter_vitesse(q, qd_s / w, t)


def analyse_dynamique(
    systeme: SystemeMecanique,
    temps: np.ndarray,
    precision: float = 1e-8,
    tolerance: float = 1e-10,
    progression: Progression = None,
    annule: Annulation = None,
) -> Resultats:
    if systeme.n == 0:
        raise ErreurCalcul("aucun_solide")
    n = systeme.n
    dyn = _Dynamique(systeme)
    t = float(temps[0])
    q = assembler_ou_echouer(systeme, systeme.q0, t, tolerance)
    dyn.verifier_inertie(q, t)
    qd = dyn.vitesses_initiales(q, t)

    def derivee(instant: float, y: np.ndarray) -> np.ndarray:
        acc, _, _, vitesse = dyn.accelerations(y[:n], y[n:], instant)
        return np.concatenate([vitesse, acc])

    enregistreur = Enregistreur(systeme, temps.size)
    acc, multiplicateurs, J, qd = dyn.accelerations(q, qd, t)
    enregistreur.noter(t, q, qd, acc, multiplicateurs, J)
    hyperstatisme, mobilite = dyn.hyperstatisme, dyn.mobilite

    rtol, atol = precision, precision * 1e-2
    h = min(1e-3, float(temps[1] - temps[0])) if temps.size > 1 else 1e-3
    arret: Optional[float] = None
    y = np.concatenate([q, qd])

    k1: Optional[np.ndarray] = None  # pente au début du pas, conservée après un pas refusé
    for i in range(1, temps.size):
        cible = float(temps[i])
        essais = 0
        while t < cible - 1e-14 * max(1.0, abs(cible)):
            if annule is not None and annule():
                raise CalculInterrompu()
            essais += 1
            if essais > ESSAIS_MAX_PAR_INTERVALLE:
                arret = t
                break
            pas = min(h, cible - t)
            if k1 is None:
                k1 = derivee(t, y)
            y_nouveau, erreur = pas_dopri(derivee, t, y, pas, k1)
            if not np.all(np.isfinite(y_nouveau)):
                h = pas * 0.25
                if h < PAS_MINIMAL:
                    arret = t
                    break
                continue
            err = norme_erreur(erreur, y, y_nouveau, rtol, atol)
            if err > 1.0:
                h = pas * facteur_de_pas(err)
                if h < PAS_MINIMAL:
                    arret = t
                    break
                continue
            t_nouveau = t + pas
            projection = assembler(systeme, y_nouveau[:n], t_nouveau, True, tolerance)
            if not projection.converge:
                h = pas * 0.25
                if h < PAS_MINIMAL:
                    arret = t
                    break
                continue
            q = projection.q
            qd = dyn.projeter_vitesse(q, y_nouveau[n:], t_nouveau)
            y = np.concatenate([q, qd])
            t = t_nouveau
            k1 = None
            # Un pas raccourci pour tomber sur un instant de sortie ne réduit pas h.
            h = pas * facteur_de_pas(err) if pas >= h else max(h, pas * facteur_de_pas(err))
        if arret is not None:
            break
        t = cible
        acc, multiplicateurs, J, qd = dyn.accelerations(q, qd, t)
        y = np.concatenate([q, qd])
        enregistreur.noter(t, q, qd, acc, multiplicateurs, J)
        if progression is not None and (i % 10 == 0 or i == temps.size - 1):
            progression(i / (temps.size - 1))

    resultats = enregistreur.resultats("dynamique")
    resultats.hyperstatisme = hyperstatisme
    resultats.mobilite_libre = mobilite
    if arret is not None:
        resultats.complet = False
        resultats.ajouter_message("avertissement", "integration_interrompue", t=arret)
    if hyperstatisme > 0:
        resultats.ajouter_message("info", "hyperstatique_norme_minimale", h=hyperstatisme)
    if mobilite == 0:
        resultats.ajouter_message("info", "aucune_mobilite_libre")
    return resultats
