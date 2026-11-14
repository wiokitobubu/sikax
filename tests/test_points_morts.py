"""Points morts en cinématique et robustesse de l'intégrateur en dynamique (solve_ivp)."""

import math
import threading

import numpy as np
import pytest

from sikax.calcul import CalculInterrompu, ErreurCalcul, coordonnee_liaison, lancer_etude, regler_liaison
from sikax.modele import LoiMouvement, Mecanisme, bibliotheque as B
from sikax.modele.etude import METHODES
from sikax.modele.solide import ID_BATI

G = 9.81


def piston_pilote(duree=2.0, pas=0.005):
    """Bielle-manivelle au point mort haut, piston piloté sur toute sa course (vitesse nulle aux extrémités)."""
    m = B.bielle_manivelle(angle_initial=0.0)
    m.supprimer_moteur("M1")
    m.creer_moteur("L4", LoiMouvement("expression", {"expression": "0.05*(cos(2*pi*t)-1)"}))
    m.etude.duree, m.etude.pas = duree, pas
    return m


def test_piston_pilote_franchit_les_points_morts():
    """Comme une machine à vapeur : la manivelle continue de tourner au passage des points morts."""
    res = lancer_etude(piston_pilote())
    assert res.complet and res.nb_instants == 401
    angle = np.degrees(res.valeurs("solide/S1/angle"))
    assert angle[-1] - angle[0] == pytest.approx(720.0, abs=1e-3)  # deux tours, sans rebrousser chemin
    assert np.all(np.abs(np.diff(angle)) < 10.0)  # aucun saut d'un tour
    codes = [x.code for x in res.messages]
    assert "depart_point_mort" in codes and "points_morts_franchis" in codes
    # efforts bornés (et non 10¹⁴ N) au voisinage des points morts
    assert np.max(np.abs(res.valeurs("moteur/M1/effort"))) < 500.0
    assert np.all(np.isfinite(res.valeurs("liaison/L1/R")))
    assert res.zones_singulieres  # signalées aux courbes


def test_position_exacte_au_point_mort():
    """La manivelle suit exactement la loi géométrique, y compris aux points morts."""
    res = lancer_etude(piston_pilote(1.0, 0.01))
    r, l = 0.05, 0.15
    theta = res.valeurs("solide/S1/angle")
    x_piston = r * np.cos(theta) + np.sqrt(l * l - (r * np.sin(theta)) ** 2)
    attendu = 0.2 + 0.05 * (np.cos(2 * np.pi * res.temps) - 1.0)
    assert x_piston == pytest.approx(attendu, abs=1e-9)


def _limite_du_balancier(m):
    """Angle limite (le plus grand) du balancier d'un quadrilatère, par bissection fine."""
    liaisons = list(m.liaisons.values())
    valeurs = []
    for a in np.linspace(-math.pi, math.pi, 1441):
        essai = m.copie()
        if regler_liaison(essai, liaisons[0].id, float(a)):
            valeurs.append((coordonnee_liaison(essai, liaisons[3].id), float(a)))
    _, meilleur = max(valeurs)
    bas, haut = meilleur - 0.01, meilleur + 0.01
    for _ in range(60):
        gauche, droite = bas + (haut - bas) / 3.0, haut - (haut - bas) / 3.0
        essais = []
        for a in (gauche, droite):
            essai = m.copie()
            regler_liaison(essai, liaisons[0].id, a)
            essais.append(coordonnee_liaison(essai, liaisons[3].id))
        if essais[0] < essais[1]:
            bas = gauche
        else:
            haut = droite
    essai = m.copie()
    regler_liaison(essai, liaisons[0].id, (bas + haut) / 2.0)
    return coordonnee_liaison(essai, liaisons[3].id)


def test_quadrilatere_pilote_par_le_balancier_sans_effort_demesure():
    """Balancier conduit jusqu'à sa position limite et retour : la manivelle continue sa rotation."""
    m = B.quatre_barres()
    liaisons = list(m.liaisons.values())
    limite = _limite_du_balancier(m)
    depart = coordonnee_liaison(m, liaisons[3].id)
    m.supprimer_moteur("M1")
    m.creer_moteur(liaisons[3].id, LoiMouvement("expression", {"expression": f"{limite - depart}*sin(pi*t)**2"}))
    m.etude.duree, m.etude.pas = 1.0, 0.005
    res = lancer_etude(m)
    assert res.complet
    angle = np.degrees(res.valeurs("solide/S1/angle"))
    assert np.all(np.abs(np.diff(angle)) < 20.0)  # continu, sans saut d'un tour
    effort = np.abs(res.valeurs("moteur/M1/effort"))
    assert np.all(np.isfinite(effort)) and np.max(effort) < 1e4


