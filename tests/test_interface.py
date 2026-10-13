"""Interface graphique, pilotée sans écran : outils, panneaux, fichiers, calcul."""

import json
import math
import re
import time

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox

from sikax.application import creer_application
from sikax.calcul import residu_de_fermeture
from sikax.chemins import dossier_exemples
from sikax.fichiers import ErreurLecture, charger, depuis_json, vers_json
from sikax.i18n import tr, traducteur
from sikax.modele import LoiMouvement, Mecanisme, bibliotheque as B
from sikax.modele.liaisons import Glissiere, Pivot
from sikax.i18n import texte_diagnostic
from sikax.ui.dialogues.diagnostics import DialogueDiagnostics
from sikax.ui.document import Document, Ref
from sikax.ui.fenetre_principale import FenetrePrincipale
from sikax.ui.theme import PALETTES, theme
from sikax.ui.theme.gestionnaire import charger_palette, feuille_de_style
from sikax.ui.widgets.champs import ChampNombre


@pytest.fixture(scope="session")
def application():
    return creer_application([])


def traiter(tours=6):
    for _ in range(tours):
        QApplication.processEvents()


@pytest.fixture
def fenetre(application):
    traducteur.charger("fr")
    traducteur.cles_manquantes.clear()
    theme.appliquer("clair")
    f = FenetrePrincipale(persistant=False)
    f.resize(1400, 900)
    f.show()
    traiter()
    yield f
    f.arreter_calcul()
    f.attendre_calcul()
    f.doc.modifie = False
    f.close()
    traiter()
    assert sorted(traducteur.cles_manquantes) == [], "textes non traduits"


def ecran(vue, x, y):
    return vue.ecran(x, y).toPoint()


def cliquer(vue, x, y, bouton=Qt.LeftButton, modificateur=Qt.NoModifier):
    QTest.mouseClick(vue, bouton, modificateur, ecran(vue, x, y))
    traiter()


