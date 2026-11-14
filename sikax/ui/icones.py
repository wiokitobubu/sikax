"""Icônes de l'interface.

Les pictogrammes sont des tracés SVG (grille 24 × 24, trait de 1,8) colorés à
la volée dans la couleur du texte du thème : ils restent lisibles en clair
comme en sombre, et nets sur les écrans à haute densité.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import theme

P = "currentColor"

TRACES: Dict[str, str] = {
    # fichier
    "nouveau": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6M9 15h6"/>',
    "ouvrir": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "enregistrer": '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3"/><path d="M7 21v-7h10v7"/>',
    "exporter": '<path d="M12 15V3"/><path d="m7 8 5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
    "image": '<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13.5" r="3.5"/><path d="M8 7l1.5-3h5L16 7"/>',
    # édition
    "annuler": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "retablir": '<path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "supprimer": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    # outils
    "selection": '<path d="M5 3l14 7-6 2-2 6z"/>',
    "manipuler": '<path d="M12 3v18M3 12h18"/><path d="m9 6 3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
    "barre": '<path d="M7.5 16.5l9-9"/><circle cx="6" cy="18" r="2.3"/><circle cx="18" cy="6" r="2.3"/>',
    "point": f'<circle cx="12" cy="12" r="2.6" fill="{P}"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>',
    "pivot": '<circle cx="12" cy="8.5" r="3.5"/><path d="M9.8 11.4 6 18h12l-3.8-6.6"/><path d="M4 21h16"/>',
    "glissiere": '<path d="M2 16h20"/><rect x="7" y="9" width="10" height="7"/><path d="M5 20l2-3M10 20l2-3M15 20l2-3M20 20l1-2"/>',
    "encastrement": '<path d="M7 4v16"/><path d="M7 12h14"/><path d="M3 8l4-3M3 13l4-3M3 18l4-3M3 22l4-3"/>',
    "ponctuelle": '<path d="M12 4l5 8H7z"/><circle cx="9" cy="15" r="1.7"/><circle cx="15" cy="15" r="1.7"/><path d="M4 19.5h16"/>',
    "force": '<path d="M5 19 19 5"/><path d="M11 5h8v8"/>',
    "couple": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M18 2v4.6h-4.6"/>',
    "ressort": '<path d="M2 12h3l1.5-4 3 8 3-8 3 8L17 12h5"/>',
    "moteur": '<circle cx="12" cy="12" r="8.5"/><path d="M8 16V8.5l4 5 4-5V16"/>',
    "cercle": f'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="1.4" fill="{P}"/><path d="M12 12l5.6-5.6"/>',
    "engrenage": '<path d="M10.6 2.5h2.8l.5 2.6 1.9.8 2.2-1.5 2 2-1.5 2.2.8 1.9 2.6.5v2.8l-2.6.5-.8 1.9 1.5 2.2-2 2-2.2-1.5-1.9.8-.5 2.6h-2.8l-.5-2.6-1.9-.8-2.2 1.5-2-2 1.5-2.2-.8-1.9-2.6-.5v-2.8l2.6-.5.8-1.9-1.5-2.2 2-2 2.2 1.5 1.9-.8z"/><circle cx="12" cy="12" r="3.2"/>',
    "came": f'<circle cx="10.5" cy="15" r="6.5"/><circle cx="8.6" cy="16.4" r="1.1" fill="{P}"/><path d="M12 8.6V2.5M9 2.5h6"/>',
    "photo": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.7"/><path d="m21 16-5.5-5.5L7 19"/>',
    "etalon": '<path d="M3 16.5 16.5 3 21 7.5 7.5 21z"/><path d="M7 12.5l2 2M10 9.5l2 2M13 6.5l2 2"/>',
    "detecter": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><circle cx="12" cy="12" r="3"/><path d="M7.5 7.5l2.4 2.4M16.5 16.5l-2.4-2.4"/>',
    "deplacer": '<path d="M12 3v18M3 12h18"/><path d="m9 6 3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
    "pivot_auto":'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    # analyse
    "valider": '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.5 6h7M7.2 8.2l3.6 7.6M16.8 8.2l-3.6 7.6"/>',
    "lancer": f'<path d="M7 4.5l12 7.5-12 7.5z" fill="{P}"/>',
    "pause": '<path d="M8.5 5v14M15.5 5v14" stroke-width="2.6"/>',
    "stop": f'<rect x="6" y="6" width="12" height="12" rx="1.5" fill="{P}"/>',
    "debut": '<path d="M6 5v14"/><path d="M19 5 9 12l10 7z"/>',
    "fin": '<path d="M18 5v14"/><path d="M5 5l10 7-10 7z"/>',
    "boucle": '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
    "equilibre": '<path d="M12 4v16M7 20h10"/><path d="M5 7h14"/><path d="M5 7l-3 7h6zM19 7l-3 7h6z"/>',
    "courbes": '<path d="M3 3v18h18"/><path d="M6 16c3-9 5 3 8-4s4-5 6-6"/>',
    "tableau": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M10 4v16"/>',
    "configuration": '<path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    # affichage
    "ajuster": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
    "zoom_plus": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M11 8v6M8 11h6"/>',
    "zoom_moins": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6"/>',
    "grille": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    "aimant": '<path d="M6 3v9a6 6 0 0 0 12 0V3h-4v9a2 2 0 0 1-4 0V3z"/><path d="M6 7h4M14 7h4"/>',
    "lune": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    "soleil": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "langue": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "info": f'<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r="0.7" fill="{P}"/>',
    "aide": f'<circle cx="12" cy="12" r="9"/><path d="M9.4 9.4a2.6 2.6 0 1 1 3.7 2.4c-.8.4-1.1.9-1.1 1.9"/><circle cx="12" cy="16.8" r="0.8" fill="{P}"/>',
    "cours": '<path d="M2.5 5.5C5 4 8.5 4 12 6c3.5-2 7-2 9.5-.5V19c-2.5-1.5-6-1.5-9.5.5-3.5-2-7-2-9.5-.5z"/><path d="M12 6v13.5"/>',
    "tutoriel": '<path d="M2 9.5 12 4.5l10 5-10 5z"/><path d="M6 11.5v5c3.2 2.2 8.8 2.2 12 0v-5"/><path d="M22 9.5v6"/>',
    "tableur": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/><path d="m13 13 4 4M17 13l-4 4"/>',
    "modeles": '<rect x="3" y="3" width="7.5" height="7.5" rx="1.2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.2"/><path d="M13.5 17.25h7.5M17.25 13.5V21"/>',
    "ensemble": '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/>',
    "vecteurs": '<path d="M4 20 12 12"/><path d="M8 12h4v4"/><path d="M13 11l7-7"/><path d="M15 4h5v5"/>',
    "trace": '<path d="M3 17c4-12 8 6 12-6"/><circle cx="18" cy="8" r="2.4"/>',
    # objets (arbre du modèle)
    "solide": '<path d="M4 17 17 4l3 3L7 20z"/>',
    "bati": '<path d="M3 9h18"/><path d="M5 9l-2 4M10 9l-2 4M15 9l-2 4M20 9l-2 4"/>',
    "dossier": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "etude": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M7.5 15h9"/>',
}

_cache: Dict[Tuple[str, str, int], QIcon] = {}


def svg(nom: str, couleur: str) -> bytes:
    trace = TRACES.get(nom, TRACES["info"]).replace(P, couleur)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{couleur}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{trace}</svg>'
    ).encode("utf-8")


def pixmap(nom: str, couleur: str, taille: int = 20, ratio: float = 2.0) -> QPixmap:
    """Image du pictogramme, rendue à la densité d'écran demandée."""
    image = QPixmap(int(taille * ratio), int(taille * ratio))
    image.fill(Qt.transparent)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg(nom, couleur))).render(peintre, QRectF(0, 0, taille * ratio, taille * ratio))
    peintre.end()
    image.setDevicePixelRatio(ratio)
    return image


def icone(nom: str, jeton: str = "texte", taille: int = 20, couleur: Optional[str] = None) -> QIcon:
    """Icône dans la couleur du thème (``jeton``), avec sa variante désactivée."""
    normale = couleur or theme.hex(jeton)
    cle = (nom, normale + theme.hex("texte_inactif"), taille)
    if cle not in _cache:
        resultat = QIcon()
        resultat.addPixmap(pixmap(nom, normale, taille), QIcon.Normal)
        resultat.addPixmap(pixmap(nom, theme.hex("texte_inactif"), taille), QIcon.Disabled)
        _cache[cle] = resultat
    return _cache[cle]


def taille_icone(cote: int = 20) -> QSize:
    return QSize(cote, cote)
