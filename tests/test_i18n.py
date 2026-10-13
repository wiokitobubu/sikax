"""Localisation : complétude des langues et couverture des clés utilisées par le code."""

import json
import re
import string
from pathlib import Path

import pytest

from sikax.fichiers import lecture
from sikax.i18n import Traducteur, tr, traducteur
from sikax.i18n.traducteur import aplatir
from sikax.modele.catalogue_spatial import CATALOGUE
from sikax.modele.etude import TYPES_ETUDE
from sikax.modele.liaisons import TYPES_LIAISON
from sikax.modele.lois import LOIS

RACINE = Path(__file__).resolve().parent.parent
LOCALES = RACINE / "locales"


def charger(code):
    donnees = json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))
    donnees.pop("_meta")
    return aplatir(donnees)


def champs(texte):
    return sorted({nom.split(":")[0] for _, nom, _, _ in string.Formatter().parse(texte) if nom})


FR = charger("fr")
LANGUES = sorted(p.stem for p in LOCALES.glob("*.json"))


def test_le_francais_est_la_langue_par_defaut():
    t = Traducteur()
    assert t.langue == "fr"
    assert t.tr("action.ouvrir") == "&Ouvrir…"
    assert "fr" in t.langues_disponibles() and t.langues_disponibles()["fr"] == "Français"


@pytest.mark.parametrize("code", [c for c in LANGUES if c != "fr"])
def test_traduction_complete(code):
    autre = charger(code)
    assert sorted(set(FR) - set(autre)) == [], "clés non traduites"
    assert sorted(set(autre) - set(FR)) == [], "clés en trop"
    for cle, texte in FR.items():
        assert champs(texte) == champs(autre[cle]), f"paramètres différents pour {cle}"
        assert autre[cle].strip(), cle


def test_textes_formatables():
    """Chaque texte se formate sans erreur avec des valeurs fictives."""
    for code in LANGUES:
        for cle, texte in charger(code).items():
            valeurs = {nom: 1.5 for nom in champs(texte)}
            texte.format(**valeurs)


def _cles_du_code():
    litterales, familles = set(), set()
    for fichier in (RACINE / "sikax").rglob("*.py"):
        source = fichier.read_text(encoding="utf-8")
        for m in re.finditer(r'(?:\btr|\.existe|\.signaler)\(\s*(f?)"([^"]+)"', source):
            cle = m.group(2)
            if m.group(1) or "{" in cle:
                familles.add(cle.split("{")[0])
            elif "." in cle:
                litterales.add(cle)
        for m in re.finditer(r'tr\("([a-z_.]+)" if [^\n]*? else "([a-z_.]+)"', source):
            litterales.update(m.groups())
    return litterales, familles


def test_toutes_les_cles_du_code_existent():
    litterales, _ = _cles_du_code()
    assert sorted(c for c in litterales if c not in FR) == []


def test_familles_de_cles_dynamiques_completes():
    attendues = set()
    attendues |= {f"liaison.type.{t}" for t in TYPES_LIAISON}
    attendues |= {f"spatial.{c}" for c in CATALOGUE}
    attendues |= {f"action.type.{t}" for t in ("force", "couple", "ressort")}
    attendues |= {f"etude.type.{t}" for t in TYPES_ETUDE} | {f"etude.description.{t}" for t in TYPES_ETUDE}
    attendues |= {f"loi.{t}" for t in LOIS} | {f"loi.aide.{t}" for t in LOIS}
    attendues |= {f"loi.param.{nom}" for parametres in LOIS.values() for nom, _, _ in parametres}
    attendues |= {f"outil.{n}.aide" for n in ("selection", "manipuler", "barre", "point", "force", "couple", "ressort", "moteur")}
    attendues |= {f"panneau.{n}" for n in ("arbre", "inspecteur", "analyse", "proprietes", "etude", "validation", "courbes", "resultats", "journal")}
    attendues |= {f"menu.{n}" for n in ("fichier", "edition", "affichage", "modele", "etude", "aide")}
    attendues |= {f"affichage.{c}" for c in ("grille", "aimantation", "noms_points", "noms_liaisons", "centres_gravite")}
    assert sorted(attendues - set(FR)) == []


