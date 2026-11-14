"""Lecture et écriture des projets : fidélité, souplesse, diagnostics, robustesse."""

import copy
import json
import math
import random
import string

import pytest

from sikax.calcul import ErreurCalcul, lancer_etude, residu_de_fermeture
from sikax.fichiers import (
    ErreurEcriture,
    ErreurLecture,
    charger,
    depuis_json,
    dict_vers_mecanisme,
    enregistrer,
    mecanisme_vers_dict,
    vers_json,
)
from sikax.fichiers import migrations
from sikax.i18n import texte_diagnostic, texte_erreur_fichier, traducteur
from sikax.fichiers import format as format_fichier
from sikax.modele import Mecanisme, bibliotheque as B
from sikax.modele.liaisons import Encastrement, Glissiere, Pivot, Ponctuelle


def document(nom="bielle_manivelle"):
    return mecanisme_vers_dict(B.EXEMPLES[nom](), horodatage="2026-01-01T00:00:00+00:00")


def lire(donnees, tolerant=False):
    return depuis_json(json.dumps(donnees, ensure_ascii=False), tolerant)


def codes_erreur(excinfo):
    return [d.code for d in excinfo.value.rapport.erreurs]


# ---------------------------------------------------------------- fidélité

@pytest.mark.parametrize("nom", list(B.EXEMPLES))
def test_aller_retour_exact(nom):
    original = B.EXEMPLES[nom]()
    texte = vers_json(original, horodatage="h")
    resultat = depuis_json(texte)
    assert resultat.mecanisme == original
    assert not resultat.rapport.diagnostics
    assert vers_json(resultat.mecanisme, horodatage="h") == texte


def test_aller_retour_valeurs_delicates():
    m = B.bielle_manivelle()
    m.titre = "Étude n°1 — « bielle » / manivelle ✓"
    m.solides["S1"].nom = "Manivelle (été)"
    libre = m.creer_barre([(0.4, 0.1), (0.5, 0.1)], nom="Solide libre")  # sans liaison : pose quelconque
    libre.pose.angle = 0.1 + 0.2  # 0.30000000000000004
    libre.points["P2"].x = 1e-17
    m.solides["S2"].inertie.jz = 1.2345678901234567e-9
    m.creer_force("S3", "P1", "100*sin(2*pi*t)", -3.3e5, repere="local")
    m.creer_couple("S2", "si(t > 1, 5, 0)")
    m.creer_ressort("S0", "P1", "S2", "P2", 1500.0, 12.5, 0.07)
    m.liaisons["L1"].modele_spatial = "rotule"
    m.etude.gx, m.etude.gy = 1.5, -9.80665
    relu = depuis_json(vers_json(m)).mecanisme
    assert relu == m
    assert relu.solides[libre.id].pose.angle == 0.30000000000000004


def test_enregistrement_atomique_et_sauvegarde(tmp_path):
    chemin = tmp_path / "dossier à créer" / "mécanisme été.sikax"
    premier = B.pendule_simple()
    enregistrer(premier, str(chemin))
    assert chemin.exists() and not (tmp_path / "dossier à créer" / "mécanisme été.sikax.bak").exists()
    second = B.double_pendule()
    enregistrer(second, str(chemin))
    assert charger(str(chemin)).mecanisme == second
    assert charger(str(chemin) + ".bak").mecanisme == premier
    # aucun fichier temporaire ne reste dans le dossier
    assert sorted(p.name for p in chemin.parent.iterdir()) == ["mécanisme été.sikax", "mécanisme été.sikax.bak"]
    assert charger(str(chemin)).chemin == str(chemin)


def test_ecriture_refuse_les_valeurs_non_finies(tmp_path):
    m = B.pendule_simple()
    m.solides["S1"].pose.x = float("nan")
    with pytest.raises(ErreurEcriture):
        vers_json(m)
    chemin = tmp_path / "p.sikax"
    enregistrer(B.pendule_simple(), str(chemin))
    with pytest.raises(ErreurEcriture):
        enregistrer(m, str(chemin))
    assert charger(str(chemin)).mecanisme == B.pendule_simple()  # l'ancien fichier est intact


