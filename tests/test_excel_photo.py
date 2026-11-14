"""Export Excel des résultats, photo de schéma en fond (étalonnage, fichier) et détection des formes."""

import base64
import json
import math
import os

import numpy as np
import pytest

from sikax.calcul import lancer_etude
from sikax.fichiers import ErreurEcriture, depuis_json, vers_json
from sikax.fichiers import excel
from sikax.fichiers.excel import Graphique, Textes, exporter_excel
from sikax.modele import Mecanisme, bibliotheque as B
from sikax.modele.fond import FondPlan, format_image
from sikax.physique.unites import Unites

openpyxl = pytest.importorskip("openpyxl")
cv2 = pytest.importorskip("cv2")


@pytest.fixture(scope="module")
def resultats():
    m = B.bielle_manivelle()
    m.etude.duree, m.etude.pas = 0.2, 0.01
    return lancer_etude(m)


# ------------------------------------------------------------------ Excel

def test_classeur_valeurs_numeriques_et_unites(resultats, tmp_path):
    chemin = tmp_path / "res.xlsx"
    cles = ["solide/S1/angle", "solide/S3/x", "moteur/M1/effort"]
    textes = Textes(informations=[("Projet", "Bielle")], messages=["un message"])
    graphiques = [Graphique("Position", "mm", ["solide/S3/x"]), Graphique("Couple", "N·m", ["moteur/M1/effort"])]
    lignes = exporter_excel(resultats, str(chemin), cles, Unites("mm", "deg"), {"solide/S3/x": "x piston"}, graphiques, textes)
    assert lignes == resultats.nb_instants == 21
    classeur = openpyxl.load_workbook(chemin)
    assert classeur.sheetnames == ["Résultats", "Graphiques", "Informations"]
    feuille = classeur["Résultats"]
    entetes = [c.value for c in feuille[1]]
    assert entetes[0] == "t (s)" and entetes[2] == "x piston (mm)" and entetes[1].endswith("(°)")
    assert feuille.freeze_panes == "B2"
    for i in range(lignes):
        t, angle, x, effort = (c.value for c in feuille[i + 2])
        assert all(isinstance(v, (int, float)) for v in (t, angle, x, effort))  # de vrais nombres, pas du texte
        assert t == pytest.approx(resultats.temps[i])
        assert angle == pytest.approx(math.degrees(resultats.valeurs("solide/S1/angle")[i]))
        assert x == pytest.approx(1000.0 * resultats.valeurs("solide/S3/x")[i])
        assert effort == pytest.approx(resultats.valeurs("moteur/M1/effort")[i])
    assert len(classeur["Graphiques"]._charts) == 2
    infos = [[c.value for c in ligne] for ligne in classeur["Informations"].iter_rows()]
    assert ["Projet", "Bielle"] in infos and [None, "un message"] in infos


def test_valeurs_non_finies_en_cellules_vides(resultats, tmp_path):
    copie = resultats
    serie = copie.canaux["solide/S1/x"].valeurs
    sauvegarde = serie.copy()
    serie[3], serie[4] = np.nan, np.inf
    try:
        exporter_excel(copie, str(tmp_path / "nan.xlsx"), ["solide/S1/x"])
    finally:
        serie[:] = sauvegarde
    feuille = openpyxl.load_workbook(tmp_path / "nan.xlsx")["Résultats"]
    assert feuille.cell(row=5, column=2).value is None and feuille.cell(row=6, column=2).value is None
    assert isinstance(feuille.cell(row=7, column=2).value, float)


def test_gros_classeur_ecrit_en_flux(resultats, tmp_path, monkeypatch):
    monkeypatch.setattr(excel, "CELLULES_MAX_MISE_EN_FORME", 10)
    lignes = exporter_excel(resultats, str(tmp_path / "flux.xlsx"), None, None, None, [Graphique("x", "m", ["solide/S3/x"])])
    classeur = openpyxl.load_workbook(tmp_path / "flux.xlsx")
    feuille = classeur["Résultats"]
    assert feuille.max_row == lignes + 1 and feuille.max_column == len(resultats.canaux) + 1
    assert len(classeur["Graphiques"]._charts) == 1


def test_ecriture_impossible_sans_fichier_partiel(resultats, tmp_path):
    dossier = tmp_path / "protege"
    dossier.mkdir()
    os.chmod(dossier, 0o500)
    try:
        with pytest.raises(ErreurEcriture):
            exporter_excel(resultats, str(dossier / "res.xlsx"))
        assert list(dossier.iterdir()) == []
    finally:
        os.chmod(dossier, 0o700)


