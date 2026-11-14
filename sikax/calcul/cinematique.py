"""Étude cinématique : le mouvement est imposé par les moteurs.

À chaque instant :

1. position      Φ(q, t) = 0                 (Gauss-Newton, voir ``assemblage``)
2. vitesse       Φq·q̇ = −Φt
3. accélération  Φq·q̈ = γ
4. efforts       Φqᵀ·λ = Q − M·q̈            (PFD ; PFS si l'inertie est négligée)

L'étape 4 est une dynamique inverse : connaissant le mouvement, on obtient
les actions de liaison et l'effort que chaque moteur doit fournir.

**Points morts.** Quand le moteur ne commande plus le mouvement (piston d'un
système bielle-manivelle au point mort haut, balancier d'un quadrilatère en
position limite), Φq devient singulière : les étapes 2 et 3 divisent alors
par une valeur singulière presque nulle et produisent des vitesses et des
efforts absurdes. Sikax procède donc en deux passes.

- *Positions.* Le mécanisme est suivi instant après instant par continuation ;
  près d'un point mort, la prédiction prolonge les positions déjà calculées,
  ce qui fait franchir le point mort dans le sens du mouvement (comme le ferait
  l'inertie) au lieu de rebrousser chemin.
- *Dérivées.* Là où Φq est bien conditionnée, vitesses et accélérations sont
  exactes (étapes 2 et 3). Près d'un point mort, elles sont obtenues en
  dérivant un polynôme ajusté sur les positions voisines, puis corrigées pour
  respecter exactement les directions de liaison bien déterminées ; les
  efforts sont calculés sans la direction dégénérée et restent bornés.

Si la loi du moteur demande un mouvement que le mécanisme ne peut pas suivre
(piston poussé au-delà de sa course), le calcul s'arrête proprement et le
signale.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .algebre import TOL_RANG, decomposer, rang, resoudre
from .assemblage import ResultatAssemblage, assembler
from .enregistreur import Enregistreur
from .erreurs import CalculInterrompu, ErreurCalcul
from .resultats import Resultats
from .systeme import SystemeMecanique

Progression = Optional[Callable[[float], None]]
Annulation = Optional[Callable[[], bool]]

SEUIL_POINT_MORT = 1e3
"""Conditionnement de Φq au-delà duquel la configuration est dite proche d'un point mort.

Un mécanisme ordinaire reste entre 10 et 100 ; au voisinage d'un point mort,
le conditionnement croît sans borne."""

SEUIL_CONDITIONNEMENT = 1e7
"""Au-delà, on considère que le point mort est atteint (franchi ou bloquant)."""

SEUIL_DERIVATION = 1e5
"""Conditionnement au-delà duquel vitesses et accélérations sont tirées des positions."""

TOL_SINGULIERE = 1e-5
"""Seuil relatif des directions de liaison conservées près d'un point mort."""

DEMI_FENETRE = 3
"""Nombre d'instants de part et d'autre utilisés pour dériver les positions."""


def _echelle(systeme: SystemeMecanique) -> np.ndarray:
    w = np.ones(systeme.n)
    w[2::3] = systeme.mecanisme.longueur_caracteristique()
    return w


def assembler_ou_echouer(systeme: SystemeMecanique, q: np.ndarray, t: float, tolerance: float, moteurs: bool = True) -> np.ndarray:
    resultat = assembler(systeme, q, t, moteurs, tolerance)
    if not resultat.converge:
        raise ErreurCalcul("assemblage_impossible", residu=resultat.residu)
    return resultat.q