def glisser(vue, depart, arrivee, etapes=6):
    a, b = ecran(vue, *depart), ecran(vue, *arrivee)
    QTest.mousePress(vue, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, etapes + 1):
        point = QPoint(round(a.x() + (b.x() - a.x()) * i / etapes), round(a.y() + (b.y() - a.y()) * i / etapes))
        # QTest.mouseMove ne transmet pas l'état des boutons : l'événement est construit à la main
        evenement = QMouseEvent(QEvent.MouseMove, QPointF(point), QPointF(vue.mapToGlobal(point)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(vue, evenement)
    QTest.mouseRelease(vue, Qt.LeftButton, Qt.NoModifier, b)
    traiter()


def calculer(f):
    f.lancer_etude()
    assert f.attendre_calcul()
    traiter(20)
    f.lecteur.arreter()


def saisir(champ, texte):
    champ.setFocus()
    champ.setText(texte)
    champ.setModified(True)
    champ.editingFinished.emit()
    traiter()


def champs_du_panneau(panneau, classe=ChampNombre):
    return panneau._zone.widget().findChildren(classe)


# --------------------------------------------------------------------- thèmes

def test_palettes_des_fichiers_identiques_aux_valeurs_par_defaut():
    for nom, palette in PALETTES.items():
        assert charger_palette(nom) == palette
    assert set(PALETTES["clair"]) == set(PALETTES["sombre"])


def test_feuille_de_style_sans_jeton_oublie():
    for nom in PALETTES:
        style = feuille_de_style(charger_palette(nom), nom)
        assert len(style) > 2000
        assert "{{" not in style and "#FF00FF" not in style
        for chemin in re.findall(r"url\(([^)]+)\)", style):
            assert __import__("os").path.isfile(chemin), chemin


def test_bascule_du_theme(fenetre):
    f = fenetre
    assert not theme.sombre and not f.commandes["theme_sombre"].isChecked()
    clair = f.vue.image(1.0)
    f.commandes["theme_sombre"].trigger()
    traiter()
    assert theme.sombre and theme.hex("canevas") == PALETTES["sombre"]["canevas"]
    assert QApplication.instance().styleSheet().count(PALETTES["sombre"]["fenetre"]) > 0
    sombre = f.vue.image(1.0)
    assert clair.pixelColor(5, 5).lightness() > 200 and sombre.pixelColor(5, 5).lightness() < 40
    f.commandes["theme_sombre"].trigger()
    traiter()
    assert not theme.sombre


# --------------------------------------------------------------------- langue

def test_changement_de_langue(fenetre):
    f = fenetre
    assert f.menus["fichier"].title() == "&Fichier" and f.onglets_droite.tabText(0) == "Propriétés"
    f.changer_langue("en")
    traiter()
    assert f.menus["fichier"].title() == "&File" and f.onglets_droite.tabText(0) == "Properties"
    assert [f.onglets_bas.tabText(i) for i in range(4)] == ["Validation", "Plots", "Forces", "Log"]
    assert f.commandes["lancer"].text() == "Run Study"
    f.doc.nouveau(B.bielle_manivelle())
    f.doc.selectionner(Ref("liaison", "L4"))
    calculer(f)
    assert "Kinematics" in f.journal.textes()[-1]
    f.changer_langue("fr")
    traiter()
    assert f.commandes["lancer"].text() == "Lancer l'étude"


# --------------------------------------------------------------------- dessin

def test_dessiner_un_mecanisme_a_la_souris(fenetre):
    """Bielle-manivelle construite entièrement avec les outils, puis calculée."""
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    m = lambda: doc.mecanisme  # noqa: E731

    f.commandes["outil_point"].trigger()
    cliquer(vue, 0.0, 0.0)  # point du bâti
    assert len(m().bati.points) == 1 and doc.selection == Ref("point", "S0", "P1")

    f.commandes["outil_barre"].trigger()
    cliquer(vue, 0.0, 0.0)
    cliquer(vue, 0.03, 0.04)
    QTest.keyClick(vue, Qt.Key_Return)
    traiter()
    assert sorted(m().solides) == ["S0", "S1"]
    assert [type(l) for l in m().liaisons.values()] == [Pivot]  # pivot automatique avec le bâti
    assert m().solides["S1"].position_globale("P2") == pytest.approx((0.03, 0.04))

    cliquer(vue, 0.03, 0.04)
    cliquer(vue, 0.15, 0.0)
    QTest.mouseDClick(vue, Qt.LeftButton, Qt.NoModifier, ecran(vue, 0.15, 0.0))
    traiter()
    assert sorted(m().solides) == ["S0", "S1", "S2"] and len(m().liaisons) == 2
    assert {m().liaisons["L2"].solide_a, m().liaisons["L2"].solide_b} == {"S1", "S2"}

    f.commandes["outil_glissiere"].trigger()
    cliquer(vue, 0.15, 0.0)  # un seul solide ici : glissière avec le bâti
    glissiere = m().liaisons["L3"]
    assert isinstance(glissiere, Glissiere) and (glissiere.solide_a, glissiere.solide_b) == ("S0", "S2")
    assert glissiere.angle_axe == 0.0

    f.commandes["outil_moteur"].trigger()
    cliquer(vue, 0.0, 0.0)
    assert list(m().moteurs) == ["M1"] and doc.selection == Ref("moteur", "M1")

    f.commandes["outil_force"].trigger()
    glisser(vue, (0.15, 0.0), (0.15 - vue.pixels(80), 0.0))
    force = m().actions["A1"]
    assert (force.solide, force.point) == ("S2", "P2") and force.fx == pytest.approx(-80.0) and force.fy == 0.0

    # manivelle + bielle guidée par le bâti (pivot, pivot, glissière) : 2×3 − 6 = 0, c'est une structure
    assert (f.validation.bilan_plan.mobilite, f.validation.bilan_plan.hyperstatisme) == (0, 0)
    for solide in m().solides_mobiles():
        solide.inertie = solide.inertie_barres_homogenes(1.0)
    m().etude.type = "statique"
    m().supprimer_moteur("M1")
    calculer(f)
    assert doc.resultats is not None and doc.resultats.equilibre


def test_piston_articule_donne_une_mobilite(fenetre):
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    f.commandes["outil_barre"].trigger()
    for sommets in ([(0.0, 0.0), (0.03, 0.04)], [(0.03, 0.04), (0.15, 0.0)], [(0.15, 0.0), (0.19, 0.0)]):
        for x, y in sommets:
            cliquer(vue, x, y)
        QTest.keyClick(vue, Qt.Key_Return)
        traiter()
    assert len(doc.mecanisme.liaisons) == 2  # deux pivots automatiques, aucun avec le bâti encore
    f.commandes["outil_pivot"].trigger()
    cliquer(vue, 0.0, 0.0)  # manivelle – bâti
    f.commandes["outil_glissiere"].trigger()
    cliquer(vue, 0.19, 0.0)  # piston – bâti
    traiter()
    assert (f.validation.bilan_plan.mobilite, f.validation.bilan_plan.hyperstatisme) == (1, 0)
    assert f.validation.bilan_espace.hyperstatisme == 3
    assert "m = 1" in f.etiquette_bilan.text()


def test_axe_de_glissiere_oriente_au_glisser(fenetre):
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    doc.nouveau()
    with doc.modification() as m:
        m.creer_barre([(0.0, 0.0), (0.1, 0.0)])
    traiter()
    f.commandes["outil_glissiere"].trigger()
    glisser(vue, (0.0, 0.0), (vue.pixels(60), vue.pixels(60)))  # tiré à 45°
    liaison = doc.mecanisme.liaisons["L1"]
    assert isinstance(liaison, Glissiere) and liaison.angle_axe == pytest.approx(math.pi / 4)


def test_messages_des_outils(fenetre):
    f, vue = fenetre, fenetre.vue
    f.commandes["outil_pivot"].trigger()
    cliquer(vue, 0.5, 0.5)
    assert f.etiquette_aide.text() == tr("outil.liaison.aucun_point")
    f.commandes["outil_point"].trigger()
    cliquer(vue, 0.0, 0.0)
    f.commandes["outil_pivot"].trigger()
    cliquer(vue, 0.0, 0.0)
    assert f.etiquette_aide.text() == tr("outil.liaison.bati_seul")
    assert not f.doc.mecanisme.liaisons
    f.commandes["outil_moteur"].trigger()
    cliquer(vue, 0.3, 0.3)
    assert f.etiquette_aide.text() == tr("outil.moteur.aucune_liaison")
    QTest.keyClick(vue, Qt.Key_Escape)
    traiter()
    assert vue.outil.nom == "selection" and f.commandes["outil_selection"].isChecked()


# ------------------------------------------------- sélection, édition, annulation

def test_selection_cyclique_et_suppression(fenetre):
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    doc.nouveau(B.quatre_barres())
    traiter()
    vue.ajuster()
    a = doc.mecanisme.point_global("S1", "P2")
    cliquer(vue, *a)
    assert doc.selection == Ref("liaison", "L2")
    cliquer(vue, *a)  # second clic : objet suivant sous le pointeur
    assert doc.selection.genre == "point"
    assert f.arbre.arbre.currentItem().text(0) == "B"
    cliquer(vue, 0.9, 0.9)
    assert doc.selection is None
    doc.selectionner(Ref("liaison", "L2"))
    QTest.keyClick(vue, Qt.Key_Delete)
    traiter()
    assert "L2" not in doc.mecanisme.liaisons and doc.peut_annuler
    f.commandes["annuler"].trigger()
    traiter()
    assert "L2" in doc.mecanisme.liaisons and doc.peut_retablir
    f.commandes["retablir"].trigger()
    assert "L2" not in doc.mecanisme.liaisons


def test_glisser_une_articulation_modifie_la_geometrie(fenetre):
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    doc.nouveau(B.quatre_barres())
    traiter()
    vue.ajuster()
    doc.mecanisme.affichage["aimantation"] = False
    avant = doc.mecanisme.point_global("S1", "P2")
    cible = (avant[0] + 0.02, avant[1] + 0.01)
    glisser(vue, avant, cible)
    m = doc.mecanisme
    # les deux points de l'articulation ont suivi et le mécanisme reste assemblé
    assert m.point_global("S1", "P2") == pytest.approx(m.point_global("S2", "P1"), abs=1e-9)
    assert residu_de_fermeture(m) < 1e-9
    assert math.hypot(m.solides["S1"].points["P2"].x, m.solides["S1"].points["P2"].y) != pytest.approx(0.10, abs=1e-4)
    # un seul pas d'annulation pour tout le glisser
    f.commandes["annuler"].trigger()
    assert doc.mecanisme.point_global("S1", "P2") == pytest.approx(avant)
    assert not doc.peut_annuler


def test_manipuler_deplace_le_mecanisme_sans_le_deformer(fenetre):
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    doc.nouveau(B.quatre_barres())
    traiter()
    vue.ajuster()
    f.commandes["outil_manipuler"].trigger()
    depart = doc.mecanisme.point_global("S1", "P2")
    glisser(vue, depart, (depart[0] - 0.08, depart[1] - 0.02), etapes=12)
    m = doc.mecanisme
    arrivee = m.point_global("S1", "P2")
    assert math.hypot(arrivee[0] - depart[0], arrivee[1] - depart[1]) > 0.03
    assert math.hypot(*arrivee) == pytest.approx(0.10, abs=1e-9)  # la manivelle garde sa longueur
    assert residu_de_fermeture(m) < 1e-9
    assert m == depuis_json(vers_json(m)).mecanisme  # géométrie intacte : seules les poses ont changé
    f.commandes["annuler"].trigger()
    assert doc.mecanisme.point_global("S1", "P2") == pytest.approx(depart)


def test_historique_et_etat_modifie():
    doc = Document()
    assert not doc.modifie and not doc.peut_annuler
    with doc.modification():
        doc.mecanisme.creer_barre([(0.0, 0.0), (1.0, 0.0)])
    for i in range(5):  # saisie continue : une seule étape
        with doc.modification(fusion="deplacement"):
            doc.mecanisme.solides["S1"].pose.x = float(i)
    doc.terminer_fusion()
    with doc.modification(fusion="deplacement"):
        doc.mecanisme.solides["S1"].pose.x = 99.0
    assert doc.modifie
    doc.annuler()
    assert doc.mecanisme.solides["S1"].pose.x == 4.0
    doc.annuler()
    assert doc.mecanisme.solides["S1"].pose.x == 0.0
    doc.annuler()
    assert doc.mecanisme.est_vide() and not doc.peut_annuler
    doc.retablir()
    doc.retablir()
    assert doc.mecanisme.solides["S1"].pose.x == 4.0
    with doc.modification():  # une nouvelle modification efface la suite à rétablir
        doc.mecanisme.titre = "x"
    assert not doc.peut_retablir
    doc.selectionner(Ref("solide", "S1"))
    doc.supprimer(doc.selection)
    assert doc.selection is None and "S1" not in doc.mecanisme.solides


# ------------------------------------------------------------------ propriétés

def test_proprietes_d_un_solide_et_unites(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.pendule_simple(longueur=0.5, masse=1.0))
    doc.selectionner(Ref("solide", "S1"))
    traiter()
    masse = next(c for c in champs_du_panneau(f.proprietes) if c.dimension == "masse")
    assert masse.text() == "1"
    saisir(masse, "2,5")
    assert doc.mecanisme.solides["S1"].inertie.masse == 2.5 and doc.peut_annuler
    saisir(masse, "-3")
    assert masse.property("invalide") is True and doc.mecanisme.solides["S1"].inertie.masse == 2.5
    saisir(masse, "abc")
    assert masse.property("invalide") is True
    # les longueurs sont saisies en mm et stockées en m
    gx = [c for c in champs_du_panneau(f.proprietes) if c.dimension == "longueur"][0]
    assert float(gx.text()) == pytest.approx(doc.mecanisme.solides["S1"].inertie.gx * 1000.0, rel=1e-6)
    saisir(gx, "100")
    assert doc.mecanisme.solides["S1"].inertie.gx == pytest.approx(0.1)
    with doc.modification():
        doc.mecanisme.unites.longueur = "m"
    traiter()
    gx = [c for c in champs_du_panneau(f.proprietes) if c.dimension == "longueur"][0]
    assert float(gx.text()) == pytest.approx(0.1)


def test_proprietes_d_une_liaison(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.bielle_manivelle())
    doc.selectionner(Ref("liaison", "L1"))
    traiter()
    angle = next(c for c in champs_du_panneau(f.proprietes) if c.dimension == "angle")
    saisir(angle, "60")  # régler l'angle de la manivelle déplace tout le mécanisme
    m = doc.mecanisme
    assert m.point_global("S1", "P2") == pytest.approx((0.05 * math.cos(math.radians(60)), 0.05 * math.sin(math.radians(60))), abs=1e-9)
    assert residu_de_fermeture(m) < 1e-9 and m.point_global("S3", "P1")[1] == pytest.approx(0.0, abs=1e-9)
    # changer le modèle spatial met à jour l'analyse dans l'espace
    assert f.validation.bilan_espace.hyperstatisme == 3
    listes = champs_du_panneau(f.proprietes, QComboBox)
    spatial = next(l for l in listes if l.findData("rotule") >= 0)
    spatial.setCurrentIndex(spatial.findData("rotule"))
    spatial.activated.emit(spatial.currentIndex())
    traiter()
    assert doc.mecanisme.liaisons["L1"].modele_spatial == "rotule"
    assert f.validation.bilan_espace.hyperstatisme == 1
    # changer le type de la liaison depuis le panneau
    doc.selectionner(Ref("liaison", "L4"))
    traiter()
    types = next(l for l in champs_du_panneau(f.proprietes, QComboBox) if l.findData("ponctuelle") >= 0)
    types.setCurrentIndex(types.findData("ponctuelle"))
    types.activated.emit(types.currentIndex())
    traiter()
    assert doc.mecanisme.liaisons["L4"].type == "ponctuelle"
    assert f.validation.bilan_plan.mobilite == 2


def test_proprietes_d_un_moteur_et_d_une_force(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.bielle_manivelle())
    doc.selectionner(Ref("moteur", "M1"))
    traiter()
    vitesse = next(c for c in champs_du_panneau(f.proprietes) if c.dimension == "vitesse_angulaire")
    saisir(vitesse, "10")
    assert doc.mecanisme.moteurs["M1"].loi.parametres["vitesse"] == 10.0
    lois = next(l for l in champs_du_panneau(f.proprietes, QComboBox) if l.findData("sinusoidale") >= 0)
    lois.setCurrentIndex(lois.findData("sinusoidale"))
    lois.activated.emit(lois.currentIndex())
    traiter()
    assert doc.mecanisme.moteurs["M1"].loi.type == "sinusoidale"
    assert any(c.dimension == "frequence" for c in champs_du_panneau(f.proprietes))
    with doc.modification() as m:
        force = m.creer_force("S3", "P1", 0.0, -100.0)
    doc.selectionner(Ref("action", force.id))
    traiter()
    fx = next(c for c in champs_du_panneau(f.proprietes) if c.dimension == "force")
    saisir(fx, "50*sin(2*pi*t)")
    assert doc.mecanisme.actions[force.id].fx == "50*sin(2*pi*t)"
    saisir(fx, "50*sin(")
    assert fx.property("invalide") is True and doc.mecanisme.actions[force.id].fx == "50*sin(2*pi*t)"


def test_panneaux_pour_chaque_type_d_objet(fenetre):
    """Aucun panneau ne lève d'erreur ni ne laisse de texte non traduit, dans les deux langues."""
    f, doc = fenetre, fenetre.doc
    m = B.bielle_manivelle()
    m.creer_force("S3", "P1", "10*t", -5.0, repere="local")
    m.creer_couple("S2", 2.0)
    m.creer_ressort("S0", "P1", "S2", "P2", 100.0, 1.0)
    m.creer_moteur("L4")
    doc.nouveau(m)
    references = [None, Ref("solide", "S0"), Ref("solide", "S2"), Ref("point", "S2", "P1"), Ref("point", "S0", "P1")]
    references += [Ref("liaison", l) for l in m.liaisons] + [Ref("action", a) for a in m.actions] + [Ref("moteur", x) for x in m.moteurs]
    for langue in ("fr", "en"):
        f.changer_langue(langue)
        for avec_resultats in (False, True):
            if avec_resultats:
                doc.mecanisme.supprimer_moteur("M2")
                calculer(f)
                assert doc.resultats is not None, f.journal.textes()[-1]
            for ref in references:
                if ref is None or doc.objet(ref) is not None:
                    doc.selectionner(ref)
                    traiter()
            if avec_resultats:
                with doc.modification() as modele:
                    modele.creer_moteur("L4")
        for type_loi in ("trapeze", "expression", "blocage", "uniformement_accelere", "sinusoidale"):
            with doc.modification() as modele:
                modele.moteurs["M1"].loi = LoiMouvement(type_loi)
            doc.selectionner(Ref("moteur", "M1"))
            traiter()
        with doc.modification() as modele:
            modele.moteurs["M1"].loi = LoiMouvement("vitesse_constante", {"vitesse": 6.0})
    f.changer_langue("fr")


# ------------------------------------------------------------- calcul et résultats

def test_etude_cinematique_depuis_la_fenetre(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.bielle_manivelle(angle_initial=math.radians(40)))
    traiter()
    calculer(f)
    resultats = doc.resultats
    assert resultats is not None and resultats.nb_instants == 401
    assert f.lecteur.isVisible() and f.lecteur.curseur.maximum() == 400
    assert f.courbes.cles_tracees() == ["moteur/M1/effort"]
    assert len(f.courbes._courbes) == 1
    assert f.resultats.table.rowCount() == 5  # quatre liaisons et un moteur
    # se déplacer dans le temps met à jour la vue, le tableau et le panneau de propriétés
    doc.selectionner(Ref("liaison", "L2"))
    f.lecteur.curseur.setValue(100)
    traiter()
    assert doc.indice == 100 and doc.temps == pytest.approx(resultats.temps[100])
    assert float(f.resultats.table.item(1, 3).text()) == pytest.approx(resultats.valeur("liaison/L2/X", 100), rel=1e-4)
    assert doc.pose("S1")[2] == pytest.approx(resultats.valeur("solide/S1/angle", 100))
    # tracer d'autres grandeurs, changer d'abscisse
    f.courbes.cocher(["point/S3/P1/x", "point/S3/P1/vx"])
    assert len(f.courbes._courbes) == 2
    f.courbes.definir_abscisse("liaison/L1/angle")
    x, _ = f.courbes._courbes["point/S3/P1/x"].getData()
    assert x[-1] == pytest.approx(math.degrees(resultats.valeur("liaison/L1/angle")))  # affiché en degrés
    f.courbes.definir_abscisse(None)
    # modifier le modèle invalide les résultats
    with doc.modification() as m:
        m.solides["S1"].inertie.masse = 3.0
    traiter()
    assert doc.resultats is None and not f.lecteur.isVisible() and f.resultats.table.rowCount() == 0


def test_etude_statique_et_tableau_des_efforts(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.poutre_sur_deux_appuis(1.0, 0.4, 1000.0))
    calculer(f)
    assert doc.resultats.equilibre is True
    table = f.resultats.table
    assert table.rowCount() == 2
    assert float(table.item(0, 4).text()) == pytest.approx(600.0) and float(table.item(1, 4).text()) == pytest.approx(400.0)
    assert not f.lecteur.isVisible()
    assert "terminée" in f.etude.bilan.text()


def test_erreurs_de_calcul_expliquees(fenetre):
    f, doc = fenetre, fenetre.doc
    m = B.double_pendule()
    m.etude.type = "cinematique"
    doc.nouveau(m)
    calculer(f)
    assert doc.resultats is None
    assert "2 mobilité(s)" in f.etude.bilan.text() and f.etude.bilan.property("etat") == "erreur"
    assert f.journal.textes()[-1].startswith("✕")
    doc.nouveau(Mecanisme())
    calculer(f)
    assert "aucun solide mobile" in f.etude.bilan.text()


def test_resultats_ignores_si_le_modele_change_pendant_le_calcul(fenetre):
    f, doc = fenetre, fenetre.doc
    m = B.double_pendule()
    m.etude.duree = 4.0
    doc.nouveau(m)
    f.lancer_etude()
    with doc.modification() as modele:
        modele.titre = "modifié pendant le calcul"
    assert f.attendre_calcul()
    traiter(20)
    assert doc.resultats is None
    assert tr("etude.modele_modifie") in f.journal.textes()[-1]


def test_arret_du_calcul(fenetre):
    f, doc = fenetre, fenetre.doc
    m = B.double_pendule()
    m.etude.duree, m.etude.pas = 150.0, 0.001  # assez long pour être interrompu en route
    doc.nouveau(m)
    f.lancer_etude()
    traiter()
    assert not f.commandes["lancer"].isEnabled() and f.commandes["arreter"].isEnabled()
    debut = time.time()
    f.arreter_calcul()
    assert f.attendre_calcul(20000)
    traiter(20)
    assert time.time() - debut < 15 and doc.resultats is None
    assert f.commandes["lancer"].isEnabled() and tr("etude.interrompu") in f.etude.bilan.text()


def test_position_d_equilibre_et_configuration_adoptee(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.pendule_simple(angle=math.radians(20)))
    f.chercher_equilibre()
    traiter()
    g = doc.mecanisme.solides["S1"].centre_gravite_global()
    assert g[0] == pytest.approx(0.0, abs=1e-5) and g[1] == pytest.approx(-0.25, abs=1e-8)
    f.commandes["annuler"].trigger()
    assert doc.mecanisme.solides["S1"].centre_gravite_global()[1] > 0
    calculer(f)
    doc.definir_indice(150)
    attendu = doc.resultats.pose("S1", 150)
    f.adopter_configuration()
    traiter()
    pose = doc.mecanisme.solides["S1"].pose
    assert (pose.x, pose.y, pose.angle) == pytest.approx(attendu)
    assert doc.resultats is None and residu_de_fermeture(doc.mecanisme) < 1e-9


def test_lecture_animee(fenetre):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.pendule_simple())
    calculer(f)
    doc.definir_indice(0)
    f.lecteur.vitesse.setCurrentIndex(f.lecteur.vitesse.count() - 1)
    f.lecteur.lire()
    assert f.lecteur.en_lecture
    fin = time.time() + 0.4
    while time.time() < fin:
        QApplication.processEvents()
    assert doc.indice > 20
    f.lecteur.basculer()
    assert not f.lecteur.en_lecture


@pytest.mark.parametrize("nom", list(B.EXEMPLES))
def test_chaque_exemple_s_ouvre_et_se_calcule(fenetre, nom):
    f, doc = fenetre, fenetre.doc
    assert f.ouvrir_exemple(str(dossier_exemples() / f"{nom}.sikax"))
    traiter()
    assert doc.chemin is None and not doc.modifie  # ouvert comme nouveau projet
    assert doc.mecanisme == B.EXEMPLES[nom]() or doc.mecanisme.auteur == "Sikax"
    calculer(f)
    assert doc.resultats is not None and doc.resultats.complet, f.journal.textes()[-1]
    for cle in ("reactions", "vitesses", "trajectoires"):
        f.commandes[f"montrer_{cle}"].setChecked(True)
    doc.definir_indice(doc.resultats.nb_instants // 2)
    traiter()
    image = f.vue.image(1.0)
    assert image.width() == f.vue.width() and not image.isNull()


# ------------------------------------------------------------------- fichiers

def test_enregistrer_puis_rouvrir(fenetre, tmp_path):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.quatre_barres())
    with doc.modification() as m:
        m.titre = "Essai d'enregistrement"
    chemin = tmp_path / "essai.sikax"
    assert f._ecrire(str(chemin)) and not doc.modifie and doc.chemin == str(chemin)
    assert "essai.sikax" in f.windowTitle() and "•" not in f.windowTitle()
    with doc.modification() as m:
        m.solides["S1"].nom = "Modifiée"
    assert "•" in f.windowTitle()
    assert f.enregistrer() and (tmp_path / "essai.sikax.bak").exists()
    sauvegarde = doc.mecanisme.copie()
    doc.nouveau()
    assert f.ouvrir(str(chemin))
    assert doc.mecanisme == sauvegarde and doc.chemin == str(chemin) and not doc.modifie
    assert f.journal.textes()[-1].endswith("essai.sikax ouvert.")


def test_ouverture_d_un_fichier_illisible(fenetre, tmp_path, monkeypatch):
    f, doc = fenetre, fenetre.doc
    messages = []
    monkeypatch.setattr("sikax.ui.fenetre_principale.QMessageBox.critical", lambda *a: messages.append(a[2]))
    doc.nouveau(B.pendule_simple())
    avant = doc.mecanisme.copie()
    casse = tmp_path / "casse.sikax"
    casse.write_text('{"format": "sikax", "solides": [', encoding="utf-8")
    assert not f.ouvrir(str(casse))
    assert "erreur de syntaxe ligne 1" in messages[-1]
    autre = tmp_path / "image.sikax"
    autre.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(200))
    assert not f.ouvrir(str(autre))
    assert messages[-1] == tr("fichier.erreur.format_inconnu")
    assert not f.ouvrir(str(tmp_path / "absent.sikax"))
    assert doc.mecanisme == avant  # le projet ouvert n'a pas été touché


