"""Journal technique de l'application et capture des erreurs imprévues.

Le journal est écrit dans le dossier de données de l'utilisateur
(``%LOCALAPPDATA%\\Sikax`` sous Windows). Une exception non interceptée y est
consignée avec sa trace, puis signalée à l'utilisateur par un message, au
lieu de fermer brutalement l'application.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

NOM = "sikax"
_chemin: Optional[Path] = None


def dossier_donnees() -> Path:
    """Dossier inscriptible propre à l'utilisateur."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Sikax"


def chemin_journal() -> Optional[Path]:
    return _chemin


def configurer() -> logging.Logger:
    """Active le journal dans un fichier tournant ; sans effet si le dossier est inaccessible."""
    global _chemin
    journal = logging.getLogger(NOM)
    if journal.handlers:
        return journal
    journal.setLevel(logging.INFO)
    try:
        dossier = dossier_donnees()
        dossier.mkdir(parents=True, exist_ok=True)
        _chemin = dossier / "sikax.log"
        gestionnaire = RotatingFileHandler(_chemin, maxBytes=512_000, backupCount=2, encoding="utf-8")
        gestionnaire.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        journal.addHandler(gestionnaire)
    except OSError:
        _chemin = None
        journal.addHandler(logging.NullHandler())
    return journal


def installer_capture(afficher=None) -> None:
    """Consigne toute exception non interceptée et la transmet à ``afficher(titre, détail)``."""
    journal = logging.getLogger(NOM)

    def capture(type_erreur, erreur, trace) -> None:
        if issubclass(type_erreur, KeyboardInterrupt):
            sys.__excepthook__(type_erreur, erreur, trace)
            return
        detail = "".join(traceback.format_exception(type_erreur, erreur, trace))
        journal.error("Erreur imprévue\n%s", detail)
        if sys.stderr is not None:
            sys.stderr.write(detail)
        if afficher is not None:
            try:
                afficher(f"{type_erreur.__name__} : {erreur}", detail)
            except Exception:  # l'affichage de l'erreur ne doit jamais en provoquer une autre
                pass

    sys.excepthook = capture
