"""Étude dynamique : intégration du principe fondamental de la dynamique (PFD).

Équations du mouvement sous contraintes :

    M·q̈ + Φqᵀ·λ = Q(q, q̇, t)
    Φq·q̈ = γ(q, q̇, t)

**Intégration en temps.** Le système est confié à ``scipy.integrate.solve_ivp``
(Radau par défaut ; BDF, LSODA, DOP853 et RK45 au choix). Ces intégrateurs
attendent une équation différentielle ordinaire ẏ = f(t, y) : on la construit
avec l'état y = (q, v) et deux idées.

1. *Accélérations par lagrangien augmenté.* Avec la matrice A = M + α·ΦqᵀΦq,
   toujours définie positive dès que chaque mobilité a de l'inertie, on itère

       A·q̈ₖ = Q − Φqᵀ·λₖ + α·Φqᵀ·γ        λₖ₊₁ = λₖ + α·(Φq·q̈ₖ − γ)

   Trois itérations donnent la solution exacte à 10⁻¹⁵ près dans une
   configuration ordinaire. Près d'un point mort ou d'une bifurcation (Φq
   presque singulière), la direction dégénérée converge lentement : λ reste
   borné au lieu d'exploser, et f reste une fonction lisse de l'état. C'est
   ce qui permet aux méthodes implicites (Radau, BDF) de traverser ces
   configurations sans s'arrêter.

2. *Stabilisation des liaisons.* Les liaisons ne sont pas imposées exactement
   pendant l'intégration ; elles deviennent attractives :

       q̇ = v̂ + δq/τ        v̇ = q̈(q, v̂) + (v̂ − v)/τ

   où v̂ est la vitesse ramenée sur Φq·v̂ = −Φt et δq le petit déplacement qui
   referme les liaisons. Sur la variété des liaisons (Φ = 0, v̂ = v), ce sont
   exactement les équations du mouvement ; en dehors, l'écart s'amortit avec
   la constante de temps τ. Un intégrateur implicite absorbe cette raideur
   artificielle sans réduire son pas.

**Résultats.** Aux instants d'échantillonnage, l'état est reprojeté exactement
sur les liaisons et les efforts sont recalculés par la méthode du noyau
(décomposition en valeurs singulières), valable aussi pour un mécanisme
hyperstatique ou comportant des solides sans masse :

    q̈ = q̈p + N·z,   (Nᵀ·M·N)·z = Nᵀ·(Q − M·q̈p),   Φqᵀ·λ = Q − M·q̈
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import LinAlgError, cho_factor, cho_solve, lstsq

from ..modele.etude import METHODE_PAR_DEFAUT, METHODES
from .algebre import decomposer, rang, resoudre
from .assemblage import assembler
from .cinematique import analyse_cinematique, assembler_ou_echouer
from .enregistreur import Enregistreur
from .erreurs import CalculInterrompu, ErreurCalcul
from .resultats import Resultats
from .systeme import SystemeMecanique

Progression = Optional[Callable[[float], None]]
Annulation = Optional[Callable[[], bool]]

TOL_DYNAMIQUE = 1e-6
"""Seuil relatif sous lequel une direction de liaison est tenue pour dégénérée (résultats)."""

PENALITE = 1e6
"""α / (masse la plus grande) : poids des liaisons dans la matrice A = M + α·ΦqᵀΦq."""

ITERATIONS_LAGRANGIEN = 3

ITERATIONS_PERTES = 30
"""Itérations quand un engrenage frotte : le frottement dépend de l'effort transmis.

Chaque itération réduit l'écart d'un facteur voisin de 1 − η ; 30 itérations
suffisent largement pour un rendement de 0,5 ou plus."""

CONSTANTE_STABILISATION = 0.05
"""τ (s) : temps de retour sur les liaisons d'un écart numérique."""

APPELS_ENTRE_CONTROLES = 100
"""Nombre d'évaluations de f entre deux tests d'annulation et de progression."""

APPELS_SANS_PROGRES = 40_000
"""Au-delà de ce nombre d'évaluations sans que le temps n'avance, l'intégrateur est déclaré bloqué."""

REPLIS = {
    "Radau": ("BDF", "LSODA"),
    "BDF": ("Radau", "LSODA"),
    "LSODA": ("Radau", "BDF"),
    "DOP853": ("Radau", "LSODA"),
    "RK45": ("Radau", "LSODA"),
}
"""Méthodes essayées, dans l'ordre, si l'intégrateur choisi échoue en cours de route."""