def test_codes_d_erreur_tous_traduits():
    """Tout code émis par le lecteur de fichiers, le modèle et le calcul a son message."""
    sources = {
        "fichier.diag": (RACINE / "sikax" / "fichiers" / "lecture.py", r'rapport\.(?:erreur|avertissement|info)\(\s*"(\w+)"'),
        "calcul.message": (RACINE / "sikax" / "calcul", r'ajouter_message\(\s*"\w+",\s*"(\w+)"'),
        "calcul.erreur": (RACINE / "sikax", r'ErreurCalcul\(\s*"(\w+)"'),
        "fichier.erreur": (RACINE / "sikax" / "fichiers", r'Erreur(?:Lecture|Ecriture)\(\s*"(\w+)"'),
        "modele.probleme": (RACINE / "sikax" / "modele" / "mecanisme.py", r'signaler\(\s*"(\w+)"'),
        "topologie.avertissement": (RACINE / "sikax" / "calcul" / "topologie.py", r'avertissements\.append\(\("(\w+)"'),
    }
    manquantes = []
    for prefixe, (chemin, motif) in sources.items():
        fichiers = [chemin] if chemin.is_file() else list(chemin.rglob("*.py"))
        codes = set()
        for fichier in fichiers:
            codes |= set(re.findall(motif, fichier.read_text(encoding="utf-8")))
        assert codes, prefixe
        manquantes += [f"{prefixe}.{c}" for c in sorted(codes) if f"{prefixe}.{c}" not in FR]
    # codes construits dynamiquement dans le lecteur
    manquantes += [f"fichier.diag.{c}" for c in ("liaison_rejetee", "liaison_inconnue", "cle_en_double", "fichier_migre", "encodage_inhabituel") if f"fichier.diag.{c}" not in FR]
    assert manquantes == []


def test_repli_sur_le_francais_et_cle_inconnue(tmp_path):
    (tmp_path / "fr.json").write_text('{"_meta": {"langue": "Français"}, "a": {"b": "Bonjour {nom}", "c": "Seulement en français"}}', encoding="utf-8")
    (tmp_path / "xx.json").write_text('{"_meta": {"langue": "Test"}, "a": {"b": "Hello {nom}"}}', encoding="utf-8")
    (tmp_path / "casse.json").write_text("{ pas du json", encoding="utf-8")
    t = Traducteur(tmp_path)
    assert t.charger("xx") and t.langue == "xx"
    assert t.tr("a.b", nom="Ada") == "Hello Ada"
    assert t.tr("a.c") == "Seulement en français"
    assert t.tr("a.inconnue") == "a.inconnue" and t.cles_manquantes == {"a.inconnue"}
    assert t.tr("a.b") == "Hello {nom}"  # paramètre oublié : pas d'exception
    assert not t.charger("zz") and t.langue == "fr"
    assert not t.charger("casse") and t.tr("a.b", nom="x") == "Bonjour x"
    assert set(t.langues_disponibles()) == {"fr", "xx"}


def test_abonnement_au_changement_de_langue():
    appels = []
    rappel = lambda: appels.append(traducteur.langue)  # noqa: E731
    traducteur.abonner(rappel)
    try:
        traducteur.charger("en")
        assert tr("action.ouvrir") == "&Open…"
        traducteur.charger("fr")
        assert tr("action.ouvrir") == "&Ouvrir…"
    finally:
        traducteur.desabonner(rappel)
        traducteur.charger("fr")
    assert appels == ["en", "fr"]


def test_synonymes_du_lecteur_pointent_vers_des_types_reels():
    assert set(lecture.SYNONYMES_LIAISON.values()) == set(TYPES_LIAISON)
    assert set(lecture.SYNONYMES_LOI.values()) == set(LOIS)
    assert set(lecture.SYNONYMES_ETUDE.values()) == set(TYPES_ETUDE)


