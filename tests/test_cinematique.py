"""Étude cinématique : comparaison aux solutions analytiques et bilans de puissance."""

import math

import numpy as np
import pytest

from sikax.calcul import ErreurCalcul, lancer_etude, regler_liaison
from sikax.calcul.enregistreur import instants
from sikax.modele import LoiMouvement, bibliotheque as B


def derivee(valeurs, temps):
    return np.gradient(valeurs, temps, edge_order=2)


def test_bielle_manivelle_formules_analytiques():
    r, l, w = 0.05, 0.15, 3.0
    m = B.bielle_manivelle(r, l, w)
    m.etude.duree, m.etude.pas = 2.0, 0.002
    res = lancer_etude(m)
    assert res.complet and not res.messages
    t = res.temps
    theta = w * t
    racine = np.sqrt(l * l - (r * np.sin(theta)) ** 2)
    x = r * np.cos(theta) + racine
    v = -r * w * np.sin(theta) - r * r * w * np.sin(theta) * np.cos(theta) / racine
    a = (
        -r * w * w * np.cos(theta)
        - r * r * w * w * (np.cos(theta) ** 2 - np.sin(theta) ** 2) / racine
        - r ** 4 * w * w * (np.sin(theta) * np.cos(theta)) ** 2 / racine ** 3
    )
    # point B du piston (premier point du solide S3)
    assert res.valeurs("point/S3/P1/x") == pytest.approx(x, abs=1e-10)
    assert res.valeurs("point/S3/P1/y") == pytest.approx(0.0, abs=1e-10)
    assert res.valeurs("point/S3/P1/vx") == pytest.approx(v, abs=1e-9)
    assert res.valeurs("point/S3/P1/ax") == pytest.approx(a, abs=1e-8)
    # coordonnées articulaires
    assert res.valeurs("liaison/L1/angle") == pytest.approx(theta, abs=1e-10)
    assert res.valeurs("liaison/L1/vitesse_angulaire") == pytest.approx(w, abs=1e-10)
    assert res.valeurs("liaison/L4/deplacement") - res.valeur("liaison/L4/deplacement", 0) == pytest.approx(x - x[0], abs=1e-10)
    assert res.valeurs("liaison/L4/vitesse") == pytest.approx(v, abs=1e-9)


@pytest.mark.parametrize("nom", ["bielle_manivelle", "quatre_barres", "coulisse_retour_rapide", "parallelogramme_double"])
def test_vitesses_et_accelerations_coherentes(nom):
    """Les vitesses et accélérations calculées sont les dérivées des positions."""
    m = B.EXEMPLES[nom]()
    m.etude.duree, m.etude.pas = 1.0, 0.0005
    res = lancer_etude(m)
    assert res.complet
    t = res.temps
    interieur = slice(3, -3)
    for cle in [c for c in res.canaux if c.startswith("point/") and c.endswith("/x")]:
        base = cle[:-1]
        for axe in "xy":
            pos, vit, acc = res.valeurs(base + axe), res.valeurs(base + "v" + axe), res.valeurs(base + "a" + axe)
            assert derivee(pos, t)[interieur] == pytest.approx(vit[interieur], rel=1e-4, abs=2e-5)
            assert derivee(vit, t)[interieur] == pytest.approx(acc[interieur], rel=1e-4, abs=2e-3)
    for sid in res.solides:
        theta, omega, alpha = (res.valeurs(f"solide/{sid}/{g}") for g in ("angle", "omega", "alpha"))
        assert derivee(theta, t)[interieur] == pytest.approx(omega[interieur], rel=1e-4, abs=2e-5)
        assert derivee(omega, t)[interieur] == pytest.approx(alpha[interieur], rel=1e-4, abs=2e-3)


def test_quatre_barres_longueurs_conservees():
    m = B.quatre_barres()
    res = lancer_etude(m)
    ax, ay = res.valeurs("point/S2/P1/x"), res.valeurs("point/S2/P1/y")
    bx, by = res.valeurs("point/S2/P2/x"), res.valeurs("point/S2/P2/y")
    assert np.hypot(bx - ax, by - ay) == pytest.approx(0.30, abs=1e-10)
    assert np.hypot(bx - 0.30, by) == pytest.approx(0.25, abs=1e-10)
    assert np.hypot(ax, ay) == pytest.approx(0.10, abs=1e-10)
    # la manivelle fait deux tours complets en 2 s
    assert res.valeur("liaison/L1/angle") - res.valeur("liaison/L1/angle", 0) == pytest.approx(4 * math.pi)