VITESSE_EMBALLEMENT = 1e3
"""Vitesse (m/s) d'un centre de gravité au-delà de laquelle le calcul s'arrête : emballement."""

ROTATION_EMBALLEMENT = 1e4
"""Vitesse angulaire (rad/s, ≈ 95 000 tr/min) au-delà de laquelle le calcul s'arrête : emballement."""

FACTEUR_ACCELERATION_CONTINUE = 100.0
"""Rapport d'énergie cinétique (fin / début) qui signale un mécanisme qui ne cesse d'accélérer."""


class _Dynamique:
    """Calculs exacts à un instant donné : accélérations, efforts, vitesses compatibles."""

    def __init__(self, systeme: SystemeMecanique) -> None:
        self.s = systeme
        self.w = np.ones(systeme.n)
        self.w[2::3] = systeme.mecanisme.longueur_caracteristique()
        self.masses_s = systeme.masses / (self.w * self.w)
        self.hyperstatisme = 0
        self.mobilite = 0

    def accelerations(self, q: np.ndarray, qd: np.ndarray, t: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(q̈, λ, Φq, q̇ cohérente) à l'état donné, par la méthode du noyau.

        La vitesse est d'abord ramenée sur les liaisons (Φq·q̇ = −Φt) : un
        écart résiduel de l'intégrateur n'est jamais réinjecté dans les
        accélérations.
        """
        s, w = self.s, self.w
        J = s.jacobienne(q, t)
        if s.nc == 0:
            self.hyperstatisme, self.mobilite = 0, s.n
            Q = s.forces(q, qd, t)
            return Q / w / self.masses_s / w, np.zeros(0), J, qd
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
        N = Vt[r:].T
        gamma = s.gamma(q, qd, t)
        particuliere = Vr @ ((Ur.T @ gamma) / sr) if r else np.zeros(s.n)
        forces = s.forces(q, qd, t)
        pertes = np.zeros(s.n)
        multiplicateurs = np.zeros(s.nc)
        acc = particuliere
        reduite = (N.T * self.masses_s) @ N if N.shape[1] else None
        for _ in range(ITERATIONS_PERTES if s.avec_pertes else 1):
            Q = (forces + pertes) / w
            acc = particuliere
            if reduite is not None:
                second = N.T @ (Q - self.masses_s * particuliere)
                try:
                    z = np.linalg.solve(reduite, second)
                except np.linalg.LinAlgError as exc:
                    raise ErreurCalcul("inertie_insuffisante") from exc
                acc = particuliere + N @ z
            multiplicateurs = Ur @ ((Vr.T @ (Q - self.masses_s * acc)) / sr) if r else np.zeros(s.nc)
            nouvelles = s.pertes(q, qd, multiplicateurs)
            ecart = float(np.max(np.abs(nouvelles - pertes), initial=0.0))
            pertes = nouvelles
            if ecart <= 1e-13 * max(float(np.max(np.abs(forces), initial=0.0)), float(np.max(np.abs(pertes), initial=0.0)), 1e-300):
                break
        multiplicateurs = s.completer_multiplicateurs(q, J, multiplicateurs, (forces + pertes) - s.masses * (acc / w), TOL_DYNAMIQUE)
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
        # Référence : la plus grande inertie du mécanisme, et non celle des seules mobilités
        # libres (toutes nulles quand la seule mobilité libre est un solide sans masse).
        echelle = max(float(valeurs[-1]), float(np.max(self.masses_s)) if self.masses_s.size else 0.0)
        if echelle <= 0.0 or valeurs[0] <= 1e-12 * echelle:
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


class _Equations:
    """Second membre f(t, y) de l'équation différentielle stabilisée (voir l'en-tête du module).

    Aucune exception ne doit traverser l'intégrateur : LSODA est écrit en
    Fortran, et une exception Python levée pendant un de ses rappels, dans le
    fil de calcul, arrête brutalement le programme. Une annulation, une erreur
    (expression invalide) ou un intégrateur qui piétine sont donc notés, et le
    second membre rend des valeurs non numériques : l'intégrateur échoue
    proprement, et l'exception est levée ensuite, hors de lui.
    """

    def __init__(self, systeme: SystemeMecanique, duree: float, progression: Progression, annule: Annulation) -> None:
        self.s = systeme
        self.n = systeme.n
        self.masses = systeme.masses.copy()
        # Sans aucune masse (mécanisme entièrement imposé), une échelle unitaire évite un α dérisoire.
        self.masse_max = float(self.masses.max()) if self.n and float(self.masses.max()) > 0.0 else 1.0
        self.duree = max(duree, 1e-300)
        self.progression = progression
        self.annule = annule
        self.appels = 0
        self.avancement = 0.0
        self.erreur: Optional[BaseException] = None
        """Exception survenue pendant l'intégration, à lever une fois l'intégrateur sorti."""
        self.bloque = False
        """Vrai si l'intégrateur n'avance plus (pas de temps réduit à rien)."""
        self._t_progres = -math.inf
        self._appels_progres = 0

    def arreter(self) -> bool:
        """Vrai si l'intégration doit cesser (annulation, erreur, intégrateur bloqué)."""
        return self.erreur is not None or self.bloque

    def relancer(self) -> None:
        """Avant d'essayer une autre méthode : le piétinement de la précédente est oublié."""
        self.bloque = False
        self._t_progres = -math.inf

    def _controler(self, t: float) -> None:
        if self.annule is not None and self.annule():
            raise CalculInterrompu()
        if self.progression is not None and t > self.avancement:
            self.avancement = t
            self.progression(min(t / self.duree, 1.0))

    def _surveiller(self, t: float) -> None:
        """Repère un intégrateur qui piétine : beaucoup d'appels sans que le temps n'avance."""
        if t > self._t_progres + 1e-9 * self.duree:
            self._t_progres = t
            self._appels_progres = self.appels
        elif self.appels - self._appels_progres > APPELS_SANS_PROGRES:
            self.bloque = True

    def __call__(self, t: float, y: np.ndarray) -> np.ndarray:
        if self.arreter():
            return np.full(y.shape, np.nan)
        try:
            self.appels += 1
            if self.appels % APPELS_ENTRE_CONTROLES == 0:
                self._controler(t)
            self._surveiller(t)
            if self.bloque or not np.all(np.isfinite(y)):
                # un état non numérique : l'intégrateur réduira son pas (inutile d'appeler LAPACK)
                return np.full(y.shape, np.nan)
            return self._derivee(t, y)
        except BaseException as exc:  # noqa: BLE001 - relevée après la sortie de l'intégrateur
            self.erreur = exc
            return np.full(y.shape, np.nan)

    def _derivee(self, t: float, y: np.ndarray) -> np.ndarray:
        s, n = self.s, self.n
        q, v = y[:n], y[n:]
        if s.nc == 0:
            acc = s.forces(q, v, t) / self.masses
            return np.concatenate([v, acc])
        J = s.jacobienne(q, t)
        Jt = J.T
        JtJ = Jt @ J
        alpha = PENALITE * self.masse_max / max(float(np.max(np.diag(JtJ))), 1e-300)
        A = alpha * JtJ
        A[np.diag_indices(n)] += self.masses
        try:
            facteur = cho_factor(A, check_finite=False)

            def resoudre_a(b: np.ndarray) -> np.ndarray:
                return cho_solve(facteur, b, check_finite=False)

        except LinAlgError:
            # Solide sans inertie sur une mobilité : A n'est que semi-définie.
            def resoudre_a(b: np.ndarray) -> np.ndarray:
                return lstsq(A, b, check_finite=False)[0]

        # Vitesse ramenée sur les liaisons et petit déplacement qui les referme.
        v_lie = v - resoudre_a(alpha * (Jt @ (J @ v + s.phi_t(q, t))))
        fermeture = -resoudre_a(alpha * (Jt @ s.phi(q, t)))
        gamma = s.gamma(q, v_lie, t)
        cible = alpha * (Jt @ gamma)
        Q = s.forces(q, v_lie, t)
        lam = np.zeros(s.nc)
        acc = np.zeros(n)
        pertes = np.zeros(n)
        for _ in range(ITERATIONS_PERTES if s.avec_pertes else ITERATIONS_LAGRANGIEN):
            acc = resoudre_a(Q + pertes - Jt @ lam + cible)
            lam = lam + alpha * (J @ acc - gamma)
            if s.avec_pertes:
                pertes = s.pertes(q, v_lie, lam)
        tau = CONSTANTE_STABILISATION
        return np.concatenate([v_lie + fermeture / tau, acc + (v_lie - v) / tau])


