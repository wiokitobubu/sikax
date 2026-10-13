"""Mécanismes de référence, construits par programme.

Ces fonctions servent trois usages : les exemples livrés avec l'application
(dossier ``resources/exemples``), les tests de validation du moteur de calcul
et l'apprentissage de l'interface de script. Toutes les valeurs sont en SI.
"""

from __future__ import annotations

import math
from typing import Callable, Dict

from .lois import LoiMouvement
from .mecanisme import Mecanisme
from .solide import ID_BATI


def _barre(m: Mecanisme, sommets, nom: str, masse: float = 0.0):
    solide = m.creer_barre(sommets, nom=nom)
    if masse > 0.0:
        solide.inertie = solide.inertie_barres_homogenes(masse)
    return solide


def pendule_simple(longueur: float = 0.5, masse: float = 1.0, angle: float = -math.pi / 6) -> Mecanisme:
    """Barre homogène articulée au bâti, lâchée sans vitesse.

    ``angle`` est l'angle de la barre avec l'horizontale (−90° = position basse).
    """
    m = Mecanisme(titre="Pendule simple")
    bout = (longueur * math.cos(angle), longueur * math.sin(angle))
    barre = _barre(m, [(0.0, 0.0), bout], "Pendule", masse)
    m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, barre.id)
    m.etude.type = "dynamique"
    m.etude.duree = 3.0
    m.etude.pas = 0.005
    return m


def double_pendule(l1: float = 0.3, l2: float = 0.3, m1: float = 1.0, m2: float = 1.0) -> Mecanisme:
    """Deux barres articulées en chaîne, lâchées à l'horizontale : mouvement chaotique."""
    m = Mecanisme(titre="Double pendule")
    b1 = _barre(m, [(0.0, 0.0), (l1, 0.0)], "Bras 1", m1)
    b2 = _barre(m, [(l1, 0.0), (l1 + l2, 0.0)], "Bras 2", m2)
    m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, b1.id)
    m.creer_liaison_en("pivot", l1, 0.0, b1.id, b2.id)
    m.etude.type = "dynamique"
    m.etude.duree = 4.0
    m.etude.pas = 0.005
    return m


def bielle_manivelle(
    rayon: float = 0.05,
    bielle: float = 0.15,
    vitesse: float = 2.0 * math.pi,
    masse_manivelle: float = 0.5,
    masse_bielle: float = 0.8,
    masse_piston: float = 1.0,
    angle_initial: float = 0.0,
) -> Mecanisme:
    """Système bielle-manivelle : manivelle motorisée, piston guidé sur l'axe x.

    ``angle_initial`` est l'angle de la manivelle avec l'axe x dans la
    configuration de départ.
    """
    m = Mecanisme(titre="Bielle-manivelle")
    b = (rayon * math.cos(angle_initial), rayon * math.sin(angle_initial))
    c = (b[0] + math.sqrt(bielle * bielle - b[1] * b[1]), 0.0)
    manivelle = _barre(m, [(0.0, 0.0), b], "Manivelle", masse_manivelle)
    tige = _barre(m, [b, c], "Bielle", masse_bielle)
    piston = _barre(m, [c, (c[0] + 0.04, 0.0)], "Piston", masse_piston)
    pivot = m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, manivelle.id)
    m.creer_liaison_en("pivot", b[0], b[1], manivelle.id, tige.id)
    m.creer_liaison_en("pivot", c[0], c[1], tige.id, piston.id)
    m.creer_liaison_en("glissiere", c[0], c[1], ID_BATI, piston.id, angle_axe_global=0.0)
    m.creer_moteur(pivot.id, LoiMouvement("vitesse_constante", {"vitesse": vitesse}), nom="Moteur manivelle")
    m.etude.type = "cinematique"
    m.etude.duree = 2.0 * abs(2.0 * math.pi / vitesse) if vitesse else 2.0
    m.etude.pas = m.etude.duree / 400.0
    return m


