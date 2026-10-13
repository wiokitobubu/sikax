"""Configuration commune des tests."""

import os
import sys
import traceback
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# Les tests d'interface tournent sans écran.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def aucune_erreur_silencieuse():
    """Fait échouer le test si une exception a été levée dans un gestionnaire Qt.

    Qt ne propage pas les exceptions Python levées dans ses événements : il les
    affiche et continue. Sans cette garde, un test pourrait réussir alors
    qu'une erreur s'est produite en chemin.
    """
    erreurs = []
    ancien = sys.excepthook
    sys.excepthook = lambda t, e, tb: erreurs.append("".join(traceback.format_exception(t, e, tb)))
    yield
    sys.excepthook = ancien
    assert not erreurs, "exception levée dans un gestionnaire Qt :\n" + "\n".join(erreurs)
