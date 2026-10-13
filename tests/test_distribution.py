"""Garde-fous sur la recette de distribution (qui ne peut être exécutée que sous Windows)."""

import ast
import re
import struct
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
RECETTE = (RACINE / "packaging" / "sikax.spec").read_text(encoding="utf-8")


def test_la_recette_est_du_python_valide():
    ast.parse(RECETTE)
    assert 'DISPOSITION = "rangee"' in RECETTE
    assert "exclude_binaries=True" in RECETTE and "console=False" in RECETTE


def test_aucun_module_qt_n_est_exclu():
    """pyqtgraph importe des modules Qt qui varient selon sa version (QtOpenGL depuis la 0.14)."""
    exclus = ast.literal_eval(re.search(r"EXCLUS = (\[.*?\])", RECETTE, flags=re.S).group(1))
    assert exclus and not [m for m in exclus if m.startswith("PySide6")]
    assert not {"numpy", "pyqtgraph", "unittest", "json", "logging"} & set(exclus)


def test_ressources_attendues_par_la_distribution():
    for chemin in ("resources/icons/sikax.ico", "resources/icons/sikax.png", "resources/themes/style.qss",
                   "resources/themes/clair.json", "resources/themes/sombre.json", "locales/fr.json", "main.py"):
        assert (RACINE / chemin).is_file(), chemin
    assert len(list((RACINE / "resources" / "exemples").glob("*.sikax"))) >= 5


def test_icone_windows_bien_formee():
    """Le .ico contient les tailles de 16 à 256 pixels, en 32 bits."""
    donnees = (RACINE / "resources" / "icons" / "sikax.ico").read_bytes()
    reserve, nature, nombre = struct.unpack("<HHH", donnees[:6])
    assert (reserve, nature) == (0, 1) and nombre >= 6
    tailles = []
    for i in range(nombre):
        largeur, hauteur, _, _, plans, bits, taille, position = struct.unpack("<BBBBHHII", donnees[6 + 16 * i : 22 + 16 * i])
        assert largeur == hauteur and bits == 32 and position + taille <= len(donnees)
        tailles.append(largeur or 256)
    assert {16, 32, 48, 256} <= set(tailles)
    assert donnees[-8:-4] == b"IEND"  # la plus grande image est un PNG complet


def test_scripts_de_fabrication_coherents():
    script = (RACINE / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "packaging\\sikax.spec" in script and "--autotest" in script and "requirements-dev.txt" in script
    assert "pyinstaller" in (RACINE / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    inno = (RACINE / "packaging" / "sikax.iss").read_text(encoding="utf-8")
    assert "..\\dist\\Sikax\\*" in inno and ".sikax" in inno