def quatre_barres(
    manivelle: float = 0.10,
    bielle: float = 0.30,
    balancier: float = 0.25,
    entraxe: float = 0.30,
    vitesse: float = 2.0 * math.pi,
) -> Mecanisme:
    """Quadrilatère articulé manivelle-balancier (condition de Grashof respectée)."""
    m = Mecanisme(titre="Quatre barres")
    angle = math.radians(60.0)
    a = (manivelle * math.cos(angle), manivelle * math.sin(angle))
    # B est à l'intersection des cercles (A, bielle) et (C, balancier), côté y > 0.
    c = (entraxe, 0.0)
    d = math.hypot(c[0] - a[0], c[1] - a[1])
    k = (bielle * bielle - balancier * balancier + d * d) / (2.0 * d)
    hauteur = math.sqrt(max(bielle * bielle - k * k, 0.0))
    ex, ey = (c[0] - a[0]) / d, (c[1] - a[1]) / d
    b = (a[0] + k * ex - hauteur * ey, a[1] + k * ey + hauteur * ex)
    s1 = _barre(m, [(0.0, 0.0), a], "Manivelle", 0.4)
    s2 = _barre(m, [a, b], "Bielle", 1.0)
    s3 = _barre(m, [b, c], "Balancier", 0.9)
    pivot = m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, s1.id)
    m.creer_liaison_en("pivot", a[0], a[1], s1.id, s2.id)
    m.creer_liaison_en("pivot", b[0], b[1], s2.id, s3.id)
    m.creer_liaison_en("pivot", c[0], c[1], ID_BATI, s3.id)
    m.bati.ajouter_segment("P1", "P2")
    m.creer_moteur(pivot.id, LoiMouvement("vitesse_constante", {"vitesse": vitesse}))
    m.etude.type = "cinematique"
    m.etude.duree = 2.0
    m.etude.pas = 0.005
    return m


def poutre_sur_deux_appuis(portee: float = 1.0, position_charge: float = 0.4, charge: float = 1000.0) -> Mecanisme:
    """Poutre isostatique : articulation en A, appui simple en B, charge verticale."""
    m = Mecanisme(titre="Poutre sur deux appuis")
    poutre = m.creer_solide("Poutre")
    pa = m.creer_point(poutre.id, 0.0, 0.0)
    pc = m.creer_point(poutre.id, position_charge, 0.0, relier_a=pa.id)
    m.creer_point(poutre.id, portee, 0.0, relier_a=pc.id)
    m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, poutre.id)
    m.creer_liaison_en("ponctuelle", portee, 0.0, ID_BATI, poutre.id, angle_axe_global=0.0)
    m.creer_force(poutre.id, pc.id, 0.0, -charge, nom="Charge")
    m.etude.type = "statique"
    m.etude.pesanteur = False
    return m


def poutre_bi_articulee(portee: float = 1.0, charge: float = 1000.0) -> Mecanisme:
    """Poutre sur deux articulations : hyperstatique d'ordre 1 dans le plan."""
    m = poutre_sur_deux_appuis(portee, portee / 2.0, charge)
    m.titre = "Poutre bi-articulée (hyperstatique)"
    ancienne = next(l for l in m.liaisons.values() if l.type == "ponctuelle")
    m.supprimer_liaison(ancienne.id)
    m.creer_liaison_en("pivot", portee, 0.0, ID_BATI, "S1")
    return m


def masse_ressort(masse: float = 2.0, raideur: float = 200.0, amortissement: float = 2.0, ecart: float = 0.05) -> Mecanisme:
    """Chariot guidé horizontalement, rappelé par un ressort-amortisseur."""
    m = Mecanisme(titre="Masse-ressort-amortisseur")
    repos = 0.2
    chariot = m.creer_barre([(repos + ecart, 0.0), (repos + ecart + 0.06, 0.0)], nom="Chariot")
    chariot.inertie.masse = masse
    chariot.inertie.gx = 0.03
    chariot.inertie.jz = masse * 0.06 ** 2 / 12.0
    glissiere = m.creer_liaison_en("glissiere", repos + ecart, 0.0, ID_BATI, chariot.id, angle_axe_global=0.0)
    ancrage = m.creer_point(ID_BATI, 0.0, 0.0, nom="O")
    m.bati.ajouter_segment(ancrage.id, glissiere.point_a)
    m.creer_ressort(ID_BATI, ancrage.id, chariot.id, "P1", raideur, amortissement, repos, nom="Ressort")
    m.etude.type = "dynamique"
    m.etude.pesanteur = False
    m.etude.duree = 3.0
    m.etude.pas = 0.005
    return m


