"""Changement de configuration du mécanisme (position initiale).

Trois façons de fixer la configuration de départ d'une étude :

- ``regler_liaison`` : donner une valeur à l'angle d'une pivot ou au
  déplacement d'une glissière, le reste du mécanisme suivant ;
- ``refermer`` : remettre les liaisons en place après une modification de
  géométrie (les solides bougent le moins possible) ;
- ``appliquer_resultats`` : reprendre la position calculée à un instant donné.

Le déplacement à la souris utilise ``sikax.calcul.assemblage.glisser``.
"""

from __future__ import annotations

import math

from ..modele.mecanisme import Mecanisme
from .assemblage import assembler
from .contraintes import AngleRelatif, TranslationPilotee
from .resultats import Resultats
from .systeme import SystemeMecanique

PAS_ANGULAIRE = math.radians(5.0)


def residu_de_fermeture(mecanisme: Mecanisme) -> float:
    """Plus grand écart de fermeture des liaisons dans la configuration du modèle."""
    systeme = SystemeMecanique(mecanisme, avec_moteurs=False)
    if systeme.nc_liaisons == 0:
        return 0.0
    ecart = float(abs(systeme.phi(systeme.q0, 0.0, False)).max())
    return ecart if math.isfinite(ecart) else float("inf")


def refermer(mecanisme: Mecanisme, tolerance: float = 1e-10) -> bool:
    """Déplace les solides pour que toutes les liaisons soient respectées.

    Retourne ``False`` si aucune configuration compatible n'a été trouvée ;
    le modèle est alors laissé inchangé.
    """
    systeme = SystemeMecanique(mecanisme, avec_moteurs=False)
    resultat = assembler(systeme, systeme.q0, 0.0, False, tolerance)
    if resultat.converge:
        systeme.appliquer_au_modele(resultat.q)
    return resultat.converge


def coordonnee_liaison(mecanisme: Mecanisme, liaison_id: str) -> float:
    """Valeur courante de la coordonnée pilotable d'une liaison (angle ou déplacement)."""
    systeme = SystemeMecanique(mecanisme, avec_moteurs=False)
    info = systeme.liaisons[liaison_id]
    deplacement, angle = systeme.coordonnee_liaison(systeme.q0, info)
    return deplacement if info.liaison.PILOTAGE == "translation" else angle


def regler_liaison(mecanisme: Mecanisme, liaison_id: str, valeur: float, tolerance: float = 1e-10) -> bool:
    """Amène la coordonnée d'une liaison à la valeur donnée, par continuation.

    La liaison est conduite pas à pas de sa valeur actuelle à la valeur
    demandée ; le mécanisme suit en restant sur la même branche d'assemblage.
    Retourne ``False`` (modèle inchangé) si la valeur est inaccessible.
    """
    systeme = SystemeMecanique(mecanisme, avec_moteurs=False)
    info = systeme.liaisons[liaison_id]
    pilotage = info.liaison.PILOTAGE
    if pilotage is None or systeme.n == 0:
        return False
    deplacement, angle = systeme.coordonnee_liaison(systeme.q0, info)
    depart = deplacement if pilotage == "translation" else angle
    ecart = valeur - depart

    def rampe(tau: float):
        return (depart + ecart * tau, ecart, 0.0)

    if pilotage == "rotation":
        pilote = AngleRelatif(info.attache_a[0], info.attache_b[0], 0.0, rampe)
        nombre = max(1, int(math.ceil(abs(ecart) / PAS_ANGULAIRE)))
    else:
        pilote = TranslationPilotee(info.attache_a, info.angle_axe, info.attache_b, 0.0, rampe)
        nombre = max(1, int(math.ceil(abs(ecart) / (0.02 * mecanisme.longueur_caracteristique()))))
    nombre = min(nombre, 2000)

    # Le pilote temporaire prend la place d'un moteur dans le système.
    systeme.contraintes = [(i, c) for i, c in systeme.contraintes if i < systeme.nc_liaisons]
    systeme.contraintes.append((systeme.nc_liaisons, pilote))
    systeme.nc = systeme.nc_liaisons + 1

    q = systeme.q0
    for etape in range(1, nombre + 1):
        resultat = assembler(systeme, q, etape / nombre, True, tolerance)
        if not resultat.converge:
            return False
        q = resultat.q
    systeme.appliquer_au_modele(q)
    return True


def appliquer_resultats(mecanisme: Mecanisme, resultats: Resultats, indice: int) -> None:
    """Place le mécanisme dans la configuration calculée à l'instant d'indice donné."""
    for solide_id in resultats.solides:
        pose = resultats.pose(solide_id, indice)
        if pose is not None and solide_id in mecanisme.solides:
            cible = mecanisme.solides[solide_id].pose
            cible.x, cible.y, cible.angle = pose
