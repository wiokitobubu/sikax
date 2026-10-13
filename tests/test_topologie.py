"""Mobilité et hyperstatisme : cas d'école et contre-vérification par la jacobienne."""

import math

import pytest

from sikax.calcul import analyser_topologie, mobilite_par_jacobienne
from sikax.calcul.topologie import boucles_independantes
from sikax.modele import Mecanisme, bibliotheque as B
from sikax.modele.catalogue_spatial import CATALOGUE
from sikax.modele.liaisons import REGISTRE_LIAISONS
from sikax.modele.solide import ID_BATI

# (exemple, m plan, h plan, m espace, h espace)
CAS = [
    ("bielle_manivelle", 1, 0, 1, 3),
    ("quatre_barres", 1, 0, 1, 3),
    ("coulisse_retour_rapide", 1, 0, 1, 3),
    ("pendule_simple", 1, 0, 1, 0),
    ("double_pendule", 2, 0, 2, 0),
    ("masse_ressort", 1, 0, 1, 0),
    ("poutre_deux_appuis", 0, 0, 0, 0),
    ("poutre_bi_articulee", 0, 1, 0, 4),
    ("parallelogramme_double", 1, 1, 1, 7),
]


@pytest.mark.parametrize("nom,m2,h2,m3,h3", CAS)
def test_cas_d_ecole(nom, m2, h2, m3, h3):
    mecanisme = B.EXEMPLES[nom]()
    plan = analyser_topologie(mecanisme, 2)
    espace = analyser_topologie(mecanisme, 3)
    assert (plan.mobilite, plan.hyperstatisme) == (m2, h2)
    assert (espace.mobilite, espace.hyperstatisme) == (m3, h3)
    assert plan.coherent and espace.coherent
    assert plan.isostatique == (h2 == 0)


@pytest.mark.parametrize("nom", list(B.EXEMPLES))
def test_accord_avec_la_jacobienne(nom):
    mecanisme = B.EXEMPLES[nom]()
    plan = analyser_topologie(mecanisme, 2)
    assert (plan.mobilite, plan.hyperstatisme) == mobilite_par_jacobienne(mecanisme)


def test_formules_du_bilan():
    bilan = analyser_topologie(B.bielle_manivelle(), 2)
    assert bilan.nb_solides == 4 and bilan.nb_liaisons == 4 and bilan.nb_boucles == 1
    assert bilan.ic == 4 and bilan.is_ == 8 and bilan.ec == 3 and bilan.es == 9
    assert bilan.rang == 3
    assert bilan.nb_moteurs == 1 and bilan.mobilite_pilotee == 1 and bilan.mobilite_libre == 0
    espace = analyser_topologie(B.bielle_manivelle(), 3)
    assert espace.ic == 4 and espace.is_ == 20 and espace.ec == 6 and espace.es == 18


def test_bielle_manivelle_rendue_isostatique_dans_l_espace():
    """Solution classique : pivot, pivot glissant, rotule, pivot glissant → h = 0."""
    m = B.bielle_manivelle()
    l1, l2, l3, l4 = m.liaisons.values()
    l2.modele_spatial = "pivot_glissant_z"
    l3.modele_spatial = "rotule"
    l4.modele_spatial = "pivot_glissant_x"
    bilan = analyser_topologie(m, 3)
    assert bilan.hyperstatisme == 0
    assert bilan.mobilite == 2  # la mobilité utile et la rotation propre du piston
    # le mouvement plan, lui, est inchangé
    assert analyser_topologie(m, 2).mobilite == 1


def test_modeles_spatiaux_compatibles_avec_le_plan():
    for classe in REGISTRE_LIAISONS.values():
        assert classe.MODELES_SPATIAUX, classe.TYPE
        for cle in classe.MODELES_SPATIAUX:
            assert CATALOGUE[cle].mobilites_planes() == classe.MOBILITES, (classe.TYPE, cle)
    for modele in CATALOGUE.values():
        assert modele.ddl + modele.inconnues_statiques == 6


def test_structure_triangulee_et_surabondante():
    # Triangle articulé posé sur deux articulations au bâti : m = 0, h = 0... puis une barre de trop.
    m = Mecanisme()
    a, b, c = (0.0, 0.0), (0.4, 0.0), (0.2, 0.3)
    ac = m.creer_barre([a, c])
    bc = m.creer_barre([b, c])
    m.creer_liaison_en("pivot", *a, ID_BATI, ac.id)
    m.creer_liaison_en("pivot", *b, ID_BATI, bc.id)
    m.creer_liaison_en("pivot", *c, ac.id, bc.id)
    bilan = analyser_topologie(m, 2)
    assert (bilan.mobilite, bilan.hyperstatisme) == (0, 0)
    d = (0.2, 0.0)
    dc = m.creer_barre([d, c])
    m.creer_liaison_en("pivot", *d, ID_BATI, dc.id)
    m.creer_liaison_en("pivot", *c, ac.id, dc.id)
    bilan = analyser_topologie(m, 2)
    assert (bilan.mobilite, bilan.hyperstatisme) == (0, 1)
    assert bilan.liaisons_hyperstatiques()
    assert (bilan.mobilite, bilan.hyperstatisme) == mobilite_par_jacobienne(m)