def coulisse_a_retour_rapide(manivelle: float = 0.06, entraxe: float = 0.14, bras: float = 0.32, vitesse: float = 2.0 * math.pi) -> Mecanisme:
    """Mécanisme à coulisse : la manivelle entraîne un coulisseau qui glisse le long d'un bras oscillant."""
    m = Mecanisme(titre="Coulisse à retour rapide")
    angle = math.radians(30.0)
    a = (manivelle * math.cos(angle), entraxe + manivelle * math.sin(angle))
    direction = math.atan2(a[1], a[0])
    bout = (bras * math.cos(direction), bras * math.sin(direction))
    s1 = _barre(m, [(0.0, entraxe), a], "Manivelle", 0.3)
    s2 = m.creer_solide("Coulisseau", x=a[0], y=a[1], angle=direction)
    m.creer_point(s2.id, a[0], a[1])
    s2.inertie.masse, s2.inertie.jz = 0.2, 1e-5
    s3 = _barre(m, [(0.0, 0.0), bout], "Bras", 1.2)
    pivot = m.creer_liaison_en("pivot", 0.0, entraxe, ID_BATI, s1.id)
    m.creer_liaison_en("pivot", a[0], a[1], s1.id, s2.id)
    m.creer_liaison_en("glissiere", a[0], a[1], s3.id, s2.id, angle_axe_global=direction)
    m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, s3.id)
    m.creer_moteur(pivot.id, LoiMouvement("vitesse_constante", {"vitesse": vitesse}))
    m.etude.type = "cinematique"
    m.etude.duree = 2.0
    m.etude.pas = 0.005
    return m


def parallelogramme_double(longueur: float = 0.2, hauteur: float = 0.12, vitesse: float = math.pi) -> Mecanisme:
    """Deux parallélogrammes accolés : mobile (m = 1) bien qu'hyperstatique (h = 1)."""
    m = Mecanisme(titre="Parallélogramme double")
    angle = math.radians(70.0)
    dx, dy = hauteur * math.cos(angle), hauteur * math.sin(angle)
    pieds = [0.0, longueur, 2.0 * longueur]
    barres = [_barre(m, [(x, 0.0), (x + dx, dy)], f"Biellette {i + 1}", 0.2) for i, x in enumerate(pieds)]
    plateau = m.creer_solide("Plateau", x=dx, y=dy)
    precedent = None
    for x in pieds:
        precedent = m.creer_point(plateau.id, x + dx, dy, relier_a=precedent).id
    plateau.inertie = plateau.inertie_barres_homogenes(0.6)
    premier = None
    for barre, x in zip(barres, pieds):
        liaison = m.creer_liaison_en("pivot", x, 0.0, ID_BATI, barre.id)
        premier = premier or liaison
        m.creer_liaison_en("pivot", x + dx, dy, barre.id, plateau.id)
    m.bati.ajouter_segment("P1", "P2")
    m.bati.ajouter_segment("P2", "P3")
    m.creer_moteur(premier.id, LoiMouvement("sinusoidale", {"amplitude": 0.6, "frequence": 0.5}))
    m.etude.type = "cinematique"
    m.etude.duree = 4.0
    m.etude.pas = 0.01
    return m


EXEMPLES: Dict[str, Callable[[], Mecanisme]] = {
    "bielle_manivelle": lambda: bielle_manivelle(angle_initial=math.radians(50.0)),
    "quatre_barres": quatre_barres,
    "coulisse_retour_rapide": coulisse_a_retour_rapide,
    "pendule_simple": pendule_simple,
    "double_pendule": double_pendule,
    "masse_ressort": masse_ressort,
    "poutre_deux_appuis": poutre_sur_deux_appuis,
    "poutre_bi_articulee": poutre_bi_articulee,
    "parallelogramme_double": parallelogramme_double,
}