def test_ouverture_tolerante_apres_compte_rendu(fenetre, tmp_path, monkeypatch):
    f, doc = fenetre, fenetre.doc
    donnees = json.loads(vers_json(B.bielle_manivelle()))
    donnees["liaisons"][1]["type"] = "engrenage"
    donnees["liaisons"][2]["point_b"] = "P42"
    chemin = tmp_path / "partiel.sikax"
    chemin.write_text(json.dumps(donnees), encoding="utf-8")
    with pytest.raises(ErreurLecture) as info:
        charger(str(chemin))
    dialogue = DialogueDiagnostics(info.value.rapport, "partiel.sikax", proposer_ouverture=True)
    textes = [texte_diagnostic(d) for d in info.value.rapport.erreurs]
    assert textes[0].startswith("liaisons[1] (L2) : type de liaison inconnu « engrenage »")
    assert "le point « P42 » n'existe pas dans le solide « S3 »" in textes[1]
    dialogue.close()

    monkeypatch.setattr(DialogueDiagnostics, "exec", lambda self: DialogueDiagnostics.Rejected)
    assert not f.ouvrir(str(chemin))
    monkeypatch.setattr(DialogueDiagnostics, "exec", lambda self: DialogueDiagnostics.Accepted)
    assert f.ouvrir(str(chemin))
    assert sorted(doc.mecanisme.liaisons) == ["L1", "L4"] and doc.modifie
    assert sum(t.startswith("✕") for t in f.journal.textes()) == 2


