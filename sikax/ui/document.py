"""Le document ouvert : modèle, fichier, sélection, historique et résultats.

``Document`` est le point de rencontre de l'interface (rôle du ``System``,
du ``SelectionManager`` et de l'``HistoricManager`` d'OpenMeca). Les panneaux
ne se parlent pas entre eux : ils modifient le document et réagissent à ses
signaux.

Toute modification du modèle passe par ``modification()`` ::

    with document.modification():
        document.mecanisme.creer_solide()

ce qui enregistre l'état précédent pour Annuler/Rétablir, marque le projet
comme modifié, invalide les résultats et prévient les vues.
"""

from __future__ import annotations

import math
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from ..calcul import Resultats
from ..fichiers import ResultatLecture, charger, enregistrer
from ..modele import Mecanisme

HISTORIQUE_MAX = 200


@dataclass(frozen=True)
class Ref:
    """Désigne un objet du modèle. Pour un point : ``id`` est le solide, ``sous`` le point."""

    genre: str
    id: str
    sous: str = ""


class Document(QObject):
    modele_change = Signal()
    selection_change = Signal()
    resultats_change = Signal()
    temps_change = Signal(int)
    etat_change = Signal()
    """Titre, état « modifié » ou disponibilité d'Annuler/Rétablir."""

    def __init__(self) -> None:
        super().__init__()
        self.mecanisme = Mecanisme()
        self.chemin: Optional[str] = None
        self.modifie = False
        self.selection: Optional[Ref] = None
        self.resultats: Optional[Resultats] = None
        self.indice = 0
        self._passe: List[Mecanisme] = []
        self._futur: List[Mecanisme] = []
        self._fusion = ""
        self._profondeur = 0

    # ------------------------------------------------------------ historique
    @contextmanager
    def modification(self, fusion: str = "") -> Iterator[Mecanisme]:
        """Encadre une modification du modèle.

        ``fusion`` regroupe en une seule étape d'annulation les modifications
        consécutives portant la même clé (glisser d'un point, saisie continue).
        """
        racine = self._profondeur == 0
        instantane = None
        if racine and not (fusion and fusion == self._fusion and self._passe):
            instantane = self.mecanisme.copie()
        self._profondeur += 1
        try:
            yield self.mecanisme
        except BaseException:
            # opération refusée en cours de route : le modèle retrouve son état d'avant
            self._profondeur -= 1
            if racine and instantane is not None:
                self.mecanisme = instantane
                self._apres_changement()
            raise
        self._profondeur -= 1
        if racine:
            if instantane is not None:
                self._passe.append(instantane)
                del self._passe[:-HISTORIQUE_MAX]
            self._fusion = fusion
            self._futur.clear()
            self.modifie = True
            self._apres_changement()

    def terminer_fusion(self) -> None:
        """La prochaine modification ouvrira une nouvelle étape d'annulation."""
        self._fusion = ""

    def _apres_changement(self) -> None:
        # L'état est d'abord rendu cohérent, les vues ne sont prévenues qu'ensuite :
        # aucune ne doit voir une sélection qui désigne un objet disparu.
        selection_perdue = self.selection is not None and self.objet(self.selection) is None
        resultats_perdus = self.resultats is not None
        if selection_perdue:
            self.selection = None
        if resultats_perdus:
            self.resultats = None
            self.indice = 0
        if selection_perdue:
            self.selection_change.emit()
        if resultats_perdus:
            self.resultats_change.emit()
        self.modele_change.emit()
        self.etat_change.emit()

    @property
    def peut_annuler(self) -> bool:
        return bool(self._passe)

    @property
    def peut_retablir(self) -> bool:
        return bool(self._futur)

    def annuler(self) -> None:
        if not self._passe:
            return
        self._futur.append(self.mecanisme)
        self.mecanisme = self._passe.pop()
        self._fusion = ""
        self.modifie = True
        self._apres_changement()

    def retablir(self) -> None:
        if not self._futur:
            return
        self._passe.append(self.mecanisme)
        self.mecanisme = self._futur.pop()
        self._fusion = ""
        self.modifie = True
        self._apres_changement()

    # --------------------------------------------------------------- fichiers
    def _remplacer(self, mecanisme: Mecanisme, chemin: Optional[str]) -> None:
        self.mecanisme = mecanisme
        self.chemin = chemin
        self.modifie = False
        self._passe.clear()
        self._futur.clear()
        self._fusion = ""
        self.selection = None
        self.resultats = None
        self.indice = 0
        self.resultats_change.emit()
        self.selection_change.emit()
        self.modele_change.emit()
        self.etat_change.emit()

    def nouveau(self, mecanisme: Optional[Mecanisme] = None) -> None:
        self._remplacer(mecanisme if mecanisme is not None else Mecanisme(), None)

    def ouvrir(self, chemin: str, tolerant: bool = False) -> ResultatLecture:
        """Ouvre un projet. Lève ``ErreurLecture`` si le fichier est refusé."""
        resultat = charger(chemin, tolerant)
        self.adopter(resultat)
        return resultat

    def adopter(self, resultat: ResultatLecture) -> None:
        """Remplace le document par le projet qui vient d'être lu."""
        self._remplacer(resultat.mecanisme, resultat.chemin or None)
        if resultat.rapport.erreurs:
            # ouvert en écartant des éléments : le projet diffère de son fichier
            self.modifie = True
            self.etat_change.emit()

    def enregistrer(self, chemin: Optional[str] = None) -> str:
        """Enregistre le projet. Lève ``ErreurEcriture`` en cas d'échec."""
        cible = chemin or self.chemin
        if not cible:
            raise ValueError("aucun chemin de fichier")
        enregistrer(self.mecanisme, cible)
        self.chemin = os.path.abspath(cible)
        self.modifie = False
        self.etat_change.emit()
        return self.chemin

    @property
    def nom(self) -> str:
        return os.path.basename(self.chemin) if self.chemin else ""

    # -------------------------------------------------------------- sélection
    def objet(self, ref: Optional[Ref]) -> Any:
        """Objet du modèle désigné par la référence, ou ``None`` s'il n'existe plus."""
        if ref is None:
            return None
        m = self.mecanisme
        if ref.genre == "solide":
            return m.solides.get(ref.id)
        if ref.genre == "point":
            solide = m.solides.get(ref.id)
            return solide.points.get(ref.sous) if solide else None
        if ref.genre == "liaison":
            return m.liaisons.get(ref.id)
        if ref.genre == "action":
            return m.actions.get(ref.id)
        if ref.genre == "moteur":
            return m.moteurs.get(ref.id)
        return None

    def selectionner(self, ref: Optional[Ref]) -> None:
        if ref is not None and self.objet(ref) is None:
            ref = None
        if ref != self.selection:
            self.selection = ref
            self.selection_change.emit()

    def supprimer(self, ref: Optional[Ref]) -> bool:
        """Supprime l'objet désigné (et ce qui en dépend). Retourne vrai si quelque chose a changé."""
        if ref is None or self.objet(ref) is None:
            return False
        with self.modification() as m:
            if ref.genre == "solide":
                m.supprimer_solide(ref.id)
            elif ref.genre == "point":
                m.supprimer_point(ref.id, ref.sous)
            elif ref.genre == "liaison":
                m.supprimer_liaison(ref.id)
            elif ref.genre == "action":
                m.supprimer_action(ref.id)
            elif ref.genre == "moteur":
                m.supprimer_moteur(ref.id)
        return True

    # -------------------------------------------------------------- résultats
    def definir_resultats(self, resultats: Optional[Resultats]) -> None:
        self.resultats = resultats
        self.indice = 0
        self.resultats_change.emit()
        self.temps_change.emit(0)

    def definir_indice(self, indice: int) -> None:
        if self.resultats is None:
            return
        indice = max(0, min(int(indice), self.resultats.nb_instants - 1))
        if indice != self.indice:
            self.indice = indice
            self.temps_change.emit(indice)

    @property
    def temps(self) -> float:
        if self.resultats is None or self.resultats.nb_instants == 0:
            return 0.0
        return float(self.resultats.temps[self.indice])

    # ------------------------------------------------- configuration affichée
    def pose(self, solide_id: str) -> Tuple[float, float, float]:
        """Pose à dessiner : celle des résultats à l'instant courant, sinon celle du modèle."""
        if self.resultats is not None and self.resultats.nb_instants:
            calculee = self.resultats.pose(solide_id, self.indice)
            if calculee is not None:
                return calculee
        pose = self.mecanisme.solides[solide_id].pose
        return (pose.x, pose.y, pose.angle)

    def position(self, solide_id: str, point_id: str) -> Tuple[float, float]:
        """Position globale d'un point dans la configuration affichée."""
        point = self.mecanisme.solides[solide_id].points[point_id]
        return self.vers_global(solide_id, point.x, point.y)

    def vers_global(self, solide_id: str, x: float, y: float) -> Tuple[float, float]:
        ox, oy, angle = self.pose(solide_id)
        c, s = math.cos(angle), math.sin(angle)
        return (ox + c * x - s * y, oy + s * x + c * y)
