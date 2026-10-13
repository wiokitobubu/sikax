"""Lecture robuste des projets ``.sikax``.

Principes :

- **Tout signaler.** Le lecteur parcourt le document en entier et consigne
  chaque anomalie avec son emplacement (``liaisons[2] (L3)``), au lieu de
  s'arrêter à la première.
- **Souple sur la forme, strict sur le sens.** Sont acceptés : majuscules et
  accents dans les clés, synonymes courants (``pivot`` / ``articulation`` /
  ``revolute``), nombres écrits en texte (``"1,5"``), angles en degrés
  (clé suffixée ``_deg``), références par nom au lieu de l'identifiant.
  Rien n'est en revanche deviné : une liaison dont un solide est introuvable
  est une erreur.
- **Jamais de chargement partiel silencieux.** En mode strict (par défaut),
  la moindre erreur lève ``ErreurLecture`` avec le rapport complet. En mode
  tolérant, les éléments invalides sont écartés et listés dans le rapport.
- **Vérifier la géométrie.** Après lecture, la fermeture de chaque liaison
  est contrôlée ; si la configuration enregistrée n'est pas assemblée, le
  mécanisme est refermé et l'écart signalé.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..calcul.configuration import refermer
from ..calcul.systeme import SystemeMecanique
from ..geometrie import Pose
from ..modele.actions import REGISTRE_ACTIONS, REPERES_FORCE, Couple, Force, Ressort
from ..modele.etude import Etude
from ..modele.liaisons import REGISTRE_LIAISONS, Liaison
from ..modele.lois import LOIS, LoiMouvement
from ..modele.mecanisme import AFFICHAGE_PAR_DEFAUT, Mecanisme
from ..modele.moteur import Moteur
from ..modele.solide import COULEUR_BATI, COULEURS_SOLIDES, ID_BATI, Inertie, Point, Solide
from ..physique.unites import ANGLES, LONGUEURS, Unites
from ..util.expression import ErreurExpression, compiler
from .diagnostics import ErreurLecture, Rapport
from .format import DIMENSION, FORMAT, TAILLE_MAX, VERSION
from .migrations import migrer

__all__ = ["ResultatLecture", "charger", "depuis_json", "dict_vers_mecanisme"]

# ----------------------------------------------------------------- synonymes

SYNONYMES_CLES = {
    "solids": "solides", "bodies": "solides", "corps": "solides", "pieces": "solides",
    "joints": "liaisons", "links": "liaisons",
    "loads": "actions", "efforts": "actions", "actions_mecaniques": "actions",
    "motors": "moteurs", "drivers": "moteurs",
    "study": "etude", "simulation": "etude",
    "units": "unites", "display": "affichage",
    "name": "nom", "label": "nom",
    "color": "couleur", "colour": "couleur",
    "ground": "bati", "fixed": "bati", "fixe": "bati",
    "body": "solide", "body_a": "solide_a", "body_b": "solide_b",
    "solide1": "solide_a", "solide2": "solide_b", "solide_1": "solide_a", "solide_2": "solide_b",
    "point1": "point_a", "point2": "point_b", "point_1": "point_a", "point_2": "point_b",
    "mass": "masse", "inertia": "inertie", "law": "loi", "joint": "liaison",
    "parameters": "parametres", "params": "parametres",
    "length": "longueur", "duration": "duree", "step": "pas", "gravity": "gravite",
    "active": "actif", "enabled": "actif", "relative": "relatif", "frame": "repere",
    "axe": "angle_axe", "angle_de_l_axe": "angle_axe", "direction": "angle_axe",
    "stiffness": "raideur", "damping": "amortissement", "free_length": "longueur_libre",
    "spatial_model": "modele_spatial", "modele_3d": "modele_spatial",
    "title": "titre", "author": "auteur",
}

SYNONYMES_LIAISON = {
    "pivot": "pivot", "articulation": "pivot", "rotoide": "pivot", "revolute": "pivot",
    "pivot_z": "pivot", "rotule": "pivot", "hinge": "pivot", "pin": "pivot",
    "glissiere": "glissiere", "prismatique": "glissiere", "prismatic": "glissiere",
    "slider": "glissiere", "coulisse": "glissiere", "translation": "glissiere",
    "encastrement": "encastrement", "liaison_fixe": "encastrement", "liaison_complete": "encastrement",
    "complete": "encastrement", "fixed": "encastrement", "weld": "encastrement", "soudure": "encastrement",
    "ponctuelle": "ponctuelle", "appui_simple": "ponctuelle", "appui": "ponctuelle",
    "point_sur_droite": "ponctuelle", "sphere_plan": "ponctuelle", "lineaire_annulaire": "ponctuelle",
    "point_line": "ponctuelle", "roller": "ponctuelle", "contact_ponctuel": "ponctuelle",
}

SYNONYMES_ACTION = {
    "force": "force", "effort": "force", "glisseur": "force",
    "couple": "couple", "moment": "couple", "torque": "couple",
    "ressort": "ressort", "spring": "ressort", "ressort_amortisseur": "ressort", "amortisseur": "ressort",
}

SYNONYMES_LOI = {
    "vitesse_constante": "vitesse_constante", "constant_speed": "vitesse_constante", "uniforme": "vitesse_constante",
    "uniformement_accelere": "uniformement_accelere", "acceleration_constante": "uniformement_accelere",
    "sinusoidale": "sinusoidale", "sinus": "sinusoidale", "sine": "sinusoidale", "harmonique": "sinusoidale",
    "trapeze": "trapeze", "trapezoidale": "trapeze", "trapezoidal": "trapeze",
    "blocage": "blocage", "fixe": "blocage", "bloque": "blocage", "locked": "blocage",
    "expression": "expression", "formule": "expression", "fonction": "expression",
}

SYNONYMES_ETUDE = {
    "statique": "statique", "static": "statique", "pfs": "statique",
    "cinematique": "cinematique", "kinematic": "cinematique", "kinematics": "cinematique",
    "dynamique": "dynamique", "dynamic": "dynamique", "dynamics": "dynamique", "pfd": "dynamique",
}

# Sections qui peuvent être écrites comme un dictionnaire {identifiant: élément}.
SECTIONS_INDEXEES = ("solides", "liaisons", "actions", "moteurs", "points")

# Au-delà, une valeur n'a plus de sens physique et ferait déborder les calculs.
VALEUR_MAX = 1e15

# Espace, espace insécable et espace fine insécable (séparateurs de milliers).
_SANS_ESPACES = {0x20: None, 0xA0: None, 0x202F: None}

VRAI = {"true", "vrai", "oui", "yes", "1", "on"}
FAUX = {"false", "faux", "non", "no", "0", "off"}

_COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _cle(texte: Any) -> str:
    """Forme canonique d'une clé ou d'un mot-clé : minuscules, sans accent, mots joints par « _ »."""
    brut = _sans_accent(str(texte)).lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", brut).strip("_")


class _Rejet(Exception):
    """Élément inutilisable ; le diagnostic a déjà été consigné."""


@dataclass
class ResultatLecture:
    mecanisme: Mecanisme
    rapport: Rapport
    version: int = VERSION
    chemin: str = ""


# ------------------------------------------------------------------ lecteur

class _Lecteur:
    def __init__(self, tolerant: bool) -> None:
        self.tolerant = tolerant
        self.rapport = Rapport()
        self.renommages: Dict[str, str] = {}
        """Identifiants de solides modifiés à la lecture (ancien → nouveau)."""
        self.rejetes: set = set()
        """Éléments écartés, pour ne pas les signaler une seconde fois comme « inconnus »."""

    # -- normalisation des clés --------------------------------------------
    def normaliser(self, valeur: Any, chemin: str = "", cles_libres: bool = False) -> Any:
        """Met les clés sous forme canonique, récursivement.

        ``cles_libres`` signale un dictionnaire indexé par des identifiants
        (``{"L1": {...}}``) : ses clés sont alors conservées telles quelles.
        Les clés commençant par « _ » sont des commentaires et sont ignorées.
        """
        if isinstance(valeur, dict):
            resultat: Dict[str, Any] = {}
            for cle, contenu in valeur.items():
                if str(cle).startswith("_"):
                    continue
                if cles_libres:
                    canonique = str(cle).strip()
                else:
                    canonique = _cle(cle)
                    canonique = SYNONYMES_CLES.get(canonique, canonique)
                sous_chemin = f"{chemin}.{canonique}" if chemin else canonique
                if canonique in resultat:
                    self.rapport.avertissement("cle_en_double", sous_chemin, cle=str(cle))
                indexe = not cles_libres and canonique in SECTIONS_INDEXEES and isinstance(contenu, dict)
                resultat[canonique] = self.normaliser(contenu, sous_chemin, indexe)
            return resultat
        if isinstance(valeur, list):
            return [self.normaliser(v, f"{chemin}[{i}]") for i, v in enumerate(valeur)]
        return valeur

    # -- conversions ---------------------------------------------------------
    @staticmethod
    def vers_nombre(valeur: Any) -> Optional[float]:
        """Nombre fini et de grandeur raisonnable, ou ``None``."""
        if isinstance(valeur, bool):
            return None
        if isinstance(valeur, (int, float)):
            try:
                nombre = float(valeur)
            except OverflowError:
                return None
        elif isinstance(valeur, str):
            texte = valeur.translate(_SANS_ESPACES).strip()
            if texte.count(",") == 1 and "." not in texte:
                texte = texte.replace(",", ".")
            try:
                nombre = float(texte)
            except ValueError:
                return None
        else:
            return None
        return nombre if math.isfinite(nombre) and abs(nombre) <= VALEUR_MAX else None

    def nombre(
        self,
        objet: Dict[str, Any],
        cle: str,
        chemin: str,
        defaut: Optional[float] = 0.0,
        minimum: Optional[float] = None,
        strict: bool = False,
        obligatoire: bool = False,
    ) -> float:
        """Lit un nombre fini. ``strict`` exige une valeur strictement supérieure au minimum."""
        if cle not in objet or objet[cle] is None:
            if obligatoire or defaut is None:
                self.rapport.erreur("champ_manquant", chemin, champ=cle)
                raise _Rejet()
            return defaut
        brut = objet[cle]
        nombre = self.vers_nombre(brut)
        if nombre is None:
            self.rapport.erreur("nombre_invalide", chemin, champ=cle, valeur=repr(brut)[:60])
            raise _Rejet()
        if isinstance(brut, str):
            self.rapport.info("nombre_en_texte", chemin, champ=cle)
        if minimum is not None and (nombre < minimum or (strict and nombre <= minimum)):
            self.rapport.erreur("valeur_hors_bornes", chemin, champ=cle, valeur=nombre, minimum=minimum)
            raise _Rejet()
        return nombre

    def angle(self, objet: Dict[str, Any], cle: str, chemin: str, defaut: Optional[float] = 0.0) -> float:
        """Angle en radians ; accepte la variante ``<cle>_deg`` exprimée en degrés."""
        en_degres = f"{cle}_deg"
        if cle not in objet and en_degres in objet:
            self.rapport.info("angle_en_degres", chemin, champ=en_degres)
            return math.radians(self.nombre(objet, en_degres, chemin, 0.0))
        return self.nombre(objet, cle, chemin, defaut)

    def valeur(self, objet: Dict[str, Any], cle: str, chemin: str, defaut: float = 0.0):
        """Nombre ou expression du temps."""
        if cle not in objet or objet[cle] is None:
            return defaut
        brut = objet[cle]
        nombre = self.vers_nombre(brut)
        if nombre is not None:
            return nombre
        if isinstance(brut, str) and brut.strip():
            try:
                compiler(brut.strip())
            except ErreurExpression as exc:
                self.rapport.erreur("expression_invalide", chemin, champ=cle, message=str(exc))
                raise _Rejet() from exc
            return brut.strip()
        self.rapport.erreur("nombre_invalide", chemin, champ=cle, valeur=repr(brut)[:60])
        raise _Rejet()

    def texte(self, objet: Dict[str, Any], cle: str, chemin: str, defaut: str = "") -> str:
        if cle not in objet or objet[cle] is None:
            return defaut
        brut = objet[cle]
        if isinstance(brut, bool) or isinstance(brut, (dict, list)):
            self.rapport.avertissement("texte_invalide", chemin, champ=cle)
            return defaut
        return str(brut).strip()

    def booleen(self, objet: Dict[str, Any], cle: str, chemin: str, defaut: bool) -> bool:
        if cle not in objet or objet[cle] is None:
            return defaut
        brut = objet[cle]
        if isinstance(brut, bool):
            return brut
        if isinstance(brut, (int, float)) and brut in (0, 1):
            return bool(brut)
        if isinstance(brut, str) and brut.strip().lower() in VRAI | FAUX:
            return brut.strip().lower() in VRAI
        self.rapport.avertissement("booleen_invalide", chemin, champ=cle, valeur=repr(brut)[:60])
        return defaut

    def liste(self, objet: Dict[str, Any], cle: str) -> List[Any]:
        """Section du document, sous forme de liste d'éléments."""
        brut = objet.get(cle)
        if brut is None:
            return []
        if isinstance(brut, list):
            return brut
        if isinstance(brut, dict):
            # forme {identifiant: {...}} : l'identifiant est reporté dans chaque élément
            elements = []
            for identifiant, contenu in brut.items():
                if isinstance(contenu, dict):
                    contenu = dict(contenu)
                    contenu.setdefault("id", identifiant)
                elements.append(contenu)
            self.rapport.info("section_en_dictionnaire", cle)
            return elements
        self.rapport.erreur("section_invalide", cle)
        return []

    @staticmethod
    def identifiant(brut: Any, prefixe: str) -> str:
        """Identifiant sous forme de texte ; un entier ``3`` devient ``<prefixe>3``."""
        if isinstance(brut, bool) or brut is None:
            return ""
        if isinstance(brut, int):
            return f"{prefixe}{brut}"
        if isinstance(brut, float) and brut.is_integer():
            return f"{prefixe}{int(brut)}"
        return str(brut).strip()

    def cles_inconnues(self, objet: Dict[str, Any], connues: Tuple[str, ...], chemin: str) -> None:
        for cle in objet:
            if cle not in connues and not cle.startswith("_"):
                self.rapport.avertissement("cle_inconnue", chemin, cle=cle)