def test_ecriture_dans_un_dossier_interdit(tmp_path):
    fichier = tmp_path / "fichier"
    fichier.write_text("x")
    with pytest.raises(ErreurEcriture) as info:
        enregistrer(B.pendule_simple(), str(fichier / "projet.sikax"))
    assert info.value.code == "ecriture_impossible"


# ------------------------------------------------- interprétation des liaisons

@pytest.mark.parametrize(
    "ecrit,classe",
    [
        ("pivot", Pivot), ("Pivot", Pivot), ("ARTICULATION", Pivot), ("rotoïde", Pivot), ("revolute", Pivot),
        ("glissière", Glissiere), ("Glissiere", Glissiere), ("prismatique", Glissiere), ("slider", Glissiere),
        ("encastrement", Encastrement), ("Liaison complète", Encastrement), ("fixed", Encastrement),
        ("ponctuelle", Ponctuelle), ("appui simple", Ponctuelle), ("Appui-Simple", Ponctuelle), ("sphère-plan", Ponctuelle),
    ],
)
def test_synonymes_de_types_de_liaison(ecrit, classe):
    d = document("poutre_deux_appuis")
    d["liaisons"][0]["type"] = ecrit
    resultat = lire(d)
    assert type(resultat.mecanisme.liaisons["L1"]) is classe


def test_chaque_liaison_est_restituee_a_l_identique():
    m = Mecanisme()
    a = m.creer_barre([(0.0, 0.0), (0.2, 0.1)])
    b = m.creer_barre([(0.2, 0.1), (0.5, 0.3)])
    a.pose.angle, b.pose.angle = 0.0, 0.0
    m.creer_liaison_en("pivot", 0.0, 0.0, "S0", a.id, amortissement=0.3, vitesse_initiale=-2.5)
    m.creer_liaison_en("glissiere", 0.2, 0.1, a.id, b.id, angle_axe_global=0.7, amortissement=1.5, vitesse_initiale=0.25)
    m.creer_liaison_en("ponctuelle", 0.5, 0.3, "S0", b.id, angle_axe_global=-1.1)
    c = m.creer_barre([(0.5, 0.3), (0.6, 0.3)])
    m.creer_liaison_en("encastrement", 0.5, 0.3, b.id, c.id)
    m.liaisons["L1"].modele_spatial = "pivot_glissant_z"
    m.liaisons["L3"].modele_spatial = "lineaire_rectiligne_y"
    relu = depuis_json(vers_json(m)).mecanisme
    for lid, liaison in m.liaisons.items():
        autre = relu.liaisons[lid]
        assert type(autre) is type(liaison)
        assert autre == liaison
    assert relu.liaisons["L2"].angle_axe == pytest.approx(0.7)
    assert relu.liaisons["L2"].vitesse_initiale == 0.25


def test_cles_avec_majuscules_accents_et_synonymes():
    d = document()
    souple = {
        "Format": "Sikax",
        "Version": "1",
        "Unités": {"Longueur": "CM", "Angle": "radians"},
        "Solides": [
            {("Bâti" if k == "bati" else "Nom" if k == "nom" else "Color" if k == "couleur" else k): v for k, v in s.items()}
            for s in d["solides"]
        ],
        "Joints": [
            {{"solide_a": "Solide A", "solide_b": "body_b", "type": "Type"}.get(k, k): v for k, v in l.items()}
            for l in d["liaisons"]
        ],
        "Moteurs": d["moteurs"],
        "Étude": d["etude"],
    }
    resultat = lire(souple)
    reference = lire(d).mecanisme
    assert resultat.mecanisme.liaisons == reference.liaisons
    assert resultat.mecanisme.solides == reference.solides
    assert resultat.mecanisme.unites.longueur == "cm" and resultat.mecanisme.unites.angle == "rad"
    assert not resultat.rapport.erreurs


