"""Algèbre des torseurs."""

import math

import pytest

from sikax.physique import Torseur, Unites


def test_transport_du_moment():
    t = Torseur.glisseur((0.0, 10.0), (2.0, 0.0))
    en_o = t.deplacer((0.0, 0.0))
    assert en_o.mz == pytest.approx(20.0)  # OA ∧ F = 2 × 10
    assert en_o.deplacer((2.0, 0.0)).mz == pytest.approx(0.0)
    assert en_o.resultante == t.resultante


def test_somme_et_opposition():
    a = Torseur.plan(3.0, -1.0, 2.0, (1.0, 1.0))
    b = Torseur.plan(-3.0, 1.0, 0.5, (4.0, -2.0))
    somme = a + b
    assert somme.norme_resultante == pytest.approx(0.0)
    assert (a - a).est_nul()
    assert (2 * a).rx == pytest.approx(6.0)
    # la somme ne dépend pas du point de réduction choisi
    assert (b + a).deplacer(somme.point).proche_de(somme)


def test_couple_invariant():
    c = Torseur.couple((0.0, 0.0, 5.0))
    assert c.deplacer((7.0, -3.0, 1.0)).moment == (0.0, 0.0, 5.0)


def test_comoment_est_une_puissance():
    statique = Torseur.plan(0.0, 100.0, 0.0, (1.0, 0.0))  # force verticale en A(1, 0)
    cinematique = Torseur((0.0, 0.0, 2.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))  # rotation 2 rad/s autour de O
    # V(A) = ω ∧ OA = (0, 2) ; P = F·V = 200 W
    assert statique.comoment(cinematique) == pytest.approx(200.0)


def test_axe_central_et_automoment():
    t = Torseur((0.0, 0.0, 4.0), (8.0, 0.0, 3.0), (0.0, 0.0, 0.0))
    assert t.automoment == pytest.approx(12.0)
    assert t.deplacer((5.0, 6.0, 7.0)).automoment == pytest.approx(12.0)
    p = t.point_axe_central()
    reduit = t.deplacer(p)
    # sur l'axe central, le moment est colinéaire à la résultante
    assert reduit.moment[0] == pytest.approx(0.0) and reduit.moment[1] == pytest.approx(0.0)
    assert Torseur.couple((0, 0, 1)).point_axe_central() is None


def test_unites():
    u = Unites("mm", "deg")
    assert u.vers_affichage(0.05, "longueur") == pytest.approx(50.0)
    assert u.depuis_affichage(90.0, "angle") == pytest.approx(math.pi / 2)
    assert u.symbole("vitesse") == "mm/s"
    assert u.vers_affichage(2000.0, "raideur") == pytest.approx(2.0)  # N/m -> N/mm
    assert u.symbole("moment") == "N·m"
    for dimension in ("longueur", "angle", "raideur", "vitesse", "force"):
        assert u.depuis_affichage(u.vers_affichage(1.234, dimension), dimension) == pytest.approx(1.234)
    assert Unites("pouce", "grade").longueur == "mm"