@pytest.mark.parametrize("nom", ["bielle_manivelle", "quatre_barres", "coulisse_retour_rapide", "parallelogramme_double"])
def test_bilan_de_puissance(nom):
    """PFD : la puissance du moteur est la dérivée de l'énergie mécanique (pas de dissipation)."""
    m = B.EXEMPLES[nom]()
    m.etude.duree, m.etude.pas = 1.0, 0.0005
    res = lancer_etude(m)
    puissance = res.valeurs("moteur/M1/puissance")
    energie = derivee(res.valeurs("energie/mecanique"), res.temps)
    echelle = max(np.max(np.abs(puissance)), 1e-9)
    assert (puissance - energie)[3:-3] == pytest.approx(0.0, abs=2e-4 * echelle + 1e-6)


def test_quasi_statique_travaux_virtuels():
    """Sans inertie : couple moteur = −F·dx/dθ pour un effort F sur le piston."""
    r, l, w, F = 0.05, 0.15, 2.0, 500.0
    m = B.bielle_manivelle(r, l, w)
    m.etude.pesanteur = False
    m.etude.inertie = False
    m.etude.duree, m.etude.pas = 3.0, 0.005
    m.creer_force("S3", "P1", -F, 0.0)
    res = lancer_etude(m)
    theta = w * res.temps
    racine = np.sqrt(l * l - (r * np.sin(theta)) ** 2)
    dx = -r * np.sin(theta) - r * r * np.sin(theta) * np.cos(theta) / racine
    assert res.valeurs("moteur/M1/effort") == pytest.approx(F * dx, abs=1e-8)
    assert "quasi_statique" in [msg.code for msg in res.messages]
    # la bielle est un solide soumis à deux glisseurs : effort porté par AB
    X, Y = res.valeurs("liaison/L2/X"), res.valeurs("liaison/L2/Y")
    ax, ay = res.valeurs("point/S2/P1/x"), res.valeurs("point/S2/P1/y")
    bx, by = res.valeurs("point/S2/P2/x"), res.valeurs("point/S2/P2/y")
    assert X * (by - ay) - Y * (bx - ax) == pytest.approx(0.0, abs=1e-8)
    # la glissière ne transmet aucun effort suivant son axe
    assert res.valeurs("liaison/L4/X") == pytest.approx(0.0, abs=1e-8)


def test_mobilite_non_pilotee():
    m = B.double_pendule()
    m.etude.type = "cinematique"
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "mobilite_non_pilotee"
    assert info.value.parametres["mobilite"] == 2
    m.creer_moteur("L1")
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.parametres["mobilite"] == 1
    m.creer_moteur("L2", LoiMouvement("sinusoidale", {"amplitude": 0.5, "frequence": 1.0}))
    assert lancer_etude(m).complet


def test_mouvement_impossible_s_arrete_proprement():
    """Un moteur linéaire pousse le piston au-delà de la course : arrêt signalé, pas de plantage."""
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    assert regler_liaison(m, "L1", math.radians(60.0))
    m.creer_moteur("L4", LoiMouvement("vitesse_constante", {"vitesse": 0.05}))
    m.etude.duree, m.etude.pas = 2.0, 0.01
    res = lancer_etude(m)
    assert not res.complet
    assert "mouvement_impossible" in [msg.code for msg in res.messages]
    assert 0 < res.nb_instants < 201
    assert np.all(np.isfinite(res.q))
    # le piston s'arrête au point mort haut : x = r + l
    assert res.valeur("point/S3/P1/x") < 0.2 + 1e-9


def test_depart_sur_un_point_mort():
    """Piston moteur alors que bielle et manivelle sont alignées : erreur explicite."""
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    m.creer_moteur("L4", LoiMouvement("vitesse_constante", {"vitesse": -0.05}))
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "position_initiale_singuliere"


