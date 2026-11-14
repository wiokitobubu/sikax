"""Export des résultats d'une étude dans un classeur Excel (.xlsx).

Les valeurs sont écrites comme de vrais nombres, et non comme du texte : Excel
les affiche avec la virgule ou le point selon les réglages de l'ordinateur,
sans aucun conflit de séparateur. Le classeur contient trois feuilles :

- **Résultats** : le temps puis une colonne par grandeur, en unités
  d'affichage, en-têtes figés en haut de l'écran ;
- **Graphiques** : des courbes Excel natives (position, vitesse, accélération,
  efforts, couples) qui pointent sur les colonnes de la première feuille ;
- **Informations** : le projet, l'étude, les unités et les messages du calcul.

Le module ne dépend pas de l'interface : les libellés lui sont fournis.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .. import __app_name__, __version__
from ..calcul.resultats import Resultats
from ..physique.unites import Unites
from .diagnostics import ErreurEcriture

CELLULES_MAX_MISE_EN_FORME = 400_000
"""Au-delà, le classeur est écrit en flux (plus rapide, sans mise en forme des colonnes)."""


@dataclass
class Graphique:
    """Courbe Excel : un titre, un titre d'axe vertical et les grandeurs tracées."""

    titre: str
    axe: str
    cles: List[str]


@dataclass
class Textes:
    """Textes du classeur, dans la langue de l'interface."""

    feuille_resultats: str = "Résultats"
    feuille_graphiques: str = "Graphiques"
    feuille_informations: str = "Informations"
    temps: str = "t (s)"
    informations: List[Tuple[str, str]] = field(default_factory=list)
    """Lignes (libellé, valeur) de la feuille d'informations."""
    messages_titre: str = "Messages du calcul"
    messages: List[str] = field(default_factory=list)


def _nombre(valeur: float) -> Optional[float]:
    """Une valeur non finie (point mort, grandeur indéfinie) devient une cellule vide."""
    valeur = float(valeur)
    return valeur if math.isfinite(valeur) else None


def exporter_excel(
    resultats: Resultats,
    chemin: str,
    cles: Optional[Sequence[str]] = None,
    unites: Optional[Unites] = None,
    libelles: Optional[Dict[str, str]] = None,
    graphiques: Sequence[Graphique] = (),
    textes: Optional[Textes] = None,
) -> int:
    """Écrit le classeur ; retourne le nombre de lignes de données.

    L'écriture passe par un fichier temporaire remplacé d'un seul coup : un
    classeur déjà ouvert ailleurs ou un disque plein ne laisse jamais de
    fichier à moitié écrit. Lève ``ErreurEcriture`` en cas d'échec.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.chart import Reference, ScatterChart, Series
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - dépendance livrée avec Sikax
        raise ErreurEcriture("module_absent", module="openpyxl") from exc

    unites = unites or Unites()
    textes = textes or Textes()
    libelles = libelles or {}
    choisies = [c for c in (cles if cles is not None else resultats.canaux) if c in resultats.canaux]
    colonnes = {cle: i + 2 for i, cle in enumerate(choisies)}
    facteurs = [unites.facteur(resultats.canaux[c].dimension) for c in choisies]
    nb = resultats.nb_instants
    en_flux = nb * (len(choisies) + 1) > CELLULES_MAX_MISE_EN_FORME

    classeur = Workbook(write_only=en_flux)
    if en_flux:
        feuille = classeur.create_sheet(textes.feuille_resultats)
    else:
        feuille = classeur.active
        feuille.title = textes.feuille_resultats

    entetes = [textes.temps]
    for cle, (_, symbole) in zip(choisies, facteurs):
        nom = libelles.get(cle, cle)
        entetes.append(f"{nom} ({symbole})" if symbole else nom)

    gras = Font(bold=True, color="FFFFFF")
    fond_entete = PatternFill("solid", fgColor="2563EB")
    bordure = Border(bottom=Side(style="thin", color="1D4FD7"))
    if en_flux:
        feuille.freeze_panes = "B2"
        feuille.append(entetes)
    else:
        feuille.append(entetes)
        for i, _ in enumerate(entetes, start=1):
            cellule = feuille.cell(row=1, column=i)
            cellule.font = gras
            cellule.fill = fond_entete
            cellule.border = bordure
            cellule.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        feuille.freeze_panes = "B2"
        feuille.row_dimensions[1].height = 34
    valeurs = [resultats.canaux[c].valeurs for c in choisies]
    for i in range(nb):
        ligne = [_nombre(resultats.temps[i])]
        for serie, (facteur, _) in zip(valeurs, facteurs):
            v = _nombre(serie[i] * facteur)
            ligne.append(None if v is None else v + 0.0)
        feuille.append(ligne)
    if not en_flux:
        for i, texte in enumerate(entetes, start=1):
            feuille.column_dimensions[get_column_letter(i)].width = max(11.0, min(34.0, 0.9 * len(texte) + 2.0))
        for ligne in feuille.iter_rows(min_row=2, max_row=nb + 1):
            for cellule in ligne:
                cellule.number_format = "0.000000" if cellule.column == 1 else "General"

    # -- graphiques natifs ---------------------------------------------------------
    utiles = [g for g in graphiques if any(c in colonnes for c in g.cles)]
    if utiles and nb > 1:
        planche = classeur.create_sheet(textes.feuille_graphiques)
        abscisses = Reference(feuille, min_col=1, min_row=2, max_row=nb + 1) if not en_flux else None
        for rang, graphique in enumerate(utiles):
            courbe = ScatterChart()
            courbe.title = graphique.titre
            courbe.style = 13
            courbe.x_axis.title = textes.temps
            courbe.y_axis.title = graphique.axe
            courbe.height, courbe.width = 8.0, 16.0
            courbe.legend.position = "b"
            for cle in graphique.cles:
                if cle not in colonnes:
                    continue
                colonne = colonnes[cle]
                donnees = Reference(feuille, min_col=colonne, min_row=1, max_row=nb + 1)
                if abscisses is None:
                    abscisses = Reference(feuille, min_col=1, min_row=2, max_row=nb + 1)
                serie = Series(donnees, abscisses, title_from_data=True)
                serie.marker.symbol = "none"
                serie.smooth = False
                courbe.series.append(serie)
            ligne, colonne = divmod(rang, 2)
            planche.add_chart(courbe, f"{('A', 'K')[colonne]}{1 + 17 * ligne}")

    # -- informations ---------------------------------------------------------------
    infos = classeur.create_sheet(textes.feuille_informations)
    lignes = [(__app_name__, __version__), ("", datetime.now().strftime("%Y-%m-%d %H:%M"))] + list(textes.informations)
    for libelle, valeur in lignes:
        infos.append([libelle, valeur])
    if textes.messages:
        infos.append([])
        infos.append([textes.messages_titre])
        for message in textes.messages:
            infos.append(["", message])
    if not en_flux:
        infos.column_dimensions["A"].width = 30
        infos.column_dimensions["B"].width = 90
        for ligne in infos.iter_rows(min_row=1, max_row=infos.max_row, max_col=1):
            for cellule in ligne:
                cellule.font = Font(bold=True)

    chemin = os.path.abspath(chemin)
    dossier = os.path.dirname(chemin)
    temporaire = None
    try:
        os.makedirs(dossier, exist_ok=True)
        descripteur, temporaire = tempfile.mkstemp(prefix=".sikax-", suffix=".xlsx", dir=dossier)
        os.close(descripteur)
        classeur.save(temporaire)
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
    return nb
