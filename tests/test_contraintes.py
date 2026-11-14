"""Les jacobiennes et seconds membres analytiques, vérifiés par différences finies."""

import math

import numpy as np
import pytest

from sikax.calcul.contraintes import (
    AngleRelatif,
    Coincidence,
    DistanceConstante,
    EngrenageCremaillere,
    EngrenageRoues,
    PlateauTangent,
    PointSurDroite,
    TranslationPilotee,
    coordonnee_translation,
    vitesse_translation,
)


def loi(t):
    return (0.3 * math.sin(2.0 * t) + 0.1 * t * t, 0.6 * math.cos(2.0 * t) + 0.2 * t, -1.2 * math.sin(2.0 * t) + 0.2)


REPOS = np.zeros(9)
"""État de référence des contraintes qui en ont besoin (phase d'un engrenage, côté d'une crémaillère)."""


def contraintes():
    a0, a1, a2 = (0, 0.21, -0.13), (1, -0.17, 0.08), (2, 0.05, 0.3)
    sol = (-1, 0.4, -0.2)
    return {
        "coincidence": Coincidence(a0, a1),
        "coincidence_bati_a": Coincidence(sol, a2),
        "coincidence_bati_b": Coincidence(a1, sol),
        "angle": AngleRelatif(0, 2, 0.4),
        "angle_bati": AngleRelatif(-1, 1, -0.2),
        "angle_pilote": AngleRelatif(1, 2, 0.3, loi),
        "angle_pilote_bati": AngleRelatif(2, -1, 0.1, loi),
        "droite": PointSurDroite(a0, 0.7, a2),
        "droite_bati_a": PointSurDroite(sol, -0.4, a1),
        "droite_bati_b": PointSurDroite(a2, 1.9, sol),
        "translation": TranslationPilotee(a1, 0.5, a2, 0.05, loi),
        "translation_bati_a": TranslationPilotee(sol, 2.2, a0, -0.1, loi),
        "translation_bati_b": TranslationPilotee(a0, -1.1, sol, 0.2, loi),
        # contacts : engrenages et cames
        "engrenage_exterieur": EngrenageRoues(a0, a1, 0.03, 0.05, 1.0, REPOS),
        "engrenage_interieur": EngrenageRoues(a2, a0, 0.02, 0.06, -1.0, REPOS),
        "engrenage_bati": EngrenageRoues(sol, a1, 0.04, 0.02, 1.0, REPOS),
        "cremaillere": EngrenageCremaillere(a1, 0.3, a2, 0.025, REPOS),
        "cremaillere_bati": EngrenageCremaillere(sol, -0.6, a0, 0.03, REPOS),
        "came_pointe": DistanceConstante(a0, a2, 0.04, 0.03),
        "came_bati": DistanceConstante(sol, a1, 0.05, 0.04),
        "plateau": PlateauTangent(a1, 0.4, a0, 0.03, REPOS),
        "plateau_bati": PlateauTangent(a2, -0.8, sol, 0.02, REPOS),
    }


def etat(graine):
    rng = np.random.default_rng(graine)
    return rng.normal(size=9), rng.normal(size=9), rng.normal(size=9), float(rng.uniform(0.0, 2.0))


def phi(c, q, t):
    sortie = np.zeros(c.n_eq)
    c.phi(q, t, sortie, 0)
    return sortie


def jac(c, q, t):
    J = np.zeros((c.n_eq, q.size))
    c.jac(q, t, J, 0)
    return J


@pytest.mark.parametrize("nom", list(contraintes()))
@pytest.mark.parametrize("graine", [1, 2, 3])
def test_jacobienne(nom, graine):
    c = contraintes()[nom]
    q, _, _, t = etat(graine)
    # éviter le saut du repliement d'angle des contraintes d'orientation fixe
    if isinstance(c, AngleRelatif) and c.loi is None:
        q = q * 0.3
    J = jac(c, q, t)
    h = 1e-6
    for j in range(q.size):
        dq = np.zeros(q.size)
        dq[j] = h
        numerique = (phi(c, q + dq, t) - phi(c, q - dq, t)) / (2 * h)
        assert J[:, j] == pytest.approx(numerique, abs=1e-8), f"colonne {j}"


@pytest.mark.parametrize("nom", list(contraintes()))
@pytest.mark.parametrize("graine", [4, 5])
def test_derivee_temporelle(nom, graine):
    c = contraintes()[nom]
    q, _, _, t = etat(graine)
    sortie = np.zeros(c.n_eq)
    c.phi_t(q, t, sortie, 0)
    h = 1e-6
    numerique = (phi(c, q, t + h) - phi(c, q, t - h)) / (2 * h)
    if isinstance(c, AngleRelatif) and c.loi is None:
        numerique = np.zeros(1)
    assert sortie == pytest.approx(numerique, abs=1e-8)


@pytest.mark.parametrize("nom", list(contraintes()))
@pytest.mark.parametrize("graine", [6, 7, 8])
def test_second_membre_acceleration(nom, graine):
    """γ doit vérifier d²Φ/dt² = Φq·q̈ − γ le long de toute trajectoire."""
    c = contraintes()[nom]
    q, qd, qdd, t = etat(graine)
    if isinstance(c, AngleRelatif) and c.loi is None:
        q, qd, qdd = q * 0.3, qd * 0.3, qdd * 0.3

    def sur_trajectoire(tau):
        return phi(c, q + qd * tau + 0.5 * qdd * tau * tau, t + tau)

    h = 1e-4
    seconde = (sur_trajectoire(h) - 2 * sur_trajectoire(0.0) + sur_trajectoire(-h)) / (h * h)
    gamma = np.zeros(c.n_eq)
    c.gamma(q, qd, t, gamma, 0)
    assert jac(c, q, t) @ qdd - gamma == pytest.approx(seconde, abs=2e-6)


@pytest.mark.parametrize("graine", [9, 10])
def test_vitesse_de_translation(graine):
    q, qd, _, _ = etat(graine)
    a, b = (0, 0.2, 0.1), (2, -0.1, 0.3)
    h = 1e-6
    numerique = (coordonnee_translation(q + h * qd, a, 0.6, b) - coordonnee_translation(q - h * qd, a, 0.6, b)) / (2 * h)
    assert vitesse_translation(q, qd, a, 0.6, b) == pytest.approx(numerique, abs=1e-8)


def test_orientation_fixe_repliee():
    c = AngleRelatif(0, 1, 0.25)
    q = np.zeros(6)
    q[5] = 0.25 + 4 * math.pi  # même orientation, à deux tours près
    assert phi(c, q, 0.0)[0] == pytest.approx(0.0, abs=1e-12)