def test_nombres_en_texte_et_angles_en_degres():
    d = document("coulisse_retour_rapide")
    glissiere = next(l for l in d["liaisons"] if l["type"] == "glissiere")
    angle = glissiere.pop("angle_axe")
    glissiere["angle_axe_deg"] = math.degrees(angle)
    d["solides"][1]["points"][1]["x"] = "0,0519615242270663"
    d["solides"][1]["inertie"]["masse"] = " 0.3 "
    d["solides"][1]["pose"]["angle_deg"] = math.degrees(d["solides"][1]["pose"].pop("angle"))
    resultat = lire(d)
    relu = resultat.mecanisme.liaisons[glissiere["id"]]
    assert relu.angle_axe == pytest.approx(angle, abs=1e-15)
    assert resultat.mecanisme.solides["S1"].points["P2"].x == pytest.approx(0.0519615242270663)
    assert resultat.mecanisme.solides["S1"].inertie.masse == 0.3
    assert {"angle_en_degres", "nombre_en_texte"} <= set(resultat.rapport.codes())
    assert not resultat.rapport.erreurs


def test_references_par_nom_et_identifiants_entiers():
    d = document()
    d["liaisons"][1]["solide_a"] = "Manivelle"
    d["liaisons"][1]["solide_b"] = "bielle"
    d["liaisons"][1]["point_b"] = "B"
    d["moteurs"][0]["liaison"] = "Pivot A"
    resultat = lire(d)
    liaison = resultat.mecanisme.liaisons["L2"]
    assert (liaison.solide_a, liaison.solide_b, liaison.point_b) == ("S1", "S2", "P1")
    assert resultat.mecanisme.moteurs["M1"].liaison == "L1"
    assert resultat.rapport.codes().count("reference_par_nom") == 4
    # identifiants numériques : 2 -> "S2", 1 -> "P1"
    d = document()
    d["liaisons"][1].update(solide_a=1, solide_b=2, point_a=2, point_b=1)
    assert lire(d).mecanisme.liaisons["L2"] == lire(document()).mecanisme.liaisons["L2"]


def test_liaison_definie_par_sa_position():
    d = document("poutre_deux_appuis")
    for liaison in d["liaisons"]:
        point = next(p for p in d["solides"][0]["points"] if p["id"] == liaison["point_a"])
        liaison["position"] = [point["x"], point["y"]]
        del liaison["point_a"], liaison["point_b"]
    d["solides"][0]["points"] = []  # le bâti n'a plus de points : ils seront recréés
    resultat = lire(d)
    m = resultat.mecanisme
    assert resultat.rapport.codes().count("point_cree") == 2
    assert not resultat.rapport.erreurs
    assert lancer_etude(m).valeur("liaison/L1/Y") == pytest.approx(600.0)


def test_orientation_relative_deduite_si_absente():
    d = document("coulisse_retour_rapide")
    glissiere = next(l for l in d["liaisons"] if l["type"] == "glissiere")
    attendu = glissiere.pop("angle_relatif")
    resultat = lire(d)
    assert resultat.mecanisme.liaisons[glissiere["id"]].angle_relatif == pytest.approx(attendu)
    assert "orientation_deduite" in resultat.rapport.codes()


def test_sections_sous_forme_de_dictionnaire():
    d = document("pendule_simple")
    d["liaisons"] = {l["id"]: {k: v for k, v in l.items() if k != "id"} for l in d["liaisons"]}
    d["solides"][1]["points"] = {p["id"]: [p["x"], p["y"]] for p in d["solides"][1]["points"]}
    resultat = lire(d)
    assert list(resultat.mecanisme.liaisons) == ["L1"]
    assert resultat.mecanisme.solides["S1"].points["P2"].x == pytest.approx(B.pendule_simple().solides["S1"].points["P2"].x)


