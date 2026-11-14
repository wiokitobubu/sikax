"""Le mécanisme : solides, liaisons, actions mécaniques, moteurs et étude.

``Mecanisme`` est le conteneur du modèle (l'équivalent du ``System``
d'OpenMeca). Il garantit les invariants simples (un bâti unique ``S0`` de
pose nulle, identifiants uniques) et propose les opérations de construction
et de suppression en cascade utilisées par l'interface et par les scripts.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..geometrie import Pose
from ..geometrie.vecteurs import Vec2
from ..physique.unites import Unites
from ..util.expression import ErreurExpression, compiler
from .actions import ActionMecanique, Couple, Force, Ressort
from .contacts import Contact, contact_came_plateau, contact_came_point, contact_cremaillere, contact_roues
from .etude import Etude
from .fond import FondPlan
from .liaisons import Came, Encastrement, Engrenage, Glissiere, Liaison, Pivot, classe_liaison
from .lois import LoiMouvement
from .moteur import Moteur
from .solide import COULEUR_BATI, COULEURS_SOLIDES, ID_BATI, Cercle, Point, Solide

NOMS_LIAISONS = {
    "pivot": "Pivot",
    "glissiere": "Glissière",
    "encastrement": "Encastrement",
    "ponctuelle": "Ponctuelle",
    "engrenage": "Engrenage",
    "came": "Came",
}

Position = Callable[[str, str], Vec2]
Orientation = Callable[[str], float]

# Au-delà, une valeur n'a plus de sens physique et ferait déborder les calculs.
VALEUR_MAX = 1e15

AFFICHAGE_PAR_DEFAUT: Dict[str, Any] = {
    "grille": True,
    "pas_grille": 0.01,
    "aimantation": True,
    "noms_points": True,
    "noms_liaisons": False,
    "centres_gravite": True,
    "echelle_forces": 0.0,  # 0 = automatique
}


@dataclass(frozen=True)
class Probleme:
    """Anomalie détectée par ``Mecanisme.verifier``."""

    code: str
    gravite: str  # "erreur" ou "avertissement"
    objet: str
    details: Tuple[Tuple[str, Any], ...] = ()

    def parametres(self) -> Dict[str, Any]:
        return dict(self.details)


def _numero(identifiant: str, prefixe: str) -> int:
    reste = identifiant[len(prefixe):]
    return int(reste) if identifiant.startswith(prefixe) and reste.isdigit() else 0


@dataclass
class Mecanisme:
    titre: str = ""
    auteur: str = ""
    description: str = ""
    unites: Unites = field(default_factory=Unites)
    solides: Dict[str, Solide] = field(default_factory=dict)
    liaisons: Dict[str, Liaison] = field(default_factory=dict)
    actions: Dict[str, ActionMecanique] = field(default_factory=dict)
    moteurs: Dict[str, Moteur] = field(default_factory=dict)
    etude: Etude = field(default_factory=Etude)
    affichage: Dict[str, Any] = field(default_factory=lambda: dict(AFFICHAGE_PAR_DEFAUT))
    fond: Optional[FondPlan] = None
    """Photo d'un schéma affichée sous le mécanisme (voir ``sikax.modele.fond``)."""

    def __post_init__(self) -> None:
        if ID_BATI not in self.solides:
            bati = Solide(ID_BATI, "Bâti", bati=True, couleur=COULEUR_BATI)
            self.solides = {ID_BATI: bati, **self.solides}

    # ------------------------------------------------------------------ accès
    @property
    def bati(self) -> Solide:
        return self.solides[ID_BATI]

    def solide(self, solide_id: str) -> Solide:
        try:
            return self.solides[solide_id]
        except KeyError:
            raise KeyError(f"solide inconnu : « {solide_id} »") from None

    def solides_mobiles(self) -> List[Solide]:
        return [s for s in self.solides.values() if not s.bati]

    def liaison(self, liaison_id: str) -> Liaison:
        try:
            return self.liaisons[liaison_id]
        except KeyError:
            raise KeyError(f"liaison inconnue : « {liaison_id} »") from None

    def point_global(self, solide_id: str, point_id: str) -> Vec2:
        return self.solide(solide_id).position_globale(point_id)

    def liaisons_du_solide(self, solide_id: str) -> List[Liaison]:
        return [l for l in self.liaisons.values() if l.concerne(solide_id)]

    def moteur_de_liaison(self, liaison_id: str) -> Optional[Moteur]:
        for moteur in self.moteurs.values():
            if moteur.liaison == liaison_id:
                return moteur
        return None

    def angle_axe_global(self, liaison: Liaison) -> float:
        """Direction de l'axe d'une liaison dans le repère global (0 si sans axe).

        Pour un engrenage ou une came, c'est la direction du mouvement relatif
        libre au point de contact.
        """
        if liaison.CONTACT:
            return self.contact(liaison).angle_glissement
        if not liaison.A_UN_AXE:
            return 0.0
        return self.solide(liaison.solide_a).pose.angle + getattr(liaison, "angle_axe", 0.0)

    def position_liaison(self, liaison: Liaison) -> Vec2:
        """Point de réduction du torseur de la liaison (le point porté par B, ou le point de contact)."""
        if liaison.CONTACT:
            return self.contact(liaison).point
        return self.point_global(liaison.solide_b, liaison.point_b)

    def contact(self, liaison: Liaison, position: Optional[Position] = None, orientation: Optional[Orientation] = None) -> Contact:
        """Géométrie du contact d'un engrenage ou d'une came.

        ``position(solide, point)`` et ``orientation(solide)`` donnent la
        configuration à utiliser : par défaut celle du modèle ; la vue passe la
        configuration animée.
        """
        position = position or self.point_global
        orientation = orientation or (lambda sid: self.solide(sid).pose.angle)
        if isinstance(liaison, Engrenage):
            oa = position(liaison.solide_a, liaison.point_a)
            ob = position(liaison.solide_b, liaison.point_b)
            if liaison.cremaillere:
                return contact_cremaillere(liaison.rayon_primitif_a(), oa, ob, orientation(liaison.solide_b) + liaison.angle_axe)
            return contact_roues(liaison.z_a, liaison.z_b, liaison.nature == "interieur", liaison.module, oa, ob)
        if isinstance(liaison, Came):
            cercle = self.solide(liaison.solide_a).cercle(liaison.cercle)
            centre = position(liaison.solide_a, cercle.centre)
            p = position(liaison.solide_b, liaison.point_b)
            if liaison.nature == "plat":
                return contact_came_plateau(centre, cercle.rayon, p, orientation(liaison.solide_b) + liaison.angle_axe)
            return contact_came_point(centre, cercle.rayon, p)
        raise ValueError(f"la liaison « {liaison.nom} » n'est pas une liaison de contact")

    def est_vide(self) -> bool:
        return (
            len(self.solides) == 1
            and not self.bati.points
            and not self.liaisons
            and not self.actions
            and not self.moteurs
            and self.fond is None
        )

    def copie(self) -> "Mecanisme":
        return copy.deepcopy(self)

    # ---------------------------------------------------------- identifiants
    @staticmethod
    def _prochain_id(prefixe: str, existants: Iterable[str]) -> str:
        return f"{prefixe}{max((_numero(i, prefixe) for i in existants), default=0) + 1}"

    def prochain_nom_point(self) -> str:
        """Prochaine lettre libre : A, B, …, Z, A1, B1, …"""
        pris = {p.nom for s in self.solides.values() for p in s.points.values()}
        tour = 0
        while True:
            for lettre in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                nom = lettre if tour == 0 else f"{lettre}{tour}"
                if nom not in pris:
                    return nom
            tour += 1

    def _nom_libre(self, base: str, pris: Iterable[str]) -> str:
        pris = set(pris)
        if base not in pris:
            return base
        k = 2
        while f"{base} ({k})" in pris:
            k += 1
        return f"{base} ({k})"

    # --------------------------------------------------------------- solides
    def creer_solide(
        self,
        nom: Optional[str] = None,
        couleur: Optional[str] = None,
        x: float = 0.0,
        y: float = 0.0,
        angle: float = 0.0,
    ) -> Solide:
        sid = self._prochain_id("S", self.solides)
        numero = _numero(sid, "S")
        solide = Solide(
            sid,
            nom or f"Solide {numero}",
            couleur=couleur or COULEURS_SOLIDES[(numero - 1) % len(COULEURS_SOLIDES)],
            pose=Pose(x, y, angle),
        )
        self.solides[sid] = solide
        return solide

    def creer_point(
        self,
        solide_id: str,
        gx: float,
        gy: float,
        nom: Optional[str] = None,
        relier_a: Optional[str] = None,
    ) -> Point:
        """Ajoute au solide un point donné par ses coordonnées globales.

        Sans nom imposé, le point reprend le nom d'un point d'un autre solide
        situé au même endroit (les deux points d'une articulation portent la
        même lettre), sinon la prochaine lettre libre.
        """
        solide = self.solide(solide_id)
        if nom is None:
            voisins = [p for s, p in self.points_en(gx, gy, 1e-9) if s.id != solide_id]
            nom = voisins[0].nom if voisins else self.prochain_nom_point()
        x, y = solide.pose.vers_local(gx, gy)
        point = solide.ajouter_point(nom, x, y)
        if relier_a is not None:
            solide.ajouter_segment(relier_a, point.id)
        return point

    def creer_barre(self, sommets: List[Vec2], nom: Optional[str] = None, couleur: Optional[str] = None) -> Solide:
        """Crée un solide dont le squelette relie les sommets donnés (repère global)."""
        if len(sommets) < 2:
            raise ValueError("une barre demande au moins deux points")
        solide = self.creer_solide(nom, couleur, x=sommets[0][0], y=sommets[0][1])
        precedent = None
        for gx, gy in sommets:
            point = self.creer_point(solide.id, gx, gy, relier_a=precedent)
            precedent = point.id
        return solide

    def points_en(self, gx: float, gy: float, rayon: float) -> List[Tuple[Solide, Point]]:
        """Points de tous les solides situés à moins de ``rayon`` de (gx, gy)."""
        trouves = []
        for solide in self.solides.values():
            point = solide.point_proche(gx, gy, rayon)
            if point is not None:
                trouves.append((solide, point))
        return trouves

    # -------------------------------------------------------------- liaisons
    def creer_liaison(
        self,
        type_liaison: str,
        solide_a: str,
        point_a: str,
        solide_b: str,
        point_b: str,
        nom: Optional[str] = None,
        **parametres: Any,
    ) -> Liaison:
        """Crée une liaison entre deux points existants.

        Pour une glissière ou un encastrement, l'orientation relative est par
        défaut celle de la configuration courante.
        """
        if solide_a == solide_b:
            raise ValueError("une liaison relie deux solides différents")
        a, b = self.solide(solide_a), self.solide(solide_b)
        a.point(point_a)
        b.point(point_b)
        classe = classe_liaison(type_liaison)
        if classe in (Glissiere, Encastrement):
            parametres.setdefault("angle_relatif", b.pose.angle - a.pose.angle)
        lid = self._prochain_id("L", self.liaisons)
        if nom is None:
            base = f"{NOMS_LIAISONS.get(type_liaison, type_liaison)} {b.point(point_b).nom}"
            nom = self._nom_libre(base, (l.nom for l in self.liaisons.values()))
        liaison = classe(lid, nom, solide_a, point_a, solide_b, point_b, **parametres)
        self.liaisons[lid] = liaison
        return liaison

    def creer_liaison_en(
        self,
        type_liaison: str,
        gx: float,
        gy: float,
        solide_a: str,
        solide_b: str,
        angle_axe_global: float = 0.0,
        nom: Optional[str] = None,
        rayon: float = 1e-9,
        **parametres: Any,
    ) -> Liaison:
        """Crée une liaison au point global (gx, gy) entre deux solides.

        Les points existants à cet endroit sont réutilisés, sinon créés.
        """
        if solide_a == solide_b:
            raise ValueError("une liaison relie deux solides différents")
        pa = self._point_en(solide_a, gx, gy, rayon, None)
        pb = self._point_en(solide_b, gx, gy, rayon, pa.nom)
        if classe_liaison(type_liaison).A_UN_AXE:
            parametres.setdefault("angle_axe", angle_axe_global - self.solide(solide_a).pose.angle)
        return self.creer_liaison(type_liaison, solide_a, pa.id, solide_b, pb.id, nom, **parametres)

    def _point_en(self, solide_id: str, gx: float, gy: float, rayon: float, nom: Optional[str]) -> Point:
        solide = self.solide(solide_id)
        existant = solide.point_proche(gx, gy, rayon)
        if existant is not None:
            return existant
        return self.creer_point(solide_id, gx, gy, nom)

    # ----------------------------------------------------- cercles et contacts
    def creer_cercle(self, solide_id: str, gx: float, gy: float, rayon: float, rayon_capture: float = 1e-9) -> Cercle:
        """Ajoute au solide un cercle de centre (gx, gy) ; le centre devient un point du solide."""
        if not (rayon > 0.0 and math.isfinite(rayon)):
            raise ValueError("le rayon d'un cercle doit être strictement positif")
        centre = self._point_en(solide_id, gx, gy, rayon_capture, None)
        return self.solide(solide_id).ajouter_cercle(centre.id, rayon)

    def creer_disque(self, gx: float, gy: float, rayon: float, nom: Optional[str] = None, couleur: Optional[str] = None) -> Solide:
        """Nouveau solide réduit à un disque de centre (gx, gy)."""
        solide = self.creer_solide(nom, couleur, x=gx, y=gy)
        if nom is None:
            solide.nom = self._nom_libre("Disque", (s.nom for s in self.solides.values()))
        self.creer_cercle(solide.id, gx, gy, rayon)
        return solide

    def supprimer_cercle(self, solide_id: str, cercle_id: str) -> None:
        """Supprime un cercle et les cames qui s'appuient dessus."""
        for liaison in [l for l in self.liaisons.values() if isinstance(l, Came) and l.solide_a == solide_id and l.cercle == cercle_id]:
            self.supprimer_liaison(liaison.id)
        if solide_id in self.solides:
            self.solides[solide_id].cercles.pop(cercle_id, None)

    def centre_de_rotation(self, solide_id: str) -> Optional[Point]:
        """Point du solide où il s'articule par une pivot (le premier trouvé), ou ``None``."""
        solide = self.solide(solide_id)
        for liaison in self.liaisons.values():
            if isinstance(liaison, Pivot) and liaison.concerne(solide_id):
                return solide.point(liaison.point_a if liaison.solide_a == solide_id else liaison.point_b)
        return None

    def creer_engrenage(
        self,
        roue_a: str,
        roue_b: str,
        nature: Optional[str] = None,
        z_a: Optional[float] = None,
        z_b: Optional[float] = None,
        module: float = 0.002,
        nom: Optional[str] = None,
        **parametres: Any,
    ) -> Engrenage:
        """Engrène la roue A avec la roue (ou la crémaillère) B.

        Les centres sont les points de pivot des roues. Sans nature imposée, B
        est une crémaillère si elle n'a pas de pivot, une couronne si elle
        entoure A (grand cercle autour du centre de A), une roue extérieure
        sinon. Les nombres de dents par défaut découlent des rayons des cercles
        tracés, ou à défaut de l'entraxe, au module donné.
        """
        if roue_a == roue_b:
            raise ValueError("un engrenage relie deux solides différents")
        centre_a = self.centre_de_rotation(roue_a)
        if centre_a is None:
            raise ValueError("la roue A doit être articulée par une liaison pivot")
        a, b = self.solide(roue_a), self.solide(roue_b)
        oa = a.position_globale(centre_a.id)
        centre_b = self.centre_de_rotation(roue_b)
        if nature is None:
            nature = "cremaillere" if centre_b is None else "exterieur"
            if centre_b is not None:
                ob = b.position_globale(centre_b.id)
                rayon_b = max((c.rayon for c in b.cercles.values() if c.centre == centre_b.id), default=0.0)
                if rayon_b > math.hypot(ob[0] - oa[0], ob[1] - oa[1]) > 0.0:
                    nature = "interieur"
        if nature not in ("exterieur", "interieur", "cremaillere"):
            raise ValueError(f"nature d'engrenage inconnue : « {nature} »")
        if nature == "cremaillere":
            direction = parametres.pop("angle_axe_global", None)
            if direction is None:
                glissiere = next((l for l in self.liaisons.values() if isinstance(l, Glissiere) and l.concerne(roue_b)), None)
                direction = self.angle_axe_global(glissiere) if glissiere is not None else 0.0
            if z_a is None:
                rayon_a = max((c.rayon for c in a.cercles.values() if c.centre == centre_a.id), default=0.0)
                z_a = float(max(6, round(2.0 * rayon_a / module))) if rayon_a > 0.0 else 20.0
            rayon = module * z_a / 2.0
            ux, uy = math.cos(direction), math.sin(direction)
            # point primitif : à la distance r du centre du pignon, du côté de la crémaillère
            gx, gy = b.position_globale(next(iter(b.points))) if b.points else (oa[0], oa[1] - rayon)
            nx, ny = -uy, ux
            if nx * (oa[0] - gx) + ny * (oa[1] - gy) < 0.0:
                nx, ny = -nx, -ny
            primitif = (oa[0] - rayon * nx, oa[1] - rayon * ny)
            point_b = self._point_en(roue_b, primitif[0], primitif[1], 1e-9, None)
            parametres.setdefault("angle_axe", direction - b.pose.angle)
            z_b = z_b if z_b is not None else 1.0
        else:
            if centre_b is None:
                raise ValueError("la roue B doit être articulée par une liaison pivot")
            point_b = centre_b
            ob = b.position_globale(centre_b.id)
            entraxe = math.hypot(ob[0] - oa[0], ob[1] - oa[1])
            if z_a is None or z_b is None:
                rayon_a = max((c.rayon for c in a.cercles.values() if c.centre == centre_a.id), default=0.0)
                rayon_b = max((c.rayon for c in b.cercles.values() if c.centre == centre_b.id), default=0.0)
                if rayon_a <= 0.0 and rayon_b <= 0.0:
                    rayon_a = rayon_b = entraxe / 2.0
                elif rayon_a <= 0.0:
                    rayon_a = abs(entraxe - rayon_b) if nature == "exterieur" else rayon_b - entraxe
                elif rayon_b <= 0.0:
                    rayon_b = entraxe - rayon_a if nature == "exterieur" else entraxe + rayon_a
                z_a = z_a if z_a is not None else float(max(6, round(2.0 * abs(rayon_a) / module)))
                z_b = z_b if z_b is not None else float(max(6, round(2.0 * abs(rayon_b) / module)))
        lid = self._prochain_id("L", self.liaisons)
        if nom is None:
            nom = self._nom_libre(f"Engrenage {a.nom}–{b.nom}", (l.nom for l in self.liaisons.values()))
        liaison = Engrenage(lid, nom, roue_a, centre_a.id, roue_b, point_b.id, nature=nature, z_a=float(z_a), z_b=float(z_b), module=module, **parametres)
        self.liaisons[lid] = liaison
        return liaison

    def creer_came(
        self,
        solide_came: str,
        cercle_id: str,
        solide_poussoir: str,
        point_poussoir: str,
        nature: str = "pointe",
        nom: Optional[str] = None,
        **parametres: Any,
    ) -> Came:
        """Contact entre le cercle d'une came et le point d'un poussoir."""
        if solide_came == solide_poussoir:
            raise ValueError("une came et son poussoir sont deux solides différents")
        came = self.solide(solide_came)
        cercle = came.cercle(cercle_id)
        poussoir = self.solide(solide_poussoir)
        poussoir.point(point_poussoir)
        if nature == "plat" and "angle_axe" not in parametres:
            # Plateau perpendiculaire au guidage du poussoir, sinon à la droite centre-poussoir.
            guidage = next((l for l in self.liaisons.values() if isinstance(l, Glissiere) and l.concerne(solide_poussoir)), None)
            if guidage is not None:
                direction = self.angle_axe_global(guidage) + math.pi / 2.0
            else:
                c = came.position_globale(cercle.centre)
                p = poussoir.position_globale(point_poussoir)
                direction = math.atan2(p[1] - c[1], p[0] - c[0]) + math.pi / 2.0
            parametres["angle_axe"] = direction - poussoir.pose.angle
        lid = self._prochain_id("L", self.liaisons)
        if nom is None:
            nom = self._nom_libre(f"Came {poussoir.point(point_poussoir).nom}", (l.nom for l in self.liaisons.values()))
        liaison = Came(lid, nom, solide_came, cercle.centre, solide_poussoir, point_poussoir, nature=nature, cercle=cercle_id, **parametres)
        self.liaisons[lid] = liaison
        return liaison

    def changer_type_liaison(self, liaison_id: str, type_liaison: str) -> Liaison:
        """Remplace une liaison par une liaison d'un autre type entre les mêmes points.

        L'axe éventuel est conservé ; un moteur devenu incompatible est supprimé.
        """
        ancienne = self.liaison(liaison_id)
        classe = classe_liaison(type_liaison)
        if type(ancienne) is classe:
            return ancienne
        if classe.CONTACT or ancienne.CONTACT:
            raise ValueError("un engrenage ou une came ne se transforme pas en une autre liaison")
        a, b = self.solide(ancienne.solide_a), self.solide(ancienne.solide_b)
        parametres: Dict[str, Any] = {}
        if classe.A_UN_AXE:
            parametres["angle_axe"] = getattr(ancienne, "angle_axe", 0.0)
        if classe in (Glissiere, Encastrement):
            parametres["angle_relatif"] = b.pose.angle - a.pose.angle
        nouvelle = classe(
            ancienne.id, ancienne.nom, ancienne.solide_a, ancienne.point_a, ancienne.solide_b, ancienne.point_b, **parametres
        )
        prefixe = NOMS_LIAISONS.get(ancienne.type, "")
        if prefixe and ancienne.nom.startswith(prefixe):
            nouvelle.nom = NOMS_LIAISONS.get(type_liaison, type_liaison) + ancienne.nom[len(prefixe):]
        self.liaisons[liaison_id] = nouvelle
        moteur = self.moteur_de_liaison(liaison_id)
        if moteur is not None and nouvelle.PILOTAGE != ancienne.PILOTAGE:
            del self.moteurs[moteur.id]
        return nouvelle

    def inverser_liaison(self, liaison_id: str) -> Liaison:
        """Échange les rôles des solides A et B (B porte alors l'axe de la liaison)."""
        liaison = self.liaison(liaison_id)
        if liaison.CONTACT:
            raise ValueError("les rôles d'un engrenage ou d'une came sont fixés par sa géométrie")
        direction = self.angle_axe_global(liaison)
        liaison.solide_a, liaison.solide_b = liaison.solide_b, liaison.solide_a
        liaison.point_a, liaison.point_b = liaison.point_b, liaison.point_a
        if liaison.A_UN_AXE:
            liaison.angle_axe = direction - self.solide(liaison.solide_a).pose.angle
        if hasattr(liaison, "angle_relatif"):
            liaison.angle_relatif = -liaison.angle_relatif
        return liaison

    def recaler_orientation(self, liaison: Liaison) -> None:
        """Fixe l'orientation relative d'une glissière ou d'un encastrement sur la pose courante."""
        if isinstance(liaison, (Glissiere, Encastrement)):
            a, b = self.solide(liaison.solide_a), self.solide(liaison.solide_b)
            liaison.angle_relatif = b.pose.angle - a.pose.angle

    # --------------------------------------------------- actions et moteurs
    def creer_force(self, solide_id: str, point_id: str, fx: Any, fy: Any, repere: str = "global", nom: Optional[str] = None) -> Force:
        self.solide(solide_id).point(point_id)
        aid = self._prochain_id("A", self.actions)
        force = Force(aid, nom or f"F{_numero(aid, 'A')}", True, solide_id, point_id, fx, fy, repere)
        self.actions[aid] = force
        return force

    def creer_couple(self, solide_id: str, mz: Any, nom: Optional[str] = None) -> Couple:
        self.solide(solide_id)
        aid = self._prochain_id("A", self.actions)
        couple = Couple(aid, nom or f"C{_numero(aid, 'A')}", True, solide_id, mz)
        self.actions[aid] = couple
        return couple

    def creer_ressort(
        self,
        solide_a: str,
        point_a: str,
        solide_b: str,
        point_b: str,
        raideur: float,
        amortissement: float = 0.0,
        longueur_libre: Optional[float] = None,
        nom: Optional[str] = None,
    ) -> Ressort:
        pa = self.point_global(solide_a, point_a)
        pb = self.point_global(solide_b, point_b)
        if longueur_libre is None:
            longueur_libre = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        aid = self._prochain_id("A", self.actions)
        ressort = Ressort(
            aid, nom or f"R{_numero(aid, 'A')}", True, solide_a, point_a, solide_b, point_b,
            float(raideur), float(amortissement), float(longueur_libre),
        )
        self.actions[aid] = ressort
        return ressort

    def creer_moteur(self, liaison_id: str, loi: Optional[LoiMouvement] = None, relatif: bool = True, nom: Optional[str] = None) -> Moteur:
        liaison = self.liaison(liaison_id)
        if liaison.PILOTAGE is None:
            raise ValueError(f"la liaison « {liaison.nom} » ne peut pas être motorisée")
        if self.moteur_de_liaison(liaison_id) is not None:
            raise ValueError(f"la liaison « {liaison.nom} » est déjà motorisée")
        mid = self._prochain_id("M", self.moteurs)
        moteur = Moteur(mid, nom or f"Moteur {_numero(mid, 'M')}", liaison_id, loi or LoiMouvement(), relatif)
        self.moteurs[mid] = moteur
        return moteur

    # ---------------------------------------------------------- suppressions
    def supprimer_liaison(self, liaison_id: str) -> None:
        self.liaisons.pop(liaison_id, None)
        for mid in [m.id for m in self.moteurs.values() if m.liaison == liaison_id]:
            del self.moteurs[mid]

    def supprimer_action(self, action_id: str) -> None:
        self.actions.pop(action_id, None)

    def supprimer_moteur(self, moteur_id: str) -> None:
        self.moteurs.pop(moteur_id, None)

    def supprimer_point(self, solide_id: str, point_id: str) -> None:
        """Supprime un point ainsi que les liaisons, actions et cercles qui s'y appuient."""
        if solide_id in self.solides:
            for cercle in [c for c in self.solides[solide_id].cercles.values() if c.centre == point_id]:
                self.supprimer_cercle(solide_id, cercle.id)
        for liaison in [l for l in self.liaisons.values() if l.utilise_point(solide_id, point_id)]:
            self.supprimer_liaison(liaison.id)
        for action in [a for a in self.actions.values() if a.utilise_point(solide_id, point_id)]:
            self.supprimer_action(action.id)
        if solide_id in self.solides:
            self.solides[solide_id].supprimer_point(point_id)

    def supprimer_solide(self, solide_id: str) -> None:
        """Supprime un solide et tout ce qui s'y rattache. Le bâti est seulement vidé."""
        if solide_id not in self.solides:
            return
        for liaison in self.liaisons_du_solide(solide_id):
            self.supprimer_liaison(liaison.id)
        for action in [a for a in self.actions.values() if a.concerne(solide_id)]:
            self.supprimer_action(action.id)
        if solide_id == ID_BATI:
            self.bati.points.clear()
            self.bati.segments.clear()
        else:
            del self.solides[solide_id]

    # ------------------------------------------------------------ géométrie
    def boite_englobante(self) -> Optional[Tuple[float, float, float, float]]:
        """(xmin, ymin, xmax, ymax) de tous les points, ou ``None`` s'il n'y en a pas."""
        xs, ys = [], []
        for solide in self.solides.values():
            for point in solide.points.values():
                X, Y = solide.pose.vers_global(point.x, point.y)
                xs.append(X)
                ys.append(Y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def longueur_caracteristique(self) -> float:
        boite = self.boite_englobante()
        if boite is None:
            return 1.0
        taille = math.hypot(boite[2] - boite[0], boite[3] - boite[1])
        return taille if taille > 1e-9 else 1.0

    # ---------------------------------------------------------- vérification
    def verifier(self) -> List[Probleme]:
        """Contrôle la cohérence interne du modèle (références, valeurs)."""
        problemes: List[Probleme] = []

        def signaler(code: str, gravite: str, objet: str, **details: Any) -> None:
            problemes.append(Probleme(code, gravite, objet, tuple(sorted(details.items()))))

        bati = self.solides.get(ID_BATI)
        if bati is None or not bati.bati:
            signaler("bati_absent", "erreur", ID_BATI)
        elif not bati.pose.est_identite():
            signaler("bati_deplace", "erreur", ID_BATI)

        def point_existe(solide_id: str, point_id: str) -> bool:
            return solide_id in self.solides and point_id in self.solides[solide_id].points

        def fini(*valeurs: Any) -> bool:
            return all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= VALEUR_MAX
                for v in valeurs
            )

        for solide in self.solides.values():
            if solide.bati and solide.id != ID_BATI:
                signaler("bati_multiple", "erreur", solide.id)
            if not fini(solide.pose.x, solide.pose.y, solide.pose.angle):
                signaler("valeur_non_finie", "erreur", solide.id, champ="pose")
            for point in solide.points.values():
                if not fini(point.x, point.y):
                    signaler("valeur_non_finie", "erreur", solide.id, champ=f"point {point.id}")
            for a, b in solide.segments:
                if a not in solide.points or b not in solide.points or a == b:
                    signaler("segment_invalide", "erreur", solide.id, a=a, b=b)
            for cercle in solide.cercles.values():
                if cercle.centre not in solide.points:
                    signaler("cercle_invalide", "erreur", solide.id, cercle=cercle.id)
                elif not fini(cercle.rayon) or cercle.rayon <= 0.0:
                    signaler("valeur_hors_bornes", "erreur", solide.id, champ=f"cercle {cercle.id}")
            inertie = solide.inertie
            if not fini(inertie.masse, inertie.gx, inertie.gy, inertie.jz):
                signaler("valeur_non_finie", "erreur", solide.id, champ="inertie")
            elif inertie.masse < 0.0 or inertie.jz < 0.0:
                signaler("inertie_negative", "erreur", solide.id)

        for liaison in self.liaisons.values():
            if liaison.solide_a == liaison.solide_b:
                signaler("liaison_meme_solide", "erreur", liaison.id)
            for cote, sid, pid in (("A", liaison.solide_a, liaison.point_a), ("B", liaison.solide_b, liaison.point_b)):
                if sid not in self.solides:
                    signaler("solide_inconnu", "erreur", liaison.id, solide=sid, cote=cote)
                elif not point_existe(sid, pid):
                    signaler("point_inconnu", "erreur", liaison.id, solide=sid, point=pid, cote=cote)
            if liaison.modele_spatial not in liaison.MODELES_SPATIAUX:
                signaler("modele_spatial_incompatible", "avertissement", liaison.id, modele=liaison.modele_spatial)
            for champ in liaison.CHAMPS:
                valeur = getattr(liaison, champ.nom)
                if not fini(valeur):
                    signaler("valeur_non_finie", "erreur", liaison.id, champ=champ.nom)
                elif not champ.admet(valeur):
                    signaler("valeur_hors_bornes", "erreur", liaison.id, champ=champ.nom)
            for nom, admises in liaison.OPTIONS:
                if getattr(liaison, nom) not in admises:
                    signaler("option_inconnue", "erreur", liaison.id, champ=nom, valeur=str(getattr(liaison, nom)))
            if isinstance(liaison, Came) and liaison.solide_a in self.solides:
                cercle = self.solides[liaison.solide_a].cercles.get(liaison.cercle)
                if cercle is None:
                    signaler("cercle_inconnu", "erreur", liaison.id, cercle=liaison.cercle)
                elif cercle.centre != liaison.point_a:
                    signaler("cercle_invalide", "erreur", liaison.id, cercle=liaison.cercle)
            if isinstance(liaison, Engrenage) and liaison.nature == "interieur" and liaison.z_b <= liaison.z_a:
                signaler("couronne_trop_petite", "erreur", liaison.id)

        for action in self.actions.values():
            if isinstance(action, Ressort):
                paires = ((action.solide_a, action.point_a), (action.solide_b, action.point_b))
                if action.solide_a == action.solide_b:
                    signaler("ressort_meme_solide", "avertissement", action.id)
            elif isinstance(action, Force):
                paires = ((action.solide, action.point),)
                if action.repere not in ("global", "local"):
                    signaler("repere_inconnu", "erreur", action.id, repere=action.repere)
            else:
                paires = ()
                if getattr(action, "solide", "") not in self.solides:
                    signaler("solide_inconnu", "erreur", action.id, solide=getattr(action, "solide", ""))
            for sid, pid in paires:
                if sid not in self.solides:
                    signaler("solide_inconnu", "erreur", action.id, solide=sid)
                elif not point_existe(sid, pid):
                    signaler("point_inconnu", "erreur", action.id, solide=sid, point=pid)
            if not isinstance(action, Ressort) and any(s == ID_BATI for s in action.solides_concernes()):
                signaler("action_sur_bati", "avertissement", action.id)
            for champ in action.CHAMPS:
                valeur = getattr(action, champ.nom)
                if isinstance(valeur, str):
                    if not champ.expression:
                        signaler("valeur_non_finie", "erreur", action.id, champ=champ.nom)
                        continue
                    try:
                        compiler(valeur)
                    except ErreurExpression as exc:
                        signaler("expression_invalide", "erreur", action.id, champ=champ.nom, message=str(exc))
                elif not fini(valeur):
                    signaler("valeur_non_finie", "erreur", action.id, champ=champ.nom)
                elif champ.minimum is not None and valeur < champ.minimum:
                    signaler("valeur_hors_bornes", "erreur", action.id, champ=champ.nom)

        pilotees: Dict[str, str] = {}
        for moteur in self.moteurs.values():
            liaison = self.liaisons.get(moteur.liaison)
            if liaison is None:
                signaler("moteur_liaison_inconnue", "erreur", moteur.id, liaison=moteur.liaison)
                continue
            if liaison.PILOTAGE is None:
                signaler("moteur_non_pilotable", "erreur", moteur.id, liaison=liaison.id)
            if moteur.liaison in pilotees:
                signaler("moteur_en_double", "erreur", moteur.id, liaison=liaison.id)
            pilotees[moteur.liaison] = moteur.id
            try:
                moteur.loi.verifier()
            except ValueError as exc:
                signaler("loi_invalide", "erreur", moteur.id, message=str(exc))

        if self.fond is not None:
            fond = self.fond
            if not fini(fond.x, fond.y, fond.largeur, fond.angle, fond.opacite) or fond.largeur <= 0.0:
                signaler("valeur_non_finie", "erreur", "fond", champ="fond")

        etude = self.etude
        if not fini(etude.duree, etude.pas, etude.gx, etude.gy, etude.tolerance, etude.precision):
            signaler("valeur_non_finie", "erreur", "etude", champ="etude")
        elif etude.duree <= 0.0 or etude.pas <= 0.0 or etude.tolerance <= 0.0 or etude.precision <= 0.0:
            signaler("etude_invalide", "erreur", "etude")
        return problemes

    def erreurs(self) -> List[Probleme]:
        return [p for p in self.verifier() if p.gravite == "erreur"]

