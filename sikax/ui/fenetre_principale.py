"""Fenêtre principale de Sikax.

Elle assemble la vue du schéma, les panneaux ancrables, les menus et les
barres d'outils, et orchestre les opérations longues (calcul en arrière-plan)
ainsi que les fichiers. La logique métier reste dans ``modele``, ``calcul``
et ``fichiers`` : la fenêtre ne fait que relier l'utilisateur au document.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon, QImage, QKeySequence, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __organisation__
from ..calcul import (
    CalculInterrompu,
    ErreurCalcul,
    Resultats,
    SystemeMecanique,
    appliquer_resultats,
    lancer_etude,
    rechercher_equilibre,
)
from ..chemins import dossier_exemples, icone_application
from ..fichiers import EXTENSION, ErreurEcriture, ErreurLecture, charger
from ..fichiers.excel import Textes, exporter_excel
from ..i18n import texte_diagnostic, texte_erreur_calcul, texte_erreur_fichier, texte_message_calcul, tr, traducteur
from ..modele import Mecanisme
from ..modele.bibliotheque import MODELES
from ..modele.fond import FondPlan, format_image
from .aide import aide
from .dialogues.a_propos import DialogueAPropos
from .dialogues.diagnostics import DialogueDiagnostics
from .document import Document, Ref
from .icones import icone
from .panneaux.arbre import PanneauArbre
from .panneaux.courbes import PanneauCourbes
from .panneaux.cours import PanneauCours
from .panneaux.etude import PanneauEtude
from .panneaux.journal import PanneauJournal
from .panneaux.lecteur import BarreLecture
from .panneaux.proprietes import PanneauProprietes
from .panneaux.resultats import PanneauResultats
from .panneaux.validation import PanneauValidation
from .schema import VueSchema
from .theme import theme
from .tutoriel import DialogueAccueil, SuperpositionTutoriel

RECENTS_MAX = 8
COTE_MAX_PHOTO = 4000
"""Une photo plus grande est réduite à l'import : le projet reste léger, la précision suffit."""
FORMATS_PHOTO = "*.png *.jpg *.jpeg *.bmp *.gif *.webp"

# nom de l'outil → (pictogramme, raccourci clavier)
OUTILS = {
    "selection": ("selection", "S"),
    "manipuler": ("manipuler", "M"),
    "barre": ("barre", "B"),
    "point": ("point", "P"),
    "cercle": ("cercle", "D"),
    "pivot": ("pivot", "1"),
    "glissiere": ("glissiere", "2"),
    "encastrement": ("encastrement", "3"),
    "ponctuelle": ("ponctuelle", "4"),
    "engrenage": ("engrenage", "E"),
    "came": ("came", "K"),
    "force": ("force", "F"),
    "couple": ("couple", "C"),
    "ressort": ("ressort", "R"),
    "moteur": ("moteur", "O"),
    "etalonnage": ("etalon", None),
    "photo": ("deplacer", None),
}


class Calcul(QThread):
    """Exécute une étude hors du fil de l'interface."""

    progression = Signal(float)
    termine = Signal(object)
    echec = Signal(object)
    interrompu = Signal()

    def __init__(self, mecanisme: Mecanisme, parent=None) -> None:
        super().__init__(parent)
        self._mecanisme = mecanisme.copie()
        self._arret = False

    def arreter(self) -> None:
        self._arret = True

    def run(self) -> None:
        try:
            resultats = lancer_etude(self._mecanisme, self.progression.emit, lambda: self._arret)
        except CalculInterrompu:
            self.interrompu.emit()
        except ErreurCalcul as erreur:
            self.echec.emit(erreur)
        except Exception as erreur:  # une erreur imprévue ne doit pas tuer l'application
            self.echec.emit(ErreurCalcul("inattendue", message=f"{type(erreur).__name__} : {erreur}"))
        else:
            self.termine.emit(resultats)