def test_modele_spatial_inconnu_remplace_par_defaut():
    d = document()
    d["liaisons"][0]["modele_spatial"] = "glissiere_x"  # incompatible avec une pivot
    resultat = lire(d)
    assert resultat.mecanisme.liaisons["L1"].modele_spatial == "pivot_z"
    assert "modele_spatial_inconnu" in resultat.rapport.codes()


# ----------------------------------------------------------------- erreurs

def test_toutes_les_erreurs_sont_signalees_ensemble():
    d = document()
    d["liaisons"][0]["type"] = "vis sans fin"
    d["liaisons"][1]["solide_a"] = "S42"
    d["liaisons"][2]["point_b"] = "P99"
    d["liaisons"][3]["angle_axe"] = "abc"
    d["moteurs"][0]["loi"]["type"] = "exotique"
    d["solides"][1]["inertie"]["masse"] = -1
    with pytest.raises(ErreurLecture) as info:
        lire(d)
    assert info.value.code == "fichier_invalide"
    codes = codes_erreur(info)
    assert sorted(codes) == [
        "liaison_rejetee",       # le moteur pilote L1, elle-même invalide
        "nombre_invalide",       # L4 : angle_axe = "abc"
        "point_inconnu",         # L3 : point P99
        "solide_inconnu",        # L2 : solide S42
        "type_liaison_inconnu",  # L1 : « vis sans fin »
        "valeur_hors_bornes",    # S1 : masse négative
    ]
    chemins = [e.chemin for e in info.value.rapport.erreurs]
    assert "liaisons[0] (L1)" in chemins and "liaisons[3] (L4)" in chemins and "solides[1] (S1).inertie" in chemins


def test_reference_a_un_element_deja_rejete():
    """Une liaison qui s'appuie sur un solide invalide le dit, au lieu de le déclarer « inconnu »."""
    d = document()
    d["solides"][2]["points"][0]["x"] = "pas un nombre"
    with pytest.raises(ErreurLecture) as info:
        lire(d)
    assert sorted(codes_erreur(info)) == ["nombre_invalide", "solide_rejete", "solide_rejete"]


def test_nombres_demesures_refuses():
    for valeur in ("1e999", "1e16", "-1e300", "123456789012345678901234567890"):
        texte = json.dumps(document()).replace('"jz": 0.0', f'"jz": {valeur}', 1)
        with pytest.raises(ErreurLecture) as info:
            depuis_json(texte)
        assert "nombre_invalide" in codes_erreur(info), valeur


def test_mode_tolerant_ecarte_les_elements_invalides():
    d = document()
    d["liaisons"][1]["solide_a"] = "S42"
    d["liaisons"].append({"id": "L9", "type": "pivot", "solide_a": "S1", "solide_b": "S1", "point_a": "P1", "point_b": "P2"})
    resultat = lire(d, tolerant=True)
    assert sorted(resultat.mecanisme.liaisons) == ["L1", "L3", "L4"]
    assert sorted(d.code for d in resultat.rapport.erreurs) == ["liaison_meme_solide", "solide_inconnu"]
    assert not resultat.mecanisme.erreurs()