def _tolerances(systeme: SystemeMecanique, precision: float) -> np.ndarray:
    """Tolérances absolues par composante de l'état (positions, angles, vitesses)."""
    longueur = systeme.mecanisme.longueur_caracteristique()
    echelle = np.ones(systeme.n)
    echelle[0::3] = longueur
    echelle[1::3] = longueur
    return precision * 1e-2 * np.concatenate([echelle, 10.0 * echelle])


def _emballement_atteint(equations: "_Equations") -> Callable[[float, np.ndarray], float]:
    """Événement d'arrêt : un solide dépasse ``ROTATION_EMBALLEMENT`` ou ``VITESSE_EMBALLEMENT``,
    ou le calcul doit cesser (annulation, erreur).

    La valeur est positive tant que toutes les vitesses restent sous les seuils.
    """
    n = equations.n

    def evenement(t: float, y: np.ndarray) -> float:
        if equations.arreter():
            return -1.0
        v = y[n:]
        if not np.all(np.isfinite(v)):
            return -1.0
        rotation = float(np.max(np.abs(v[2::3]), initial=0.0)) / ROTATION_EMBALLEMENT
        translation = float(np.max(np.hypot(v[0::3], v[1::3]), initial=0.0)) / VITESSE_EMBALLEMENT
        return 1.0 - max(rotation, translation)

    evenement.terminal = True  # type: ignore[attr-defined]
    return evenement