class FenetrePrincipale(QMainWindow):
    def __init__(self, persistant: bool = True) -> None:
        super().__init__()
        self._persistant = persistant
        self.doc = Document()
        self._calcul: Optional[Calcul] = None
        self._revision_calcul = 0
        self._revision = 0
        self.commandes: Dict[str, QAction] = {}

        self.setWindowIcon(QIcon(str(icone_application())))
        self.resize(1440, 900)
        self.setCorner(Qt.BottomLeftCorner, Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        self.vue = VueSchema(self.doc)
        self.lecteur = BarreLecture(self.doc)
        centre = QWidget()
        disposition = QVBoxLayout(centre)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self.vue, 1)
        disposition.addWidget(self.lecteur)
        self.setCentralWidget(centre)

        self.arbre = PanneauArbre(self.doc)
        self.proprietes = PanneauProprietes(self.doc)
        self.etude = PanneauEtude(self.doc)
        self.validation = PanneauValidation(self.doc)
        self.courbes = PanneauCourbes(self.doc)
        self.resultats = PanneauResultats(self.doc)
        self.journal = PanneauJournal()
        self.cours = PanneauCours()
        self._tutoriel: Optional[SuperpositionTutoriel] = None

        # Trois blocs ancrables : le modèle à gauche, l'inspecteur à droite (propriétés,
        # étude) et l'analyse en bas (validation, courbes, efforts, journal).
        self.onglets: Dict[str, QWidget] = {
            "proprietes": self.proprietes,
            "etude": self.etude,
            "cours": self.cours,
            "validation": self.validation,
            "courbes": self.courbes,
            "resultats": self.resultats,
            "journal": self.journal,
        }
        self.onglets_droite = self._onglets("proprietes", "etude", "cours")
        self.onglets_bas = self._onglets("validation", "courbes", "resultats", "journal")
        self.docks: Dict[str, QDockWidget] = {}
        self._ancrer("arbre", self.arbre, Qt.LeftDockWidgetArea)
        self._ancrer("inspecteur", self.onglets_droite, Qt.RightDockWidgetArea, titre=False)
        self._ancrer("analyse", self.onglets_bas, Qt.BottomDockWidgetArea, titre=False)
        self.resizeDocks([self.docks["arbre"], self.docks["inspecteur"]], [250, 340], Qt.Horizontal)
        self.resizeDocks([self.docks["analyse"]], [310], Qt.Vertical)

        self._creer_actions()
        self._creer_menus()
        self._creer_barres()
        self._creer_barre_etat()

        self.doc.etat_change.connect(self._sur_etat)
        self.doc.modele_change.connect(self._compter_revision)
        self.doc.modele_change.connect(self._sur_modele)
        self.doc.selection_change.connect(self._sur_etat)
        self.doc.selection_change.connect(self._montrer_proprietes)
        self.doc.resultats_change.connect(self._sur_etat)
        self.vue.aide.connect(self.etiquette_aide.setText)
        self.vue.coordonnees.connect(self._sur_coordonnees)
        self.vue.outil_change.connect(self._sur_outil)
        self.vue.menu_demande.connect(self._menu_contextuel)
        self.arbre.menu_demande.connect(self._menu_contextuel)
        self.etude.lancer.connect(self.lancer_etude)
        self.etude.annuler.connect(self.arreter_calcul)
        self.etude.equilibre.connect(self.chercher_equilibre)
        self.courbes.exporter_demande.connect(self.exporter_resultats)
        self.proprietes.outil_demande.connect(self.vue.choisir_outil)
        self.proprietes.detection_demandee.connect(self.detecter_formes)
        aide.ouvrir.connect(self.ouvrir_cours)
        theme.change.connect(lambda _: self._icones())
        traducteur.abonner(self.traduire)

        self._restaurer()
        self.traduire()
        self._sur_modele()
        self.vue.choisir_outil("selection")

    # ------------------------------------------------------------ construction
    def _onglets(self, *noms: str) -> QTabWidget:
        """Regroupe plusieurs panneaux sous des onglets."""
        groupe = QTabWidget()
        groupe.setDocumentMode(True)
        for nom in noms:
            groupe.addTab(self.onglets[nom], "")
        return groupe

    def montrer(self, nom: str) -> None:
        """Amène un panneau au premier plan de son groupe d'onglets."""
        panneau = self.onglets[nom]
        for groupe in (self.onglets_droite, self.onglets_bas):
            if groupe.indexOf(panneau) >= 0:
                groupe.setCurrentWidget(panneau)

    def _ancrer(self, nom: str, composant: QWidget, zone: Qt.DockWidgetArea, titre: bool = True) -> None:
        dock = QDockWidget()
        dock.setObjectName(f"dock_{nom}")
        dock.setWidget(composant)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        if not titre:
            dock.setTitleBarWidget(QWidget())  # les onglets tiennent lieu de titre
        self.addDockWidget(zone, dock)
        self.docks[nom] = dock

    def _action(self, nom: str, rappel, raccourci=None, pictogramme: str = "", cochable: bool = False) -> QAction:
        action = QAction(self)
        action.setObjectName(nom)
        if raccourci is not None:
            action.setShortcuts(raccourci if isinstance(raccourci, list) else [raccourci])
        action.setCheckable(cochable)
        action.setProperty("pictogramme", pictogramme)
        if cochable:
            action.toggled.connect(rappel)
        else:
            action.triggered.connect(lambda _=False: rappel())
        self.commandes[nom] = action
        self.addAction(action)
        return action

    def _creer_actions(self) -> None:
        a = self._action
        a("nouveau", self.nouveau, QKeySequence.New, "nouveau")
        a("ouvrir", self.ouvrir, QKeySequence.Open, "ouvrir")
        a("enregistrer", self.enregistrer, QKeySequence.Save, "enregistrer")
        a("enregistrer_sous", self.enregistrer_sous, QKeySequence("Ctrl+Shift+S"))
        a("importer_photo", self.importer_photo, QKeySequence("Ctrl+Shift+I"), "photo")
        a("detecter_formes", self.detecter_formes, None, "detecter")
        a("supprimer_photo", lambda: self.doc.supprimer(Ref("fond", "fond")), None, "supprimer")
        a("exporter_image", self.exporter_image, None, "image")
        a("exporter_resultats", lambda: self.exporter_resultats([]), QKeySequence("Ctrl+E"), "tableur")
        a("quitter", self.close, QKeySequence("Ctrl+Q"))

        a("annuler", self.doc.annuler, QKeySequence.Undo, "annuler")
        a("retablir", self.doc.retablir, [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")], "retablir")
        a("supprimer", lambda: self.doc.supprimer(self.doc.selection), QKeySequence.Delete, "supprimer")
        a("deselectionner", lambda: self.doc.selectionner(None))

        a("theme_sombre", self._sur_theme, QKeySequence("Ctrl+T"), "lune", cochable=True)
        a("ajuster", self.vue.ajuster, QKeySequence("A"), "ajuster")
        a("zoom_plus", lambda: self.vue.zoomer(1.25), QKeySequence.ZoomIn, "zoom_plus")
        a("zoom_moins", lambda: self.vue.zoomer(0.8), QKeySequence.ZoomOut, "zoom_moins")
        for cle, pictogramme, raccourci in (
            ("grille", "grille", "G"),
            ("aimantation", "aimant", None),
            ("noms_points", "", None),
            ("noms_liaisons", "", None),
            ("centres_gravite", "", None),
        ):
            a(f"affichage_{cle}", lambda etat, c=cle: self._sur_affichage(c, etat), QKeySequence(raccourci) if raccourci else None, pictogramme, cochable=True)
        for cle, pictogramme in (("reactions", "vecteurs"), ("vitesses", "vecteurs"), ("trajectoires", "trace")):
            a(f"montrer_{cle}", lambda etat, c=cle: self._sur_option_resultats(c, etat), None, pictogramme, cochable=True)

        self.groupe_outils = QActionGroup(self)
        self.groupe_outils.setExclusive(True)
        for nom, (pictogramme, raccourci) in OUTILS.items():
            action = a(f"outil_{nom}", lambda etat, n=nom: etat and self.vue.choisir_outil(n), QKeySequence(raccourci) if raccourci else None, pictogramme, cochable=True)
            self.groupe_outils.addAction(action)
        a("pivots_automatiques", lambda etat: setattr(self.vue, "pivots_automatiques", etat), None, "pivot_auto", cochable=True)

        a("lancer", self.lancer_etude, QKeySequence("F5"), "lancer")
        a("arreter", self.arreter_calcul, None, "stop")
        a("equilibre", self.chercher_equilibre, None, "equilibre")
        a("adopter_configuration", self.adopter_configuration, None, "configuration")
        a("effacer_resultats", lambda: self.doc.definir_resultats(None))
        a("lecture", self.lecteur.basculer, QKeySequence("Space"), "lancer")
        a("a_propos", lambda: DialogueAPropos(self).exec(), None, "info")
        a("tutoriel", self.tutoriel, QKeySequence("F1"), "tutoriel")
        a("cours", lambda: self.ouvrir_cours(self.cours.fiche, ""), QKeySequence("Shift+F1"), "cours")
        a("accueil", self.accueillir, None, "aide")

    def _creer_menus(self) -> None:
        barre = self.menuBar()
        self.menus: Dict[str, QMenu] = {}
        for nom in ("fichier", "edition", "affichage", "modele", "etude", "aide"):
            self.menus[nom] = barre.addMenu("")
        m, a = self.menus, self.commandes

        m["fichier"].addAction(a["nouveau"])
        self.menu_modeles = m["fichier"].addMenu("")
        m["fichier"].addAction(a["ouvrir"])
        self.menu_recents = m["fichier"].addMenu("")
        self.menu_exemples = m["fichier"].addMenu("")
        m["fichier"].addSeparator()
        m["fichier"].addActions([a["enregistrer"], a["enregistrer_sous"]])
        m["fichier"].addSeparator()
        m["fichier"].addAction(a["importer_photo"])
        m["fichier"].addActions([a["exporter_image"], a["exporter_resultats"]])
        m["fichier"].addSeparator()
        m["fichier"].addAction(a["quitter"])

        m["edition"].addActions([a["annuler"], a["retablir"]])
        m["edition"].addSeparator()
        m["edition"].addActions([a["supprimer"], a["deselectionner"]])

        m["affichage"].addAction(a["theme_sombre"])
        self.menu_langue = m["affichage"].addMenu("")
        m["affichage"].addSeparator()
        m["affichage"].addActions([a["ajuster"], a["zoom_plus"], a["zoom_moins"]])
        m["affichage"].addSeparator()
        m["affichage"].addActions([a[f"affichage_{c}"] for c in ("grille", "aimantation", "noms_points", "noms_liaisons", "centres_gravite")])
        m["affichage"].addSeparator()
        m["affichage"].addActions([a["montrer_reactions"], a["montrer_vitesses"], a["montrer_trajectoires"]])
        m["affichage"].addSeparator()
        self.menu_panneaux = m["affichage"].addMenu("")
        for dock in self.docks.values():
            self.menu_panneaux.addAction(dock.toggleViewAction())

        m["modele"].addActions([a["outil_selection"], a["outil_manipuler"]])
        m["modele"].addSeparator()
        m["modele"].addActions([a["outil_barre"], a["outil_point"], a["outil_cercle"]])
        m["modele"].addSeparator()
        m["modele"].addActions([a[f"outil_{n}"] for n in ("pivot", "glissiere", "encastrement", "ponctuelle", "engrenage", "came")])
        m["modele"].addSeparator()
        m["modele"].addActions([a[f"outil_{n}"] for n in ("force", "couple", "ressort", "moteur")])
        m["modele"].addSeparator()
        m["modele"].addAction(a["pivots_automatiques"])
        m["modele"].addSeparator()
        self.menu_photo = m["modele"].addMenu("")
        self.menu_photo.addActions([a["importer_photo"], a["outil_etalonnage"], a["outil_photo"], a["detecter_formes"]])
        self.menu_photo.addSeparator()
        self.menu_photo.addAction(a["supprimer_photo"])

        m["etude"].addActions([a["lancer"], a["arreter"]])
        m["etude"].addSeparator()
        m["etude"].addActions([a["equilibre"], a["adopter_configuration"]])
        m["etude"].addSeparator()
        m["etude"].addActions([a["lecture"], a["effacer_resultats"]])

        m["aide"].addActions([a["tutoriel"], a["cours"], a["accueil"]])
        m["aide"].addSeparator()
        m["aide"].addAction(a["a_propos"])

    def _creer_barres(self) -> None:
        a = self.commandes
        self.barre_principale = QToolBar()
        self.barre_principale.setObjectName("barre_principale")
        self.barre_principale.setMovable(False)
        self.barre_principale.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.TopToolBarArea, self.barre_principale)
        self.barre_principale.addActions([a["nouveau"], a["ouvrir"], a["enregistrer"]])
        self.barre_principale.addSeparator()
        self.barre_principale.addActions([a["annuler"], a["retablir"]])
        self.barre_principale.addSeparator()
        self.barre_principale.addActions([a["ajuster"], a["affichage_grille"], a["affichage_aimantation"], a["pivots_automatiques"]])
        self.barre_principale.addSeparator()
        self.barre_principale.addActions([a["montrer_reactions"], a["montrer_vitesses"], a["montrer_trajectoires"]])
        self.barre_principale.addSeparator()
        self.barre_principale.addActions([a["lancer"], a["equilibre"]])
        espace = QWidget()
        espace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.barre_principale.addWidget(espace)
        self.barre_principale.addAction(a["theme_sombre"])

        self.barre_outils = QToolBar()
        self.barre_outils.setObjectName("barre_outils")
        self.barre_outils.setMovable(False)
        self.barre_outils.setIconSize(QSize(22, 22))
        self.barre_outils.setOrientation(Qt.Vertical)
        self.addToolBar(Qt.LeftToolBarArea, self.barre_outils)
        for groupe in (
            ("selection", "manipuler"),
            ("barre", "point", "cercle"),
            ("pivot", "glissiere", "encastrement", "ponctuelle", "engrenage", "came"),
            ("force", "couple", "ressort", "moteur"),
        ):
            if groupe[0] != "selection":
                self.barre_outils.addSeparator()
            self.barre_outils.addActions([a[f"outil_{n}"] for n in groupe])

    def _creer_barre_etat(self) -> None:
        barre = self.statusBar()
        self.etiquette_aide = QLabel()
        self.etiquette_bilan = QLabel()
        self.etiquette_coordonnees = QLabel()
        self.etiquette_coordonnees.setMinimumWidth(230)
        self.etiquette_coordonnees.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        barre.addWidget(self.etiquette_aide, 1)
        barre.addPermanentWidget(self.etiquette_bilan)
        barre.addPermanentWidget(self.etiquette_coordonnees)

    # -------------------------------------------------------- langue et thème
    def traduire(self) -> None:
        for nom, action in self.commandes.items():
            action.setText(tr(f"action.{nom}"))
            cle_aide = f"aide_action.{nom}"
            aide = tr(cle_aide) if traducteur.existe(cle_aide) else action.text().replace("&", "")
            raccourci = action.shortcut().toString(QKeySequence.NativeText)
            action.setToolTip(f"{aide}  ({raccourci})" if raccourci else aide)
            action.setStatusTip("")
        for nom, menu in self.menus.items():
            menu.setTitle(tr(f"menu.{nom}"))
        self.menu_recents.setTitle(tr("menu.recents"))
        self.menu_exemples.setTitle(tr("menu.exemples"))
        self.menu_modeles.setTitle(tr("menu.modeles"))
        self.menu_modeles.setIcon(icone("modeles"))
        self.menu_photo.setTitle(tr("menu.photo"))
        self.menu_photo.setIcon(icone("photo"))
        self.menu_langue.setTitle(tr("menu.langue"))
        self.menu_panneaux.setTitle(tr("menu.panneaux"))
        for nom, dock in self.docks.items():
            dock.setWindowTitle(tr(f"panneau.{nom}"))
        for nom, panneau in self.onglets.items():
            for groupe in (self.onglets_droite, self.onglets_bas):
                if groupe.indexOf(panneau) >= 0:
                    groupe.setTabText(groupe.indexOf(panneau), tr(f"panneau.{nom}"))
        self.barre_principale.setWindowTitle(tr("barre.principale"))
        self.barre_outils.setWindowTitle(tr("barre.outils"))
        self._remplir_langues()
        self._remplir_recents()
        self._remplir_exemples()
        self._remplir_modeles()
        self._icones()
        self._sur_etat()
        self._sur_modele()
        self.etiquette_aide.setText(tr(self.vue.outil.cle_aide))

    def _icones(self) -> None:
        for action in self.commandes.values():
            pictogramme = action.property("pictogramme")
            if pictogramme:
                action.setIcon(icone(pictogramme))
        self.commandes["theme_sombre"].setIcon(icone("soleil" if theme.sombre else "lune"))
        self.commandes["lancer"].setIcon(icone("lancer", "succes"))
        self.menu_langue.setIcon(icone("langue"))

    def _remplir_langues(self) -> None:
        self.menu_langue.clear()
        groupe = QActionGroup(self.menu_langue)
        for code, nom in traducteur.langues_disponibles().items():
            action = QAction(nom, self.menu_langue)
            action.setCheckable(True)
            action.setChecked(code == traducteur.langue)
            action.triggered.connect(lambda _=False, c=code: self.changer_langue(c))
            groupe.addAction(action)
            self.menu_langue.addAction(action)

    def changer_langue(self, code: str) -> None:
        if code != traducteur.langue:
            traducteur.charger(code)
            self._reglage("langue", code)

    def _sur_theme(self, sombre: bool) -> None:
        nom = "sombre" if sombre else "clair"
        if theme.nom != nom:
            theme.appliquer(nom)
            self._reglage("theme", nom)

    def _sur_affichage(self, cle: str, etat: bool) -> None:
        if self.doc.mecanisme.affichage.get(cle) != etat:
            with self.doc.modification():
                self.doc.mecanisme.affichage[cle] = etat

    def _sur_option_resultats(self, cle: str, etat: bool) -> None:
        self.vue.rendu.options[cle] = etat
        self.vue.update()

    # ----------------------------------------------------------------- réglages
    def _reglages(self) -> Optional[QSettings]:
        return QSettings(__organisation__, __app_name__) if self._persistant else None

    def _reglage(self, cle: str, valeur) -> None:
        reglages = self._reglages()
        if reglages is not None:
            reglages.setValue(cle, valeur)

    def _restaurer(self) -> None:
        reglages = self._reglages()
        self.commandes["pivots_automatiques"].setChecked(True)
        self.commandes["montrer_reactions"].setChecked(True)
        self.commandes["outil_selection"].setChecked(True)
        self.commandes["theme_sombre"].setChecked(theme.sombre)
        if reglages is None:
            return
        geometrie = reglages.value("geometrie")
        etat = reglages.value("etat")
        if isinstance(geometrie, QByteArray):
            self.restoreGeometry(geometrie)
        if isinstance(etat, QByteArray):
            self.restoreState(etat)

    def recents(self) -> List[str]:
        reglages = self._reglages()
        if reglages is None:
            return []
        valeur = reglages.value("recents", [])
        if isinstance(valeur, str):
            valeur = [valeur]
        return [str(c) for c in (valeur or []) if c]

    def _noter_recent(self, chemin: str) -> None:
        reglages = self._reglages()
        if reglages is None:
            return
        liste = [chemin] + [c for c in self.recents() if c != chemin]
        reglages.setValue("recents", liste[:RECENTS_MAX])
        self._remplir_recents()

    def _remplir_recents(self) -> None:
        self.menu_recents.clear()
        chemins = [c for c in self.recents() if os.path.isfile(c)]
        for chemin in chemins:
            action = QAction(os.path.basename(chemin), self.menu_recents)
            action.setToolTip(chemin)
            action.triggered.connect(lambda _=False, c=chemin: self.ouvrir(c))
            self.menu_recents.addAction(action)
        self.menu_recents.setEnabled(bool(chemins))

    def _remplir_exemples(self) -> None:
        self.menu_exemples.clear()
        dossier = dossier_exemples()
        fichiers = sorted(dossier.glob(f"*{EXTENSION}")) if dossier.is_dir() else []
        for fichier in fichiers:
            cle = f"exemple.{fichier.stem}"
            action = QAction(tr(cle) if traducteur.existe(cle) else fichier.stem, self.menu_exemples)
            action.triggered.connect(lambda _=False, c=str(fichier): self.ouvrir_exemple(c))
            self.menu_exemples.addAction(action)
        self.menu_exemples.setEnabled(bool(fichiers))

    def _remplir_modeles(self) -> None:
        self.menu_modeles.clear()
        for nom in MODELES:
            action = QAction(icone("modeles"), tr(f"modele_depart.{nom}"), self.menu_modeles)
            action.setToolTip(tr(f"modele_depart.{nom}_aide"))
            action.triggered.connect(lambda _=False, n=nom: self.nouveau_depuis_modele(n))
            self.menu_modeles.addAction(action)

    # ---------------------------------------------------------------- réactions
    def _sur_etat(self) -> None:
        doc = self.doc
        nom = doc.nom or tr("fenetre.sans_titre")
        self.setWindowTitle(f"{nom}{' •' if doc.modifie else ''} — {__app_name__}")
        a = self.commandes
        a["annuler"].setEnabled(doc.peut_annuler)
        a["retablir"].setEnabled(doc.peut_retablir)
        a["supprimer"].setEnabled(doc.selection is not None)
        resultats = doc.resultats is not None
        a["exporter_resultats"].setEnabled(resultats)
        a["effacer_resultats"].setEnabled(resultats)
        a["adopter_configuration"].setEnabled(resultats and doc.resultats.nb_instants > 1)
        a["lecture"].setEnabled(resultats and doc.resultats.nb_instants > 1)
        photo = doc.mecanisme.fond is not None
        for nom in ("detecter_formes", "supprimer_photo", "outil_etalonnage", "outil_photo"):
            a[nom].setEnabled(photo)
        en_cours = self._calcul is not None
        a["lancer"].setEnabled(not en_cours)
        a["arreter"].setEnabled(en_cours)
        a["equilibre"].setEnabled(not en_cours)

    def _montrer_proprietes(self) -> None:
        """Sélectionner un objet amène ses propriétés au premier plan."""
        if self.doc.selection is not None:
            self.montrer("proprietes")

    def _compter_revision(self) -> None:
        """Chaque modification invalide un calcul lancé sur l'état précédent."""
        self._revision += 1

    def _sur_modele(self) -> None:
        affichage = self.doc.mecanisme.affichage
        for cle in ("grille", "aimantation", "noms_points", "noms_liaisons", "centres_gravite"):
            action = self.commandes[f"affichage_{cle}"]
            if action.isChecked() != bool(affichage.get(cle, True)):
                action.blockSignals(True)
                action.setChecked(bool(affichage.get(cle, True)))
                action.blockSignals(False)
        QTimer.singleShot(0, self, lambda: self.etiquette_bilan.setText(self.validation.resume()))

    def _sur_outil(self, nom: str) -> None:
        action = self.commandes.get(f"outil_{nom}")
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def _sur_coordonnees(self, x: float, y: float) -> None:
        unites = self.doc.mecanisme.unites
        self.etiquette_coordonnees.setText(f"x = {unites.formater(x, 'longueur', 5)}    y = {unites.formater(y, 'longueur', 5)}")

    def _menu_contextuel(self, ref: Optional[Ref], position: QPoint) -> None:
        menu = QMenu(self)
        doc = self.doc
        if ref is not None:
            doc.selectionner(ref)
            if ref.genre == "liaison":
                liaison = doc.mecanisme.liaisons[ref.id]
                if liaison.PILOTAGE is not None and doc.mecanisme.moteur_de_liaison(ref.id) is None:
                    action = menu.addAction(icone("moteur"), tr("contexte.motoriser"))
                    action.triggered.connect(lambda: self._motoriser(ref.id))
                action = menu.addAction(tr("contexte.inverser"))
                action.triggered.connect(lambda: self._inverser(ref.id))
                menu.addSeparator()
            if ref.genre == "solide" and ref.id in doc.mecanisme.solides:
                action = menu.addAction(icone("point"), tr("contexte.ajouter_point"))
                action.triggered.connect(lambda: self.vue.choisir_outil("point"))
                menu.addSeparator()
            menu.addAction(self.commandes["supprimer"])
        else:
            menu.addActions([self.commandes["ajuster"], self.commandes["affichage_grille"], self.commandes["affichage_aimantation"]])
        menu.exec(position)

    def _motoriser(self, liaison_id: str) -> None:
        with self.doc.modification() as m:
            moteur = m.creer_moteur(liaison_id)
        self.doc.selectionner(Ref("moteur", moteur.id))

    def _inverser(self, liaison_id: str) -> None:
        with self.doc.modification() as m:
            m.inverser_liaison(liaison_id)

    def noter(self, niveau: str, texte: str, duree: int = 6000) -> None:
        """Consigne un message dans le journal et l'affiche brièvement dans la barre d'état."""
        self.journal.ajouter(niveau, texte)
        self.statusBar().showMessage(texte, duree)

    # ----------------------------------------------------------------- fichiers
    def _confirmer_abandon(self) -> bool:
        """Propose d'enregistrer les modifications. Retourne faux si l'utilisateur annule."""
        if not self.doc.modifie:
            return True
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Question)
        boite.setWindowTitle(__app_name__)
        boite.setText(tr("fichier.confirmer.texte", nom=self.doc.nom or tr("fenetre.sans_titre")))
        boite.setInformativeText(tr("fichier.confirmer.detail"))
        enregistrer = boite.addButton(tr("action.enregistrer").replace("&", ""), QMessageBox.AcceptRole)
        ignorer = boite.addButton(tr("fichier.confirmer.ne_pas_enregistrer"), QMessageBox.DestructiveRole)
        boite.addButton(tr("commun.annuler"), QMessageBox.RejectRole)
        boite.setDefaultButton(enregistrer)
        boite.exec()
        choix = boite.clickedButton()
        if choix is enregistrer:
            return self.enregistrer()
        return choix is ignorer

    def nouveau(self) -> None:
        if not self._confirmer_abandon():
            return
        self.arreter_calcul()
        self.doc.nouveau()
        self.vue.demander_ajustement()

    def _erreur_fichier(self, erreur) -> None:
        texte = texte_erreur_fichier(erreur)
        self.noter("erreur", texte)
        QMessageBox.critical(self, __app_name__, texte)

    def _charger(self, chemin: str):
        """Lit un fichier, en proposant le mode tolérant s'il contient des erreurs."""
        try:
            return charger(chemin)
        except ErreurLecture as erreur:
            if erreur.code != "fichier_invalide":
                self._erreur_fichier(erreur)
                return None
            dialogue = DialogueDiagnostics(erreur.rapport, os.path.basename(chemin), proposer_ouverture=True, parent=self)
            if dialogue.exec() != DialogueDiagnostics.Accepted:
                return None
            try:
                return charger(chemin, tolerant=True)
            except ErreurLecture as seconde:
                self._erreur_fichier(seconde)
                return None

    def _journaliser_rapport(self, resultat, nom: str) -> None:
        for diagnostic in resultat.rapport:
            if diagnostic.niveau != "info":
                self.journal.ajouter(diagnostic.niveau, f"{nom} — {texte_diagnostic(diagnostic)}")
        avertissements = len(resultat.rapport.avertissements) + len(resultat.rapport.erreurs)
        if avertissements:
            self.noter("avertissement", tr("fichier.ouvert_avec_remarques", nom=nom, nombre=avertissements))
        else:
            self.noter("succes", tr("fichier.ouvert", nom=nom))

    def ouvrir(self, chemin: Optional[str] = None) -> bool:
        if not self._confirmer_abandon():
            return False
        if not chemin:
            depart = os.path.dirname(self.doc.chemin) if self.doc.chemin else ""
            chemin, _ = QFileDialog.getOpenFileName(self, tr("fichier.dialogue.ouvrir"), depart, tr("fichier.filtre", ext=EXTENSION))
            if not chemin:
                return False
        resultat = self._charger(chemin)
        if resultat is None:
            return False
        self.arreter_calcul()
        self.doc.adopter(resultat)
        self._noter_recent(resultat.chemin)
        self._journaliser_rapport(resultat, os.path.basename(chemin))
        self.vue.demander_ajustement()
        return True

    def nouveau_depuis_modele(self, nom: str) -> bool:
        """Nouveau projet sans titre construit à partir d'un modèle de départ (pendule, came, engrenages)."""
        if not self._confirmer_abandon():
            return False
        self.arreter_calcul()
        mecanisme = MODELES[nom]()
        self.doc.nouveau(mecanisme)
        self.noter("info", tr("fichier.modele_ouvert", nom=tr(f"modele_depart.{nom}")))
        self.vue.demander_ajustement()
        return True

    def ouvrir_exemple(self, chemin: str) -> bool:
        """Ouvre un exemple comme nouveau projet sans titre : l'original n'est jamais écrasé."""
        if not self._confirmer_abandon():
            return False
        resultat = self._charger(chemin)
        if resultat is None:
            return False
        self.arreter_calcul()
        self.doc.nouveau(resultat.mecanisme)
        self.noter("info", tr("fichier.exemple_ouvert", nom=resultat.mecanisme.titre or os.path.basename(chemin)))
        self.vue.demander_ajustement()
        return True

    def enregistrer(self) -> bool:
        if not self.doc.chemin:
            return self.enregistrer_sous()
        return self._ecrire(self.doc.chemin)

    def enregistrer_sous(self) -> bool:
        depart = self.doc.chemin or (self.doc.mecanisme.titre or tr("fenetre.sans_titre")) + EXTENSION
        chemin, _ = QFileDialog.getSaveFileName(self, tr("fichier.dialogue.enregistrer"), depart, tr("fichier.filtre", ext=EXTENSION))
        if not chemin:
            return False
        if not chemin.lower().endswith(EXTENSION):
            chemin += EXTENSION
        return self._ecrire(chemin)

    def _ecrire(self, chemin: str) -> bool:
        try:
            ecrit = self.doc.enregistrer(chemin)
        except ErreurEcriture as erreur:
            self._erreur_fichier(erreur)
            return False
        self._noter_recent(ecrit)
        self.noter("succes", tr("fichier.enregistre", nom=os.path.basename(ecrit)))
        return True

    def exporter_image(self, chemin: Optional[str] = None) -> bool:
        if not chemin:
            depart = os.path.splitext(self.doc.chemin or tr("fenetre.sans_titre"))[0] + ".png"
            chemin, _ = QFileDialog.getSaveFileName(self, tr("fichier.dialogue.image"), depart, "PNG (*.png);;SVG (*.svg)")
            if not chemin:
                return False
        if chemin.lower().endswith(".svg"):
            generateur = QSvgGenerator()
            generateur.setFileName(chemin)
            generateur.setSize(self.vue.size())
            generateur.setViewBox(self.vue.rect())
            generateur.setTitle(self.doc.mecanisme.titre or __app_name__)
            peintre = QPainter(generateur)
            self.vue.peindre(peintre)
            peintre.end()
            reussi = os.path.isfile(chemin)
        else:
            if not chemin.lower().endswith(".png"):
                chemin += ".png"
            reussi = self.vue.image(3.0).save(chemin)
        self.noter("succes" if reussi else "erreur", tr("fichier.image_exportee" if reussi else "fichier.export_impossible", nom=os.path.basename(chemin)))
        return reussi

    def exporter_resultats(self, cles: Optional[List[str]] = None, chemin: Optional[str] = None) -> bool:
        """Classeur Excel des grandeurs données (toutes si ``cles`` est vide), avec ses graphiques."""
        resultats = self.doc.resultats
        if resultats is None:
            return False
        if not chemin:
            depart = os.path.splitext(self.doc.chemin or tr("fenetre.sans_titre"))[0] + ".xlsx"
            chemin, _ = QFileDialog.getSaveFileName(self, tr("fichier.dialogue.excel"), depart, tr("fichier.filtre_excel"))
            if not chemin:
                return False
        if not chemin.lower().endswith(".xlsx"):
            chemin += ".xlsx"
        choisies = list(cles) if cles else list(resultats.canaux)
        m = self.doc.mecanisme
        unites = m.unites
        etude = m.etude
        informations = [
            (tr("excel.projet"), m.titre or self.doc.nom or tr("fenetre.sans_titre")),
            (tr("excel.auteur"), m.auteur),
            (tr("excel.etude"), tr(f"etude.type.{resultats.type_etude}")),
            (tr("excel.duree"), f"{float(resultats.temps[-1]) if resultats.nb_instants else 0.0:g} s"),
            (tr("excel.instants"), str(resultats.nb_instants)),
            (tr("excel.unites"), f"{unites.longueur}, {unites.angle}"),
            (tr("excel.mobilite"), str(resultats.mobilite_libre)),
            (tr("excel.hyperstatisme"), str(resultats.hyperstatisme)),
        ]
        if resultats.type_etude == "dynamique":
            informations.append((tr("excel.methode"), f"{resultats.methode or etude.methode} (rtol = {etude.precision:g})"))
        textes = Textes(
            feuille_resultats=tr("excel.feuille_resultats"),
            feuille_graphiques=tr("excel.feuille_graphiques"),
            feuille_informations=tr("excel.feuille_informations"),
            temps=tr("excel.temps"),
            informations=informations,
            messages_titre=tr("excel.messages"),
            messages=[texte_message_calcul(message) for message in resultats.messages],
        )
        libelles = {cle: self.courbes.libelle(cle, avec_unite=False) for cle in choisies}
        try:
            lignes = exporter_excel(resultats, chemin, choisies, unites, libelles, self.courbes.graphiques_excel(), textes)
        except ErreurEcriture as erreur:
            self._erreur_fichier(erreur)
            return False
        self.noter("succes", tr("fichier.excel_exporte", nom=os.path.basename(chemin), lignes=lignes, colonnes=len(choisies)))
        return True

    # -------------------------------------------------------------- photo de fond
    def importer_photo(self, chemin: Optional[str] = None) -> bool:
        """Place la photo d'un schéma sous le mécanisme, puis propose de l'étalonner."""
        if not chemin:
            depart = os.path.dirname(self.doc.chemin) if self.doc.chemin else ""
            chemin, _ = QFileDialog.getOpenFileName(self, tr("fichier.dialogue.photo"), depart, f"{tr('fichier.filtre_photo')} ({FORMATS_PHOTO})")
            if not chemin:
                return False
        image = QImage(chemin)
        if image.isNull():
            self.noter("erreur", tr("fichier.photo_illisible", nom=os.path.basename(chemin)))
            return False
        try:
            with open(chemin, "rb") as fichier:
                donnees = fichier.read()
        except OSError as erreur:
            self.noter("erreur", tr("fichier.photo_illisible", nom=os.path.basename(chemin)) + f" ({erreur.strerror})")
            return False
        nature = format_image(donnees)
        if nature is None or max(image.width(), image.height()) > COTE_MAX_PHOTO:
            # format exotique ou image démesurée : réencodée en JPEG, d'une taille raisonnable
            if max(image.width(), image.height()) > COTE_MAX_PHOTO:
                image = image.scaled(COTE_MAX_PHOTO, COTE_MAX_PHOTO, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            octets = QByteArray()
            tampon = QBuffer(octets)
            tampon.open(QIODevice.WriteOnly)
            image.convertToFormat(QImage.Format_RGB32).save(tampon, "JPEG", 90)
            donnees, nature = bytes(octets), "jpeg"
        vue = self.vue
        largeur = 0.8 * vue.width() / vue.echelle
        centre_x, centre_y = vue.monde(QPointF(vue.width() / 2.0, vue.height() / 2.0))
        hauteur = largeur * image.height() / max(image.width(), 1)
        fond = FondPlan(donnees, nature, image.width(), image.height(), centre_x - largeur / 2.0, centre_y - hauteur / 2.0, largeur, nom=os.path.basename(chemin))
        with self.doc.modification() as m:
            m.fond = fond
        self.doc.selectionner(Ref("fond", "fond"))
        self.vue.choisir_outil("etalonnage")
        self.noter("info", tr("fichier.photo_importee", nom=fond.nom))
        return True

    def detecter_formes(self) -> None:
        """Détection automatique des traits et des cercles de la photo de fond."""
        from ..vision import creer_solides, disponible
        from .dialogues.detection import DialogueDetection

        fond = self.doc.mecanisme.fond
        if fond is None:
            self.noter("avertissement", tr("outil.etalonnage.sans_photo"))
            return
        if not disponible():
            QMessageBox.information(self, __app_name__, tr("detection.indisponible"))
            return
        dialogue = DialogueDetection(fond, self)
        if dialogue.exec() != QDialog.Accepted or dialogue.detection is None:
            return
        with self.doc.modification() as m:
            nombres = creer_solides(m, m.fond, dialogue.detection, dialogue.barres.isChecked(), dialogue.disques.isChecked(), dialogue.pivots.isChecked())
        self.noter("succes", tr("detection.cree", barres=nombres[0], disques=nombres[1], pivots=nombres[2]))

    # ----------------------------------------------------------- aide et tutoriel
    def ouvrir_cours(self, fiche: str, section: str = "") -> None:
        """Montre une fiche de cours (à une section donnée) dans le panneau « Cours »."""
        self.docks["inspecteur"].show()
        self.montrer("cours")
        self.cours.afficher(fiche, section)

    def tutoriel(self, debut: int = 0) -> SuperpositionTutoriel:
        """Lance (ou relance) le tutoriel animé, par-dessus la fenêtre."""
        if self._tutoriel is not None:
            try:
                self._tutoriel.fermer()
            except RuntimeError:
                pass
        self.vue.choisir_outil("selection")
        self._tutoriel = SuperpositionTutoriel(self, debut=debut)
        self._tutoriel.termine.connect(self._tutoriel_termine)
        return self._tutoriel

    def _tutoriel_termine(self) -> None:
        self._tutoriel = None
        self.noter("info", tr("tutoriel.termine_message"))

    def accueillir(self) -> Optional[str]:
        """Fenêtre de bienvenue ; retourne le choix (``nouveau`` ou ``habitue``)."""
        reglages = self._reglages()
        masque = bool(reglages.value("accueil/masquer", False, bool)) if reglages is not None else False
        dialogue = DialogueAccueil(self, masque)
        dialogue.exec()
        if reglages is not None:
            reglages.setValue("accueil/masquer", dialogue.ne_plus_demander)
        if dialogue.choix == DialogueAccueil.NOUVEAU:
            self.tutoriel()
        elif dialogue.choix == DialogueAccueil.HABITUE:
            self.noter("info", tr("accueil_dialogue.bon_travail"))
        return dialogue.choix

    def accueil_au_demarrage(self) -> bool:
        """Vrai si la fenêtre de bienvenue doit s'ouvrir au lancement."""
        reglages = self._reglages()
        return reglages is not None and not bool(reglages.value("accueil/masquer", False, bool))

    # ------------------------------------------------------------------- calcul
    def lancer_etude(self) -> None:
        if self._calcul is not None:
            return
        self.lecteur.arreter()
        self._revision_calcul = self._revision
        self._calcul = Calcul(self.doc.mecanisme, self)
        self._calcul.progression.connect(self.etude.avancement)
        self._calcul.termine.connect(self._calcul_termine)
        self._calcul.echec.connect(self._calcul_echoue)
        self._calcul.interrompu.connect(self._calcul_interrompu)
        self._calcul.finished.connect(self._calcul_fini)
        self._calcul.finished.connect(self._calcul.deleteLater)
        self.etude.calcul_en_cours(True)
        self.etude.afficher_bilan(tr("etude.calcul_en_cours"))
        self._sur_etat()
        self._calcul.start()

    def arreter_calcul(self) -> None:
        if self._calcul is not None:
            self._calcul.arreter()

    def attendre_calcul(self, delai_ms: int = 60000) -> bool:
        """Attend la fin du calcul en cours (utile aux tests et à la fermeture)."""
        if self._calcul is None:
            return True
        return self._calcul.wait(delai_ms)

    def _calcul_fini(self) -> None:
        self._calcul = None
        self.etude.calcul_en_cours(False)
        self._sur_etat()

    def _calcul_interrompu(self) -> None:
        self.etude.afficher_bilan(tr("etude.interrompu"), "attention")
        self.noter("avertissement", tr("etude.interrompu"))

    def _calcul_echoue(self, erreur: ErreurCalcul) -> None:
        texte = texte_erreur_calcul(erreur)
        self.etude.afficher_bilan(texte, "erreur")
        self.noter("erreur", texte, 10000)

    def _calcul_termine(self, resultats: Resultats) -> None:
        if self._revision_calcul != self._revision:
            self.noter("avertissement", tr("etude.modele_modifie"))
            self.etude.afficher_bilan(tr("etude.modele_modifie"), "attention")
            return
        self.doc.definir_resultats(resultats)
        nature = tr(f"etude.type.{resultats.type_etude}")
        lignes = [tr("etude.bilan", type=nature, instants=resultats.nb_instants, duree=f"{resultats.duree_calcul:.2f}")]
        etat = "succes"
        for message in resultats.messages:
            texte = texte_message_calcul(message)
            lignes.append(texte)
            self.journal.ajouter(message.niveau, texte)
            if message.niveau == "avertissement":
                etat = "attention"
        self.etude.afficher_bilan("\n".join(lignes), etat)
        self.noter("succes" if etat == "succes" else "avertissement", lignes[0])
        self.vue.demander_ajustement()
        if resultats.nb_instants > 1:
            self.montrer("courbes")
            self.lecteur.lire()
        else:
            self.montrer("resultats")

    def chercher_equilibre(self) -> None:
        """Déplace le mécanisme vers une position d'équilibre stable."""
        modele = self.doc.mecanisme.copie()
        try:
            with np.errstate(all="ignore"):
                systeme = SystemeMecanique(modele)
                q, trouve = rechercher_equilibre(systeme, tolerance=modele.etude.tolerance)
        except ErreurCalcul as erreur:
            self.noter("erreur", texte_erreur_calcul(erreur))
            return
        except (np.linalg.LinAlgError, ArithmeticError) as erreur:
            self.noter("erreur", texte_erreur_calcul(ErreurCalcul("erreur_numerique", message=str(erreur))))
            return
        if not trouve or not np.all(np.isfinite(q)):
            self.noter("avertissement", tr("etude.equilibre_introuvable"))
            return
        with self.doc.modification():
            SystemeMecanique(self.doc.mecanisme).appliquer_au_modele(q)
        self.noter("succes", tr("etude.equilibre_trouve"))

    def adopter_configuration(self) -> None:
        """La position affichée devient la configuration initiale du modèle."""
        resultats, indice = self.doc.resultats, self.doc.indice
        if resultats is None:
            return
        instant = f"{self.doc.temps:.4g}"
        with self.doc.modification() as m:
            appliquer_resultats(m, resultats, indice)
        self.noter("info", tr("etude.configuration_adoptee", t=instant))

    # ---------------------------------------------------------------- fermeture
    def closeEvent(self, evenement: QCloseEvent) -> None:
        if not self._confirmer_abandon():
            evenement.ignore()
            return
        self.arreter_calcul()
        self.attendre_calcul(5000)
        self.lecteur.arreter()
        reglages = self._reglages()
        if reglages is not None:
            reglages.setValue("geometrie", self.saveGeometry())
            reglages.setValue("etat", self.saveState())
        evenement.accept()
