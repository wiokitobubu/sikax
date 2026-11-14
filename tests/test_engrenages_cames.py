"""Engrenages et cames : rapports, formule de Willis, efforts sur la denture, rendement, levée des cames."""

import math

import numpy as np
import pytest

from sikax.calcul import analyser_topologie, lancer_etude, mobilite_par_jacobienne
from sikax.modele import LoiMouvement, Mecanisme, bibliotheque as B
from sikax.modele.liaisons import Came, Engrenage
from sikax.modele.solide import ID_BATI

MODULE = 0.002
ALPHA = math.radians(20.0)


def paire(z1=20, z2=40, rendement=1.0, interieur=False):
    """Pignon motorisé à 2π rad/s et roue (extérieure ou couronne) articulés au bâti."""
    m = Mecanisme()
    r1, r2 = MODULE * z1 / 2, MODULE * z2 / 2
    entraxe = r2 - r1 if interieur else r1 + r2
    a = m.creer_disque(0.0, 0.0, r1, nom="Pignon")
    a.inertie = a.inertie_disque_homogene(0.1)
    b = m.creer_disque(entraxe, 0.0, r2, nom="Roue")
    b.inertie = b.inertie_disque_homogene(0.4)
    p1 = m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, a.id)
    p2 = m.creer_liaison_en("pivot", entraxe, 0.0, ID_BATI, b.id)
    e = m.creer_engrenage(a.id, b.id, rendement=rendement)
    m.creer_moteur(p1.id, LoiMouvement("vitesse_constante", {"vitesse": 2 * math.pi}))
    m.etude.pesanteur = False
    m.etude.duree, m.etude.pas = 0.5, 0.01
    return m, a, b, p1, p2, e


def test_creation_deduit_nature_et_dents_des_cercles():
    m, _, _, _, _, e = paire(20, 40)
    assert (e.nature, e.z_a, e.z_b) == ("exterieur", 20.0, 40.0)
    assert e.entraxe_theorique() == pytest.approx(0.06) and e.rapport() == pytest.approx(-0.5)
    assert m.position_liaison(e) == pytest.approx((0.02, 0.0))  # point primitif
    m2, *_, e2 = paire(20, 60, interieur=True)
    assert (e2.nature, e2.z_a, e2.z_b) == ("interieur", 20.0, 60.0)
    assert e2.rapport() == pytest.approx(1.0 / 3.0)
    assert m2.position_liaison(e2) == pytest.approx((-0.02, 0.0))  # au-delà du pignon, côté couronne
    assert not m.verifier() and not m2.verifier()


def test_engrenage_exterieur_rapport_et_efforts():
    m, a, b, p1, p2, e = paire()
    couple_resistant = 3.0
    m.creer_couple(b.id, couple_resistant)  # la roue tourne en sens négatif : ce couple s'y oppose
    res = lancer_etude(m)
    assert res.complet
    assert res.valeurs(f"solide/{b.id}/omega") == pytest.approx(-math.pi)
    ft = couple_resistant / (MODULE * 40 / 2)
    assert np.abs(res.valeurs(f"liaison/{e.id}/Ft")) == pytest.approx(ft)
    assert res.valeurs(f"liaison/{e.id}/Fr") == pytest.approx(ft * math.tan(ALPHA))
    assert res.valeurs(f"liaison/{e.id}/Fn") == pytest.approx(ft / math.cos(ALPHA))
    # le pivot de la roue reprend tout l'effort de denture (tangentiel et radial)
    assert res.valeurs(f"liaison/{p2.id}/R") == pytest.approx(ft / math.cos(ALPHA))
    # le moteur fournit le couple résistant divisé par le rapport des rayons
    assert res.valeurs("moteur/M1/effort") == pytest.approx(couple_resistant * 20 / 40)
    assert np.abs(res.valeurs(f"liaison/{e.id}/couple_b")) == pytest.approx(couple_resistant)


def test_rendement_retire_la_part_de_puissance_perdue():
    m, a, b, *_ = paire(rendement=0.9)
    m.creer_couple(b.id, 3.0)
    res = lancer_etude(m)
    entree = res.valeurs("moteur/M1/puissance")
    sortie = -3.0 * res.valeurs(f"solide/{b.id}/omega")
    assert sortie / entree == pytest.approx(0.9, rel=1e-9)
    assert res.valeurs("moteur/M1/effort") == pytest.approx(3.0 * 20 / 40 / 0.9, rel=1e-9)


