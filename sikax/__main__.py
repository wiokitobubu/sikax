"""Permet ``python -m sikax``."""

import sys

from .application import lancer

if __name__ == "__main__":
    sys.exit(lancer())