def test_loi_au_dela_de_la_course_arret_explique():
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    assert regler_liaison(m, "L1", math.radians(60.0))
    m.creer_moteur("L4", LoiMouvement("vitesse_constante", {"vitesse": 0.05}))
    m.etude.duree, m.etude.pas = 2.0, 0.01
    res = lancer_etude(m)
    assert not res.complet
    message = next(x for x in res.messages if x.code == "mouvement_impossible")
    # le piston atteint r + l = 0,2 m vers t = 0,628 s : arrêt au premier instant au-delà
    depart = 0.05 * math.cos(math.radians(60.0)) + math.sqrt(0.15**2 - (0.05 * math.sin(math.radians(60.0))) ** 2)
    fin_de_course = (0.2 - depart) / 0.05
    assert res.temps[-1] <= fin_de_course < float(message.parametres["t"])


# ------------------------------------------------------------- intégrateurs

@pytest.mark.parametrize("methode", METHODES)
def test_chaque_methode_d_integration(methode):
    """Pendule pesant de petite amplitude : même période avec chaque intégrateur."""
    longueur = 0.5
    m = B.pendule_simple(longueur, 1.0, angle=-math.pi / 2 + math.radians(2.0))
    m.etude.duree, m.etude.pas, m.etude.methode = 3.0, 0.005, methode
    res = lancer_etude(m)
    assert res.complet and res.methode == methode
    x = res.valeurs("solide/S1/x") - np.mean(res.valeurs("solide/S1/x"))
    passages = np.where((x[:-1] < 0.0) & (x[1:] >= 0.0))[0]
    periode = float(np.mean(np.diff(res.temps[passages])))
    assert periode == pytest.approx(2 * math.pi * math.sqrt(2 * longueur / (3 * G)), rel=5e-3)


def test_emballement_arrete_et_explique():
    """Couple constant sans charge sur une manivelle légère : la vitesse s'envole, le calcul s'arrête."""
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    m.etude.pesanteur = False
    for solide in m.solides_mobiles():
        solide.inertie = solide.inertie_barres_homogenes(0.01)
    m.creer_couple("S1", 50.0)
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 5.0, 0.01
    res = lancer_etude(m)
    assert not res.complet
    message = next(x for x in res.messages if x.code.startswith("emballement"))
    assert float(message.parametres["valeur"]) >= 1e4


def test_acceleration_continue_signalee():
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    m.etude.pesanteur = False
    m.creer_couple("S1", 0.5)
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 3.0, 0.01
    res = lancer_etude(m)
    assert res.complet and "acceleration_continue" in [x.code for x in res.messages]


def test_tout_impose_resolu_directement():
    """Sans mobilité libre, le PFD ne sert qu'aux efforts : calcul exact et immédiat."""
    m = B.bielle_manivelle()
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 0.5, 0.01
    for solide in m.solides_mobiles():
        solide.inertie.masse = solide.inertie.jz = 0.0  # aucune masse : la dynamique n'aurait rien à intégrer
    res = lancer_etude(m)
    assert res.complet and res.type_etude == "dynamique"
    assert "aucune_mobilite_libre" in [x.code for x in res.messages]


@pytest.mark.parametrize("methode", ["LSODA", "Radau"])
def test_annulation_dans_un_fil_sans_plantage(methode):
    """Annuler pendant LSODA (Fortran) depuis un fil de calcul ne doit jamais arrêter le programme."""
    m = B.double_pendule()
    m.etude.duree, m.etude.methode = 30.0, methode
    compteur = {"n": 0}

    def annule():
        compteur["n"] += 1
        return compteur["n"] > 20

    issue = {}

    def calculer():
        try:
            lancer_etude(m, annule=annule)
        except CalculInterrompu:
            issue["interrompu"] = True

    fil = threading.Thread(target=calculer)
    fil.start()
    fil.join(60.0)
    assert not fil.is_alive() and issue == {"interrompu": True}


@pytest.mark.parametrize("methode", ["LSODA", "Radau"])
def test_expression_invalide_en_cours_d_integration(methode):
    """Une force qui devient incalculable en cours de route : erreur claire, pas de plantage."""
    m = B.pendule_simple()
    m.etude.methode, m.etude.duree = methode, 1.0
    m.creer_force("S1", "P2", "sqrt(0.5-t)", 0.0)  # racine d'un nombre négatif après t = 0,5 s
    issue = {}

    def calculer():
        try:
            lancer_etude(m)
        except ErreurCalcul as erreur:
            issue["code"] = erreur.code

    fil = threading.Thread(target=calculer)
    fil.start()
    fil.join(60.0)
    assert not fil.is_alive() and issue.get("code") == "expression"


def test_force_infinie_arret_explique():
    """Une force qui tend vers l'infini (1/(t − 0,5)) : arrêt juste avant, résultats gardés."""
    m = B.pendule_simple()
    m.etude.duree = 1.0
    m.creer_force("S1", "P2", "1/(t-0.5)", 0.0)
    res = lancer_etude(m)
    assert not res.complet and 0.45 <= res.temps[-1] < 0.5
    assert "integration_interrompue" in [x.code for x in res.messages]