@pytest.mark.parametrize(
    "modification,code",
    [
        (lambda d: d["liaisons"][0].pop("type"), "champ_manquant"),
        (lambda d: d["liaisons"][0].pop("solide_b"), "champ_manquant"),
        (lambda d: d["liaisons"][0].update(solide_b=d["liaisons"][0]["solide_a"]), "liaison_meme_solide"),
        (lambda d: d["liaisons"][1].update(id="L1"), "identifiant_en_double"),
        (lambda d: d["liaisons"][0].update(id=None), "identifiant_manquant"),
        (lambda d: d["liaisons"].append("pivot"), "element_invalide"),
        (lambda d: (d["liaisons"][0].pop("point_a"), d["liaisons"][0].pop("point_b")), "champ_manquant"),
        (lambda d: d["liaisons"][3].update(amortissement=-2.0), "valeur_hors_bornes"),
        (lambda d: d["liaisons"][3].update(angle_axe=1e16), "nombre_invalide"),
        (lambda d: d["liaisons"][3].update(angle_axe=True), "nombre_invalide"),
        (lambda d: d["liaisons"][3].update(angle_axe=[1]), "nombre_invalide"),
        (lambda d: d["solides"][1].update(id="S2"), "identifiant_en_double"),
        (lambda d: d["solides"][1]["points"][0].pop("x"), "champ_manquant"),
        (lambda d: d["solides"][1]["points"][1].update(id="P1"), "identifiant_en_double"),
        (lambda d: d["solides"][0].update(bati=False, id="S7"), "bati_absent"),
        (lambda d: d["solides"][1].update(bati=True), "bati_multiple"),
        (lambda d: d["moteurs"][0].update(liaison="L77"), "liaison_inconnue"),
        (lambda d: d["moteurs"].append(dict(d["moteurs"][0], id="M2")), "moteur_en_double"),
        (lambda d: d["moteurs"][0].pop("loi"), "champ_manquant"),
        (lambda d: d["moteurs"][0]["loi"].update(type="expression", parametres={"expression": "2*("}), "expression_invalide"),
        (lambda d: d["moteurs"][0]["loi"].update(type="trapeze", parametres={"vitesse_max": 0}), "loi_invalide"),
        (lambda d: d["actions"].append({"id": "A1", "type": "poussée", "solide": "S1"}), "type_action_inconnu"),
        (lambda d: d["actions"].append({"id": "A1", "type": "force", "solide": "S1", "point": "P1", "fx": "1/("}), "expression_invalide"),
        (lambda d: d["actions"].append({"id": "A1", "type": "force", "solide": "S1", "point": "P8"}), "point_inconnu"),
        (lambda d: d["actions"].append({"id": "A1", "type": "couple", "solide": "inconnu", "mz": 1}), "solide_inconnu"),
        (lambda d: d["actions"].append({"id": "A1", "type": "ressort", "solide_a": "S0", "point_a": "P1", "solide_b": "S1", "point_b": "P1", "raideur": -5}), "valeur_hors_bornes"),
    ],
)
def test_erreurs_detectees(modification, code):
    d = document()
    modification(d)
    with pytest.raises(ErreurLecture) as info:
        lire(d)
    assert code in codes_erreur(info)
    # le mode tolérant, lui, ouvre toujours un modèle cohérent
    resultat = lire(d, tolerant=True)
    assert not resultat.mecanisme.erreurs()


def test_moteur_sur_liaison_non_pilotable():
    d = document("poutre_deux_appuis")
    d["moteurs"] = [{"id": "M1", "liaison": "L2", "loi": {"type": "blocage"}}]
    with pytest.raises(ErreurLecture) as info:
        lire(d)
    assert codes_erreur(info) == ["liaison_non_pilotable"]


# ------------------------------------------------------- en-tête et encodage

@pytest.mark.parametrize(
    "texte,code",
    [
        ("", "fichier_vide"),
        ("   \n\t ", "fichier_vide"),
        ("<?xml version='1.0'?><OpenMeca/>", "format_inconnu"),
        ("PK\x03\x04binaire", "format_inconnu"),
        ("[1, 2, 3]", "structure_invalide"),
        ('"texte"', "structure_invalide"),
        ('{"format": "sikax", "solides": [', "json_invalide"),
        ('{"format": "sikax", "version": 1,, }', "json_invalide"),
        ('{"format": "autre", "solides": []}', "format_inconnu"),
        ('{"cle": 1}', "format_inconnu"),
        ('{"format": "sikax", "dimension": 3, "solides": []}', "dimension_non_geree"),
        ('{"format": "sikax", "solides": [{"id": "S0", "bati": true, "pose": {"x": NaN}}]}', "nombre_non_fini"),
        ('{"format": "sikax", "solides": [{"id": "S0", "bati": true, "pose": {"x": Infinity}}]}', "nombre_non_fini"),
        pytest.param("[" * 100000, "json_invalide", id="imbrication_excessive"),
    ],
)
def test_documents_refuses(texte, code):
    with pytest.raises(ErreurLecture) as info:
        depuis_json(texte)
    assert info.value.code == code