def test_encastrement_et_double_liaison():
    m = Mecanisme()
    s = m.creer_barre([(0.0, 0.0), (0.3, 0.0)])
    m.creer_liaison_en("encastrement", 0.0, 0.0, ID_BATI, s.id)
    assert (analyser_topologie(m, 2).mobilite, analyser_topologie(m, 2).hyperstatisme) == (0, 0)
    assert analyser_topologie(m, 3).hyperstatisme == 0
    # un second encastrement entre les deux mêmes solides : boucle à deux liaisons
    m.creer_liaison_en("encastrement", 0.3, 0.0, ID_BATI, s.id)
    bilan = analyser_topologie(m, 2)
    assert bilan.nb_boucles == 1 and (bilan.mobilite, bilan.hyperstatisme) == (0, 3)
    assert analyser_topologie(m, 3).hyperstatisme == 6


def test_solides_isoles_et_flottants():
    m = B.pendule_simple()
    m.creer_barre([(1.0, 1.0), (1.2, 1.0)], nom="Isolé")
    a = m.creer_barre([(2.0, 0.0), (2.2, 0.0)], nom="Flottant 1")
    b = m.creer_barre([(2.2, 0.0), (2.4, 0.1)], nom="Flottant 2")
    m.creer_liaison_en("pivot", 2.2, 0.0, a.id, b.id)
    bilan = analyser_topologie(m, 2)
    assert bilan.solides_isoles == ["S2"]
    assert sorted(bilan.solides_flottants) == [a.id, b.id]
    assert bilan.nb_composantes == 3
    codes = [code for code, _ in bilan.avertissements]
    assert "solides_isoles" in codes and "solides_flottants" in codes
    # pendule (1) + solide isolé (3) + chaîne flottante (3 + 1)
    assert bilan.mobilite == 8
    assert (bilan.mobilite, bilan.hyperstatisme) == mobilite_par_jacobienne(m)


def test_singularite_points_alignes():
    """Quatre barres aplati : les trois articulations mobiles alignées, rang en défaut."""
    m = Mecanisme()
    s1 = m.creer_barre([(0.0, 0.0), (0.1, 0.0)])
    s2 = m.creer_barre([(0.1, 0.0), (0.3, 0.0)])
    s3 = m.creer_barre([(0.3, 0.0), (0.5, 0.0)])
    m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, s1.id)
    m.creer_liaison_en("pivot", 0.1, 0.0, s1.id, s2.id)
    m.creer_liaison_en("pivot", 0.3, 0.0, s2.id, s3.id)
    m.creer_liaison_en("pivot", 0.5, 0.0, ID_BATI, s3.id)
    bilan = analyser_topologie(m, 2)
    assert (bilan.mobilite, bilan.hyperstatisme) == (2, 1)  # configuration singulière
    assert (bilan.mobilite, bilan.hyperstatisme) == mobilite_par_jacobienne(m)


def test_boucles_fermees_et_signees():
    m = B.parallelogramme_double()
    boucles = boucles_independantes(m)
    assert len(boucles) == 2
    for boucle in boucles:
        # en suivant la boucle, on revient au solide de départ
        courant = boucle.solides[0]
        for lid, sens in boucle.liaisons:
            liaison = m.liaisons[lid]
            depart, arrivee = (liaison.solide_a, liaison.solide_b) if sens > 0 else (liaison.solide_b, liaison.solide_a)
            assert depart == courant
            courant = arrivee
        assert courant == boucle.solides[0]


def test_moteurs_surabondants():
    m = B.quatre_barres()
    liaisons = list(m.liaisons.values())
    m.creer_moteur(liaisons[3].id)  # second moteur sur un mécanisme à une mobilité
    bilan = analyser_topologie(m, 2)
    assert bilan.nb_moteurs == 2 and bilan.mobilite_pilotee == 1 and bilan.moteurs_surabondants == 1
    assert "moteurs_surabondants" in [code for code, _ in bilan.avertissements]


def test_mecanisme_vide():
    bilan = analyser_topologie(Mecanisme(), 2)
    assert (bilan.mobilite, bilan.hyperstatisme, bilan.nb_boucles) == (0, 0, 0)
    assert "aucun_solide" in [code for code, _ in bilan.avertissements]
    assert math.isfinite(bilan.rang)