# --------------------------------------------------------------- les sections

CLES_RACINE = (
    "format", "version", "application", "dimension", "meta", "unites", "solides",
    "liaisons", "actions", "moteurs", "etude", "affichage", "titre", "auteur", "description",
)


def _lire_entete(lecteur: _Lecteur, donnees: Dict[str, Any]) -> int:
    rapport = lecteur.rapport
    marque = donnees.get("format")
    if marque is None:
        if "solides" not in donnees:
            raise ErreurLecture("format_inconnu", rapport)
        rapport.avertissement("format_absent")
    elif _cle(marque) != FORMAT:
        raise ErreurLecture("format_inconnu", rapport, format=str(marque)[:40])

    version = VERSION
    if "version" in donnees:
        lue = lecteur.vers_nombre(donnees["version"])
        if lue is None or lue < 1 or int(lue) != lue:
            rapport.avertissement("version_invalide", "version", valeur=repr(donnees["version"])[:40])
        else:
            version = int(lue)
    else:
        rapport.avertissement("version_absente")
    if version > VERSION:
        rapport.avertissement("version_plus_recente", "version", version=version, geree=VERSION)

    if "dimension" in donnees:
        dimension = lecteur.vers_nombre(donnees["dimension"])
        if dimension != DIMENSION:
            raise ErreurLecture("dimension_non_geree", rapport, dimension=str(donnees["dimension"])[:20])
    return version