def test_remplacement_d_un_classeur_existant(resultats, tmp_path):
    chemin = tmp_path / "res.xlsx"
    chemin.write_bytes(b"ancien contenu")
    exporter_excel(resultats, str(chemin), ["solide/S1/x"])
    assert openpyxl.load_workbook(chemin)["Résultats"].max_column == 2
    assert [p.name for p in tmp_path.iterdir()] == ["res.xlsx"]  # aucun fichier temporaire oublié


# ------------------------------------------------------------- photo de fond

def image_png(largeur=320, hauteur=200, dessin=None):
    image = np.full((hauteur, largeur, 3), 255, np.uint8)
    if dessin is not None:
        dessin(image)
    ok, donnees = cv2.imencode(".png", image)
    assert ok
    return donnees.tobytes()


def test_formats_reconnus():
    assert format_image(image_png()) == "png"
    ok, jpeg = cv2.imencode(".jpg", np.zeros((8, 8, 3), np.uint8))
    assert format_image(jpeg.tobytes()) == "jpeg"
    assert format_image(b"GIF89a....") is None


@pytest.mark.parametrize("angle", [0.0, 0.4, -2.5])
def test_repere_de_la_photo(angle):
    fond = FondPlan(b"", "png", 400, 300, x=0.1, y=-0.2, largeur=0.8, angle=angle)
    for u, v in [(0, 0), (400, 300), (123.4, 56.7)]:
        assert fond.vers_pixels(*fond.vers_modele(u, v)) == pytest.approx((u, v))
    # coin inférieur gauche de l'image = (x, y) ; haut de l'image à une hauteur de 0,6 m
    assert fond.vers_modele(0, 300) == pytest.approx((0.1, -0.2))
    haut = fond.vers_modele(0, 0)
    assert math.hypot(haut[0] - 0.1, haut[1] + 0.2) == pytest.approx(0.6)


def test_etalonnage_deux_clics_et_une_longueur():
    fond = FondPlan(b"", "png", 1000, 500, largeur=0.5, angle=0.3)
    a, b = fond.vers_modele(100, 250), fond.vers_modele(600, 250)  # 500 px d'écart
    fond.etalonner(a, b, 0.120)  # « ces deux points sont à 120 mm »
    assert fond.vers_modele(100, 250) == pytest.approx(a)  # le premier point ne bouge pas
    a2, b2 = fond.vers_modele(100, 250), fond.vers_modele(600, 250)
    assert math.hypot(b2[0] - a2[0], b2[1] - a2[1]) == pytest.approx(0.120)
    assert fond.metres_par_pixel == pytest.approx(0.120 / 500)
    for longueur in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            fond.etalonner(a, b, longueur)
    with pytest.raises(ValueError):
        fond.etalonner(a, a, 0.1)


def test_photo_enregistree_dans_le_projet():
    m = B.quatre_barres()
    donnees = image_png()
    m.fond = FondPlan(donnees, "png", 320, 200, x=-0.05, y=0.01, largeur=0.3, angle=0.2, opacite=0.6, nom="schema.png")
    texte = vers_json(m, horodatage="h")
    relu = depuis_json(texte)
    assert relu.mecanisme == m and relu.mecanisme.fond.donnees == donnees
    assert not relu.rapport.diagnostics
    assert json.loads(texte)["fond"]["image"] == base64.b64encode(donnees).decode("ascii")


@pytest.mark.parametrize("alteration", [
    lambda f: f.update(image="pas du base64 !"),
    lambda f: f.update(image=base64.b64encode(b"ceci n'est pas une image").decode()),
    lambda f: f.update(largeur=-1.0),
    lambda f: f.pop("image"),
])
def test_photo_illisible_ecartee_sans_perdre_le_projet(alteration):
    m = B.quatre_barres()
    m.fond = FondPlan(image_png(), "png", 320, 200)
    document = json.loads(vers_json(m, horodatage="h"))
    alteration(document["fond"])
    relu = depuis_json(json.dumps(document))
    assert relu.mecanisme.fond is None
    assert len(relu.mecanisme.solides) == len(m.solides)
    assert [d.code for d in relu.rapport.avertissements] == ["fond_ignore"]


def test_synonymes_de_la_photo():
    m = B.quatre_barres()
    m.fond = FondPlan(image_png(), "png", 320, 200, largeur=0.25)
    document = json.loads(vers_json(m, horodatage="h"))
    document["photo"] = document.pop("fond")
    relu = depuis_json(json.dumps(document))
    assert relu.mecanisme.fond is not None and relu.mecanisme.fond.largeur == pytest.approx(0.25)


# ---------------------------------------------------------------- détection

ARTICULATIONS = [(60, 330), (130, 130), (420, 110), (520, 330)]
BARRES = [(ARTICULATIONS[0], ARTICULATIONS[1]), (ARTICULATIONS[1], ARTICULATIONS[2]), (ARTICULATIONS[2], ARTICULATIONS[3])]