def test_exports(fenetre, tmp_path):
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.bielle_manivelle())
    traiter()
    assert f.exporter_image(str(tmp_path / "schema.png"))
    image = QImage(str(tmp_path / "schema.png"))
    assert image.width() == 3 * f.vue.width() and image.height() == 3 * f.vue.height()
    assert f.exporter_image(str(tmp_path / "schema.svg"))
    assert (tmp_path / "schema.svg").read_text(encoding="utf-8").lstrip().startswith("<?xml")
    assert not f.exporter_resultats([], str(tmp_path / "rien.csv"))  # pas encore de résultats
    calculer(f)
    assert f.exporter_resultats(["moteur/M1/effort", "point/S3/P1/x"], str(tmp_path / "courbes.csv"))
    lignes = (tmp_path / "courbes.csv").read_text(encoding="utf-8-sig").splitlines()
    assert lignes[0] == "t (s);Moteur manivelle · Effort (N·m);C (Piston) · Position x (mm)"
    assert len(lignes) == 402
    t, effort, x = lignes[51].split(";")
    assert float(t.replace(",", ".")) == pytest.approx(doc.resultats.temps[50])
    assert float(effort.replace(",", ".")) == pytest.approx(doc.resultats.valeur("moteur/M1/effort", 50))
    assert float(x.replace(",", ".")) == pytest.approx(1000.0 * doc.resultats.valeur("point/S3/P1/x", 50))
    assert f.exporter_resultats([], str(tmp_path / "tout.csv"))
    assert len((tmp_path / "tout.csv").read_text(encoding="utf-8-sig").splitlines()[0].split(";")) == len(doc.resultats.canaux) + 1