def test_erreur_de_syntaxe_localisee():
    texte = '{\n  "format": "sikax",\n  "version": 1,\n  "solides": [ {"id": "S0" "bati": true} ]\n}'
    with pytest.raises(ErreurLecture) as info:
        depuis_json(texte)
    assert info.value.code == "json_invalide"
    assert info.value.parametres["ligne"] == 4 and info.value.parametres["colonne"] > 20


def test_fichier_minimal_et_cles_inconnues():
    resultat = depuis_json('{"format": "sikax", "version": 2, "solides": [{"id": "S0", "bati": true}], "inconnu": 3, "_note": "ok"}')
    assert resultat.mecanisme.est_vide()
    assert [(d.code, d.parametres) for d in resultat.rapport] == [("cle_inconnue", {"cle": "inconnu"})]
    # un fichier de Sikax 1.0 s'ouvre tel quel, avec une simple note de conversion
    ancien = depuis_json('{"format": "sikax", "version": 1, "solides": [{"id": "S0", "bati": true}]}')
    assert [(d.niveau, d.code) for d in ancien.rapport] == [("info", "fichier_migre")]


def test_cles_en_double_signalees():
    resultat = depuis_json('{"format": "sikax", "version": 1, "version": 1, "solides": [{"id": "S0", "bati": true}]}')
    assert "cle_en_double" in resultat.rapport.codes()


def test_version_plus_recente_et_absente():
    d = document()
    d["version"] = 99
    assert "version_plus_recente" in lire(d).rapport.codes()
    del d["version"]
    assert "version_absente" in lire(d).rapport.codes()
    d["version"] = "deux"
    assert "version_invalide" in lire(d).rapport.codes()


def test_chaine_de_migrations(monkeypatch):
    """Un fichier d'une version antérieure est converti étape par étape."""
    monkeypatch.setattr(format_fichier, "VERSION", 3)
    monkeypatch.setattr(migrations, "VERSION", 3)

    def v1_vers_v2(d):
        d["solides"] = d.pop("pieces_v1")
        return d

    def v2_vers_v3(d):
        for liaison in d.get("liaisons", []):
            liaison["type"] = liaison.pop("genre")
        return d

    monkeypatch.setattr(migrations, "MIGRATIONS", {1: v1_vers_v2, 2: v2_vers_v3})
    d = document("pendule_simple")
    d["pieces_v1"] = d.pop("solides")
    d["liaisons"][0]["genre"] = d["liaisons"][0].pop("type")
    d["version"] = 1
    resultat = dict_vers_mecanisme(d)
    assert resultat.mecanisme.liaisons == B.pendule_simple().liaisons
    assert "fichier_migre" in resultat.rapport.codes()
    monkeypatch.setattr(migrations, "MIGRATIONS", {2: v2_vers_v3})
    with pytest.raises(ErreurLecture) as info:
        dict_vers_mecanisme(dict(d, version=1))
    assert info.value.code == "migration_impossible"


@pytest.mark.parametrize("encodage", ["utf-8", "utf-8-sig", "utf-16", "cp1252"])
def test_encodages(tmp_path, encodage):
    m = B.pendule_simple()
    m.titre = "Pendule à ressort — étude n°2"
    chemin = tmp_path / "p.sikax"
    chemin.write_bytes(vers_json(m).replace("—", "-").encode(encodage))
    resultat = charger(str(chemin))
    assert resultat.mecanisme.titre == "Pendule à ressort - étude n°2"
    assert ("encodage_inhabituel" in resultat.rapport.codes()) == (encodage == "cp1252")


