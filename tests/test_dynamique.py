"""Étude dynamique (PFD) : périodes, conservation de l'énergie, réponses analytiques."""

import math

import numpy as np
import pytest

from sikax.calcul import CalculInterrompu, ErreurCalcul, SystemeMecanique, lancer_etude
from sikax.modele import LoiMouvement, Mecanisme, bibliotheque as B
from sikax.modele.solide import ID_BATI
from sikax.physique import Torseur

G = 9.81


def periode(temps, signal):
    """Période moyenne d'un signal oscillant, par ses passages par zéro montants."""
    s = signal - np.mean(signal)
    indices = np.where((s[:-1] < 0.0) & (s[1:] >= 0.0))[0]
    instants = temps[indices] - s[indices] * (temps[indices + 1] - temps[indices]) / (s[indices + 1] - s[indices])
    return float(np.mean(np.diff(instants)))


def integrale_elliptique(k):
    """Intégrale elliptique complète de première espèce, par la moyenne arithmético-géométrique."""
    a, b = 1.0, math.sqrt(1.0 - k * k)
    for _ in range(40):
        a, b = (a + b) / 2.0, math.sqrt(a * b)
    return math.pi / (2.0 * a)


def test_pendule_petites_oscillations():
    L = 0.5
    m = B.pendule_simple(L, 1.0, angle=-math.pi / 2 + math.radians(2.0))
    m.etude.duree, m.etude.pas = 6.0, 0.002
    res = lancer_etude(m)
    assert res.complet and res.mobilite_libre == 1
    attendu = 2.0 * math.pi * math.sqrt(2.0 * L / (3.0 * G))  # pendule pesant : J_O = m·L²/3
    assert periode(res.temps, res.valeurs("solide/S1/x")) == pytest.approx(attendu, rel=2e-4)


def test_pendule_grande_amplitude():
    """Lâché à l'horizontale (amplitude 90°) : période exacte par l'intégrale elliptique."""
    L = 0.5
    m = B.pendule_simple(L, 1.0, angle=0.0)
    m.etude.duree, m.etude.pas = 8.0, 0.002
    res = lancer_etude(m)
    attendu = 4.0 * math.sqrt(2.0 * L / (3.0 * G)) * integrale_elliptique(math.sin(math.pi / 4))
    assert periode(res.temps, res.valeurs("solide/S1/x") - 0.0) == pytest.approx(attendu, rel=1e-5)


@pytest.mark.parametrize("nom", ["pendule_simple", "double_pendule"])
def test_conservation_de_l_energie(nom):
    m = B.EXEMPLES[nom]()
    m.etude.duree = 5.0
    res = lancer_etude(m)
    energie = res.valeurs("energie/mecanique")
    amplitude = np.ptp(res.valeurs("energie/cinetique"))
    assert np.max(np.abs(energie - energie[0])) < 2e-6 * amplitude
    assert res.complet


def test_liaisons_respectees_sans_derive():
    m = B.double_pendule()
    m.etude.duree = 5.0
    res = lancer_etude(m)
    # extrémité du bras 1 et origine du bras 2 confondues, bras 1 de longueur constante
    ecart = np.hypot(
        res.valeurs("point/S1/P2/x") - res.valeurs("point/S2/P1/x"),
        res.valeurs("point/S1/P2/y") - res.valeurs("point/S2/P1/y"),
    )
    assert np.max(ecart) < 1e-9
    assert np.hypot(res.valeurs("point/S1/P2/x"), res.valeurs("point/S1/P2/y")) == pytest.approx(0.3, abs=1e-9)


def test_masse_ressort_amortisseur():
    masse, k, c, x0 = 2.0, 200.0, 2.0, 0.05
    m = B.masse_ressort(masse, k, c, x0)
    res = lancer_etude(m)
    t = res.temps
    w0 = math.sqrt(k / masse)
    xi = c / (2.0 * math.sqrt(k * masse))
    wd = w0 * math.sqrt(1.0 - xi * xi)
    attendu = x0 * np.exp(-xi * w0 * t) * (np.cos(wd * t) + xi * w0 / wd * np.sin(wd * t))
    assert res.valeurs("point/S1/P1/x") - 0.2 == pytest.approx(attendu, abs=2e-8)
    assert res.valeurs("action/A1/longueur") - 0.2 == pytest.approx(attendu, abs=2e-8)
    # l'énergie mécanique ne peut que décroître
    assert np.all(np.diff(res.valeurs("energie/mecanique")) <= 1e-12)


def test_chute_libre():
    m = Mecanisme()
    s = m.creer_barre([(0.0, 0.0), (0.2, 0.0)])
    s.inertie = s.inertie_barres_homogenes(1.5)
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 1.0, 0.01
    res = lancer_etude(m)
    t = res.temps
    assert res.valeurs("solide/S1/y") == pytest.approx(-0.5 * G * t * t, abs=1e-9)
    assert res.valeurs("solide/S1/angle") == pytest.approx(0.0, abs=1e-12)
    assert res.mobilite_libre == 3