def test_fermeture_avec_modifications_non_enregistrees(fenetre, monkeypatch):
    f, doc = fenetre, fenetre.doc
    with doc.modification() as m:
        m.titre = "à enregistrer"
    reponses = iter([False, True])
    monkeypatch.setattr(f, "_confirmer_abandon", lambda: next(reponses))
    f.close()
    assert f.isVisible()  # l'utilisateur a annulé
    f.close()
    assert not f.isVisible()
    doc.modifie = False


def test_vue_zoom_et_cadrage(fenetre):
    vue, doc = fenetre.vue, fenetre.doc
    doc.nouveau(B.quatre_barres())
    traiter()
    vue.ajuster()
    for solide in doc.mecanisme.solides.values():
        for point_id in solide.points:
            p = vue.ecran(*solide.position_globale(point_id))
            assert 0 < p.x() < vue.width() and 0 < p.y() < vue.height()
    centre = QPointF(200.0, 150.0)
    avant = vue.monde(centre)
    vue.zoomer(2.0, centre)
    assert vue.monde(centre) == pytest.approx(avant)  # le point sous le pointeur ne bouge pas
    x, y = 0.0123, -0.0456
    assert vue.monde(vue.ecran(x, y)) == pytest.approx((x, y))
    assert vue.aimanter(0.0101, 0.0199) == pytest.approx((0.01, 0.02))  # grille de 10 mm
    b = doc.mecanisme.point_global("S1", "P2")
    assert vue.aimanter(b[0] + vue.pixels(4), b[1]) == pytest.approx(b)  # un point existant l'emporte