def test_erreurs_et_messages_de_calcul_mis_en_phrases():
    """Chaque erreur ou message réellement produit par le moteur donne une phrase complète."""
    import math

    from sikax.calcul import ErreurCalcul, lancer_etude, regler_liaison
    from sikax.i18n import texte_erreur_calcul, texte_message_calcul
    from sikax.modele import LoiMouvement, Mecanisme, bibliotheque as B
    from sikax.modele.solide import ID_BATI

    def sans_solide():
        return Mecanisme()

    def non_pilote():
        m = B.double_pendule()
        m.etude.type = "cinematique"
        return m

    def point_mort():
        m = B.bielle_manivelle()
        m.supprimer_moteur("M1")
        m.creer_moteur("L4")
        return m

    def sans_inertie():
        m = B.double_pendule()
        m.solides["S2"].inertie.masse = m.solides["S2"].inertie.jz = 0.0
        return m

    def expression():
        m = B.pendule_simple()
        m.creer_moteur("L1", LoiMouvement("expression", {"expression": "sqrt(0.01 - t)"}))
        m.etude.type = "cinematique"
        return m

    def invalide():
        m = B.pendule_simple()
        m.solides["S1"].inertie.masse = -1.0
        return m

    def impossible():
        m = Mecanisme()
        s = m.creer_barre([(0.0, 0.0), (0.1, 0.0)])
        m.creer_liaison_en("pivot", 0.0, 0.0, ID_BATI, s.id)
        m.creer_liaison("pivot", ID_BATI, m.creer_point(ID_BATI, 0.5, 0.0).id, s.id, "P2")
        return m

    def demesure():
        m = B.pendule_simple()
        m.etude.duree, m.etude.pas = 1e6, 1e-3
        return m

    erreurs = {}
    for construire in (sans_solide, non_pilote, point_mort, sans_inertie, expression, invalide, impossible, demesure):
        with pytest.raises(ErreurCalcul) as info:
            lancer_etude(construire())
        erreurs[info.value.code] = info.value
    assert set(erreurs) == {
        "aucun_solide", "mobilite_non_pilotee", "position_initiale_singuliere", "inertie_insuffisante",
        "expression", "modele_invalide", "assemblage_impossible", "trop_d_instants",
    }

    def arret():
        m = B.bielle_manivelle()
        m.supprimer_moteur("M1")
        regler_liaison(m, "L1", math.radians(60.0))
        m.creer_moteur("L4", LoiMouvement("vitesse_constante", {"vitesse": 0.05}))
        return m

    def quasi_statique():
        m = B.parallelogramme_double()
        m.etude.inertie = False
        return m

    def non_equilibre():
        m = B.pendule_simple(angle=0.0)
        m.etude.type = "statique"
        return m

    def equilibre_libre():
        m = B.pendule_simple(angle=-math.pi / 2)
        m.etude.type = "statique"
        return m

    def echelle():
        m = Mecanisme()
        barre = m.creer_barre([(0.7, 0.0), (0.0, 1.9)])
        barre.inertie = barre.inertie_barres_homogenes(10.0)
        m.creer_liaison_en("ponctuelle", 0.7, 0.0, ID_BATI, barre.id, angle_axe_global=0.0)
        m.creer_liaison_en("ponctuelle", 0.0, 1.9, ID_BATI, barre.id, angle_axe_global=math.pi / 2)
        m.etude.type, m.etude.duree = "dynamique", 0.9
        return m

    def tout_impose():
        m = B.bielle_manivelle()
        m.etude.type, m.etude.duree, m.etude.pas = "dynamique", 0.1, 0.01
        return m

    messages = {}
    for construire in (arret, quasi_statique, non_equilibre, equilibre_libre, echelle, tout_impose):
        for message in lancer_etude(construire()).messages:
            messages[message.code] = message
    assert {"mouvement_impossible", "hyperstatique_norme_minimale", "quasi_statique", "pas_en_equilibre",
            "equilibre_avec_mobilite", "decollement", "aucune_mobilite_libre"} <= set(messages)

    for langue in LANGUES:
        traducteur.charger(langue)
        for texte in [texte_erreur_calcul(e) for e in erreurs.values()] + [texte_message_calcul(m) for m in messages.values()]:
            assert "{" not in texte and len(texte) > 25 and "calcul." not in texte, texte
    traducteur.charger("fr")
    assert "la masse et le moment d'inertie doivent être positifs" in texte_erreur_calcul(erreurs["modele_invalide"])
    assert "2 mobilité(s)" in texte_erreur_calcul(erreurs["mobilite_non_pilotee"])