def _integrer(
    equations: _Equations,
    methode: str,
    temps: np.ndarray,
    y0: np.ndarray,
    precision: float,
    atol: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, str, Optional[Tuple[float, np.ndarray]]]:
    """Intègre de temps[0] à temps[-1].

    Retourne (instants atteints, états, issue, emballement) avec issue
    ``"fin"``, ``"emballement"``, ``"bloque"`` ou le message d'échec de
    l'intégrateur ; ``emballement`` est l'instant et l'état où la vitesse
    a franchi son seuil (souvent entre deux instants enregistrés), ou None.
    """
    if temps.size == 1:
        return temps.copy(), y0[None, :], "fin", None
    try:
        solution = solve_ivp(
            equations,
            (float(temps[0]), float(temps[-1])),
            y0,
            method=methode,
            t_eval=temps,
            rtol=precision,
            atol=atol,
            events=_emballement_atteint(equations),
        )
    except (ArithmeticError, LinAlgError, ValueError) as exc:
        if equations.erreur is not None:
            raise equations.erreur from exc
        return temps[:1], y0[None, :], str(exc) or type(exc).__name__, None
    if equations.erreur is not None:
        raise equations.erreur
    if equations.bloque:
        return solution.t, solution.y.T, "bloque", None
    if solution.status == 1:
        evenement = (float(solution.t_events[0][0]), solution.y_events[0][0]) if len(solution.t_events[0]) else None
        return solution.t, solution.y.T, "emballement", evenement
    return solution.t, solution.y.T, "fin" if solution.status == 0 else str(solution.message), None


def _plus_rapide(systeme: SystemeMecanique, qd: np.ndarray) -> Tuple[str, str, float]:
    """(nature, solide, valeur) de la vitesse la plus proche de son seuil d'emballement."""
    rotations = np.max(np.abs(qd[:, 2::3]), axis=0)
    translations = np.max(np.hypot(qd[:, 0::3], qd[:, 1::3]), axis=0)
    k_r, k_t = int(np.argmax(rotations)), int(np.argmax(translations))
    if rotations[k_r] / ROTATION_EMBALLEMENT >= translations[k_t] / VITESSE_EMBALLEMENT:
        return "rotation", systeme.mecanisme.solides[systeme.corps[k_r]].nom, float(rotations[k_r])
    return "translation", systeme.mecanisme.solides[systeme.corps[k_t]].nom, float(translations[k_t])