def test_fichiers_inaccessibles(tmp_path):
    with pytest.raises(ErreurLecture) as info:
        charger(str(tmp_path / "absent.sikax"))
    assert info.value.code == "fichier_introuvable"
    with pytest.raises(ErreurLecture) as info:
        charger(str(tmp_path))
    assert info.value.code == "lecture_impossible"
    gros = tmp_path / "gros.sikax"
    with open(gros, "wb") as f:
        f.truncate(format_fichier.TAILLE_MAX + 1)
    with pytest.raises(ErreurLecture) as info:
        charger(str(gros))
    assert info.value.code == "fichier_trop_gros"


# --------------------------------------------------------- bâti et géométrie

def test_bati_avec_autre_identifiant_et_pose():
    d = document("poutre_deux_appuis")
    bati = d["solides"][0]
    bati["id"] = "sol"
    bati["pose"] = {"x": 0.3, "y": -0.2, "angle": 0.0}
    for point in bati["points"]:
        point["x"] -= 0.3
        point["y"] += 0.2
    for liaison in d["liaisons"]:
        liaison["solide_a"] = "sol"
    resultat = lire(d)
    m = resultat.mecanisme
    assert m.bati.id == "S0" and m.bati.pose.est_identite()
    assert all(l.solide_a == "S0" for l in m.liaisons.values())
    assert {"bati_renomme", "bati_recale"} <= set(resultat.rapport.codes())
    assert lancer_etude(m).valeur("liaison/L1/Y") == pytest.approx(600.0)


def test_solide_s0_non_bati_est_renomme():
    d = document("pendule_simple")
    d["solides"][0].update(id="B", bati=True)
    d["solides"][1]["id"] = "S0"
    d["liaisons"][0].update(solide_a="B", solide_b="S0")
    resultat = lire(d)
    m = resultat.mecanisme
    assert sorted(m.solides) == ["S0", "S1"] and m.solides["S0"].bati and not m.solides["S1"].bati
    assert (m.liaisons["L1"].solide_a, m.liaisons["L1"].solide_b) == ("S0", "S1")
    assert "solide_renomme" in resultat.rapport.codes()


def test_configuration_non_assemblee_est_refermee():
    d = document("quatre_barres")
    d["solides"][2]["pose"]["x"] += 0.01  # la bielle est décalée : deux articulations ouvertes
    resultat = lire(d)
    codes = resultat.rapport.codes()
    assert codes.count("liaison_ouverte") == 2 and "mecanisme_referme" in codes
    assert residu_de_fermeture(resultat.mecanisme) < 1e-9


def test_fermeture_impossible_signalee():
    d = document("poutre_bi_articulee")
    d["solides"][0]["points"][1]["x"] += 0.2  # l'appui s'éloigne : la poutre ne peut plus s'y articuler
    resultat = lire(d)
    assert "fermeture_impossible" in resultat.rapport.codes()


def test_segments_et_couleurs_invalides_sans_gravite():
    d = document()
    d["solides"][1]["segments"] = [["P1", "P2"], ["P1", "P9"], ["P1"], "x", ["P2", "P1"], ["P1", "P1"]]
    d["solides"][1]["couleur"] = "rouge"
    d["etude"].update(duree=-1, pas="abc", type="thermique", gravite=[0, "x"])
    resultat = lire(d)
    assert resultat.mecanisme.solides["S1"].segments == [("P1", "P2")]
    assert resultat.rapport.codes().count("segment_ignore") == 4
    assert "couleur_invalide" in resultat.rapport.codes() and "type_etude_inconnu" in resultat.rapport.codes()
    assert resultat.mecanisme.etude.duree == 2.0 and resultat.mecanisme.etude.gy == -9.81
    assert not resultat.rapport.erreurs


