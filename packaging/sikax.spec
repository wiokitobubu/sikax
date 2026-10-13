# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller de Sikax : un dossier d'application, pas un exécutable unique.

    pyinstaller packaging/sikax.spec --noconfirm --clean

Résultat dans ``dist/Sikax/`` ::

    Sikax.exe      le programme (icône et numéro de version intégrés)
    runtime/       ses dépendances : python3xx.dll, Qt6*.dll, modules .pyd, NumPy
    locales/       fr.json, en.json : textes de l'interface
    resources/     icons/, themes/, exemples/

``locales`` et ``resources`` sont copiés tels quels à côté de l'exécutable :
on peut y corriger une traduction, retoucher une palette ou ajouter un
exemple sans refaire la distribution.
"""

import shutil
import sys
from pathlib import Path

RACINE = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(RACINE))

from sikax import __app_name__, __version__  # noqa: E402

# "rangee" : les DLL et modules sont regroupés dans le sous-dossier « runtime » ;
#            la racine ne contient que Sikax.exe, locales/ et resources/.
# "plate"  : les DLL et modules sont posés directement à côté de Sikax.exe
#            (ancienne disposition de PyInstaller). Windows uniquement : ailleurs,
#            l'exécutable « Sikax » sans extension entre en conflit avec le
#            paquet Python « sikax » sur un disque insensible à la casse.
DISPOSITION = "rangee"

if DISPOSITION not in ("rangee", "plate"):
    raise SystemExit(f"DISPOSITION inconnue : {DISPOSITION!r} (attendu : 'rangee' ou 'plate')")
if DISPOSITION == "plate" and sys.platform != "win32":
    raise SystemExit("La disposition « plate » n'est prévue que pour Windows ; utilisez « rangee » sur ce système.")
DOSSIER_BIBLIOTHEQUES = "." if DISPOSITION == "plate" else "runtime"

# Paquets présents sur certaines machines mais étrangers à Sikax : les écarter
# évite d'embarquer des centaines de mégaoctets si l'environnement n'est pas neuf.
# Aucun module de PySide6 n'est exclu : pyqtgraph en importe plusieurs (QtSvg,
# QtTest, QtOpenGL selon sa version) et un seul qui manque empêche le démarrage.
EXCLUS = [
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "jupyter", "notebook",
    "PyQt5", "PyQt6", "PySide2", "h5py", "numba", "cupy", "sympy",
    "pytest", "setuptools", "pip", "wheel", "lib2to3",
]


def fichier_de_version() -> str:
    """Bloc « Propriétés → Détails » de l'exécutable Windows."""
    numeros = [int(n) for n in (__version__.split(".") + ["0", "0", "0"])[:4]]
    quadruplet = ", ".join(str(n) for n in numeros)
    contenu = f"""
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({quadruplet}), prodvers=({quadruplet}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
      StringStruct('CompanyName', '{__app_name__}'),
      StringStruct('FileDescription', 'Sikax - mécanismes plans'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{__app_name__}'),
      StringStruct('OriginalFilename', '{__app_name__}.exe'),
      StringStruct('ProductName', '{__app_name__}'),
      StringStruct('ProductVersion', '{__version__}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])]),
  ]
)
"""
    chemin = Path(workpath) / "version_info.txt"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return str(chemin)


analyse = Analysis(
    [str(RACINE / "main.py")],
    pathex=[str(RACINE)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUS,
    noarchive=False,
)

archive = PYZ(analyse.pure)

executable = EXE(
    archive,
    analyse.scripts,
    [],
    exclude_binaries=True,  # mode « dossier » : les bibliothèques restent des fichiers séparés
    name=__app_name__,
    console=False,  # application graphique : pas de fenêtre de terminal
    icon=str(RACINE / "resources" / "icons" / "sikax.ico") if sys.platform == "win32" else None,
    version=fichier_de_version() if sys.platform == "win32" else None,
    contents_directory=DOSSIER_BIBLIOTHEQUES,
    upx=False,
)

dossier = COLLECT(
    executable,
    analyse.binaries,
    analyse.datas,
    name=__app_name__,
    upx=False,
)

# Données de l'application, copiées à côté de l'exécutable.
destination = Path(DISTPATH) / __app_name__
for nom in ("locales", "resources"):
    cible = destination / nom
    if cible.exists():
        shutil.rmtree(cible)
    shutil.copytree(RACINE / nom, cible, ignore=shutil.ignore_patterns("*.bak", ".DS_Store", "Thumbs.db"))