def _lire_meta(lecteur: _Lecteur, donnees: Dict[str, Any], mecanisme: Mecanisme) -> None:
    meta = donnees.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    for champ in ("titre", "auteur", "description"):
        source = meta if champ in meta else donnees
        setattr(mecanisme, champ, lecteur.texte(source, champ, "meta", ""))

    unites = donnees.get("unites")
    if isinstance(unites, dict):
        longueur = _cle(lecteur.texte(unites, "longueur", "unites", "mm"))
        angle = _cle(lecteur.texte(unites, "angle", "unites", "deg"))
        angle = {"degre": "deg", "degres": "deg", "degree": "deg", "radian": "rad", "radians": "rad"}.get(angle, angle)
        if longueur not in LONGUEURS:
            lecteur.rapport.avertissement("unite_inconnue", "unites.longueur", valeur=longueur)
            longueur = "mm"
        if angle not in ANGLES:
            lecteur.rapport.avertissement("unite_inconnue", "unites.angle", valeur=angle)
            angle = "deg"
        mecanisme.unites = Unites(longueur, angle)
    elif unites is not None:
        lecteur.rapport.avertissement("section_invalide", "unites")

    affichage = donnees.get("affichage")
    if isinstance(affichage, dict):
        for cle, defaut in AFFICHAGE_PAR_DEFAUT.items():
            if cle not in affichage:
                continue
            if isinstance(defaut, bool):
                mecanisme.affichage[cle] = lecteur.booleen(affichage, cle, "affichage", defaut)
            else:
                nombre = lecteur.vers_nombre(affichage[cle])
                if nombre is None or nombre < 0.0:
                    lecteur.rapport.avertissement("valeur_ignoree", "affichage", champ=cle)
                else:
                    mecanisme.affichage[cle] = nombre
        if mecanisme.affichage["pas_grille"] <= 0.0:
            mecanisme.affichage["pas_grille"] = AFFICHAGE_PAR_DEFAUT["pas_grille"]