def test_moteur_lineaire_et_lois():
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    assert regler_liaison(m, "L1", math.radians(90.0))
    m.creer_moteur("L4", LoiMouvement("sinusoidale", {"amplitude": -0.03, "frequence": 1.0}))
    m.etude.duree, m.etude.pas = 1.0, 0.002
    res = lancer_etude(m)
    assert res.complet
    x = res.valeurs("point/S3/P1/x")
    assert x - x[0] == pytest.approx(-0.03 * np.sin(2 * math.pi * res.temps), abs=1e-10)
    assert res.canal("moteur/M1/effort").dimension == "force"


def test_moteur_absolu_et_blocage():
    m = B.pendule_simple(angle=0.0)
    m.creer_moteur("L1", LoiMouvement("blocage", {"position": math.radians(40.0)}), relatif=False)
    m.etude.type = "cinematique"
    m.etude.duree, m.etude.pas = 0.1, 0.05
    res = lancer_etude(m)
    assert res.valeurs("solide/S1/angle") == pytest.approx(math.radians(40.0), abs=1e-10)
    # couple de maintien = m·g·(L/2)·cos(40°)
    assert res.valeurs("moteur/M1/effort") == pytest.approx(1.0 * 9.81 * 0.25 * math.cos(math.radians(40.0)), abs=1e-9)


def test_loi_trapeze():
    loi = LoiMouvement("trapeze", {"course": 2.0, "vitesse_max": 1.0, "acceleration": 2.0, "depart": 0.5})
    assert loi.evaluer(0.2) == (0.0, 0.0, 0.0)
    assert loi.evaluer(0.75) == pytest.approx((0.0625, 0.5, 2.0))
    assert loi.evaluer(1.5) == pytest.approx((0.75, 1.0, 0.0))
    assert loi.evaluer(10.0) == pytest.approx((2.0, 0.0, 0.0))
    assert loi.duree_caracteristique() == pytest.approx(3.0)
    # profil triangulaire quand la vitesse maximale n'est jamais atteinte
    court = LoiMouvement("trapeze", {"course": -0.5, "vitesse_max": 10.0, "acceleration": 2.0})
    p, v, a = court.evaluer(0.5)
    assert (p, v, a) == pytest.approx((-0.25, -1.0, 2.0)) or (p, v) == pytest.approx((-0.25, -1.0))
    assert court.evaluer(1.0)[0] == pytest.approx(-0.5)
    # continuité de la position et de la vitesse
    ts = np.linspace(0.0, 4.0, 4001)
    valeurs = np.array([loi.evaluer(float(t)) for t in ts])
    assert np.max(np.abs(np.diff(valeurs[:, 0]))) < 2e-3
    assert derivee(valeurs[:, 0], ts)[5:-5] == pytest.approx(valeurs[5:-5, 1], abs=3e-3)


def test_loi_expression_et_erreur():
    m = B.pendule_simple(angle=0.0)
    m.creer_moteur("L1", LoiMouvement("expression", {"expression": "0.5*sin(3*t)"}))
    m.etude.type = "cinematique"
    m.etude.duree, m.etude.pas = 1.0, 0.01
    res = lancer_etude(m)
    assert res.valeurs("solide/S1/angle") == pytest.approx(0.5 * np.sin(3 * res.temps), abs=1e-10)
    assert res.valeurs("solide/S1/alpha") == pytest.approx(-4.5 * np.sin(3 * res.temps), abs=1e-8)
    m.moteurs["M1"].loi = LoiMouvement("expression", {"expression": "sqrt(0.5 - t)"})
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "expression"


def test_instants():
    assert instants(1.0, 0.25) == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])
    assert instants(0.3, 0.1).size == 4
    assert instants(0.0, 0.1).size == 1
    assert instants(1.0, 3.0) == pytest.approx([0.0, 1.0])  # pas ramené à la durée


def test_etude_sans_solide():
    from sikax.modele import Mecanisme

    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(Mecanisme())
    assert info.value.code == "aucun_solide"


def test_le_modele_n_est_pas_modifie():
    m = B.quatre_barres()
    avant = [(s.pose.x, s.pose.y, s.pose.angle) for s in m.solides.values()]
    lancer_etude(m)
    assert avant == [(s.pose.x, s.pose.y, s.pose.angle) for s in m.solides.values()]


def test_etude_demesuree_refusee():
    m = B.bielle_manivelle()
    m.etude.duree, m.etude.pas = 1000.0, 1e-4
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "trop_d_instants" and info.value.parametres["nombre"] == 10_000_000