def schema(echelle=1.0, photo=False):
    """Quadrilatère dessiné comme dans un cours : barres, pivots (petits cercles blancs), sol hachuré, une came."""
    largeur, hauteur = int(600 * echelle), int(400 * echelle)
    image = np.full((hauteur, largeur, 3), 255, np.uint8)
    encre = (30, 30, 30)

    def p(x, y):
        return int(x * echelle), int(y * echelle)

    def e(n):
        return max(1, int(n * echelle))

    for a, b in BARRES:
        cv2.line(image, p(*a), p(*b), encre, e(5), cv2.LINE_AA)
    cv2.line(image, p(20, 360), p(580, 360), encre, e(3), cv2.LINE_AA)  # sol
    for k in range(20):
        cv2.line(image, p(30 + 28 * k, 362), p(18 + 28 * k, 376), encre, e(2), cv2.LINE_AA)  # hachures
    for centre in ARTICULATIONS:
        cv2.circle(image, p(*centre), int(11 * echelle), (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(image, p(*centre), int(11 * echelle), encre, e(3), cv2.LINE_AA)
    cv2.circle(image, p(300, 280), int(55 * echelle), encre, e(4), cv2.LINE_AA)  # came
    if not photo:
        return cv2.imencode(".png", image)[1].tobytes()
    # photo : éclairage inégal, papier teinté, grain, flou léger, compression JPEG
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:hauteur, 0:largeur]
    claire = image.astype(float) * ((0.65 + 0.35 * xx / largeur) * (0.85 + 0.15 * yy / hauteur))[..., None]
    claire = claire * np.array([0.95, 0.97, 1.0]) + rng.normal(0.0, 9.0, claire.shape)
    claire = cv2.GaussianBlur(np.clip(claire, 0, 255).astype(np.uint8), (3, 3), 0)
    return cv2.imencode(".jpg", claire, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()


def proche(p, q, tolerance):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tolerance


@pytest.mark.parametrize("echelle, photo", [(1.0, False), (1.0, True), (2.5, False), (2.5, True)])
@pytest.mark.parametrize("sensibilite", [0.2, 0.4, 0.7])
def test_detection_d_un_schema_de_cours(echelle, photo, sensibilite):
    from sikax.vision import detecter

    detection = detecter(schema(echelle, photo), sensibilite, 0.06)
    assert (detection.largeur, detection.hauteur) == (int(600 * echelle), int(400 * echelle))
    tolerance = 4.0 * echelle

    def en_pixels(x, y):
        return x * echelle, y * echelle

    (disque,) = detection.disques()
    assert proche(disque.centre, en_pixels(300, 280), tolerance) and disque.rayon == pytest.approx(55 * echelle, abs=tolerance)
    articulations = detection.articulations()
    assert len(articulations) == 4
    for centre in ARTICULATIONS:
        assert any(proche(c.centre, en_pixels(*centre), tolerance) for c in articulations), centre
    # trois barres d'articulation à articulation, et le sol
    assert len(detection.segments) == 4
    for a, b in BARRES:
        a, b = en_pixels(*a), en_pixels(*b)
        assert any(
            (proche(s.a, a, tolerance) and proche(s.b, b, tolerance)) or (proche(s.a, b, tolerance) and proche(s.b, a, tolerance))
            for s in detection.segments
        ), (a, b)


def test_creation_des_solides_a_l_echelle():
    from sikax.vision import creer_solides, detecter

    donnees = schema()
    fond = FondPlan(donnees, "png", 600, 400, largeur=0.6)  # 1 mm par pixel
    detection = detecter(donnees)
    m = Mecanisme()
    barres, disques, pivots = creer_solides(m, fond, detection, pivots=True)
    assert (barres, disques) == (4, 1)
    assert len(m.solides_mobiles()) == 5
    # deux pivots entre barres (en haut), deux pivots avec le bâti (en bas) : quadrilatère articulé
    assert pivots == 4 and len(m.liaisons) == 4
    disque = next(s for s in m.solides.values() if s.cercles)
    (cercle,) = disque.cercles.values()
    assert cercle.rayon == pytest.approx(0.055, abs=0.004)
    assert disque.position_globale(cercle.centre) == pytest.approx((0.300, 0.120), abs=0.004)  # y compté depuis le bas
    assert not m.erreurs()


@pytest.mark.parametrize("donnees", [b"", b"\x89PNG\r\n\x1a\n tronque", b"n'importe quoi"])
def test_image_illisible(donnees):
    from sikax.vision import detecter

    with pytest.raises(ValueError):
        detecter(donnees)


def test_image_vide_sans_forme():
    from sikax.vision import detecter

    detection = detecter(image_png(300, 300))
    assert detection.segments == [] and detection.cercles == []