def _lire_etude(lecteur: _Lecteur, donnees: Dict[str, Any], mecanisme: Mecanisme) -> None:
    brut = donnees.get("etude")
    if brut is None:
        return
    if not isinstance(brut, dict):
        lecteur.rapport.avertissement("section_invalide", "etude")
        return
    rapport = lecteur.rapport
    etude = Etude()
    nature = SYNONYMES_ETUDE.get(_cle(lecteur.texte(brut, "type", "etude", etude.type)))
    if nature is None:
        rapport.avertissement("type_etude_inconnu", "etude", valeur=str(brut.get("type"))[:40])
    else:
        etude.type = nature

    def positif(cle: str, defaut: float) -> float:
        if cle not in brut:
            return defaut
        nombre = lecteur.vers_nombre(brut[cle])
        if nombre is None or nombre <= 0.0:
            rapport.avertissement("valeur_ignoree", "etude", champ=cle)
            return defaut
        return nombre

    etude.duree = positif("duree", etude.duree)
    etude.pas = positif("pas", etude.pas)
    etude.tolerance = positif("tolerance", etude.tolerance)
    etude.precision = positif("precision", etude.precision)
    etude.pesanteur = lecteur.booleen(brut, "pesanteur", "etude", etude.pesanteur)
    etude.inertie = lecteur.booleen(brut, "inertie", "etude", etude.inertie)
    gravite = brut.get("gravite")
    if isinstance(gravite, list) and len(gravite) == 2:
        gx, gy = lecteur.vers_nombre(gravite[0]), lecteur.vers_nombre(gravite[1])
        if gx is None or gy is None:
            rapport.avertissement("valeur_ignoree", "etude", champ="gravite")
        else:
            etude.gx, etude.gy = gx, gy
    elif gravite is not None:
        rapport.avertissement("valeur_ignoree", "etude", champ="gravite")
    mecanisme.etude = etude


def _lire_points(lecteur: _Lecteur, brut: Any, chemin: str) -> Dict[str, Point]:
    points: Dict[str, Point] = {}
    if brut is None:
        return points
    if isinstance(brut, dict):
        elements = []
        for identifiant, contenu in brut.items():
            if isinstance(contenu, dict):
                contenu = dict(contenu)
                contenu.setdefault("id", identifiant)
            elif isinstance(contenu, list):
                contenu = {"id": identifiant, "coordonnees": contenu}
            elements.append(contenu)
    elif isinstance(brut, list):
        elements = brut
    else:
        lecteur.rapport.erreur("section_invalide", f"{chemin}.points")
        raise _Rejet()

    for i, element in enumerate(elements):
        lieu = f"{chemin}.points[{i}]"
        if isinstance(element, list):
            element = {"coordonnees": element}
        if not isinstance(element, dict):
            lecteur.rapport.erreur("element_invalide", lieu)
            raise _Rejet()
        pid = lecteur.identifiant(element.get("id"), "P")
        if not pid:
            numero = 1
            while f"P{numero}" in points:
                numero += 1
            pid = f"P{numero}"
        if pid in points:
            lecteur.rapport.erreur("identifiant_en_double", lieu, id=pid)
            raise _Rejet()
        coordonnees = element.get("coordonnees")
        if isinstance(coordonnees, list) and len(coordonnees) == 2 and "x" not in element:
            element = dict(element, x=coordonnees[0], y=coordonnees[1])
        x = lecteur.nombre(element, "x", lieu, None)
        y = lecteur.nombre(element, "y", lieu, None)
        points[pid] = Point(pid, lecteur.texte(element, "nom", lieu, pid) or pid, x, y)
    return points


