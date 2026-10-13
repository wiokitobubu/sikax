"""Point d'entrée de Sikax.

    python main.py                 ouvre l'application
    python main.py projet.sikax    ouvre un projet
    python main.py --theme clair   démarre en thème clair (le thème sombre est celui par défaut)
    python main.py --autotest      vérifie l'installation (sans fenêtre)
"""

import sys

from sikax.application import lancer

if __name__ == "__main__":
    sys.exit(lancer())
