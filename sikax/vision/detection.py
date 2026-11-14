"""Détection automatique des formes de base d'une photo de schéma (OpenCV).

L'objectif est de *pré-générer* le mécanisme : les traits deviennent des
barres, les grands cercles des disques, les petits cercles (symboles
d'articulation) des points où les barres se rejoignent. Le résultat se
corrige ensuite à la main, par-dessus la photo.

Étapes :

1. niveaux de gris, réduction à 1400 pixels au plus, léger flou ;
2. *encre* : seuil adaptatif (une photo est rarement éclairée de façon
   uniforme), puis suppression des petites taches (grain du papier) ;
3. *squelette* de l'encre (amincissement de Zhang et Suen) : chaque trait,
   fin ou épais, devient une ligne d'un pixel en son milieu ;
4. segments par la transformée de Hough probabiliste sur le squelette ;
   les morceaux alignés d'un même trait sont réunis ;
5. cercles : d'abord les *trous* de l'encre bien ronds (un symbole
   d'articulation, une came tracée au trait), puis la transformée de Hough à
   gradient pour les cercles coupés par un trait ou pleins ;
6. tout ce qui est retenu doit reposer sur l'encre ; les morceaux d'arc
   d'un cercle sont écartés ; les extrémités proches sont réunies, et
   accrochées au centre d'un petit cercle voisin : les barres qui se
   touchent partagent un point.

Les coordonnées sont en pixels de l'image d'origine, v compté depuis le haut.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..modele.fond import FondPlan
from ..modele.mecanisme import Mecanisme
from ..modele.solide import ID_BATI

Pixel = Tuple[float, float]

COTE_MAX = 1400
"""Les grandes photos sont réduites à ce côté avant analyse (rapidité, bruit)."""


@dataclass(frozen=True)
class SegmentDetecte:
    a: Pixel
    b: Pixel

    @property
    def longueur(self) -> float:
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])


@dataclass(frozen=True)
class CercleDetecte:
    centre: Pixel
    rayon: float


@dataclass
class Detection:
    largeur: int
    hauteur: int
    segments: List[SegmentDetecte] = field(default_factory=list)
    cercles: List[CercleDetecte] = field(default_factory=list)

    @property
    def diagonale(self) -> float:
        return math.hypot(self.largeur, self.hauteur)

    def seuil_disque(self) -> float:
        """Rayon (px) au-dessus duquel un cercle est un disque plutôt qu'un symbole d'articulation."""
        return 0.035 * self.diagonale

    def disques(self) -> List[CercleDetecte]:
        return [c for c in self.cercles if c.rayon > self.seuil_disque()]

    def articulations(self) -> List[CercleDetecte]:
        return [c for c in self.cercles if c.rayon <= self.seuil_disque()]


def disponible() -> bool:
    """Vrai si OpenCV est installé (la détection est alors proposée)."""
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


def _angle(s: SegmentDetecte) -> float:
    return math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0]) % math.pi


def _fusionner(segments: List[SegmentDetecte], tolerance: float) -> List[SegmentDetecte]:
    """Réunit les segments presque alignés et voisins (les deux bords d'un trait épais)."""
    restants = sorted(segments, key=lambda s: -s.longueur)
    resultat: List[SegmentDetecte] = []
    while restants:
        base = restants.pop(0)
        theta = _angle(base)
        ux, uy = math.cos(theta), math.sin(theta)
        nx, ny = -uy, ux
        groupe = [base]
        gardes = []
        for autre in restants:
            ecart = abs((_angle(autre) - theta + math.pi / 2) % math.pi - math.pi / 2)
            milieu = ((autre.a[0] + autre.b[0]) / 2.0, (autre.a[1] + autre.b[1]) / 2.0)
            distance = abs((milieu[0] - base.a[0]) * nx + (milieu[1] - base.a[1]) * ny)
            projections = [(p[0] - base.a[0]) * ux + (p[1] - base.a[1]) * uy for p in (autre.a, autre.b)]
            recouvre = max(projections) >= -tolerance and min(projections) <= base.longueur + tolerance
            if ecart < math.radians(5.0) and distance < tolerance and recouvre:
                groupe.append(autre)
            else:
                gardes.append(autre)
        restants = gardes
        extremites = [p for s in groupe for p in (s.a, s.b)]
        abscisses = [(p[0] - base.a[0]) * ux + (p[1] - base.a[1]) * uy for p in extremites]
        decalage = sum((p[0] - base.a[0]) * nx + (p[1] - base.a[1]) * ny for p in extremites) / len(extremites)
        debut, fin = min(abscisses), max(abscisses)
        ox, oy = base.a[0] + decalage * nx, base.a[1] + decalage * ny
        resultat.append(SegmentDetecte((ox + debut * ux, oy + debut * uy), (ox + fin * ux, oy + fin * uy)))
    return resultat


def _regrouper_extremites(segments: List[SegmentDetecte], cercles: List[CercleDetecte], tolerance: float, seuil_disque: float) -> List[SegmentDetecte]:
    """Réunit les extrémités voisines ; une extrémité proche d'un petit cercle va en son centre."""
    extremites = [p for s in segments for p in (s.a, s.b)]
    cibles: Dict[int, Pixel] = {}
    petits = [c for c in cercles if c.rayon <= seuil_disque]
    for i, p in enumerate(extremites):
        for c in petits:
            if math.hypot(p[0] - c.centre[0], p[1] - c.centre[1]) <= c.rayon + tolerance:
                cibles[i] = c.centre
                break
    groupes: List[List[int]] = []
    for i, p in enumerate(extremites):
        if i in cibles:
            continue
        for groupe in groupes:
            q = extremites[groupe[0]]
            if math.hypot(p[0] - q[0], p[1] - q[1]) <= tolerance:
                groupe.append(i)
                break
        else:
            groupes.append([i])
    for groupe in groupes:
        cx = sum(extremites[i][0] for i in groupe) / len(groupe)
        cy = sum(extremites[i][1] for i in groupe) / len(groupe)
        for i in groupe:
            cibles[i] = (cx, cy)
    resultat = []
    for k, _ in enumerate(segments):
        a, b = cibles[2 * k], cibles[2 * k + 1]
        if math.hypot(b[0] - a[0], b[1] - a[1]) > tolerance:
            resultat.append(SegmentDetecte(a, b))
    return resultat


def _sans_recouvrement(segments: List[SegmentDetecte], tolerance: float) -> List[SegmentDetecte]:
    """Réunit les morceaux d'un même trait : sur la même droite (à ``tolerance`` près) et qui se recouvrent.

    Les extrémités gardées sont des extrémités réelles (déjà accrochées aux
    articulations), jamais des projections.
    """
    gardes: List[SegmentDetecte] = []
    for s in sorted(segments, key=lambda e: -e.longueur):
        for k, g in enumerate(gardes):
            ux, uy = (g.b[0] - g.a[0]) / g.longueur, (g.b[1] - g.a[1]) / g.longueur
            abscisses = []
            for p in (s.a, s.b):
                dx, dy = p[0] - g.a[0], p[1] - g.a[1]
                if abs(dx * uy - dy * ux) > tolerance:
                    break
                abscisses.append(dx * ux + dy * uy)
            else:
                if max(abscisses) >= -tolerance and min(abscisses) <= g.longueur + tolerance:
                    points = [(0.0, g.a), (g.longueur, g.b), (abscisses[0], s.a), (abscisses[1], s.b)]
                    gardes[k] = SegmentDetecte(min(points)[1], max(points)[1])
                    break
        else:
            gardes.append(s)
    return gardes


def _part_sur_encre(encre: np.ndarray, points: np.ndarray) -> float:
    """Fraction des points (x, y) qui tombent sur l'encre (masque déjà épaissi)."""
    h, w = encre.shape[:2]
    if not points.size:
        return 0.0
    x = np.clip(np.round(points[:, 0]).astype(int), 0, w - 1)
    y = np.clip(np.round(points[:, 1]).astype(int), 0, h - 1)
    return float(np.mean(encre[y, x] > 0))


def _squelette(masque: np.ndarray) -> np.ndarray:
    """Amincissement de Zhang et Suen : chaque trait devient une ligne d'un pixel en son milieu."""
    image = np.pad((masque > 0).astype(np.uint8), 1)
    while True:
        modifie = False
        for passe in (0, 1):
            p1 = image[1:-1, 1:-1]
            p2, p3, p4 = image[:-2, 1:-1], image[:-2, 2:], image[1:-1, 2:]
            p5, p6, p7 = image[2:, 2:], image[2:, 1:-1], image[2:, :-2]
            p8, p9 = image[1:-1, :-2], image[:-2, :-2]
            voisins = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            nombre = sum(v.astype(np.int16) for v in voisins[:8])
            transitions = sum(((voisins[i] == 0) & (voisins[i + 1] == 1)).astype(np.int16) for i in range(8))
            if passe == 0:
                libre = ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
            else:
                libre = ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
            retirer = (p1 == 1) & (nombre >= 2) & (nombre <= 6) & (transitions == 1) & libre
            if retirer.any():
                p1[retirer] = 0
                modifie = True
        if not modifie:
            return image[1:-1, 1:-1]


def _encre(flou: np.ndarray, sensibilite: float, diagonale: float) -> np.ndarray:
    """Masque (0/255) des pixels tracés : nettement plus sombres que leur voisinage."""
    import cv2

    bloc = max(15, int(0.04 * diagonale)) | 1
    ecart = 6.0 + 16.0 * (1.0 - sensibilite)  # plus sensible : traits plus pâles retenus
    encre = cv2.adaptiveThreshold(flou, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, bloc, ecart)
    # Un aplat sombre plus large que le bloc (disque plein, ombre) est évidé par le seuil
    # adaptatif : on rend l'encre aux pixels franchement sombres d'après Otsu.
    otsu, sombre = cv2.threshold(flou, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if float(np.mean(sombre > 0)) < 0.5:  # le fond est clair : Otsu sépare bien l'encre du papier
        encre = cv2.bitwise_or(encre, cv2.erode(sombre, np.ones((3, 3), np.uint8)))
    # grain du papier, poussières : taches trop petites pour être un trait
    nombre, etiquettes, statistiques, _ = cv2.connectedComponentsWithStats(encre, connectivity=8)
    if nombre > 1:
        aire_min = max(12.0, (0.006 * diagonale) ** 2)
        gardees = np.zeros(nombre, dtype=bool)
        gardees[1:] = statistiques[1:, cv2.CC_STAT_AREA] >= aire_min
        encre = np.where(gardees[etiquettes], 255, 0).astype(np.uint8)
    return encre


def _cercles_par_trous(encre: np.ndarray, epaisseur: float, rayon_min: float) -> List[CercleDetecte]:
    """Régions blanches entièrement entourées d'encre et bien rondes : cercles tracés au trait."""
    import cv2

    trouves = cv2.findContours(encre, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    contours, hierarchie = trouves[-2], trouves[-1]
    cercles: List[CercleDetecte] = []
    if hierarchie is None:
        return cercles
    for contour, (_, _, _, parent) in zip(contours, hierarchie[0]):
        if parent < 0 or len(contour) < 8:
            continue  # contour extérieur, ou trou minuscule
        aire = cv2.contourArea(contour)
        perimetre = cv2.arcLength(contour, True)
        (x, y), rayon = cv2.minEnclosingCircle(contour)
        if rayon < rayon_min or perimetre <= 0.0:
            continue
        rondeur = 4.0 * math.pi * aire / (perimetre * perimetre)
        remplissage = aire / (math.pi * rayon * rayon)
        if rondeur > 0.75 and remplissage > 0.75:
            moments = cv2.moments(contour)
            if moments["m00"] > 0.0:
                x, y = moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]
            # le trait du cercle : à mi-épaisseur au-delà du bord du trou
            cercles.append(CercleDetecte((float(x), float(y)), float(math.sqrt(aire / math.pi) + epaisseur / 2.0)))
    return cercles


def _sans_doublons(cercles: List[CercleDetecte]) -> List[CercleDetecte]:
    """Écarte un cercle qui en répète un autre déjà retenu (même centre, même rayon à peu près)."""
    gardes: List[CercleDetecte] = []
    for c in cercles:
        doublon = any(
            math.hypot(c.centre[0] - g.centre[0], c.centre[1] - g.centre[1]) < 0.5 * max(c.rayon, g.rayon)
            and abs(c.rayon - g.rayon) < 0.35 * max(c.rayon, g.rayon)
            for g in gardes
        )
        if not doublon:
            gardes.append(c)
    return gardes


def _cercles_fiables(cercles: List[CercleDetecte], encre: np.ndarray, exigence: float) -> List[CercleDetecte]:
    """Garde les cercles réellement tracés : de l'encre sur la majeure partie du tour."""
    angles = np.linspace(0.0, 2.0 * np.pi, 96, endpoint=False)
    notes = []
    for c in cercles:
        points = np.column_stack([c.centre[0] + c.rayon * np.cos(angles), c.centre[1] + c.rayon * np.sin(angles)])
        notes.append((_part_sur_encre(encre, points), c))
    return [c for note, c in sorted(notes, key=lambda e: -e[0]) if note >= exigence]


def _segments_fiables(segments: List[SegmentDetecte], encre: np.ndarray, exigence: float) -> List[SegmentDetecte]:
    gardes = []
    for s in segments:
        u = np.linspace(0.0, 1.0, max(8, int(s.longueur / 3.0)))
        points = np.column_stack([s.a[0] + u * (s.b[0] - s.a[0]), s.a[1] + u * (s.b[1] - s.a[1])])
        if _part_sur_encre(encre, points) >= exigence:
            gardes.append(s)
    return gardes


def detecter(donnees: bytes, sensibilite: float = 0.4, longueur_min: float = 0.06, avec_cercles: bool = True) -> Detection:
    """Traits et cercles d'une image PNG ou JPEG.

    ``sensibilite`` (0 à 1) : plus elle est haute, plus on détecte de formes
    (et de faux positifs). ``longueur_min`` : longueur minimale d'un trait,
    en fraction de la diagonale de l'image. Lève ``ValueError`` si l'image
    est illisible, ``ImportError`` sans OpenCV.
    """
    import cv2

    if not donnees:
        raise ValueError("image illisible")
    try:
        image = cv2.imdecode(np.frombuffer(donnees, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    except cv2.error as exc:
        raise ValueError("image illisible") from exc
    if image is None or image.size == 0:
        raise ValueError("image illisible")
    hauteur, largeur = image.shape[:2]
    facteur = min(1.0, COTE_MAX / max(hauteur, largeur))
    if facteur < 1.0:
        image = cv2.resize(image, (max(1, int(largeur * facteur)), max(1, int(hauteur * facteur))), interpolation=cv2.INTER_AREA)
    h, w = image.shape[:2]
    diagonale = math.hypot(w, h)
    sensibilite = max(0.0, min(1.0, sensibilite))
    exigence = 0.9 - 0.25 * sensibilite

    flou = cv2.GaussianBlur(image, (5, 5), 0)
    encre = _encre(flou, sensibilite, diagonale)
    squelette = _squelette(encre)
    sur_squelette = cv2.distanceTransform(encre, cv2.DIST_L2, 3)[squelette > 0]
    epaisseur = float(max(1.0, 2.0 * np.median(sur_squelette))) if sur_squelette.size else 2.0
    marge = max(1, int(round(epaisseur / 2.0)))
    encre_large = cv2.dilate(encre, np.ones((2 * marge + 1, 2 * marge + 1), np.uint8))

    seuil = int(max(10, (1.2 - sensibilite) * 0.04 * diagonale))
    # Un trait presque horizontal a un squelette en escalier sur deux rangées : le suivi de
    # Hough y verrait des trous. Une bande de trois pixels autour du squelette les comble.
    bande = cv2.dilate(squelette * 255, np.ones((3, 3), np.uint8))
    lignes = cv2.HoughLinesP(
        bande,
        1,
        math.pi / 360.0,
        threshold=seuil,
        minLineLength=max(8.0, longueur_min * diagonale),
        maxLineGap=max(4.0, 2.0 * epaisseur, 0.01 * diagonale),
    )
    # OpenCV 4 rend un tableau (N, 1, 4), OpenCV 5 un tableau (N, 4) : on aplatit.
    lignes = np.zeros((0, 4)) if lignes is None else np.asarray(lignes, dtype=float).reshape(-1, 4)
    segments = [SegmentDetecte((x1, y1), (x2, y2)) for x1, y1, x2, y2 in lignes.tolist()]

    cercles: List[CercleDetecte] = []
    if avec_cercles:
        rayon_min = max(4.0, 0.008 * diagonale, 1.5 * epaisseur)
        cercles = _cercles_par_trous(encre, epaisseur, rayon_min)
        trouves = cv2.HoughCircles(
            flou,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(8.0, 0.04 * diagonale),
            param1=max(30.0, float(cv2.threshold(flou, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0])),
            param2=18.0 + (1.0 - sensibilite) * 30.0,
            minRadius=int(rayon_min),
            maxRadius=int(0.3 * diagonale),
        )
        if trouves is not None:
            hough = [CercleDetecte((x, y), r) for x, y, r in np.asarray(trouves, dtype=float).reshape(-1, 3).tolist()]
            cercles += _cercles_fiables(hough, encre_large, exigence)
        cercles = _sans_doublons(cercles)

    tolerance = max(0.018 * diagonale, 2.0 * epaisseur)
    segments = _segments_fiables(_fusionner(segments, max(0.012 * diagonale, 1.5 * epaisseur)), encre_large, exigence)
    # morceaux d'arc : courts, et dont le milieu est sur le bord d'un cercle
    segments = [
        s for s in segments
        if not any(
            abs(math.hypot((s.a[0] + s.b[0]) / 2 - c.centre[0], (s.a[1] + s.b[1]) / 2 - c.centre[1]) - c.rayon) < tolerance
            and s.longueur < 1.6 * c.rayon
            for c in cercles
        )
    ]
    seuil_disque = 0.035 * diagonale
    segments = _sans_recouvrement(_regrouper_extremites(segments, cercles, tolerance, seuil_disque), tolerance / 2.0)

    retour = 1.0 / facteur
    return Detection(
        largeur,
        hauteur,
        [SegmentDetecte((s.a[0] * retour, s.a[1] * retour), (s.b[0] * retour, s.b[1] * retour)) for s in segments],
        [CercleDetecte((c.centre[0] * retour, c.centre[1] * retour), c.rayon * retour) for c in cercles],
    )


def creer_solides(
    mecanisme: Mecanisme,
    fond: FondPlan,
    detection: Detection,
    barres: bool = True,
    disques: bool = True,
    pivots: bool = False,
) -> Tuple[int, int, int]:
    """Ajoute au mécanisme les formes détectées. Retourne (barres, disques, pivots) créés.

    Chaque trait devient une barre ; les extrémités réunies à la détection
    portent la même lettre. Avec ``pivots``, chaque petit cercle où aboutissent
    des barres devient une articulation (avec le bâti s'il n'y aboutit qu'une
    barre).
    """
    nb_barres = nb_disques = nb_pivots = 0
    tolerance = 0.02 * detection.diagonale * fond.metres_par_pixel
    if barres:
        for segment in detection.segments:
            mecanisme.creer_barre([fond.vers_modele(*segment.a), fond.vers_modele(*segment.b)])
            nb_barres += 1
    if disques:
        for cercle in detection.disques():
            centre = fond.vers_modele(*cercle.centre)
            mecanisme.creer_disque(centre[0], centre[1], cercle.rayon * fond.metres_par_pixel)
            nb_disques += 1
    if pivots and barres:
        for cercle in detection.articulations():
            x, y = fond.vers_modele(*cercle.centre)
            presents = [s for s, _ in mecanisme.points_en(x, y, tolerance) if not s.bati]
            if len(presents) == 1:
                mecanisme.creer_liaison_en("pivot", x, y, ID_BATI, presents[0].id, rayon=tolerance)
                nb_pivots += 1
            for autre in presents[1:]:
                mecanisme.creer_liaison_en("pivot", x, y, presents[0].id, autre.id, rayon=tolerance)
                nb_pivots += 1
    return nb_barres, nb_disques, nb_pivots