def test_rendement_en_dynamique_dissipe_l_energie():
    m, a, b, p1, *_ = paire(rendement=0.95)
    m.supprimer_moteur("M1")
    p1.vitesse_initiale = 20.0
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 0.3, 0.005
    m.creer_couple(b.id, 0.02)  # léger frein sur la roue (elle tourne en sens négatif)
    res = lancer_etude(m)
    assert res.complet
    wa, wb = res.valeurs(f"solide/{a.id}/omega"), res.valeurs(f"solide/{b.id}/omega")
    assert wb / wa == pytest.approx(-0.5)
    energie = res.valeurs("energie/cinetique")
    travail_du_frein = np.concatenate([[0.0], np.cumsum(0.5 * 0.02 * (wb[1:] + wb[:-1]) * np.diff(res.temps))])
    perdue = energie[0] + travail_du_frein - energie
    assert np.all(np.diff(perdue) >= -1e-9) and perdue[-1] > 0.0  # la denture ne fait que dissiper


def test_train_epicycloidal_formule_de_willis():
    m = B.train_epicycloidal()
    res = lancer_etude(m)
    ids = {s.nom: s.id for s in m.solides_mobiles()}
    w_porte = res.valeurs(f"solide/{ids['Porte-satellites']}/omega")
    assert res.valeurs(f"solide/{ids['Soleil']}/omega") == pytest.approx(w_porte * (1 + 40 / 20))
    assert res.valeurs(f"solide/{ids['Satellite']}/omega") == pytest.approx(w_porte * (1 - 40 / 10))
    bilan = analyser_topologie(m)
    assert (bilan.mobilite, bilan.hyperstatisme) == (1, 0)
    assert mobilite_par_jacobienne(m) == (1, 0)


def test_reducteur_deux_etages():
    m = B.train_engrenages()
    res = lancer_etude(m)
    ids = {s.nom: s.id for s in m.solides_mobiles()}
    pignon = ids["Pignon d'entrée"]
    entree = res.valeurs(f"solide/{pignon}/omega")
    sortie = res.valeurs(f"solide/{ids['Roue de sortie']}/omega")
    assert sortie / entree == pytest.approx(1.0 / 9.0)
    # deux étages de rendement 0,98 : C_moteur = C_sortie / 9 / 0,98²
    assert res.valeurs("moteur/M1/effort") == pytest.approx(2.0 / 9.0 / 0.98 ** 2, rel=1e-9)


def test_pignon_cremaillere():
    m = B.pignon_cremaillere()
    res = lancer_etude(m)
    pignon = next(s for s in m.solides_mobiles() if s.nom == "Pignon")
    cremaillere = next(s for s in m.solides_mobiles() if s.nom == "Crémaillère")
    r = MODULE * 20 / 2
    w = res.valeurs(f"solide/{pignon.id}/omega")
    v = res.valeurs(f"solide/{cremaillere.id}/vx")
    assert np.abs(v) == pytest.approx(r * np.abs(w), abs=1e-12)
    # PFD de la crémaillère le long de x : effort de denture − charge = m·a
    e = next(l for l in m.liaisons.values() if isinstance(l, Engrenage))
    attendu = 50.0 + cremaillere.inertie.masse * res.valeurs(f"solide/{cremaillere.id}/ax")
    assert res.valeurs(f"liaison/{e.id}/Ft") == pytest.approx(attendu, rel=1e-9, abs=1e-9)


def test_engrenage_en_statique():
    m, a, b, p1, p2, e = paire()
    m.supprimer_moteur("M1")
    m.creer_couple(a.id, 1.0)
    m.creer_couple(b.id, 2.0)  # 1 / r1 = 2 / r2 : équilibre
    m.etude.type = "statique"
    res = lancer_etude(m)
    assert res.equilibre
    assert abs(res.valeur(f"liaison/{e.id}/Ft")) == pytest.approx(50.0)
    assert res.valeur(f"liaison/{p2.id}/R") == pytest.approx(50.0 / math.cos(ALPHA))


def test_hyperstatisme_spatial_d_un_engrenage():
    m, *_, e = paire()
    assert (analyser_topologie(m, 3).hyperstatisme, e.modele_spatial) == (1, "lineaire_rectiligne_y")
    e.modele_spatial = "ponctuelle_y"  # denture bombée : contact ponctuel
    assert analyser_topologie(m, 3).hyperstatisme == 0