# -------------------------------------------------------------- robustesse

def _phrases(rapport, erreur=None):
    """Chaque diagnostic se met en phrase, dans les deux langues, avec tous ses paramètres."""
    elements = list(rapport) + ([erreur] if erreur is not None else [])
    for langue in ("fr", "en"):
        traducteur.charger(langue)
        for element in elements:
            modele = traducteur.modele(element.cle_i18n)
            assert modele is not None, f"message non traduit : {element.code}"
            attendus = {nom.split(":")[0] for _, nom, _, _ in string.Formatter().parse(modele) if nom}
            assert attendus <= set(element.parametres), f"{element.code} : paramètres manquants {attendus - set(element.parametres)}"
            texte = texte_erreur_fichier(element) if element is erreur else texte_diagnostic(element)
            assert texte and element.code not in texte.split(" : ")[-1].split(" ")[0]
    traducteur.charger("fr")


def _muter(valeur, rng, profondeur=0):
    """Altère au hasard un document : valeurs remplacées, clés supprimées, éléments dupliqués."""
    poisons = [None, True, -1, 0, 1e308, "", "x", "S1", "P1", [], {}, [1, 2], {"a": 1}, "1,5", -0.0, 2 ** 70, "nan", "L1"]
    if isinstance(valeur, dict):
        sortie = {}
        for cle, contenu in valeur.items():
            tirage = rng.random()
            if tirage < 0.04:
                continue
            if tirage < 0.10:
                sortie[cle] = rng.choice(poisons)
            else:
                sortie[cle] = _muter(contenu, rng, profondeur + 1)
        return sortie
    if isinstance(valeur, list):
        sortie = []
        for contenu in valeur:
            tirage = rng.random()
            if tirage < 0.04:
                continue
            sortie.append(rng.choice(poisons) if tirage < 0.08 else _muter(contenu, rng, profondeur + 1))
            if tirage > 0.96:
                sortie.append(copy.deepcopy(contenu))
        return sortie
    if rng.random() < 0.05:
        return rng.choice(poisons)
    return valeur


@pytest.mark.parametrize("graine", range(40))
def test_documents_alteres_jamais_de_plantage(graine):
    """Quel que soit le document, la lecture réussit ou lève ``ErreurLecture`` — rien d'autre."""
    rng = random.Random(graine)
    for nom in B.EXEMPLES:
        for _ in range(6):
            abime = _muter(document(nom), rng)
            for tolerant in (False, True):
                try:
                    resultat = lire(abime, tolerant)
                except ErreurLecture as erreur:
                    _phrases(erreur.rapport, erreur)
                    continue
                _phrases(resultat.rapport)
                m = resultat.mecanisme
                assert not m.erreurs()
                vers_json(m)  # ce qui a été lu peut toujours être réécrit
                m.etude.duree, m.etude.pas = 0.02, 0.01
                try:
                    lancer_etude(m)
                except ErreurCalcul:
                    pass


@pytest.mark.parametrize("graine", range(20))
def test_texte_corrompu_jamais_de_plantage(graine):
    rng = random.Random(1000 + graine)
    texte = vers_json(B.EXEMPLES[rng.choice(list(B.EXEMPLES))]())
    for _ in range(60):
        abime = list(texte)
        for _ in range(rng.randint(1, 6)):
            position = rng.randrange(len(abime))
            operation = rng.random()
            if operation < 0.4:
                del abime[position]
            elif operation < 0.8:
                abime[position] = rng.choice('{}[]",:0123456789.-eE \n\\ntrue')
            else:
                del abime[position : position + rng.randint(1, 200)]
        try:
            _phrases(depuis_json("".join(abime), tolerant=rng.random() < 0.5).rapport)
        except ErreurLecture as erreur:
            _phrases(erreur.rapport, erreur)
