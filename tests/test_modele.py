"""Modèle : construction, suppressions en cascade, cohérence."""

import math

import numpy as np
import pytest

from sikax.calcul import lancer_etude
from sikax.modele import Glissiere, Mecanisme, Pivot, Ponctuelle, bibliotheque as B
from sikax.modele.solide import ID_BATI


def test_mecanisme_vide_a_un_bati():
    m = Mecanisme()
    assert list(m.solides) == [ID_BATI] and m.bati.bati and m.est_vide()
    assert m.verifier() == []
    assert m.boite_englobante() is None and m.longueur_caracteristique() == 1.0


def test_noms_des_points_partages_aux_articulations():
    m = B.bielle_manivelle()
    assert [p.nom for p in m.solides["S1"].points.values()] == ["A", "B"]
    assert [p.nom for p in m.solides["S2"].points.values()] == ["B", "C"]  # B commun avec la manivelle
    assert [p.nom for p in m.bati.points.values()] == ["A", "C"]
    assert [l.nom for l in m.liaisons.values()] == ["Pivot A", "Pivot B", "Pivot C", "Glissière C"]
    m2 = Mecanisme()
    for i in range(30):
        m2.creer_point(ID_BATI, float(i), 0.0)
    noms = [p.nom for p in m2.bati.points.values()]
    assert noms[:3] == ["A", "B", "C"] and noms[26] == "A1" and len(set(noms)) == 30


def test_suppressions_en_cascade():
    m = B.bielle_manivelle()
    m.creer_force("S2", "P1", 1.0, 0.0)
    m.creer_ressort(ID_BATI, "P1", "S2", "P2", 10.0)
    m.supprimer_solide("S2")  # la bielle : deux pivots, une force et un ressort disparaissent
    assert sorted(m.solides) == ["S0", "S1", "S3"]
    assert sorted(m.liaisons) == ["L1", "L4"] and not m.actions and list(m.moteurs) == ["M1"]
    assert m.verifier() == []
    m.supprimer_liaison("L1")  # son moteur part avec elle
    assert not m.moteurs
    m.supprimer_point("S3", "P1")
    assert "L4" not in m.liaisons and m.solides["S3"].segments == []
    m.supprimer_solide(ID_BATI)  # le bâti n'est jamais supprimé, seulement vidé
    assert ID_BATI in m.solides and not m.bati.points
    assert m.verifier() == []


def test_identifiants_uniques_apres_suppression():
    m = Mecanisme()
    a, b, c = (m.creer_barre([(i, 0.0), (i + 0.5, 0.0)]) for i in range(3))
    m.supprimer_solide(b.id)
    d = m.creer_barre([(5.0, 0.0), (6.0, 0.0)])
    assert len({a.id, c.id, d.id}) == 3


def test_refus_des_constructions_invalides():
    m = B.pendule_simple()
    with pytest.raises(ValueError):
        m.creer_liaison("pivot", "S1", "P1", "S1", "P2")
    with pytest.raises(KeyError):
        m.creer_liaison("pivot", "S0", "P1", "S9", "P1")
    with pytest.raises(KeyError):
        m.creer_liaison("vis", "S0", "P1", "S1", "P1")
    with pytest.raises(KeyError):
        m.creer_force("S1", "P9", 1.0, 0.0)
    moteur = m.creer_moteur("L1")
    with pytest.raises(ValueError):
        m.creer_moteur("L1")  # déjà motorisée
    m.supprimer_moteur(moteur.id)
    m.changer_type_liaison("L1", "ponctuelle")
    with pytest.raises(ValueError):
        m.creer_moteur("L1")  # une ponctuelle ne se motorise pas
    with pytest.raises(ValueError):
        m.creer_barre([(0.0, 0.0)])


def test_verifier_signale_chaque_incoherence():
    m = B.bielle_manivelle()
    m.liaisons["L2"].solide_a = "S9"
    m.liaisons["L3"].point_b = "P9"
    m.solides["S1"].inertie.masse = -1.0
    m.solides["S2"].segments.append(("P1", "P7"))
    m.solides["S3"].pose.x = float("inf")
    m.moteurs["M1"].loi.parametres["vitesse"] = float("nan")
    m.creer_force("S1", "P1", "2*(", 0.0)
    m.etude.pas = 0.0
    m.liaisons["L4"].amortissement = -3.0
    m.liaisons["L1"].modele_spatial = "appui_plan_y"
    codes = sorted(p.code for p in m.verifier())
    assert codes == sorted([
        "solide_inconnu", "point_inconnu", "inertie_negative", "segment_invalide", "valeur_non_finie",
        "loi_invalide", "expression_invalide", "etude_invalide", "valeur_hors_bornes", "modele_spatial_incompatible",
    ])
    assert len(m.erreurs()) == len(codes) - 1  # le modèle spatial n'est qu'un avertissement


