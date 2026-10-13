"""Étude statique (PFS) : réactions d'appui, équilibre des solides, cas dégénérés."""

import math

import numpy as np
import pytest

from sikax.calcul import (
    ErreurCalcul,
    SystemeMecanique,
    analyse_statique,
    lancer_etude,
    rechercher_equilibre,
    regler_liaison,
)
from sikax.modele import LoiMouvement, Mecanisme, bibliotheque as B
from sikax.modele.solide import ID_BATI
from sikax.physique import Torseur


def test_poutre_sur_deux_appuis():
    portee, a, F = 1.0, 0.4, 1000.0
    res = lancer_etude(B.poutre_sur_deux_appuis(portee, a, F))
    assert res.equilibre is True
    assert res.hyperstatisme == 0 and res.mobilite_libre == 0
    # A (articulation) : Ya = F·(L−a)/L ; B (appui simple) : Yb = F·a/L
    assert res.valeur("liaison/L1/X") == pytest.approx(0.0, abs=1e-9)
    assert res.valeur("liaison/L1/Y") == pytest.approx(F * (portee - a) / portee)
    assert res.valeur("liaison/L2/Y") == pytest.approx(F * a / portee)
    assert res.valeur("liaison/L2/Fn") == pytest.approx(F * a / portee)
    assert res.valeur("liaison/L1/N") == pytest.approx(0.0, abs=1e-9)
    torseur = res.torseur_liaison("L1")
    assert isinstance(torseur, Torseur) and torseur.ry == pytest.approx(600.0)
    assert not res.messages


def test_poutre_encastree():
    """Console : effort tranchant et moment d'encastrement."""
    m = Mecanisme()
    s = m.creer_barre([(0.0, 0.0), (0.8, 0.0)])
    m.creer_liaison_en("encastrement", 0.0, 0.0, ID_BATI, s.id)
    m.creer_force(s.id, "P2", 30.0, -200.0)
    m.creer_couple(s.id, 15.0)
    m.etude.type, m.etude.pesanteur = "statique", False
    res = lancer_etude(m)
    assert res.equilibre
    assert res.valeur("liaison/L1/X") == pytest.approx(-30.0)
    assert res.valeur("liaison/L1/Y") == pytest.approx(200.0)
    assert res.valeur("liaison/L1/N") == pytest.approx(0.8 * 200.0 - 15.0)


def test_poids_propre_et_centre_de_gravite():
    m = Mecanisme()
    s = m.creer_barre([(0.0, 0.0), (1.0, 0.0)])
    s.inertie = s.inertie_barres_homogenes(4.0)
    m.creer_liaison_en("encastrement", 0.0, 0.0, ID_BATI, s.id)
    m.etude.type = "statique"
    res = lancer_etude(m)
    assert res.valeur("liaison/L1/Y") == pytest.approx(4.0 * 9.81)
    assert res.valeur("liaison/L1/N") == pytest.approx(4.0 * 9.81 * 0.5)
    m.etude.pesanteur = False
    assert lancer_etude(m).valeur("liaison/L1/Y") == pytest.approx(0.0, abs=1e-12)


def _equilibre_des_solides(mecanisme, res):
    """Somme des torseurs appliqués à chaque solide mobile, réduits à l'origine."""
    systeme = SystemeMecanique(mecanisme)
    gx, gy = systeme.gravite
    for solide in mecanisme.solides_mobiles():
        total = Torseur()
        for liaison in mecanisme.liaisons.values():
            torseur = res.torseur_liaison(liaison.id)
            if liaison.solide_b == solide.id:
                total = total + torseur
            elif liaison.solide_a == solide.id:
                total = total - torseur
        for moteur in mecanisme.moteurs.values():
            liaison = mecanisme.liaisons[moteur.liaison]
            effort = res.valeur(f"moteur/{moteur.id}/effort")
            if liaison.PILOTAGE == "rotation":
                action = Torseur.couple((0.0, 0.0, effort))
            else:
                beta = mecanisme.angle_axe_global(liaison)
                action = Torseur.glisseur((effort * math.cos(beta), effort * math.sin(beta)), mecanisme.position_liaison(liaison))
            if liaison.solide_b == solide.id:
                total = total + action
            elif liaison.solide_a == solide.id:
                total = total - action
        for action in mecanisme.actions.values():
            if action.type == "force" and action.solide == solide.id:
                total = total + Torseur.glisseur((float(action.fx), float(action.fy)), mecanisme.point_global(solide.id, action.point))
            elif action.type == "couple" and action.solide == solide.id:
                total = total + Torseur.couple((0.0, 0.0, float(action.mz)))
        poids = solide.inertie.masse
        total = total + Torseur.glisseur((poids * gx, poids * gy), solide.centre_gravite_global())
        yield solide, total.deplacer((0.0, 0.0, 0.0))


@pytest.mark.parametrize("nom", ["bielle_manivelle", "quatre_barres", "coulisse_retour_rapide", "poutre_deux_appuis", "poutre_bi_articulee", "parallelogramme_double"])
def test_chaque_solide_est_en_equilibre(nom):
    """Les torseurs calculés vérifient le PFS solide par solide (vérification indépendante)."""
    m = B.EXEMPLES[nom]()
    m.etude.type = "statique"
    if nom == "bielle_manivelle":
        assert regler_liaison(m, "L1", math.radians(50.0))
        m.creer_force("S3", "P1", -800.0, 0.0)
        m.creer_couple("S2", 3.0)
    res = lancer_etude(m)
    assert res.equilibre
    for solide, total in _equilibre_des_solides(m, res):
        assert total.norme_resultante == pytest.approx(0.0, abs=1e-7), solide.nom
        assert total.mz == pytest.approx(0.0, abs=1e-7), solide.nom


