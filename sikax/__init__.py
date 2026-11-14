"""Sikax — modélisation, validation et simulation de mécanismes plans.

Organisation du paquet (inspirée d'OpenMeca : Core / Geom / Item / Physic / Gui) :

- ``geometrie`` : vecteurs, rotations, repères ;
- ``physique``  : torseurs et unités ;
- ``util``      : expressions mathématiques sûres, outils divers ;
- ``modele``    : solides, points, liaisons, actions mécaniques, moteurs ;
- ``calcul``    : moteur de calcul (topologie, cinématique, PFS, PFD) ;
- ``fichiers``  : lecture/écriture robuste des projets ``.sikax`` ;
- ``i18n``      : localisation (français par défaut) ;
- ``ui``        : interface graphique Qt (thèmes clair et sombre).

Les couches ``modele``, ``calcul`` et ``fichiers`` n'importent jamais Qt : elles
sont utilisables seules, en script ou dans des tests.
"""

__version__ = "2.0.0"
__app_name__ = "Sikax"
__organisation__ = "Sikax"

__all__ = ["__version__", "__app_name__", "__organisation__"]