def test_validation_des_parametres():
    m, *_, e = paire()
    e.z_a = 20.5
    assert "valeur_hors_bornes" in [p.code for p in m.verifier()]
    e.z_a, e.rendement = 20.0, 1.2
    assert "valeur_hors_bornes" in [p.code for p in m.verifier()]
    e.rendement, e.nature = 1.0, "conique"
    assert "option_inconnue" in [p.code for p in m.verifier()]
    e.nature, e.z_b = "interieur", 10.0
    assert "couronne_trop_petite" in [p.code for p in m.verifier()]


# --------------------------------------------------------------------- cames

R, E, RHO = 0.03, 0.01, 0.006


def came(nature, ressort=True):
    m = Mecanisme()
    disque = m.creer_disque(E, 0.0, R, nom="Came")
    disque.inertie = disque.inertie_disque_homogene(0.5)
    o = m.creer_point(disque.id, 0.0, 0.0)
    pivot = m.creer_liaison("pivot", ID_BATI, m.creer_point(ID_BATI, 0.0, 0.0).id, disque.id, o.id)
    contact = R + (RHO if nature == "galet" else 0.0)
    y0 = math.sqrt(contact ** 2 - E ** 2) if nature != "plat" else R
    poussoir = m.creer_barre([(0.0, y0), (0.0, y0 + 0.08)], nom="Poussoir")
    poussoir.inertie = poussoir.inertie_barres_homogenes(0.2)
    m.creer_liaison_en("glissiere", 0.0, y0 + 0.04, ID_BATI, poussoir.id, angle_axe_global=math.pi / 2)
    if ressort:
        m.creer_ressort(ID_BATI, m.creer_point(ID_BATI, 0.0, y0 + 0.12).id, poussoir.id, "P2", 500.0, longueur_libre=0.06)
    liaison = m.creer_came(disque.id, "C1", poussoir.id, "P1", nature=nature, rayon_galet=RHO if nature == "galet" else 0.0)
    m.creer_moteur(pivot.id, LoiMouvement("vitesse_constante", {"vitesse": 2 * math.pi}))
    m.etude.duree, m.etude.pas = 2.0, 0.005
    return m, poussoir, liaison


@pytest.mark.parametrize("nature", ["pointe", "galet", "plat"])
def test_came_excentrique_deux_tours_complets(nature):
    m, poussoir, liaison = came(nature)
    res = lancer_etude(m)
    assert res.complet and res.nb_instants == 401
    theta = 2 * math.pi * res.temps
    if nature == "plat":
        attendu = E * np.sin(theta) + R
    else:
        attendu = E * np.sin(theta) + np.sqrt((R + (RHO if nature == "galet" else 0.0)) ** 2 - (E * np.cos(theta)) ** 2)
    assert res.valeurs(f"point/{poussoir.id}/P1/y") == pytest.approx(attendu, abs=1e-10)
    assert np.ptp(res.valeurs(f"point/{poussoir.id}/P1/y")) == pytest.approx(2 * E, rel=1e-6)
    normal = res.valeurs(f"liaison/{liaison.id}/Fn")
    assert np.all(normal > 0.0)  # le ressort maintient le contact
    assert "decollement" not in [x.code for x in res.messages]
    assert res.torseur_liaison(liaison.id).mz == 0.0  # l'effort passe par le point de contact


def test_came_sans_ressort_decolle():
    m, poussoir, liaison = came("galet", ressort=False)
    # à 8 tr/s, e·ω² ≈ 25 m/s² dépasse g : la pesanteur seule ne retient plus le poussoir
    m.moteurs["M1"].loi = LoiMouvement("vitesse_constante", {"vitesse": 16 * math.pi})
    res = lancer_etude(m)
    assert res.valeurs(f"liaison/{liaison.id}/Fn").min() < 0.0
    assert "decollement" in [x.code for x in res.messages]


def test_came_validation_et_suppression_du_cercle():
    m, poussoir, liaison = came("pointe")
    assert not m.verifier()
    liaison.cercle = "C9"
    assert "cercle_inconnu" in [p.code for p in m.verifier()]
    liaison.cercle = "C1"
    m.supprimer_cercle(liaison.solide_a, "C1")
    assert liaison.id not in m.liaisons  # la came disparaît avec son cercle


def test_modeles_de_depart():
    for nom, construire in B.MODELES.items():
        m = construire()
        bilan = analyser_topologie(m)
        assert bilan.mobilite == 1 and bilan.hyperstatisme == 0, nom
        assert lancer_etude(m).complet, nom