def test_hyperstatique_solution_de_norme_minimale():
    res = lancer_etude(B.poutre_bi_articulee(1.0, 1000.0))
    assert res.equilibre and res.hyperstatisme == 1
    assert "hyperstatique_norme_minimale" in [msg.code for msg in res.messages]
    # les composantes verticales sont déterminées ; la poussée horizontale ne l'est pas
    assert res.valeur("liaison/L1/Y") == pytest.approx(500.0)
    assert res.valeur("liaison/L2/Y") == pytest.approx(500.0)
    assert res.valeur("liaison/L1/X") + res.valeur("liaison/L2/X") == pytest.approx(0.0, abs=1e-9)


def test_mecanisme_non_bloque_pas_en_equilibre():
    m = B.pendule_simple(angle=0.0)  # barre horizontale, libre de tomber
    m.etude.type = "statique"
    res = lancer_etude(m)
    assert res.equilibre is False and res.mobilite_libre == 1
    assert "pas_en_equilibre" in [msg.code for msg in res.messages]


def test_equilibre_malgre_une_mobilite():
    m = B.pendule_simple(angle=-math.pi / 2)  # barre verticale vers le bas
    m.etude.type = "statique"
    res = lancer_etude(m)
    assert res.equilibre is True and res.mobilite_libre == 1
    assert "equilibre_avec_mobilite" in [msg.code for msg in res.messages]
    assert res.valeur("liaison/L1/Y") == pytest.approx(9.81)


def test_recherche_equilibre_pendule():
    m = B.pendule_simple(angle=math.radians(20.0))
    systeme = SystemeMecanique(m)
    q, trouve = rechercher_equilibre(systeme)
    assert trouve
    # barre verticale vers le bas : G à l'aplomb de l'articulation
    assert q[0] == pytest.approx(0.0, abs=1e-6) and q[1] == pytest.approx(-0.25, abs=1e-9)
    assert analyse_statique(systeme, q_depart=q).equilibre


def test_recherche_equilibre_ressort_sous_charge():
    m = B.masse_ressort(masse=2.0, raideur=200.0, ecart=0.05)
    m.creer_force("S1", "P1", 30.0, 0.0)
    systeme = SystemeMecanique(m)
    q, trouve = rechercher_equilibre(systeme)
    assert trouve
    systeme.appliquer_au_modele(q)
    # allongement d'équilibre = F / k
    assert m.point_global("S1", "P1")[0] == pytest.approx(0.2 + 30.0 / 200.0, abs=1e-6)


def test_recherche_equilibre_quatre_barres_pesant():
    m = B.quatre_barres()
    m.supprimer_moteur("M1")
    systeme = SystemeMecanique(m)
    q, trouve = rechercher_equilibre(systeme)
    assert trouve
    res = analyse_statique(systeme, q_depart=q)
    assert res.equilibre
    # équilibre stable : l'énergie potentielle n'y dépasse pas celle du départ
    assert systeme.energies(q, np.zeros(systeme.n))[1] <= systeme.energies(systeme.q0, np.zeros(systeme.n))[1]


def test_force_suiveuse_et_force_fonction_du_temps():
    m = Mecanisme()
    s = m.creer_barre([(0.0, 0.0), (0.5, 0.0)])
    pivot = m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, s.id)
    m.creer_moteur(pivot.id, LoiMouvement("vitesse_constante", {"vitesse": 1.0}))
    m.creer_force(s.id, "P2", 0.0, "10*t", repere="local", nom="Suiveuse")
    m.etude.type, m.etude.pesanteur, m.etude.inertie = "cinematique", False, False
    m.etude.duree, m.etude.pas = 2.0, 0.1
    res = lancer_etude(m)
    t = res.temps
    # force toujours perpendiculaire à la barre : couple résistant = 0,5 × 10·t
    assert res.valeurs("moteur/M1/effort") == pytest.approx(-0.5 * 10.0 * t, abs=1e-9)
    assert res.valeurs("action/A1/f") == pytest.approx(10.0 * t)
    assert res.valeurs("action/A1/fx") == pytest.approx(-10.0 * t * np.sin(t), abs=1e-9)


def test_force_sur_le_bati_sans_effet():
    m = B.poutre_sur_deux_appuis()
    reference = lancer_etude(m).valeur("liaison/L1/Y")
    m.creer_force(ID_BATI, "P1", 1e6, 1e6)
    assert lancer_etude(m).valeur("liaison/L1/Y") == pytest.approx(reference)
    assert "action_sur_bati" in [p.code for p in m.verifier()]


def test_action_inactive_ignoree():
    m = B.poutre_sur_deux_appuis()
    m.actions["A1"].actif = False
    res = lancer_etude(m)
    assert res.valeur("liaison/L1/Y") == pytest.approx(0.0, abs=1e-12)


def test_assemblage_impossible():
    """Deux articulations au bâti trop éloignées pour une barre : erreur explicite."""
    m = Mecanisme()
    s = m.creer_barre([(0.0, 0.0), (0.1, 0.0)])
    m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, s.id)
    loin = m.creer_point(ID_BATI, 0.5, 0.0)
    m.creer_liaison("pivot", ID_BATI, loin.id, s.id, "P2")
    m.etude.type = "statique"
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "assemblage_impossible"


def test_modele_invalide_refuse():
    m = B.poutre_sur_deux_appuis()
    m.actions["A1"].fy = "1/("
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "modele_invalide"
    assert info.value.parametres["probleme"] == "expression_invalide"
