"""Tutoriel en superposition : l'écran s'assombrit, un panneau sombre guide pas à pas.

Le panneau, à droite, montre de haut en bas :

1. un cadre où une démonstration animée tourne en boucle (le pointeur clique
   et l'élément se crée sur une mini-grille) — ou, s'il existe, le fichier
   ``resources/tutoriel/<étape>.gif`` joué par ``QMovie`` ;
2. un titre et deux ou trois puces, chacune avec le pictogramme du geste ;
3. les boutons « Précédent », « Suivant » et « Compris ».

Le reste de la fenêtre est assombri, sauf le bouton de l'outil présenté,
entouré d'un halo : on voit où le trouver.
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMovie, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QToolBar, QVBoxLayout, QWidget

from ...chemins import dossier_tutoriel
from ...i18n import tr, traducteur
from . import demos
from .etapes import ETAPES, Etape
from .touches import pictogramme

TRAIT = QColor("#E7EAF0")
SECONDAIRE = QColor("#98A1B3")
ACCENT = QColor("#5B93FF")
FOND_TOUCHE = QColor("#242833")
LARGEUR_PANNEAU = 410
IMAGES_PAR_SECONDE = 30


class LecteurDemo(QWidget):
    """Cadre de la démonstration : animation dessinée, ou GIF s'il en existe un pour l'étape."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(214)
        self.nom = "bienvenue"
        self._debut = time.monotonic()
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(int(1000 / IMAGES_PAR_SECONDE))
        self._minuteur.timeout.connect(self.update)
        self._film: Optional[QMovie] = None
        self._ecran = QLabel(self)
        self._ecran.setAlignment(Qt.AlignCenter)
        self._ecran.hide()

    def jouer(self, nom: str) -> None:
        self.nom = nom
        self._debut = time.monotonic()
        gif = dossier_tutoriel() / f"{nom}.gif"
        if self._film is not None:
            self._film.stop()
            self._film = None
        if gif.is_file():
            self._film = QMovie(str(gif))
            self._film.setScaledSize(QSize(self.width() - 16, self.height() - 16))
            self._ecran.setMovie(self._film)
            self._ecran.setGeometry(self.rect())
            self._ecran.show()
            self._film.start()
            self._minuteur.stop()
        else:
            self._ecran.hide()
            self._minuteur.start()
        self.update()

    def arreter(self) -> None:
        self._minuteur.stop()
        if self._film is not None:
            self._film.stop()

    @property
    def instant(self) -> float:
        return time.monotonic() - self._debut

    def resizeEvent(self, evenement) -> None:
        self._ecran.setGeometry(self.rect())
        super().resizeEvent(evenement)

    def paintEvent(self, evenement) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cadre = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        chemin = QPainterPath()
        chemin.addRoundedRect(cadre, 10.0, 10.0)
        p.setClipPath(chemin)
        if self._film is None:
            demos.dessiner(self.nom, p, cadre, self.instant)
        p.setClipping(False)
        p.setPen(QPen(QColor("#2E3442"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(chemin)
        p.end()


class SuperpositionTutoriel(QWidget):
    """Assombrit la fenêtre principale et présente les étapes du tutoriel."""

    termine = Signal()

    def __init__(self, fenetre: QMainWindow, etapes: Sequence[Etape] = ETAPES, debut: int = 0) -> None:
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.etapes = tuple(etapes)
        self.indice = max(0, min(debut, len(self.etapes) - 1))
        self.setObjectName("superposition_tutoriel")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.panneau = QFrame(self)
        self.panneau.setObjectName("panneau_tutoriel")
        self.panneau.setStyleSheet(
            "#panneau_tutoriel { background: #14161B; border: 1px solid #2E3442; border-radius: 16px; }"
            "#panneau_tutoriel QLabel { color: #E7EAF0; background: transparent; }"
            "#panneau_tutoriel QLabel[role='secondaire'] { color: #98A1B3; }"
            "#panneau_tutoriel QPushButton { background: #242833; color: #E7EAF0; border: 1px solid #2E3442;"
            " border-radius: 8px; padding: 7px 16px; font-weight: 600; }"
            "#panneau_tutoriel QPushButton:hover { background: #2C3140; }"
            "#panneau_tutoriel QPushButton[principal='true'] { background: #5B93FF; border-color: #5B93FF; color: white; }"
            "#panneau_tutoriel QPushButton[principal='true']:hover { background: #77A6FF; }"
            "#panneau_tutoriel QPushButton:disabled { color: #5C6475; }"
        )
        self.demo = LecteurDemo(self.panneau)
        self.etape = QLabel()
        self.etape.setProperty("role", "secondaire")
        self.titre = QLabel()
        police = self.titre.font()
        police.setPointSizeF(police.pointSizeF() + 5.0)
        police.setBold(True)
        self.titre.setFont(police)
        self.titre.setWordWrap(True)
        self.puces = QVBoxLayout()
        self.puces.setSpacing(10)
        self.points = QLabel()
        self.points.setAlignment(Qt.AlignCenter)
        self.precedent = QPushButton()
        self.suivant = QPushButton()
        self.compris = QPushButton()
        self.compris.setProperty("principal", True)
        self.precedent.clicked.connect(self.reculer)
        self.suivant.clicked.connect(self.avancer)
        self.compris.clicked.connect(self.fermer)
        for bouton in (self.precedent, self.suivant, self.compris):
            bouton.setCursor(Qt.PointingHandCursor)
            bouton.setFocusPolicy(Qt.NoFocus)
            bouton.setMinimumWidth(96)

        colonne = QVBoxLayout(self.panneau)
        colonne.setContentsMargins(18, 18, 18, 16)
        colonne.setSpacing(10)
        colonne.addWidget(self.demo)
        colonne.addSpacing(4)
        colonne.addWidget(self.etape)
        colonne.addWidget(self.titre)
        colonne.addLayout(self.puces)
        colonne.addStretch(1)
        colonne.addWidget(self.points)
        boutons = QHBoxLayout()
        boutons.addWidget(self.precedent)
        boutons.addStretch(1)
        boutons.addWidget(self.suivant)
        boutons.addWidget(self.compris)
        colonne.addLayout(boutons)

        fenetre.installEventFilter(self)
        traducteur.abonner(self._afficher)
        self.setGeometry(fenetre.rect())
        self._placer()
        self._afficher()
        self.show()
        self.raise_()
        self.setFocus()

    # -------------------------------------------------------------- navigation
    def avancer(self) -> None:
        if self.indice < len(self.etapes) - 1:
            self.indice += 1
            self._afficher()
        else:
            self.fermer()

    def reculer(self) -> None:
        if self.indice > 0:
            self.indice -= 1
            self._afficher()

    def aller(self, indice: int) -> None:
        self.indice = max(0, min(indice, len(self.etapes) - 1))
        self._afficher()

    def fermer(self) -> None:
        self.demo.arreter()
        traducteur.desabonner(self._afficher)
        self.fenetre.removeEventFilter(self)
        self.hide()
        self.termine.emit()
        self.deleteLater()

    @property
    def etape_courante(self) -> Etape:
        return self.etapes[self.indice]

    # ------------------------------------------------------------------ contenu
    def _afficher(self) -> None:
        etape = self.etape_courante
        self.etape.setText(tr("tutoriel.etape", numero=self.indice + 1, total=len(self.etapes)))
        self.titre.setText(tr(f"tutoriel.{etape.cle}.titre"))
        while self.puces.count():
            element = self.puces.takeAt(0)
            ancienne = element.widget()
            if ancienne is not None:
                # Cachée tout de suite (pas de chevauchement), détruite au prochain tour de boucle.
                # Surtout pas setParent(None) : le widget appartiendrait alors à Python et serait
                # détruit dès la fin de l'instruction, avant le deleteLater (plantage).
                ancienne.hide()
                ancienne.deleteLater()
        for numero, geste in enumerate(etape.gestes, start=1):
            self.puces.addWidget(self._puce(geste, tr(f"tutoriel.{etape.cle}.puce{numero}")))
        self.points.setText("  ".join("●" if i == self.indice else "○" for i in range(len(self.etapes))))
        self.points.setStyleSheet("color: #5B93FF; font-size: 9pt;")
        dernier = self.indice == len(self.etapes) - 1
        self.precedent.setText(tr("tutoriel.precedent"))
        self.precedent.setEnabled(self.indice > 0)
        self.suivant.setText(tr("tutoriel.suivant"))
        self.suivant.setVisible(not dernier)
        self.compris.setText(tr("tutoriel.terminer") if dernier else tr("tutoriel.compris"))
        self.demo.jouer(etape.demo)
        self.update()

    def _puce(self, geste: str, texte: str) -> QWidget:
        if geste.startswith("touche:@"):
            geste = "touche:" + tr(f"touches.{geste[len('touche:@'):]}")
        rangee = QWidget()
        boite = QHBoxLayout(rangee)
        boite.setContentsMargins(0, 0, 0, 0)
        boite.setSpacing(10)
        icone = QLabel()
        icone.setPixmap(pictogramme(geste, TRAIT, ACCENT, FOND_TOUCHE))
        icone.setFixedWidth(max(34, icone.pixmap().width() // 2 + 4))
        icone.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        libelle = QLabel(texte)
        libelle.setWordWrap(True)
        libelle.setTextFormat(Qt.RichText)
        boite.addWidget(icone, 0, Qt.AlignTop)
        boite.addWidget(libelle, 1)
        return rangee

    # ------------------------------------------------------------------ dessin
    def _placer(self) -> None:
        marge = 18
        largeur = min(LARGEUR_PANNEAU, max(300, self.width() - 2 * marge))
        hauteur = min(max(self.height() - 2 * marge, 420), 640)
        self.panneau.setGeometry(QRect(self.width() - largeur - marge, max(marge, (self.height() - hauteur) // 2), largeur, hauteur))

    def zone_mise_en_lumiere(self) -> Optional[QRect]:
        """Rectangle du bouton de l'outil présenté, dans le repère de la superposition."""
        nom = self.etape_courante.action
        commandes = getattr(self.fenetre, "commandes", {})
        action = commandes.get(nom)
        if action is None:
            return None
        for barre in self.fenetre.findChildren(QToolBar):
            bouton = barre.widgetForAction(action)
            if bouton is not None and bouton.isVisible():
                coin = bouton.mapTo(self.fenetre, bouton.rect().topLeft())
                return QRect(coin, bouton.size()).adjusted(-4, -4, 4, 4)
        return None

    def paintEvent(self, evenement) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        voile = QPainterPath()
        voile.addRect(QRectF(self.rect()))
        zone = self.zone_mise_en_lumiere()
        if zone is not None:
            trou = QPainterPath()
            trou.addRoundedRect(QRectF(zone), 8.0, 8.0)
            voile = voile.subtracted(trou)
        p.fillPath(voile, QColor(5, 7, 12, 165))
        if zone is not None:
            for largeur, alpha in ((8.0, 60), (2.2, 255)):
                couleur = QColor(ACCENT)
                couleur.setAlpha(alpha)
                p.setPen(QPen(couleur, largeur))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(QRectF(zone), 8.0, 8.0)
        p.end()

    # -------------------------------------------------------------- événements
    def eventFilter(self, objet: QObject, evenement: QEvent) -> bool:
        if objet is self.fenetre and evenement.type() == QEvent.Resize:
            self.setGeometry(self.fenetre.rect())
            self._placer()
        return False

    def resizeEvent(self, evenement) -> None:
        self._placer()
        super().resizeEvent(evenement)

    def keyPressEvent(self, evenement: QKeyEvent) -> None:
        touche = evenement.key()
        if touche == Qt.Key_Escape:
            self.fermer()
        elif touche in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.avancer()
        elif touche == Qt.Key_Left:
            self.reculer()
        else:
            super().keyPressEvent(evenement)

    def mousePressEvent(self, evenement) -> None:
        evenement.accept()  # la fenêtre derrière reste inactive pendant le tutoriel

    def wheelEvent(self, evenement) -> None:
        evenement.accept()