def test_modification_refusee_ne_laisse_aucune_trace():
    """Une opération qui échoue ne modifie ni le modèle ni l'historique."""
    doc = Document()
    doc.nouveau(B.pendule_simple())
    avant = doc.mecanisme.copie()
    with pytest.raises(ValueError):
        with doc.modification() as m:
            m.solides["S1"].nom = "changé avant l'échec"
            m.creer_liaison("pivot", "S1", "P1", "S1", "P2")  # refusé : même solide
    assert doc.mecanisme == avant and not doc.peut_annuler and not doc.modifie


def test_suppression_de_l_objet_selectionne_avec_resultats(fenetre):
    """Supprimer l'objet sélectionné pendant l'affichage de résultats ne provoque aucune erreur."""
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.bielle_manivelle())
    calculer(f)
    for ref in (Ref("moteur", "M1"), Ref("liaison", "L3"), Ref("point", "S2", "P1"), Ref("solide", "S3")):
        doc.selectionner(ref)
        traiter()
        assert doc.supprimer(ref)
        traiter()
        assert doc.selection is None and doc.resultats is None
    while doc.peut_annuler:
        f.commandes["annuler"].trigger()
        traiter()
    assert doc.mecanisme == B.bielle_manivelle()


def test_choix_de_la_paire_quand_trois_solides_partagent_un_point(fenetre, monkeypatch):
    """Au point C de la bielle-manivelle se rejoignent bâti, bielle et piston : un menu propose les paires."""
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    doc.nouveau(B.bielle_manivelle(angle_initial=math.radians(40)))
    with doc.modification() as m:
        m.supprimer_liaison("L3")  # bielle et piston ne sont plus articulés
    traiter()
    vue.ajuster()
    propositions = []

    def choisir(paires, _position):
        propositions.extend(paires)
        return ("S2", "S3")

    monkeypatch.setattr(vue.outils["pivot"], "choisir_paire", choisir)
    f.commandes["outil_pivot"].trigger()
    cliquer(vue, *doc.mecanisme.point_global("S3", "P1"))
    assert sorted(propositions) == [("S0", "S2"), ("S0", "S3"), ("S2", "S3")]  # le bâti toujours en A
    nouvelle = doc.mecanisme.liaisons[doc.selection.id]
    assert (nouvelle.solide_a, nouvelle.solide_b, nouvelle.type) == ("S2", "S3", "pivot")
    assert f.validation.bilan_plan.mobilite == 1