def _bilan_dynamique(mecanisme, res, indice):
    """Pour chaque solide : somme des torseurs extérieurs − torseur dynamique (doit être nulle)."""
    systeme = SystemeMecanique(mecanisme)
    gx, gy = systeme.gravite
    for solide in mecanisme.solides_mobiles():
        total = Torseur()
        for liaison in mecanisme.liaisons.values():
            torseur = res.torseur_liaison(liaison.id, indice)
            if liaison.solide_b == solide.id:
                total = total + torseur
            elif liaison.solide_a == solide.id:
                total = total - torseur
        for moteur in mecanisme.moteurs.values():
            liaison = mecanisme.liaisons[moteur.liaison]
            action = Torseur.couple((0.0, 0.0, res.valeur(f"moteur/{moteur.id}/effort", indice)))
            if liaison.solide_b == solide.id:
                total = total + action
            elif liaison.solide_a == solide.id:
                total = total - action
        base = f"solide/{solide.id}/"
        g = (res.valeur(base + "x", indice), res.valeur(base + "y", indice))
        masse = solide.inertie.masse
        total = total + Torseur.glisseur((masse * gx, masse * gy), g)
        dynamique = Torseur(
            (masse * res.valeur(base + "ax", indice), masse * res.valeur(base + "ay", indice), 0.0),
            (0.0, 0.0, solide.inertie.jz * res.valeur(base + "alpha", indice)),
            (g[0], g[1], 0.0),
        )
        yield solide, (total - dynamique).deplacer((0.0, 0.0, 0.0))


@pytest.mark.parametrize("nom", ["pendule_simple", "double_pendule", "bielle_manivelle", "quatre_barres", "coulisse_retour_rapide"])
def test_pfd_solide_par_solide(nom):
    """Les efforts de liaison vérifient le PFD pour chaque solide isolé (vérification indépendante)."""
    m = B.EXEMPLES[nom]()
    m.etude.duree, m.etude.pas = 0.6, 0.01
    res = lancer_etude(m)
    for indice in (0, 17, 33, res.nb_instants - 1):
        for solide, ecart in _bilan_dynamique(m, res, indice):
            assert ecart.norme_resultante == pytest.approx(0.0, abs=1e-7), (solide.nom, indice)
            assert ecart.mz == pytest.approx(0.0, abs=1e-7), (solide.nom, indice)


def test_dynamique_avec_moteur_bilan_de_puissance():
    """Bras motorisé portant un pendule libre : puissance moteur = dE/dt."""
    m = B.double_pendule()
    m.creer_moteur("L1", LoiMouvement("sinusoidale", {"amplitude": 0.4, "frequence": 1.0}))
    m.etude.duree, m.etude.pas = 2.0, 0.001
    res = lancer_etude(m)
    assert res.mobilite_libre == 1
    puissance = res.valeurs("moteur/M1/puissance")
    derivee = np.gradient(res.valeurs("energie/mecanique"), res.temps, edge_order=2)
    assert (puissance - derivee)[3:-3] == pytest.approx(0.0, abs=2e-4 * np.max(np.abs(puissance)))


def test_vitesse_initiale_et_amortissement_visqueux():
    """Volant lancé à ω0, freiné par un frottement visqueux : ω = ω0·exp(−c·t/J)."""
    m = Mecanisme()
    volant = m.creer_barre([(-0.1, 0.0), (0.1, 0.0)])
    centre = m.creer_point(volant.id, 0.0, 0.0)
    volant.inertie.masse, volant.inertie.jz = 3.0, 0.02
    volant.inertie.gx, volant.inertie.gy = 0.1, 0.0  # G au centre (origine du solide en −0,1)
    pivot = m.creer_liaison("pivot", ID_BATI, m.creer_point(ID_BATI, 0.0, 0.0).id, volant.id, centre.id)
    pivot.vitesse_initiale = 12.0
    pivot.amortissement = 0.05
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 1.0, 0.01
    res = lancer_etude(m)
    assert res.valeurs("solide/S1/omega") == pytest.approx(12.0 * np.exp(-0.05 * res.temps / 0.02), rel=1e-6)
    assert res.valeurs("liaison/L1/vitesse_angulaire")[0] == pytest.approx(12.0)


def test_amortissement_de_glissiere():
    m = B.masse_ressort(masse=2.0, raideur=0.0, amortissement=0.0, ecart=0.0)
    m.liaisons["L1"].vitesse_initiale = 0.5
    m.liaisons["L1"].amortissement = 4.0
    m.etude.duree = 1.0
    res = lancer_etude(m)
    assert res.valeurs("liaison/L1/vitesse") == pytest.approx(0.5 * np.exp(-4.0 * res.temps / 2.0), rel=1e-6)


def test_mecanisme_hyperstatique_en_dynamique():
    m = B.parallelogramme_double()
    m.supprimer_moteur("M1")
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 1.5, 0.005
    res = lancer_etude(m)
    assert res.complet and res.hyperstatisme == 1 and res.mobilite_libre == 1
    energie = res.valeurs("energie/mecanique")
    assert np.max(np.abs(energie - energie[0])) < 1e-6 * max(np.ptp(res.valeurs("energie/cinetique")), 1e-9)


