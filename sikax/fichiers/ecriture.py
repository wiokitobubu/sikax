"""Écriture des projets ``.sikax``.

L'enregistrement est atomique : le document est écrit dans un fichier
temporaire du même dossier, synchronisé sur le disque, puis substitué à
l'ancien fichier en une seule opération. Une coupure de courant ou un
plantage pendant l'écriture ne peut donc pas laisser un projet tronqué.
L'ancienne version est conservée à côté sous le nom ``<fichier>.bak``.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .. import __app_name__, __version__
from ..modele.mecanisme import Mecanisme
from .diagnostics import ErreurEcriture
from .format import DIMENSION, FORMAT, VERSION


def mecanisme_vers_dict(mecanisme: Mecanisme, horodatage: Optional[str] = None) -> Dict[str, Any]:
    """Représentation sérialisable du mécanisme (structure du fichier)."""
    solides = []
    for solide in mecanisme.solides.values():
        solides.append(
            {
                "id": solide.id,
                "nom": solide.nom,
                "bati": solide.bati,
                "couleur": solide.couleur,
                "pose": {"x": solide.pose.x, "y": solide.pose.y, "angle": solide.pose.angle},
                "points": [{"id": p.id, "nom": p.nom, "x": p.x, "y": p.y} for p in solide.points.values()],
                "segments": [[a, b] for a, b in solide.segments],
                "inertie": {
                    "masse": solide.inertie.masse,
                    "g": [solide.inertie.gx, solide.inertie.gy],
                    "jz": solide.inertie.jz,
                },
            }
        )

    liaisons = []
    for liaison in mecanisme.liaisons.values():
        element = {
            "id": liaison.id,
            "nom": liaison.nom,
            "type": liaison.type,
            "solide_a": liaison.solide_a,
            "point_a": liaison.point_a,
            "solide_b": liaison.solide_b,
            "point_b": liaison.point_b,
            "modele_spatial": liaison.modele_spatial,
        }
        element.update(liaison.parametres())
        liaisons.append(element)

    actions = []
    for action in mecanisme.actions.values():
        element = {"id": action.id, "nom": action.nom, "type": action.type, "actif": action.actif}
        for attribut in ("solide", "point", "solide_a", "point_a", "solide_b", "point_b", "repere"):
            if hasattr(action, attribut):
                element[attribut] = getattr(action, attribut)
        element.update(action.parametres())
        actions.append(element)

    moteurs = [
        {
            "id": moteur.id,
            "nom": moteur.nom,
            "liaison": moteur.liaison,
            "relatif": moteur.relatif,
            "actif": moteur.actif,
            "loi": {"type": moteur.loi.type, "parametres": dict(moteur.loi.parametres)},
        }
        for moteur in mecanisme.moteurs.values()
    ]

    etude = mecanisme.etude
    return {
        "format": FORMAT,
        "version": VERSION,
        "application": {"nom": __app_name__, "version": __version__},
        "dimension": DIMENSION,
        "meta": {
            "titre": mecanisme.titre,
            "auteur": mecanisme.auteur,
            "description": mecanisme.description,
            "modifie_le": horodatage if horodatage is not None else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "unites": {"longueur": mecanisme.unites.longueur, "angle": mecanisme.unites.angle},
        "solides": solides,
        "liaisons": liaisons,
        "actions": actions,
        "moteurs": moteurs,
        "etude": {
            "type": etude.type,
            "duree": etude.duree,
            "pas": etude.pas,
            "pesanteur": etude.pesanteur,
            "gravite": [etude.gx, etude.gy],
            "inertie": etude.inertie,
            "tolerance": etude.tolerance,
            "precision": etude.precision,
        },
        "affichage": dict(mecanisme.affichage),
    }


def vers_json(mecanisme: Mecanisme, horodatage: Optional[str] = None) -> str:
    """Texte JSON du projet. Refuse les valeurs non finies (NaN, infini)."""
    try:
        return json.dumps(mecanisme_vers_dict(mecanisme, horodatage), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except (ValueError, TypeError) as exc:
        raise ErreurEcriture("donnees_invalides", message=str(exc)) from exc


def enregistrer(mecanisme: Mecanisme, chemin: str, sauvegarde: bool = True) -> None:
    """Enregistre le projet de façon atomique.

    Si ``sauvegarde`` est vrai et que le fichier existe déjà, sa version
    précédente est copiée dans ``<chemin>.bak`` avant d'être remplacée.
    """
    texte = vers_json(mecanisme)
    chemin = os.path.abspath(chemin)
    dossier = os.path.dirname(chemin)
    temporaire = None
    try:
        os.makedirs(dossier, exist_ok=True)
        descripteur, temporaire = tempfile.mkstemp(prefix=".sikax-", suffix=".tmp", dir=dossier)
        with os.fdopen(descripteur, "w", encoding="utf-8", newline="\n") as fichier:
            fichier.write(texte)
            fichier.flush()
            os.fsync(fichier.fileno())
        if sauvegarde and os.path.isfile(chemin):
            try:
                shutil.copy2(chemin, chemin + ".bak")
            except OSError:
                pass  # une copie de secours impossible ne doit pas empêcher d'enregistrer
        os.replace(temporaire, chemin)
        temporaire = None
    except OSError as exc:
        raise ErreurEcriture("ecriture_impossible", chemin=chemin, message=exc.strerror or str(exc)) from exc
    finally:
        if temporaire is not None:
            try:
                os.remove(temporaire)
            except OSError:
                pass