def _lire_solides(lecteur: _Lecteur, donnees: Dict[str, Any], mecanisme: Mecanisme) -> None:
    rapport = lecteur.rapport
    solides: Dict[str, Solide] = {}
    declares_bati: List[str] = []
    for i, brut in enumerate(lecteur.liste(donnees, "solides")):
        chemin = f"solides[{i}]"
        if not isinstance(brut, dict):
            rapport.erreur("element_invalide", chemin)
            continue
        sid = lecteur.identifiant(brut.get("id"), "S")
        if sid:
            chemin = f"{chemin} ({sid})"
        try:
            if not sid:
                rapport.erreur("identifiant_manquant", chemin)
                raise _Rejet()
            if sid in solides:
                rapport.erreur("identifiant_en_double", chemin, id=sid)
                raise _Rejet()
            est_bati = lecteur.booleen(brut, "bati", chemin, False)
            pose_brute = brut.get("pose") if isinstance(brut.get("pose"), dict) else {}
            if "pose" in brut and not isinstance(brut["pose"], dict):
                rapport.avertissement("valeur_ignoree", chemin, champ="pose")
            pose = Pose(
                lecteur.nombre(pose_brute, "x", f"{chemin}.pose", 0.0),
                lecteur.nombre(pose_brute, "y", f"{chemin}.pose", 0.0),
                lecteur.angle(pose_brute, "angle", f"{chemin}.pose", 0.0),
            )
            points = _lire_points(lecteur, brut.get("points"), chemin)

            segments: List[Tuple[str, str]] = []
            segments_bruts = brut.get("segments")
            if segments_bruts is not None and not isinstance(segments_bruts, list):
                rapport.avertissement("valeur_ignoree", chemin, champ="segments")
                segments_bruts = []
            for j, segment in enumerate(segments_bruts or []):
                valide = isinstance(segment, list) and len(segment) == 2
                a = lecteur.identifiant(segment[0], "P") if valide else ""
                b = lecteur.identifiant(segment[1], "P") if valide else ""
                if not valide or a not in points or b not in points or a == b:
                    rapport.avertissement("segment_ignore", f"{chemin}.segments[{j}]")
                elif (a, b) not in segments and (b, a) not in segments:
                    segments.append((a, b))

            inertie_brute = brut.get("inertie") if isinstance(brut.get("inertie"), dict) else {}
            inertie = Inertie(
                lecteur.nombre(inertie_brute, "masse", f"{chemin}.inertie", 0.0, minimum=0.0),
                lecteur.nombre(inertie_brute, "gx", f"{chemin}.inertie", 0.0),
                lecteur.nombre(inertie_brute, "gy", f"{chemin}.inertie", 0.0),
                lecteur.nombre(inertie_brute, "jz", f"{chemin}.inertie", 0.0, minimum=0.0),
            )
            g = inertie_brute.get("g")
            if isinstance(g, list) and len(g) == 2:
                gx, gy = lecteur.vers_nombre(g[0]), lecteur.vers_nombre(g[1])
                if gx is None or gy is None:
                    rapport.erreur("nombre_invalide", f"{chemin}.inertie", champ="g", valeur=repr(g)[:60])
                    raise _Rejet()
                inertie.gx, inertie.gy = gx, gy

            defaut = COULEUR_BATI if est_bati else COULEURS_SOLIDES[len(solides) % len(COULEURS_SOLIDES)]
            couleur = lecteur.texte(brut, "couleur", chemin, defaut)
            if not _COULEUR.match(couleur):
                rapport.avertissement("couleur_invalide", chemin, valeur=couleur[:20])
                couleur = defaut
            lecteur.cles_inconnues(brut, ("id", "nom", "bati", "couleur", "pose", "points", "segments", "inertie"), chemin)
            solide = Solide(sid, lecteur.texte(brut, "nom", chemin, sid) or sid, est_bati, couleur.upper(), pose, points, segments, inertie)
        except _Rejet:
            if sid:
                lecteur.rejetes.add(("solide", sid))
            continue
        solides[sid] = solide
        if est_bati:
            declares_bati.append(sid)

    # -- le bâti : unique, d'identifiant S0, de pose nulle ------------------------
    if len(declares_bati) > 1:
        rapport.erreur("bati_multiple", "solides", solides=", ".join(declares_bati))
        for sid in declares_bati[1:]:
            solides[sid].bati = False
    bati_id = declares_bati[0] if declares_bati else (ID_BATI if ID_BATI in solides else None)
    renommages: Dict[str, str] = {}
    if bati_id is None:
        rapport.erreur("bati_absent", "solides")
        bati = Solide(ID_BATI, "Bâti", True, COULEUR_BATI)
    else:
        bati = solides.pop(bati_id)
        bati.bati = True
        if bati_id != ID_BATI:
            renommages[bati_id] = ID_BATI
            bati.id = ID_BATI
            rapport.info("bati_renomme", "solides", ancien=bati_id)
            if ID_BATI in solides:  # un autre solide portait déjà « S0 »
                autre = solides.pop(ID_BATI)
                numero = 1
                while f"S{numero}" in solides or f"S{numero}" == ID_BATI:
                    numero += 1
                autre.id = f"S{numero}"
                renommages[ID_BATI] = autre.id
                solides[autre.id] = autre
                rapport.avertissement("solide_renomme", "solides", ancien=ID_BATI, nouveau=autre.id)
        if not bati.pose.est_identite():
            for point in bati.points.values():
                point.x, point.y = bati.pose.vers_global(point.x, point.y)
            bati.inertie.gx, bati.inertie.gy = bati.pose.vers_global(bati.inertie.gx, bati.inertie.gy)
            bati.pose = Pose()
            rapport.info("bati_recale", "solides")
    mecanisme.solides = {ID_BATI: bati, **solides}
    lecteur.renommages = renommages


def _trouver_solide(lecteur: _Lecteur, mecanisme: Mecanisme, objet: Dict[str, Any], cle: str, chemin: str) -> Solide:
    brut = objet.get(cle)
    reference = lecteur.identifiant(brut, "S")
    if not reference:
        lecteur.rapport.erreur("champ_manquant", chemin, champ=cle)
        raise _Rejet()
    if reference in lecteur.renommages:
        return mecanisme.solides[lecteur.renommages[reference]]
    if reference in mecanisme.solides:
        return mecanisme.solides[reference]
    if ("solide", reference) in lecteur.rejetes:
        lecteur.rapport.erreur("solide_rejete", chemin, champ=cle, solide=reference)
        raise _Rejet()
    cible = _cle(reference)
    homonymes = [s for s in mecanisme.solides.values() if _cle(s.nom) == cible]
    if len(homonymes) == 1:
        lecteur.rapport.info("reference_par_nom", chemin, champ=cle, nom=reference)
        return homonymes[0]
    lecteur.rapport.erreur("solide_inconnu", chemin, champ=cle, solide=reference)
    raise _Rejet()


def _trouver_point(lecteur: _Lecteur, solide: Solide, objet: Dict[str, Any], cle: str, chemin: str, obligatoire: bool = True) -> Optional[Point]:
    brut = objet.get(cle)
    reference = lecteur.identifiant(brut, "P")
    if not reference:
        if obligatoire:
            lecteur.rapport.erreur("champ_manquant", chemin, champ=cle)
            raise _Rejet()
        return None
    if reference in solide.points:
        return solide.points[reference]
    homonymes = [p for p in solide.points.values() if p.nom == reference]
    if len(homonymes) == 1:
        lecteur.rapport.info("reference_par_nom", chemin, champ=cle, nom=reference)
        return homonymes[0]
    lecteur.rapport.erreur("point_inconnu", chemin, champ=cle, point=reference, solide=solide.id)
    raise _Rejet()


def _point_a_la_position(lecteur: _Lecteur, solide: Solide, position: Tuple[float, float], rayon: float, chemin: str, nom: str) -> Point:
    """Point du solide situé à la position globale donnée, créé s'il n'existe pas."""
    existant = solide.point_proche(position[0], position[1], rayon)
    if existant is not None:
        return existant
    x, y = solide.pose.vers_local(*position)
    point = solide.ajouter_point(nom, x, y)
    lecteur.rapport.avertissement("point_cree", chemin, solide=solide.id, point=point.id)
    return point