@pytest.mark.parametrize("graine", range(8))
def test_utilisation_aleatoire_sans_erreur(fenetre, graine, monkeypatch):
    """Suite d'actions tirées au hasard : jamais d'exception, le modèle reste cohérent."""
    import random

    rng = random.Random(graine)
    # le menu de choix d'une paire de solides attendrait une réponse : on prend la première
    for outil in fenetre.vue.outils.values():
        if hasattr(outil, "choisir_paire"):
            monkeypatch.setattr(outil, "choisir_paire", lambda paires, _position: paires[0])
    f, vue, doc = fenetre, fenetre.vue, fenetre.doc
    if graine % 2:
        doc.nouveau(B.EXEMPLES[rng.choice(list(B.EXEMPLES))]())
        traiter()
        vue.ajuster()
    outils = ["selection", "manipuler", "barre", "point", "pivot", "glissiere", "encastrement", "ponctuelle", "force", "couple", "ressort", "moteur"]

    def position():
        """Tantôt un point existant, tantôt un endroit quelconque de la vue."""
        points = [(s.id, p) for s in doc.mecanisme.solides.values() for p in s.points]
        if points and rng.random() < 0.7:
            solide_id, point_id = rng.choice(points)
            return doc.position(solide_id, point_id)
        return vue.monde(QPointF(rng.uniform(20, vue.width() - 20), rng.uniform(20, vue.height() - 20)))

    def dessiner_barre():
        f.commandes["outil_barre"].trigger()
        for _ in range(rng.randint(2, 4)):
            cliquer(vue, *position())
        QTest.keyClick(vue, Qt.Key_Return)

    if not graine % 2:  # départ d'une page blanche : quelques solides pour commencer
        for _ in range(3):
            dessiner_barre()
    for etape in range(90):
        tirage = rng.random()
        if tirage < 0.08:
            dessiner_barre()
        elif tirage < 0.18:
            f.commandes[f"outil_{rng.choice(outils)}"].trigger()
        elif tirage < 0.50:
            cliquer(vue, *position())
        elif tirage < 0.66:
            glisser(vue, position(), position(), etapes=4)
        elif tirage < 0.72:
            QTest.keyClick(vue, rng.choice([Qt.Key_Return, Qt.Key_Escape, Qt.Key_Delete]))
        elif tirage < 0.80:
            f.commandes[rng.choice(["annuler", "retablir"])].trigger()
        elif tirage < 0.86:
            references = [Ref("solide", s) for s in doc.mecanisme.solides] + [Ref("liaison", l) for l in doc.mecanisme.liaisons]
            references += [Ref("action", a) for a in doc.mecanisme.actions] + [Ref("moteur", x) for x in doc.mecanisme.moteurs]
            doc.selectionner(rng.choice(references))
        elif tirage < 0.90:
            QTest.mouseDClick(vue, Qt.LeftButton, Qt.NoModifier, ecran(vue, *position()))
        elif tirage < 0.94:
            with doc.modification() as m:
                m.etude.type = rng.choice(["statique", "cinematique", "dynamique"])
                m.etude.duree, m.etude.pas = 0.05, 0.01
            calculer(f)
            if doc.resultats is not None and doc.resultats.nb_instants > 1:
                doc.definir_indice(rng.randrange(doc.resultats.nb_instants))
        elif tirage < 0.97:
            f.chercher_equilibre()
        else:
            f.commandes[rng.choice(["ajuster", "zoom_plus", "zoom_moins", "theme_sombre", "montrer_vitesses", "montrer_trajectoires"])].trigger()
        traiter(3)
        assert not doc.mecanisme.erreurs(), (graine, etape, doc.mecanisme.erreurs())
    QTest.keyClick(vue, Qt.Key_Escape)
    relu = depuis_json(vers_json(doc.mecanisme))
    assert not relu.rapport.erreurs
    theme.appliquer("clair")


