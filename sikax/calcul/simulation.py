"""Lancement d'une étude complète sur un mécanisme."""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from ..modele.mecanisme import Mecanisme
from .cinematique import analyse_cinematique
from .dynamique import analyse_dynamique
from .enregistreur import instants
from .erreurs import ErreurCalcul
from .resultats import Resultats
from .statique import analyse_statique
from .systeme import SystemeMecanique

Progression = Optional[Callable[[float], None]]
Annulation = Optional[Callable[[], bool]]

INSTANTS_MAX = 200_000
"""Nombre maximal d'instants calculés : au-delà, la mémoire ne suit plus."""


def lancer_etude(
    mecanisme: Mecanisme,
    progression: Progression = None,
    annule: Annulation = None,
) -> Resultats:
    """Exécute l'étude décrite par ``mecanisme.etude`` et retourne ses résultats.

    Le calcul travaille sur une copie : le modèle reçu n'est jamais modifié et
    peut continuer d'être édité pendant un calcul lancé en arrière-plan.
    """
    modele = mecanisme.copie()
    erreurs = modele.erreurs()
    if erreurs:
        premiere = erreurs[0]
        raise ErreurCalcul("modele_invalide", probleme=premiere.code, objet=premiere.objet, nombre=len(erreurs))
    if not modele.solides_mobiles():
        raise ErreurCalcul("aucun_solide")

    debut = time.perf_counter()
    etude = modele.etude
    if etude.type != "statique" and etude.duree / etude.pas > INSTANTS_MAX:
        raise ErreurCalcul("trop_d_instants", nombre=int(etude.duree / etude.pas), maximum=INSTANTS_MAX)
    try:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            systeme = SystemeMecanique(modele)
            if etude.type == "statique":
                resultats = analyse_statique(systeme, 0.0, etude.tolerance)
            else:
                temps = instants(etude.duree, etude.pas)
                if etude.type == "cinematique":
                    resultats = analyse_cinematique(systeme, temps, etude.inertie, etude.tolerance, progression, annule)
                else:
                    resultats = analyse_dynamique(systeme, temps, etude.precision, etude.tolerance, progression, annule)
    except (np.linalg.LinAlgError, FloatingPointError, OverflowError, ZeroDivisionError) as exc:
        raise ErreurCalcul("erreur_numerique", message=str(exc)) from exc
    if not all(np.all(np.isfinite(canal.valeurs)) for canal in resultats.canaux.values()):
        raise ErreurCalcul("erreur_numerique", message="valeurs non finies")
    resultats.duree_calcul = time.perf_counter() - debut
    return resultats