def _avancer(
    systeme: SystemeMecanique,
    q: np.ndarray,
    prediction: np.ndarray,
    t_avant: float,
    t: float,
    tolerance: float,
    directions: Optional[np.ndarray] = None,
) -> ResultatAssemblage:
    """Position à l'instant t, avec replis si la première tentative échoue.

    ``directions`` (colonnes) sont les mouvements que Φq ne voit plus à un
    point mort. Gauss-Newton, parti du point mort lui-même, ne sait pas de
    quel côté aller : on l'aide en décalant le départ le long de ces
    directions, d'abord d'un côté puis de l'autre.
    """
    essai = assembler(systeme, prediction, t, True, tolerance)
    if essai.converge:
        return essai
    essai = assembler(systeme, q, t, True, tolerance)
    if essai.converge:
        return essai
    if directions is not None and directions.size:
        longueur = systeme.mecanisme.longueur_caracteristique()
        for amplitude in (1e-2, 1e-3, 3e-2, 1e-1):
            for signe in (1.0, -1.0):
                for k in range(directions.shape[1]):
                    depart = q + signe * amplitude * longueur * directions[:, k]
                    decale = assembler(systeme, depart, t, True, tolerance)
                    if decale.converge:
                        return decale
    # Continuation : on rejoint t par petits pas depuis la dernière position sûre.
    for divisions in (4, 16, 64):
        courant = q
        reussi = True
        for etape in range(1, divisions + 1):
            intermediaire = t_avant + (t - t_avant) * etape / divisions
            essai = assembler(systeme, courant, intermediaire, True, tolerance)
            if not essai.converge:
                reussi = False
                break
            courant = essai.q
        if reussi:
            return essai
    return essai


def _extrapoler(instants: Sequence[float], positions: Sequence[np.ndarray], t: float) -> np.ndarray:
    """Polynôme de Lagrange passant par les dernières positions, évalué en t."""
    points = list(zip(instants[-3:], positions[-3:]))
    resultat = np.zeros_like(points[-1][1])
    for j, (tj, qj) in enumerate(points):
        poids = 1.0
        for k, (tk, _) in enumerate(points):
            if k != j:
                poids *= (t - tk) / (tj - tk)
        resultat += poids * qj
    return resultat


def _predire(instants, positions, vitesses, accelerations, conditionnements, t: float) -> np.ndarray:
    """Position attendue à l'instant t, d'où partira Gauss-Newton.

    En configuration ordinaire, le développement de Taylor (vitesse et
    accélération exactes) est le plus précis. Près d'un point mort, la vitesse
    calculée peut être démesurée et projeter la prédiction un tour plus loin :
    on prolonge alors simplement les dernières positions.
    """
    q = positions[-1]
    dt = t - instants[-1]
    taylor = q + vitesses[-1] * dt + 0.5 * accelerations[-1] * dt * dt
    if len(positions) < 2:
        return taylor if conditionnements[-1] <= SEUIL_POINT_MORT else q
    extrapolation = _extrapoler(instants, positions, t)
    if conditionnements[-1] > SEUIL_POINT_MORT:
        return extrapolation
    dernier_pas = float(np.max(np.abs(positions[-1] - positions[-2])))
    if float(np.max(np.abs(taylor - q))) > 4.0 * dernier_pas * dt / max(instants[-1] - instants[-2], 1e-300) + 1e-12:
        return extrapolation
    return taylor


