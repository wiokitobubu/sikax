"""La documentation dit vrai : ses exemples s'exécutent et ses liens existent."""

import re
from pathlib import Path

import pytest

from sikax.fichiers import depuis_json

RACINE = Path(__file__).resolve().parent.parent
DOCUMENTS = [RACINE / "README.md"] + sorted((RACINE / "docs").glob("*.md"))


def blocs(chemin, langage):
    return re.findall(rf"```{langage}\n(.*?)```", chemin.read_text(encoding="utf-8"), flags=re.S)


def test_exemple_de_script_du_readme():
    (script,) = blocs(RACINE / "README.md", "python")
    espace = {}
    exec(compile(script, "README.md", "exec"), espace)  # noqa: S102 - code du dépôt
    assert (espace["bilan"].mobilite, espace["bilan"].hyperstatisme) == (1, 0)
    resultats = espace["resultats"]
    assert resultats.type_etude == "cinematique" and resultats.complet
    assert resultats.valeurs("point/S2/P2/x").size == resultats.nb_instants > 100
    assert resultats.valeurs("point/S2/P2/y") == pytest.approx(0.0, abs=1e-9)  # guidée par la ponctuelle


def test_exemple_de_fichier_de_la_documentation():
    (exemple,) = blocs(RACINE / "docs" / "FORMAT_FICHIER.md", "json")
    resultat = depuis_json(exemple)
    assert not resultat.rapport.erreurs and not resultat.rapport.avertissements
    assert resultat.mecanisme.titre == "Pendule simple" and list(resultat.mecanisme.liaisons) == ["L1"]


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda p: p.name)
def test_liens_et_chemins_cites(document):
    texte = document.read_text(encoding="utf-8")
    for cible in re.findall(r"\]\(([^)#]+)\)", texte):
        if "://" not in cible:
            assert (document.parent / cible).exists(), f"lien cassé : {cible}"
    # fichiers et dossiers du projet cités entre accents graves
    for chemin in re.findall(r"`((?:sikax|tests|packaging|resources|locales|outils|docs)/[\w./-]+)`", texte):
        assert (RACINE / chemin.rstrip("/")).exists(), f"chemin cité inexistant : {chemin}"


def test_arborescence_du_readme():
    """Chaque fichier nommé dans l'arborescence du README existe réellement."""
    (arbre,) = [b for b in blocs(RACINE / "README.md", "text") if "├── sikax/" in b]
    attendus = [
        "main.py", "requirements.txt", "requirements-dev.txt", "pyproject.toml",
        "sikax/application.py", "sikax/chemins.py", "sikax/journal.py",
        "sikax/physique/torseur.py", "sikax/physique/unites.py", "sikax/util/expression.py",
        "sikax/modele/solide.py", "sikax/modele/liaisons.py", "sikax/modele/catalogue_spatial.py",
        "sikax/modele/actions.py", "sikax/modele/moteur.py", "sikax/modele/lois.py", "sikax/modele/etude.py",
        "sikax/modele/mecanisme.py", "sikax/modele/bibliotheque.py",
        "sikax/calcul/contraintes.py", "sikax/calcul/systeme.py", "sikax/calcul/topologie.py",
        "sikax/calcul/assemblage.py", "sikax/calcul/cinematique.py", "sikax/calcul/statique.py",
        "sikax/calcul/dynamique.py", "sikax/calcul/resultats.py",
        "sikax/fichiers/lecture.py", "sikax/fichiers/ecriture.py", "sikax/fichiers/diagnostics.py", "sikax/fichiers/migrations.py",
        "sikax/i18n/traducteur.py", "sikax/ui/fenetre_principale.py", "sikax/ui/document.py",
        "sikax/ui/schema/vue.py", "sikax/ui/schema/rendu.py", "sikax/ui/schema/outils.py",
        "locales/fr.json", "locales/en.json", "resources/icons/sikax.ico", "resources/themes/style.qss",
        "packaging/sikax.spec", "packaging/build_windows.ps1", "packaging/sikax.iss",
    ]
    for chemin in attendus:
        assert (RACINE / chemin).exists(), chemin
        assert chemin.rsplit("/", 1)[-1].split(".")[0] in arbre, f"{chemin} absent de l'arborescence"
    assert len(list((RACINE / "resources" / "exemples").glob("*.sikax"))) == 9  # « neuf projets »