CLES_LIAISON = ("id", "nom", "type", "solide_a", "point_a", "solide_b", "point_b", "modele_spatial", "position")


def _lire_liaisons(lecteur: _Lecteur, donnees: Dict[str, Any], mecanisme: Mecanisme) -> None:
    rapport = lecteur.rapport
    rayon = 1e-6 * mecanisme.longueur_caracteristique()
    for i, brut in enumerate(lecteur.liste(donnees, "liaisons")):
        chemin = f"liaisons[{i}]"
        if not isinstance(brut, dict):
            rapport.erreur("element_invalide", chemin)
            continue
        lid = lecteur.identifiant(brut.get("id"), "L")
        if lid:
            chemin = f"{chemin} ({lid})"
        try:
            if not lid:
                rapport.erreur("identifiant_manquant", chemin)
                raise _Rejet()
            if lid in mecanisme.liaisons:
                rapport.erreur("identifiant_en_double", chemin, id=lid)
                raise _Rejet()
            if "type" not in brut:
                rapport.erreur("champ_manquant", chemin, champ="type")
                raise _Rejet()
            nature = SYNONYMES_LIAISON.get(_cle(brut["type"]))
            if nature is None:
                rapport.erreur("type_liaison_inconnu", chemin, type=str(brut["type"])[:40], connus=", ".join(REGISTRE_LIAISONS))
                raise _Rejet()
            if nature != brut["type"]:
                rapport.info("type_liaison_interprete", chemin, lu=str(brut["type"])[:40], type=nature)
            classe = REGISTRE_LIAISONS[nature]

            solide_a = _trouver_solide(lecteur, mecanisme, brut, "solide_a", chemin)
            solide_b = _trouver_solide(lecteur, mecanisme, brut, "solide_b", chemin)
            if solide_a.id == solide_b.id:
                rapport.erreur("liaison_meme_solide", chemin, solide=solide_a.id)
                raise _Rejet()

            # -- points de liaison : par identifiant, sinon par position ------------
            position = None
            if "position" in brut:
                p = brut["position"]
                if isinstance(p, list) and len(p) == 2 and None not in (lecteur.vers_nombre(p[0]), lecteur.vers_nombre(p[1])):
                    position = (lecteur.vers_nombre(p[0]), lecteur.vers_nombre(p[1]))
                else:
                    rapport.avertissement("valeur_ignoree", chemin, champ="position")
            point_a = _trouver_point(lecteur, solide_a, brut, "point_a", chemin, obligatoire=False)
            point_b = _trouver_point(lecteur, solide_b, brut, "point_b", chemin, obligatoire=False)
            if point_a is None and point_b is None and position is None:
                rapport.erreur("champ_manquant", chemin, champ="point_a")
                raise _Rejet()
            if point_a is None:
                cible = position or solide_b.position_globale(point_b.id)
                point_a = _point_a_la_position(lecteur, solide_a, cible, rayon, chemin, point_b.nom if point_b else mecanisme.prochain_nom_point())
            if point_b is None:
                cible = position or solide_a.position_globale(point_a.id)
                point_b = _point_a_la_position(lecteur, solide_b, cible, rayon, chemin, point_a.nom)

            # -- paramètres propres au type -----------------------------------------
            parametres: Dict[str, Any] = {}
            for champ in classe.CHAMPS:
                lieu = chemin
                if champ.dimension == "angle":
                    defaut: Optional[float] = champ.defaut
                    if champ.nom == "angle_relatif" and "angle_relatif" not in brut and "angle_relatif_deg" not in brut:
                        defaut = solide_b.pose.angle - solide_a.pose.angle
                        rapport.info("orientation_deduite", chemin)
                    parametres[champ.nom] = lecteur.angle(brut, champ.nom, lieu, defaut)
                else:
                    parametres[champ.nom] = lecteur.nombre(brut, champ.nom, lieu, champ.defaut, minimum=champ.minimum)

            modele = _cle(lecteur.texte(brut, "modele_spatial", chemin, ""))
            if modele and modele not in classe.MODELES_SPATIAUX:
                rapport.avertissement("modele_spatial_inconnu", chemin, valeur=modele, defaut=classe.MODELES_SPATIAUX[0])
                modele = ""
            lecteur.cles_inconnues(
                brut,
                CLES_LIAISON + tuple(c.nom for c in classe.CHAMPS) + tuple(f"{c.nom}_deg" for c in classe.CHAMPS if c.dimension == "angle"),
                chemin,
            )
            nom = lecteur.texte(brut, "nom", chemin, lid) or lid
            liaison = classe(lid, nom, solide_a.id, point_a.id, solide_b.id, point_b.id, modele, **parametres)
        except _Rejet:
            if lid:
                lecteur.rejetes.add(("liaison", lid))
            continue
        mecanisme.liaisons[lid] = liaison