def test_inertie_des_barres_homogenes():
    m = Mecanisme()
    barre = m.creer_barre([(0.0, 0.0), (2.0, 0.0)])
    inertie = barre.inertie_barres_homogenes(3.0)
    assert (inertie.masse, inertie.gx, inertie.gy) == (3.0, 1.0, 0.0)
    assert inertie.jz == pytest.approx(3.0 * 2.0 ** 2 / 12.0)
    # équerre : deux barres de 1 m à angle droit, masse 2 kg
    equerre = m.creer_barre([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    inertie = equerre.inertie_barres_homogenes(2.0)
    assert (inertie.gx, inertie.gy) == pytest.approx((0.75, 0.25))
    assert inertie.jz == pytest.approx(2 * (1.0 / 12.0 + 0.125))  # Huygens sur chaque barre
    point_seul = m.creer_solide()
    m.creer_point(point_seul.id, 4.0, 5.0)
    assert point_seul.inertie_barres_homogenes(1.0).jz == 0.0


def test_changer_le_type_d_une_liaison():
    m = B.bielle_manivelle()
    nouvelle = m.changer_type_liaison("L4", "ponctuelle")
    assert isinstance(nouvelle, Ponctuelle) and nouvelle.nom == "Ponctuelle C" and nouvelle.angle_axe == 0.0
    assert (nouvelle.solide_a, nouvelle.point_a, nouvelle.solide_b, nouvelle.point_b) == ("S0", "P2", "S3", "P1")
    assert m.verifier() == []
    # le moteur d'une pivot disparaît si elle devient glissière (pilotage différent)
    devenue = m.changer_type_liaison("L1", "glissiere")
    assert isinstance(devenue, Glissiere) and not m.moteurs
    assert m.changer_type_liaison("L1", "glissiere") is devenue
    m.liaisons["L2"].nom = "Maneton"
    assert m.changer_type_liaison("L2", "encastrement").nom == "Maneton"  # un nom personnalisé est conservé


def test_inverser_une_liaison_ne_change_pas_le_mouvement():
    reference = lancer_etude(B.coulisse_a_retour_rapide())
    m = B.coulisse_a_retour_rapide()
    glissiere = next(l for l in m.liaisons.values() if isinstance(l, Glissiere))
    direction = m.angle_axe_global(glissiere)
    m.inverser_liaison(glissiere.id)
    assert m.angle_axe_global(glissiere) == pytest.approx(direction)
    for liaison in list(m.liaisons.values()):
        if isinstance(liaison, Pivot) and m.moteur_de_liaison(liaison.id) is None:
            m.inverser_liaison(liaison.id)
    assert m.verifier() == []
    inverse = lancer_etude(m)
    for cle in ("solide/S3/angle", "point/S2/P1/x", "moteur/M1/effort"):
        assert inverse.valeurs(cle) == pytest.approx(reference.valeurs(cle), abs=1e-8)
    # l'action de A sur B change de signe quand A et B sont échangés
    assert inverse.valeurs(f"liaison/{glissiere.id}/X") == pytest.approx(-reference.valeurs(f"liaison/{glissiere.id}/X"), abs=1e-7)


def test_copie_independante():
    m = B.quatre_barres()
    copie = m.copie()
    assert copie == m
    copie.solides["S1"].points["P2"].x += 1.0
    copie.liaisons["L1"].nom = "autre"
    copie.moteurs["M1"].loi.parametres["vitesse"] = 0.0
    assert copie != m and m.solides["S1"].points["P2"].x != copie.solides["S1"].points["P2"].x
    assert m.liaisons["L1"].nom == "Pivot A" and m.moteurs["M1"].loi.parametres["vitesse"] != 0.0


def test_liaison_creee_a_une_position_reutilise_les_points():
    m = Mecanisme()
    a = m.creer_barre([(0.0, 0.0), (1.0, 0.0)])
    b = m.creer_barre([(1.0, 0.0), (2.0, 1.0)])
    avant = (len(a.points), len(b.points))
    pivot = m.creer_liaison_en("pivot", 1.0, 0.0, a.id, b.id)
    assert (len(a.points), len(b.points)) == avant
    assert (pivot.point_a, pivot.point_b) == ("P2", "P1")
    glissiere = m.creer_liaison_en("glissiere", 1.5, 0.5, ID_BATI, b.id, angle_axe_global=math.pi / 4)
    assert len(b.points) == 3 and len(m.bati.points) == 1  # points créés des deux côtés
    assert glissiere.angle_axe == pytest.approx(math.pi / 4) and glissiere.angle_relatif == 0.0
    assert np.allclose(m.position_liaison(glissiere), (1.5, 0.5))