def _au_plus_pres(q: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Ramène chaque angle au tour le plus proche de la référence.

    Deux configurations dont un angle diffère de 2π sont identiques ; garder
    l'angle continu évite des sauts d'un tour dans les courbes et les dérivées.
    """
    resultat = q.copy()
    ecart = resultat[2::3] - reference[2::3]
    resultat[2::3] -= 2.0 * np.pi * np.round(ecart / (2.0 * np.pi))
    return resultat


def _deriver(instants: np.ndarray, positions: np.ndarray, i: int) -> tuple:
    """(q̇, q̈) à l'instant i, par un polynôme ajusté sur les positions voisines."""
    debut = max(0, i - DEMI_FENETRE)
    fin = min(len(instants), i + DEMI_FENETRE + 1)
    t = instants[debut:fin] - instants[i]
    echelle = float(np.max(np.abs(t))) or 1.0
    x = t / echelle
    degre = min(4, len(t) - 1)
    if degre < 1:
        return np.zeros(positions.shape[1]), np.zeros(positions.shape[1])
    V = np.vander(x, degre + 1, increasing=True)
    coefficients, *_ = np.linalg.lstsq(V, positions[debut:fin], rcond=None)
    vitesse = coefficients[1] / echelle
    acceleration = 2.0 * coefficients[2] / (echelle * echelle) if degre >= 2 else np.zeros_like(vitesse)
    return vitesse, acceleration


def _corriger(Js: np.ndarray, estimation_s: np.ndarray, cible: np.ndarray) -> np.ndarray:
    """Rend Js·x = cible exact dans les directions bien conditionnées, sans toucher aux autres."""
    correction, _, _ = resoudre(Js, Js @ estimation_s - cible, TOL_SINGULIERE)
    return estimation_s - correction


def _zones(instants: Sequence[float], conditionnements: Sequence[float]) -> List[Tuple[float, float]]:
    """Intervalles de temps passés au voisinage d'un point mort (Φq mal conditionnée)."""
    zones: List[Tuple[float, float]] = []
    debut: Optional[float] = None
    for t, c in zip(instants, conditionnements):
        if c > SEUIL_POINT_MORT:
            if debut is None:
                debut = t
            fin = t
        elif debut is not None:
            zones.append((debut, fin))
            debut = None
    if debut is not None:
        zones.append((debut, fin))
    return zones


def _pic_d_effort(resultats: Resultats, zones: List[Tuple[float, float]]) -> Optional[Tuple[float, str, str]]:
    """(instant, moteur, valeur) si l'effort d'un moteur s'envole au voisinage d'un point mort.

    On compare l'effort dans les zones de point mort à celui du reste du
    mouvement : un rapport de plus de 10 signale un moteur qui n'a presque plus
    de prise sur le mécanisme et doit fournir un effort démesuré.
    """
    if not zones:
        return None
    t = resultats.temps
    dans = np.zeros(t.size, dtype=bool)
    for debut, fin in zones:
        dans |= (t >= debut) & (t <= fin)
    pire: Optional[Tuple[float, str, str]] = None
    rapport_max = 10.0
    for cle in resultats.cles("moteur/"):
        if not cle.endswith("/effort"):
            continue
        canal = resultats.canal(cle)
        valeurs = np.abs(canal.valeurs)
        if not dans.any():
            continue
        hors = float(np.max(valeurs[~dans])) if (~dans).any() else 0.0
        i = int(np.argmax(np.where(dans, valeurs, -1.0)))
        rapport = valeurs[i] / max(hors, 1e-12)
        if rapport > rapport_max:
            unite = "N·m" if canal.dimension == "moment" else "N"
            rapport_max = rapport
            pire = (float(t[i]), canal.objet, f"{valeurs[i]:.3g} {unite}")
    return pire


def analyse_cinematique(
    systeme: SystemeMecanique,
    temps: np.ndarray,
    inertie: bool = True,
    tolerance: float = 1e-10,
    progression: Progression = None,
    annule: Annulation = None,
) -> Resultats:
    if systeme.n == 0:
        raise ErreurCalcul("aucun_solide")
    n = systeme.n
    w = _echelle(systeme)
    t0 = float(temps[0])
    q = assembler_ou_echouer(systeme, systeme.q0, t0, tolerance)

    J = systeme.jacobienne(q, t0)
    r = rang(J / w) if J.size else 0
    depart_singulier = False
    if r < n:
        rang_liaisons = rang(J[: systeme.nc_liaisons] / w) if systeme.nc_liaisons else 0
        mobilite = n - rang_liaisons
        if len(systeme.moteurs) < mobilite:
            raise ErreurCalcul("mobilite_non_pilotee", mobilite=n - r, moteurs=len(systeme.moteurs))
        # Assez de moteurs, mais ils ne commandent pas le mouvement ici (point mort).
        # On ne peut partir que si la loi n'y impose pas une vitesse impossible.
        phi_t = systeme.phi_t(q, t0)
        _, _, residu = resoudre(J / w, -phi_t)
        if residu > 1e-6 * max(float(np.linalg.norm(phi_t)), 1e-12) and float(np.linalg.norm(phi_t)) > 1e-12:
            raise ErreurCalcul("position_initiale_singuliere", mobilite=n - r)
        depart_singulier = True

    # -- 1. positions, et dérivées exactes là où elles sont bien définies ---------
    instants: List[float] = []
    positions: List[np.ndarray] = []
    vitesses: List[np.ndarray] = []
    accelerations: List[np.ndarray] = []
    conditionnements: List[float] = []
    rangs: List[int] = []
    directions: Optional[np.ndarray] = None
    arret: Optional[float] = None
    for i, t in enumerate(temps):
        t = float(t)
        if annule is not None and annule():
            raise CalculInterrompu()
        if i > 0:
            prediction = _predire(instants, positions, vitesses, accelerations, conditionnements, t)
            essai = _avancer(systeme, q, prediction, instants[-1], t, tolerance, directions)
            if not essai.converge:
                arret = t
                break
            q = _au_plus_pres(essai.q, prediction)
        J = systeme.jacobienne(q, t)
        Js = J / w
        _, sv, Vt, rang_q = decomposer(Js, TOL_RANG)
        conditionnement = float(sv[0] / sv[-1]) if sv.size == n and sv[-1] > 0.0 else float("inf")
        rangs.append(rang_q)
        if conditionnement > SEUIL_DERIVATION:
            petites = int(np.sum(sv < TOL_SINGULIERE * sv[0])) + max(0, n - sv.size) if sv.size else n
            directions = (Vt[n - max(petites, 1):].T / w[:, None]) if Vt.size else None
        else:
            directions = None
        qd_s, _, _ = resoudre(Js, -systeme.phi_t(q, t))
        qd = qd_s / w
        qdd_s, _, _ = resoudre(Js, systeme.gamma(q, qd, t))
        instants.append(t)
        positions.append(q)
        vitesses.append(qd)
        accelerations.append(qdd_s / w)
        conditionnements.append(conditionnement)
        if progression is not None and (i % 20 == 0 or i == temps.size - 1):
            progression(0.8 * (i + 1) / temps.size)

    # -- 2. dérivées près des points morts, puis efforts -------------------------
    T = np.array(instants)
    P = np.array(positions)
    enregistreur = Enregistreur(systeme, len(instants))
    for i, t in enumerate(instants):
        if annule is not None and annule():
            raise CalculInterrompu()
        q = positions[i]
        J = systeme.jacobienne(q, t)
        Js = J / w
        tol_efforts = TOL_RANG
        qd, qdd = vitesses[i], accelerations[i]
        if conditionnements[i] > SEUIL_DERIVATION and len(instants) > 1:
            estimation_v, estimation_a = _deriver(T, P, i)
            qd = _corriger(Js, estimation_v * w, -systeme.phi_t(q, t)) / w
            qdd = _corriger(Js, estimation_a * w, systeme.gamma(q, qd, t)) / w
            tol_efforts = TOL_SINGULIERE
        second_membre = systeme.forces(q, qd, t)
        if inertie:
            second_membre = second_membre - systeme.masses * qdd
        multiplicateurs = systeme.multiplicateurs(q, qd, J, second_membre, tol_efforts)
        enregistreur.noter(t, q, qd, qdd, multiplicateurs, J)
        if progression is not None and (i % 20 == 0 or i == len(instants) - 1):
            progression(0.8 + 0.2 * (i + 1) / len(instants))

    resultats = enregistreur.resultats("cinematique")
    # Hyperstatisme lu dans une configuration ordinaire : à un point mort, Φq perd un rang.
    reguliers = [rangs[i] for i, c in enumerate(conditionnements) if c <= SEUIL_POINT_MORT]
    resultats.hyperstatisme = systeme.nc - (max(reguliers) if reguliers else max(rangs, default=r))
    resultats.mobilite_libre = 0
    zones = _zones(instants, conditionnements)
    resultats.zones_singulieres = zones
    franchies = [debut for debut, fin in zones if instants[0] < debut and fin < instants[-1]]
    if arret is not None:
        resultats.complet = False
        resultats.ajouter_message("avertissement", "mouvement_impossible", t=arret)
    if depart_singulier:
        resultats.ajouter_message("info", "depart_point_mort")
    if franchies:
        resultats.ajouter_message("info", "points_morts_franchis", t=", ".join(f"{t:.4g}" for t in franchies), nombre=len(franchies))
    pic = _pic_d_effort(resultats, zones)
    if pic is not None:
        resultats.ajouter_message("avertissement", "efforts_point_mort", t=f"{pic[0]:.4g}", moteur=pic[1], valeur=pic[2])
    if resultats.hyperstatisme > 0:
        resultats.ajouter_message("info", "hyperstatique_norme_minimale", h=resultats.hyperstatisme)
    if not inertie:
        resultats.ajouter_message("info", "quasi_statique")
    elif not systeme.masse_definie_positive:
        resultats.ajouter_message("info", "inertie_partielle")
    return resultats
