"""Pictogrammes des gestes : boutons de la souris, molette et touches du clavier.

Ils sont dessinés à la volée (aucune image à livrer) et servent de puces dans
le tutoriel : on voit d'un coup d'œil quel bouton presser.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap

HAUTEUR = 26
RATIO = 2.0


def _toile(largeur: float) -> QPixmap:
    image = QPixmap(int(largeur * RATIO), int(HAUTEUR * RATIO))
    image.fill(Qt.transparent)
    image.setDevicePixelRatio(RATIO)
    return image


def souris(bouton: str, trait: QColor, accent: QColor) -> QPixmap:
    """Souris vue de dessus ; ``bouton`` : ``gauche``, ``droit``, ``molette``, ``glisser``."""
    image = _toile(22)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    corps = QRectF(4.0, 2.0, 14.0, 22.0)
    contour = QPainterPath()
    contour.addRoundedRect(corps, 7.0, 7.0)
    if bouton in ("gauche", "droit"):
        zone = QPainterPath()
        x = corps.left() if bouton == "gauche" else corps.center().x()
        zone.addRect(QRectF(x, corps.top(), corps.width() / 2.0, 9.0))
        p.fillPath(contour.intersected(zone), accent)
    p.setPen(QPen(trait, 1.5))
    p.setBrush(Qt.NoBrush)
    p.drawPath(contour)
    p.drawLine(QPointF(corps.left(), corps.top() + 9.0), QPointF(corps.right(), corps.top() + 9.0))
    p.drawLine(QPointF(corps.center().x(), corps.top()), QPointF(corps.center().x(), corps.top() + 9.0))
    if bouton == "molette":
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(corps.center().x() - 1.8, corps.top() + 2.0, 3.6, 6.0), 1.8, 1.8)
    if bouton == "glisser":
        p.fillPath(contour.intersected(_gauche(corps)), accent)
        p.setPen(QPen(trait, 1.5))
        p.drawPath(contour)
    p.end()
    return image


def _gauche(corps: QRectF) -> QPainterPath:
    zone = QPainterPath()
    zone.addRect(QRectF(corps.left(), corps.top(), corps.width() / 2.0, 9.0))
    return zone


def touche(texte: str, trait: QColor, fond: QColor) -> QPixmap:
    """Touche du clavier portant ``texte`` (« B », « Entrée », « Ctrl+Z »…)."""
    police = QFont()
    police.setPointSizeF(8.5)
    police.setBold(True)
    largeur = max(22.0, QFontMetrics(police).horizontalAdvance(texte) + 12.0)
    image = _toile(largeur + 2.0)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(1.0, 3.0, largeur, HAUTEUR - 6.0)
    p.setPen(QPen(trait, 1.3))
    p.setBrush(fond)
    p.drawRoundedRect(rect.adjusted(0, 0, 0, 1.5), 4.0, 4.0)
    p.drawRoundedRect(rect, 4.0, 4.0)
    p.setFont(police)
    p.setPen(trait)
    p.drawText(rect, Qt.AlignCenter, texte)
    p.end()
    return image


def pictogramme(geste: str, trait: QColor, accent: QColor, fond: QColor) -> QPixmap:
    """``clic``, ``clic_droit``, ``molette``, ``glisser`` ou ``touche:<texte>``."""
    if geste.startswith("touche:"):
        return touche(geste.split(":", 1)[1], trait, fond)
    return souris({"clic": "gauche", "clic_droit": "droit", "molette": "molette", "glisser": "glisser"}.get(geste, "gauche"), trait, accent)