def _lire_actions(lecteur: _Lecteur, donnees: Dict[str, Any], mecanisme: Mecanisme) -> None:
    rapport = lecteur.rapport
    for i, brut in enumerate(lecteur.liste(donnees, "actions")):
        chemin = f"actions[{i}]"
        if not isinstance(brut, dict):
            rapport.erreur("element_invalide", chemin)
            continue
        aid = lecteur.identifiant(brut.get("id"), "A")
        if aid:
            chemin = f"{chemin} ({aid})"
        try:
            if not aid:
                rapport.erreur("identifiant_manquant", chemin)
                raise _Rejet()
            if aid in mecanisme.actions:
                rapport.erreur("identifiant_en_double", chemin, id=aid)
                raise _Rejet()
            nature = SYNONYMES_ACTION.get(_cle(brut.get("type", "")))
            if nature is None:
                rapport.erreur("type_action_inconnu", chemin, type=str(brut.get("type"))[:40], connus=", ".join(REGISTRE_ACTIONS))
                raise _Rejet()
            nom = lecteur.texte(brut, "nom", chemin, aid) or aid
            actif = lecteur.booleen(brut, "actif", chemin, True)
            if nature == "force":
                solide = _trouver_solide(lecteur, mecanisme, brut, "solide", chemin)
                point = _trouver_point(lecteur, solide, brut, "point", chemin)
                repere = _cle(lecteur.texte(brut, "repere", chemin, "global"))
                if repere not in REPERES_FORCE:
                    rapport.avertissement("repere_inconnu", chemin, valeur=repere)
                    repere = "global"
                action = Force(
                    aid, nom, actif, solide.id, point.id,
                    lecteur.valeur(brut, "fx", chemin), lecteur.valeur(brut, "fy", chemin), repere,
                )
            elif nature == "couple":
                solide = _trouver_solide(lecteur, mecanisme, brut, "solide", chemin)
                action = Couple(aid, nom, actif, solide.id, lecteur.valeur(brut, "mz", chemin))
            else:
                solide_a = _trouver_solide(lecteur, mecanisme, brut, "solide_a", chemin)
                solide_b = _trouver_solide(lecteur, mecanisme, brut, "solide_b", chemin)
                point_a = _trouver_point(lecteur, solide_a, brut, "point_a", chemin)
                point_b = _trouver_point(lecteur, solide_b, brut, "point_b", chemin)
                action = Ressort(
                    aid, nom, actif, solide_a.id, point_a.id, solide_b.id, point_b.id,
                    lecteur.nombre(brut, "raideur", chemin, 0.0, minimum=0.0),
                    lecteur.nombre(brut, "amortissement", chemin, 0.0, minimum=0.0),
                    lecteur.nombre(brut, "longueur_libre", chemin, 0.0, minimum=0.0),
                )
            lecteur.cles_inconnues(
                brut,
                ("id", "nom", "type", "actif", "solide", "point", "solide_a", "point_a", "solide_b", "point_b", "repere")
                + tuple(c.nom for c in REGISTRE_ACTIONS[nature].CHAMPS),
                chemin,
            )
        except _Rejet:
            continue
        mecanisme.actions[aid] = action


def _lire_moteurs(lecteur: _Lecteur, donnees: Dict[str, Any], mecanisme: Mecanisme) -> None:
    rapport = lecteur.rapport
    pilotees = set()
    for i, brut in enumerate(lecteur.liste(donnees, "moteurs")):
        chemin = f"moteurs[{i}]"
        if not isinstance(brut, dict):
            rapport.erreur("element_invalide", chemin)
            continue
        mid = lecteur.identifiant(brut.get("id"), "M")
        if mid:
            chemin = f"{chemin} ({mid})"
        try:
            if not mid:
                rapport.erreur("identifiant_manquant", chemin)
                raise _Rejet()
            if mid in mecanisme.moteurs:
                rapport.erreur("identifiant_en_double", chemin, id=mid)
                raise _Rejet()
            reference = lecteur.identifiant(brut.get("liaison"), "L")
            liaison: Optional[Liaison] = mecanisme.liaisons.get(reference)
            if liaison is None and reference:
                homonymes = [l for l in mecanisme.liaisons.values() if _cle(l.nom) == _cle(reference)]
                if len(homonymes) == 1:
                    liaison = homonymes[0]
                    rapport.info("reference_par_nom", chemin, champ="liaison", nom=reference)
            if liaison is None:
                code = "liaison_rejetee" if ("liaison", reference) in lecteur.rejetes else "liaison_inconnue"
                rapport.erreur(code, chemin, liaison=reference or "?")
                raise _Rejet()
            if liaison.PILOTAGE is None:
                rapport.erreur("liaison_non_pilotable", chemin, liaison=liaison.id, type=liaison.type)
                raise _Rejet()
            if liaison.id in pilotees:
                rapport.erreur("moteur_en_double", chemin, liaison=liaison.id)
                raise _Rejet()

            loi_brute = brut.get("loi")
            if not isinstance(loi_brute, dict):
                rapport.erreur("champ_manquant", chemin, champ="loi")
                raise _Rejet()
            nature = SYNONYMES_LOI.get(_cle(loi_brute.get("type", "")))
            if nature is None:
                rapport.erreur("loi_inconnue", chemin, type=str(loi_brute.get("type"))[:40], connus=", ".join(LOIS))
                raise _Rejet()
            source = loi_brute.get("parametres") if isinstance(loi_brute.get("parametres"), dict) else loi_brute
            parametres: Dict[str, Any] = {}
            for nom_parametre, role, defaut in LOIS[nature]:
                lieu = f"{chemin}.loi"
                if role == "expression":
                    texte = lecteur.texte(source, nom_parametre, lieu, str(defaut))
                    try:
                        compiler(texte)
                    except ErreurExpression as exc:
                        rapport.erreur("expression_invalide", lieu, champ=nom_parametre, message=str(exc))
                        raise _Rejet() from exc
                    parametres[nom_parametre] = texte
                else:
                    parametres[nom_parametre] = lecteur.nombre(source, nom_parametre, lieu, float(defaut))
            loi = LoiMouvement(nature, parametres)
            try:
                loi.verifier()
            except ValueError as exc:
                rapport.erreur("loi_invalide", f"{chemin}.loi", message=str(exc))
                raise _Rejet() from exc
            moteur = Moteur(
                mid,
                lecteur.texte(brut, "nom", chemin, mid) or mid,
                liaison.id,
                loi,
                lecteur.booleen(brut, "relatif", chemin, True),
                lecteur.booleen(brut, "actif", chemin, True),
            )
            lecteur.cles_inconnues(brut, ("id", "nom", "liaison", "loi", "relatif", "actif"), chemin)
        except _Rejet:
            continue
        pilotees.add(liaison.id)
        mecanisme.moteurs[mid] = moteur