def test_inertie_manquante():
    m = B.double_pendule()
    m.solides["S2"].inertie.masse = 0.0
    m.solides["S2"].inertie.jz = 0.0
    with pytest.raises(ErreurCalcul) as info:
        lancer_etude(m)
    assert info.value.code == "inertie_insuffisante"
    assert "Bras 2" in info.value.parametres["solides"]


def test_solide_sans_masse_entraine_accepte():
    """Une bielle sans masse entre deux solides pesants ne bloque pas le calcul."""
    m = B.bielle_manivelle()
    m.supprimer_moteur("M1")
    m.solides["S2"].inertie.masse = 0.0
    m.solides["S2"].inertie.jz = 0.0
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 0.3, 0.01
    m.creer_couple("S1", 0.5)
    res = lancer_etude(m)
    assert res.complet and np.all(np.isfinite(res.q))


def test_annulation():
    m = B.double_pendule()
    compteur = {"n": 0}

    def annule():
        compteur["n"] += 1
        return compteur["n"] > 50

    with pytest.raises(CalculInterrompu):
        lancer_etude(m, annule=annule)


def test_progression():
    valeurs = []
    lancer_etude(B.pendule_simple(), progression=valeurs.append)
    assert valeurs and valeurs[-1] == pytest.approx(1.0)
    assert all(b >= a for a, b in zip(valeurs, valeurs[1:]))


def echelle_glissante(longueur=2.0, masse=10.0, angle=math.radians(70.0)):
    """Barre dont une extrémité glisse sur le sol et l'autre sur un mur, sans frottement."""
    m = Mecanisme(titre="Échelle")
    a, b = (longueur * math.cos(angle), 0.0), (0.0, longueur * math.sin(angle))
    barre = m.creer_barre([a, b], nom="Échelle")
    barre.inertie = barre.inertie_barres_homogenes(masse)
    m.creer_liaison_en("ponctuelle", a[0], a[1], ID_BATI, barre.id, angle_axe_global=0.0, nom="Sol")
    m.creer_liaison_en("ponctuelle", b[0], b[1], ID_BATI, barre.id, angle_axe_global=math.pi / 2, nom="Mur")
    m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 0.9, 0.002
    return m


def test_echelle_glissante_ponctuelles_en_dynamique():
    L, masse, theta0 = 2.0, 10.0, math.radians(70.0)
    m = echelle_glissante(L, masse, theta0)
    res = lancer_etude(m)
    assert res.complet and res.mobilite_libre == 1 and res.hyperstatisme == 0
    # les deux extrémités restent sur leurs droites
    assert res.valeurs("point/S1/P1/y") == pytest.approx(0.0, abs=1e-9)
    assert res.valeurs("point/S1/P2/x") == pytest.approx(0.0, abs=1e-9)
    energie = res.valeurs("energie/mecanique")
    assert np.max(np.abs(energie - energie[0])) < 1e-7 * masse * G * L
    # accélération angulaire au lâcher : θ'' = −(3g / 2L)·cos θ  (θ compté depuis le sol)
    assert abs(res.valeur("solide/S1/alpha", 0)) == pytest.approx(1.5 * G / L * math.cos(theta0), rel=1e-9)
    # au lâcher : réaction du sol N = m·g − m·(L/2)·θ''·cos θ, verticale ; réaction du mur horizontale
    alpha0 = 1.5 * G / L * math.cos(theta0)
    assert res.valeur("liaison/L1/Y", 0) == pytest.approx(masse * G - masse * L / 2 * alpha0 * math.cos(theta0), rel=1e-9)
    assert res.valeur("liaison/L1/X", 0) == pytest.approx(0.0, abs=1e-9)
    assert res.valeur("liaison/L2/Y", 0) == pytest.approx(0.0, abs=1e-9)
    # l'échelle quitte le mur quand sin θ = (2/3)·sin θ0 : l'effort normal du mur s'y annule
    decollements = [msg for msg in res.messages if msg.code == "decollement"]
    assert [msg.parametres["liaison"] for msg in decollements] == ["Mur"]
    instant = decollements[0].parametres["t"]
    i = res.indice_du_temps(instant)
    hauteur = res.valeur("point/S1/P2/y", i)
    assert hauteur / L == pytest.approx(2.0 / 3.0 * math.sin(theta0), abs=2e-3)
    for indice in (0, 100, 300, res.nb_instants - 1):
        for solide, ecart in _bilan_dynamique(m, res, indice):
            assert ecart.norme_resultante == pytest.approx(0.0, abs=1e-7) and ecart.mz == pytest.approx(0.0, abs=1e-7)


def test_grand_mecanisme_tolerance_adaptee():
    """Un mécanisme de plusieurs kilomètres s'assemble malgré l'arrondi des nombres."""
    m = B.quatre_barres(manivelle=1000.0, bielle=3000.0, balancier=2500.0, entraxe=3000.0)
    m.etude.duree, m.etude.pas = 0.5, 0.01
    res = lancer_etude(m)
    assert res.complet and res.nb_instants == 51
