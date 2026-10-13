"""Démarrage de l'application graphique."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, Qt, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __app_name__, __organisation__, __version__
from . import journal
from .chemins import dossier_exemples, icone_application
from .i18n import LANGUE_PAR_DEFAUT, tr, traducteur
from .ui.theme import THEME_PAR_DEFAUT, THEMES, theme


def _arguments(argv: List[str]) -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(prog=__app_name__, description="Modélisation et simulation de mécanismes plans.")
    analyseur.add_argument("fichier", nargs="?", help="projet .sikax à ouvrir")
    analyseur.add_argument("--langue", help="code de langue de l'interface (fr, en…)")
    analyseur.add_argument("--theme", choices=THEMES, help="thème de l'interface")
    analyseur.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    analyseur.add_argument("--autotest", action="store_true", help="vérifie l'installation sans ouvrir de fenêtre, puis quitte")
    return analyseur.parse_args(argv)


def creer_application(argv: Optional[List[str]] = None) -> QApplication:
    """Crée (ou retrouve) l'application Qt, avec son identité et son style."""
    existante = QApplication.instance()
    if existante is not None:
        return existante  # type: ignore[return-value]
    if sys.platform == "win32":
        # Sans cet identifiant, Windows regroupe la fenêtre sous l'icône de python.exe.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{__organisation__}.{__app_name__}")
        except (AttributeError, OSError):
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    application = QApplication(argv if argv is not None else sys.argv)
    application.setApplicationName(__app_name__)
    application.setApplicationDisplayName(__app_name__)
    application.setOrganizationName(__organisation__)
    application.setApplicationVersion(__version__)
    application.setStyle("Fusion")
    application.setWindowIcon(QIcon(str(icone_application())))
    return application


def installer_traduction_qt(application: QApplication, langue: str) -> None:
    """Traduit les textes fournis par Qt lui-même (boutons des dialogues standard…)."""
    ancien = getattr(application, "_traducteur_qt", None)
    if ancien is not None:
        application.removeTranslator(ancien)
    traducteur_qt = QTranslator(application)
    if traducteur_qt.load(QLocale(langue), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        application.installTranslator(traducteur_qt)
    application._traducteur_qt = traducteur_qt  # type: ignore[attr-defined]
    QLocale.setDefault(QLocale(langue))


def autotest() -> int:
    """Vérifie l'installation sans rien afficher. Code de retour 0 si tout réussit.

    1. Ressources : fichiers de langue, thèmes et exemples sont trouvés.
    2. Calcul : chaque exemple livré est chargé et son étude exécutée.
    3. Interface : Qt démarre, la fenêtre principale se construit (sans être
       montrée), ouvre un exemple, calcule et produit une image du schéma.

    C'est le contrôle exécuté sur la distribution après sa fabrication.
    """
    from .calcul import lancer_etude
    from .chemins import dossier_locales, dossier_themes
    from .fichiers import EXTENSION, charger

    echecs = 0

    def verifier(condition: bool, texte: str) -> None:
        nonlocal echecs
        echecs += 0 if condition else 1
        print(f"{'OK    ' if condition else 'ÉCHEC '} {texte}")

    dossier = dossier_exemples()
    fichiers = sorted(dossier.glob(f"*{EXTENSION}")) if dossier.is_dir() else []
    verifier(traducteur.charger(LANGUE_PAR_DEFAUT), f"langue par défaut dans {dossier_locales()}")
    verifier((dossier_themes() / "style.qss").is_file(), f"thèmes dans {dossier_themes()}")
    verifier(bool(fichiers), f"{len(fichiers)} exemples dans {dossier}")
    verifier(icone_application().is_file(), f"icône {icone_application().name}")

    for fichier in fichiers:
        try:
            etude = lancer_etude(charger(str(fichier)).mecanisme)
            verifier(etude.complet, f"{fichier.name:34s} {etude.type_etude:12s} {etude.nb_instants:5d} instants")
        except Exception as erreur:  # le but est de tout signaler
            verifier(False, f"{fichier.name} : {type(erreur).__name__} : {erreur}")

    try:
        application = creer_application([])
        theme.appliquer("sombre")
        from .ui.fenetre_principale import FenetrePrincipale

        fenetre = FenetrePrincipale(persistant=False)
        fenetre.resize(1280, 800)
        ouvert = bool(fichiers) and fenetre.ouvrir_exemple(str(fichiers[0]))
        fenetre.lancer_etude()
        fenetre.attendre_calcul()
        application.processEvents()
        fenetre.lecteur.arreter()
        image = fenetre.vue.image(1.0)
        verifier(ouvert and fenetre.doc.resultats is not None, "interface : exemple ouvert et calculé dans la fenêtre")
        verifier(not image.isNull() and image.width() > 0, f"interface : schéma dessiné ({image.width()} × {image.height()} px)")
        verifier(not traducteur.cles_manquantes, "interface : tous les textes sont traduits")
        fenetre.doc.modifie = False
        fenetre.close()
    except Exception as erreur:
        verifier(False, f"interface : {type(erreur).__name__} : {erreur}")

    print("Tout est en ordre." if not echecs else f"{echecs} vérification(s) en échec.")
    return 1 if echecs else 0


def lancer(argv: Optional[List[str]] = None) -> int:
    """Point d'entrée : ouvre la fenêtre principale et exécute la boucle d'événements."""
    options = _arguments(list(sys.argv[1:] if argv is None else argv))
    journal.configurer()
    if options.autotest:
        return autotest()

    application = creer_application()
    reglages = QSettings(__organisation__, __app_name__)
    langue = options.langue or str(reglages.value("langue", LANGUE_PAR_DEFAUT))
    if not traducteur.charger(langue):
        langue = LANGUE_PAR_DEFAUT
    installer_traduction_qt(application, traducteur.langue)
    traducteur.abonner(lambda: installer_traduction_qt(application, traducteur.langue))
    theme.appliquer(options.theme or str(reglages.value("theme", THEME_PAR_DEFAUT)))

    from .ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale()

    def afficher_erreur(titre: str, detail: str) -> None:
        boite = QMessageBox(fenetre)
        boite.setIcon(QMessageBox.Critical)
        boite.setWindowTitle(__app_name__)
        boite.setText(tr("erreur.imprevue"))
        chemin = journal.chemin_journal()
        boite.setInformativeText(f"{titre}\n\n{tr('erreur.journal', chemin=str(chemin))}" if chemin else titre)
        boite.setDetailedText(detail)
        boite.exec()

    journal.installer_capture(afficher_erreur)
    fenetre.show()
    if options.fichier:
        fenetre.ouvrir(options.fichier)
    return application.exec()
