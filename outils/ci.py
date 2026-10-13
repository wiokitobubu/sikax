"""Outils de l'intégration continue (GitHub Actions).

    python outils/ci.py executer <journal> -- <commande...>
        Lance la commande, recopie sa sortie à l'écran et dans le journal,
        et retourne son code de sortie.

    python outils/ci.py signaler <journal...>
        Publie l'essentiel des journaux sous forme d'annotations d'erreur :
        la cause d'un échec se lit alors sur la page de l'exécution, sans
        avoir à ouvrir le journal complet.
"""

import re
import subprocess
import sys
from pathlib import Path

TAILLE_ANNOTATION = 3500
ANNOTATIONS_MAX = 9


def executer(journal: str, commande) -> int:
    with open(journal, "w", encoding="utf-8", errors="replace") as sortie:
        processus = subprocess.Popen(commande, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for ligne in iter(processus.stdout.readline, b""):
            texte = ligne.decode("utf-8", errors="replace")
            sortie.write(texte)
            sortie.flush()
            try:
                sys.stdout.write(texte)
                sys.stdout.flush()
            except UnicodeEncodeError:
                sys.stdout.write(texte.encode("ascii", errors="replace").decode("ascii"))
        return processus.wait()


def essentiel(texte: str) -> str:
    """Partie utile d'un journal : résumé et détail des échecs de pytest, sinon la fin."""
    lignes = texte.splitlines()
    resume = [l for l in lignes if re.match(r"^(FAILED|ERROR) ", l)]
    debut = next((i for i, l in enumerate(lignes) if re.match(r"^=+ (FAILURES|ERRORS) =+", l)), None)
    if resume or debut is not None:
        detail = lignes[debut:] if debut is not None else []
        return "\n".join(resume + ["", "--- détail ---"] + detail)
    return "\n".join(lignes[-70:])


def annotation(titre: str, message: str) -> None:
    code = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title={titre}::{code}")


def signaler(journaux) -> int:
    restantes = ANNOTATIONS_MAX
    for chemin in journaux:
        fichier = Path(chemin)
        if not fichier.is_file():
            continue
        contenu = essentiel(fichier.read_text(encoding="utf-8", errors="replace"))
        morceaux = [contenu[i : i + TAILLE_ANNOTATION] for i in range(0, len(contenu), TAILLE_ANNOTATION)] or [""]
        for numero, morceau in enumerate(morceaux, 1):
            if restantes == 0:
                return 0
            annotation(f"{fichier.name} ({numero}/{len(morceaux)})", morceau)
            restantes -= 1
    return 0


def main(arguments) -> int:
    if len(arguments) >= 4 and arguments[0] == "executer" and arguments[2] == "--":
        return executer(arguments[1], arguments[3:])
    if len(arguments) >= 2 and arguments[0] == "signaler":
        return signaler(arguments[1:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