def _controler_fermeture(lecteur: _Lecteur, mecanisme: Mecanisme) -> None:
    """Vérifie que la configuration enregistrée respecte les liaisons, sinon referme."""
    if not mecanisme.liaisons:
        return
    systeme = SystemeMecanique(mecanisme, avec_moteurs=False)
    residus = systeme.phi(systeme.q0, 0.0, False)
    seuil = max(1e-7 * mecanisme.longueur_caracteristique(), 1e-10)
    ouvertes = 0
    for info in systeme.liaisons.values():
        ecart = float(abs(residus[info.lignes]).max()) if residus[info.lignes].size else 0.0
        if ecart > seuil:
            ouvertes += 1
            lecteur.rapport.avertissement("liaison_ouverte", f"liaisons ({info.liaison.id})", ecart=ecart)
    if ouvertes:
        if refermer(mecanisme):
            lecteur.rapport.info("mecanisme_referme", "liaisons", nombre=ouvertes)
        else:
            lecteur.rapport.avertissement("fermeture_impossible", "liaisons", nombre=ouvertes)


# ------------------------------------------------------------------ interface

def dict_vers_mecanisme(donnees: Any, tolerant: bool = False) -> ResultatLecture:
    """Construit un mécanisme à partir du document déjà décodé."""
    lecteur = _Lecteur(tolerant)
    rapport = lecteur.rapport
    if not isinstance(donnees, dict):
        raise ErreurLecture("structure_invalide", rapport)
    donnees = lecteur.normaliser(donnees)
    version = _lire_entete(lecteur, donnees)
    donnees = migrer(donnees, version, rapport)
    lecteur.cles_inconnues(donnees, CLES_RACINE, "")

    mecanisme = Mecanisme()
    _lire_meta(lecteur, donnees, mecanisme)
    _lire_etude(lecteur, donnees, mecanisme)
    _lire_solides(lecteur, donnees, mecanisme)
    _lire_liaisons(lecteur, donnees, mecanisme)
    _lire_actions(lecteur, donnees, mecanisme)
    _lire_moteurs(lecteur, donnees, mecanisme)

    for probleme in mecanisme.verifier():
        if probleme.gravite == "erreur":
            rapport.erreur("modele_incoherent", probleme.objet, probleme=probleme.code)

    if rapport.a_des_erreurs and not tolerant:
        raise ErreurLecture("fichier_invalide", rapport, nombre=len(rapport.erreurs))
    if any(d.code == "modele_incoherent" for d in rapport.erreurs):
        # même en mode tolérant, un modèle incohérent ne peut pas être ouvert
        raise ErreurLecture("fichier_invalide", rapport, nombre=len(rapport.erreurs))
    _controler_fermeture(lecteur, mecanisme)
    return ResultatLecture(mecanisme, rapport, version)


def _refuser_constante(nom: str):
    raise ValueError(f"constante non finie : {nom}")


def depuis_json(texte: str, tolerant: bool = False) -> ResultatLecture:
    """Lit un projet à partir de son texte JSON."""
    if not texte or not texte.strip():
        raise ErreurLecture("fichier_vide")
    premier = len(texte) - len(texte.lstrip())
    doublons: List[str] = []

    def paires(elements):
        resultat = {}
        for cle, valeur in elements:
            if cle in resultat:
                doublons.append(str(cle))
            resultat[cle] = valeur
        return resultat

    try:
        donnees = json.loads(texte, object_pairs_hook=paires, parse_constant=_refuser_constante)
    except json.JSONDecodeError as exc:
        if exc.pos <= premier:  # dès le premier caractère : ce n'est pas du JSON du tout
            raise ErreurLecture("format_inconnu") from exc
        raise ErreurLecture("json_invalide", ligne=exc.lineno, colonne=exc.colno, message=exc.msg) from exc
    except ValueError as exc:
        raise ErreurLecture("nombre_non_fini", message=str(exc)) from exc
    except RecursionError as exc:
        raise ErreurLecture("json_invalide", ligne=0, colonne=0, message="imbrication excessive") from exc
    resultat = dict_vers_mecanisme(donnees, tolerant)
    for cle in doublons:
        resultat.rapport.avertissement("cle_en_double", "", cle=cle)
    return resultat


def _decoder(octets: bytes, rapport: Rapport) -> str:
    if octets.startswith(b"\xef\xbb\xbf"):
        return octets[3:].decode("utf-8")
    if octets.startswith((b"\xff\xfe", b"\xfe\xff")):
        return octets.decode("utf-16")
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        rapport.avertissement("encodage_inhabituel", "", encodage="cp1252")
        return octets.decode("cp1252", errors="replace")


def charger(chemin: str, tolerant: bool = False) -> ResultatLecture:
    """Lit un fichier projet.

    Lève ``ErreurLecture`` si le fichier est illisible ou, en mode strict,
    s'il contient la moindre erreur ; ``exc.rapport`` détaille alors toutes
    les anomalies rencontrées.
    """
    try:
        taille = os.path.getsize(chemin)
        if taille > TAILLE_MAX:
            raise ErreurLecture("fichier_trop_gros", taille=taille)
        with open(chemin, "rb") as fichier:
            octets = fichier.read()
    except FileNotFoundError as exc:
        raise ErreurLecture("fichier_introuvable", chemin=chemin) from exc
    except IsADirectoryError as exc:
        raise ErreurLecture("lecture_impossible", chemin=chemin, message="dossier") from exc
    except OSError as exc:
        raise ErreurLecture("lecture_impossible", chemin=chemin, message=exc.strerror or str(exc)) from exc
    rapport_decodage = Rapport()
    try:
        texte = _decoder(octets, rapport_decodage)
    except UnicodeError as exc:
        raise ErreurLecture("encodage_invalide", chemin=chemin) from exc
    resultat = depuis_json(texte, tolerant)
    resultat.rapport.diagnostics[:0] = rapport_decodage.diagnostics
    resultat.chemin = os.path.abspath(chemin)
    return resultat