def test_les_onglets_suivent_le_travail_en_cours(fenetre):
    """Sélectionner montre les propriétés ; un calcul montre les courbes ou le tableau des efforts."""
    f, doc = fenetre, fenetre.doc
    doc.nouveau(B.bielle_manivelle())
    f.montrer("etude")
    assert f.onglets_droite.currentWidget() is f.etude
    doc.selectionner(Ref("liaison", "L1"))
    traiter()
    assert f.onglets_droite.currentWidget() is f.proprietes
    calculer(f)
    assert f.onglets_bas.currentWidget() is f.courbes
    doc.nouveau(B.poutre_sur_deux_appuis())
    calculer(f)
    assert f.onglets_bas.currentWidget() is f.resultats
    # aucune barre d'onglets orpheline ne traîne dans la fenêtre
    from PySide6.QtWidgets import QTabBar

    assert all(isinstance(barre.parent().parent(), type(f.onglets_bas)) or barre.parent() is not f for barre in f.findChildren(QTabBar))


def test_theme_sombre_par_defaut(application):
    """Sans réglage enregistré ni option, l'application démarre en thème sombre."""
    from sikax.ui.theme import THEME_PAR_DEFAUT, GestionnaireTheme

    assert THEME_PAR_DEFAUT == "sombre"
    neuf = GestionnaireTheme()
    assert neuf.sombre and neuf.hex("canevas") == PALETTES["sombre"]["canevas"]
    theme.appliquer("inconnu")  # un nom invalide retombe sur le thème par défaut
    assert theme.sombre
    f = FenetrePrincipale(persistant=False)
    assert f.commandes["theme_sombre"].isChecked()
    f.close()
    theme.appliquer("clair")