def _accelere_sans_cesse(cinetique: np.ndarray) -> bool:
    """Vrai si l'énergie cinétique ne fait que croître et finit très au-dessus de son départ.

    C'est la signature d'un couple ou d'une force motrice que rien n'équilibre
    (ni charge, ni frottement, ni pesanteur) : la vitesse augmente sans limite.
    """
    if cinetique.size < 20:
        return False
    fin = cinetique[-max(5, cinetique.size // 5):]
    reference = max(float(cinetique[0]), float(np.max(cinetique[: max(2, cinetique.size // 10)])), 1e-300)
    return bool(np.all(np.diff(fin) > 0.0) and float(cinetique[-1]) > FACTEUR_ACCELERATION_CONTINUE * reference)


def analyse_dynamique(
    systeme: SystemeMecanique,
    temps: np.ndarray,
    precision: float = 1e-8,
    tolerance: float = 1e-10,
    progression: Progression = None,
    annule: Annulation = None,
    methode: str = METHODE_PAR_DEFAUT,
) -> Resultats:
    if systeme.n == 0:
        raise ErreurCalcul("aucun_solide")
    if methode not in METHODES:
        methode = METHODE_PAR_DEFAUT
    n = systeme.n
    dyn = _Dynamique(systeme)
    t0 = float(temps[0])
    q = assembler_ou_echouer(systeme, systeme.q0, t0, tolerance)
    dyn.verifier_inertie(q, t0)
    if systeme.nc and rang(systeme.jacobienne(q, t0) / dyn.w) == n:
        # Aucune mobilité libre : moteurs et liaisons imposent tout le mouvement. Le PFD ne
        # sert plus qu'à calculer les efforts : c'est exactement l'étude cinématique avec inertie.
        resultats = analyse_cinematique(systeme, temps, True, tolerance, progression, annule)
        resultats.type_etude = "dynamique"
        resultats.ajouter_message("info", "aucune_mobilite_libre")
        return resultats
    qd = dyn.vitesses_initiales(q, t0)

    equations = _Equations(systeme, float(temps[-1] - t0), progression, annule)
    atol = _tolerances(systeme, precision)
    etats: List[np.ndarray] = [np.concatenate([q, qd])]
    atteints: List[float] = [t0]
    essais = [methode] + [m for m in REPLIS.get(methode, ()) if m != methode]
    utilisees: List[str] = []
    issue = "fin"
    evenement: Optional[Tuple[float, np.ndarray]] = None
    for courante in essais:
        utilisees.append(courante)
        equations.relancer()
        restants = temps[len(atteints) - 1:]
        with np.errstate(all="ignore"):
            instants_atteints, y, issue, evenement = _integrer(equations, courante, restants, etats[-1], precision, atol)
        for t_i, y_i in zip(instants_atteints[1:], y[1:]):
            atteints.append(float(t_i))
            etats.append(y_i)
        if issue in ("fin", "emballement"):
            break
        # échec ou piétinement : on repart du dernier instant atteint avec la méthode suivante
    arret = None if issue == "fin" else atteints[-1]

    enregistreur = Enregistreur(systeme, len(atteints))
    hyperstatisme, mobilite = 0, n
    vitesses = np.zeros((len(atteints), n))
    for i, (t_i, y_i) in enumerate(zip(atteints, etats)):
        if annule is not None and annule():
            raise CalculInterrompu()
        q_i, qd_i = y_i[:n], y_i[n:]
        projection = assembler(systeme, q_i, t_i, True, tolerance)
        if projection.converge:
            q_i = projection.q
        qd_i = dyn.projeter_vitesse(q_i, qd_i, t_i)
        acc, multiplicateurs, J, qd_i = dyn.accelerations(q_i, qd_i, t_i)
        enregistreur.noter(t_i, q_i, qd_i, acc, multiplicateurs, J)
        vitesses[i] = qd_i
        if i == 0:
            hyperstatisme, mobilite = dyn.hyperstatisme, dyn.mobilite
    if progression is not None:
        progression(1.0)

    resultats = enregistreur.resultats("dynamique")
    resultats.hyperstatisme = hyperstatisme
    resultats.mobilite_libre = mobilite
    resultats.methode = utilisees[-1]
    if len(utilisees) > 1 and issue != "emballement":
        resultats.ajouter_message("info", "methode_de_repli", methode=utilisees[0], repli=utilisees[-1])
    if issue == "emballement":
        resultats.complet = False
        if evenement is not None:
            # l'état où le seuil est franchi, pas seulement les instants enregistrés avant lui
            arret = evenement[0]
            vitesses = np.vstack([vitesses, evenement[1][None, n:]])
        nature, solide, valeur = _plus_rapide(systeme, vitesses)
        resultats.ajouter_message("avertissement", f"emballement_{nature}", t=arret, solide=solide, valeur=f"{valeur:.3g}")
    elif arret is not None:
        resultats.complet = False
        resultats.ajouter_message("avertissement", "integration_interrompue", t=arret)
    elif _accelere_sans_cesse(resultats.valeurs("energie/cinetique")):
        nature, solide, valeur = _plus_rapide(systeme, vitesses)
        resultats.ajouter_message("avertissement", "acceleration_continue", solide=solide, valeur=f"{valeur:.3g}", nature=nature)
    if hyperstatisme > 0:
        resultats.ajouter_message("info", "hyperstatique_norme_minimale", h=hyperstatisme)
    if mobilite == 0:
        resultats.ajouter_message("info", "aucune_mobilite_libre")
    return resultats
