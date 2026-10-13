# Fabriquer la distribution Windows

Objectif : un **dossier d'application** que l'on copie ou que l'on installe, et qui
fonctionne sur un poste sans Python.

```text
dist\Sikax\
├── Sikax.exe            le programme : icône et numéro de version intégrés
├── runtime\             ses dépendances
│   ├── python312.dll
│   ├── PySide6\         Qt6Core.dll, Qt6Gui.dll, Qt6Widgets.dll, plugins\…
│   ├── numpy\ …
│   └── *.pyd, base_library.zip
├── locales\
│   ├── fr.json
│   └── en.json
└── resources\
    ├── icons\           sikax.ico, sikax.png…
    ├── themes\          style.qss, clair.json, sombre.json
    └── exemples\        *.sikax
```

`locales\` et `resources\` sont de vrais dossiers, à côté de l'exécutable : on peut y
corriger une traduction, retoucher une palette ou déposer un exemple sans rien refaire.

## En une commande

Sur un poste Windows avec Python 3.9 ou plus récent :

```powershell
packaging\build_windows.bat
```

Le script `packaging\build_windows.ps1` :

1. crée un environnement isolé `.venv-build` et y installe `requirements-dev.txt` ;
2. lance la suite de tests ;
3. lance PyInstaller avec `packaging\sikax.spec` ;
4. **contrôle le résultat** en exécutant `dist\Sikax\Sikax.exe --autotest`, qui vérifie
   sans rien afficher que les langues, les thèmes et les exemples sont trouvés, que
   chaque exemple se calcule et que la fenêtre se construit ;
5. produit `dist\Sikax-<version>-windows.zip`.

Options : `-SansTests`, `-Installateur`, `-Python <chemin>`.

## À la main

```powershell
python -m venv .venv-build
.venv-build\Scripts\activate
pip install -r requirements-dev.txt
pyinstaller packaging\sikax.spec --noconfirm --clean
dist\Sikax\Sikax.exe
```

Toujours fabriquer depuis un environnement qui ne contient **que** les dépendances de
Sikax : PyInstaller embarque ce qu'il trouve, et un environnement chargé (matplotlib,
scipy, pandas…) donnerait une distribution de plusieurs centaines de mégaoctets.

## La recette `sikax.spec`

Un fichier `.spec` est un script Python lu par PyInstaller. Celui de Sikax fait quatre
choses.

**Mode dossier.** `EXE(..., exclude_binaries=True)` suivi de `COLLECT(...)` : les
bibliothèques restent des fichiers séparés. C'est l'équivalent de `--onedir`. À l'inverse
de `--onefile`, rien n'est décompressé dans un dossier temporaire à chaque lancement :
le démarrage est immédiat et les antivirus ne s'alarment pas.

**Application graphique.** `console=False` : pas de fenêtre de terminal.
`icon=resources/icons/sikax.ico` : l'icône de l'exécutable (16 à 256 pixels).
`version=...` : le bloc affiché dans *Propriétés → Détails*, généré depuis
`sikax.__version__`.

**Disposition.** La variable `DISPOSITION` en tête du fichier :

| Valeur | Résultat |
|---|---|
| `"rangee"` (par défaut) | les DLL et modules vont dans `runtime\` ; la racine ne contient que `Sikax.exe`, `locales\` et `resources\` |
| `"plate"` | les DLL et modules sont posés directement à côté de `Sikax.exe`, comme le faisaient les anciennes versions de PyInstaller |

**Données.** Après `COLLECT`, la recette copie `locales/` et `resources/` à côté de
l'exécutable. Ils ne sont pas passés par `datas=` pour rester visibles et modifiables.

La liste `EXCLUS` écarte les paquets étrangers à Sikax (tkinter, matplotlib, scipy…) au
cas où l'environnement de fabrication ne serait pas neuf. Aucun module de PySide6 n'y
figure : pyqtgraph en importe plusieurs, qui varient selon sa version, et un seul module
manquant empêche l'application de démarrer.

### Comment le programme retrouve ses fichiers

`sikax/chemins.py` cherche `locales` et `resources` :

1. dans le dossier désigné par la variable d'environnement `SIKAX_RESSOURCES`, si elle existe ;
2. à côté de l'exécutable (`sys.executable`) quand l'application est figée ;
3. dans le dossier interne de PyInstaller (`sys._MEIPASS`) ;
4. à la racine du projet, en développement.

Le même code fonctionne donc depuis VS Code et depuis `Sikax.exe`. Si le dossier des
thèmes manque, l'application démarre avec ses couleurs par défaut.

## Installateur (facultatif)

Avec [Inno Setup 6](https://jrsoftware.org/isinfo.php) installé :

```powershell
packaging\build_windows.bat -Installateur
```

produit `dist\Sikax-<version>-setup.exe` : installation dans *Program Files* ou dans le
profil de l'utilisateur, raccourcis, désinstallation, et association des fichiers
`.sikax` (un double-clic sur un projet l'ouvre dans Sikax). La recette est
`packaging\sikax.iss`.

## Sans poste Windows

`.github/workflows/windows.yml` fait la même fabrication sur une machine Windows de
GitHub à chaque envoi sur la branche `main` ; l'archive se télécharge depuis la page de
l'exécution (compte GitHub nécessaire).

Pour la rendre publique, poser une étiquette de version :

```powershell
git tag v1.0.1
git push origin v1.0.1
```

Si les tests et la fabrication réussissent, l'archive est publiée dans une *Release* :
elle se télécharge alors sans compte depuis la page des versions du dépôt.

## Ce qui a été vérifié, et ce qui ne l'a pas été

PyInstaller ne fabrique que pour le système sur lequel il tourne. La recette a été
exécutée sur macOS, avec Python 3.9 puis Python 3.13 et les versions les plus récentes de
PySide6, NumPy et pyqtgraph : le dossier produit a la disposition décrite ci-dessus et
son exécutable passe l'auto-contrôle, lancé depuis un autre dossier. **La fabrication
sous Windows elle-même n'a pas pu être essayée** : le script PowerShell, l'intégration de
l'icône et du bloc de version, l'installateur Inno Setup et le flux GitHub sont écrits
selon la documentation de ces outils, mais restent à valider au premier essai sur un
poste Windows. L'étape 4 du script est là pour cela : elle échoue clairement si quelque
chose manque.

La disposition `"plate"` est réservée à Windows. Sur un disque insensible à la casse où
l'exécutable s'appelle `Sikax` sans extension (macOS), il entre en conflit avec le paquet
Python `sikax` ; la recette refuse donc cette combinaison.

## En cas de problème

| Symptôme | Piste |
|---|---|
| Rien ne se passe au lancement | Dans `sikax.spec`, passer `console=True`, refabriquer et lancer depuis un terminal pour lire l'erreur. Le journal est aussi dans `%LOCALAPPDATA%\Sikax\sikax.log`. |
| « Qt platform plugin "windows" » introuvable | Le dossier `runtime\PySide6\plugins\platforms` manque : refabriquer avec `--clean` depuis un environnement neuf. |
| Interface en anglais ou sans style | `locales\` ou `resources\themes\` n'est pas à côté de `Sikax.exe`. |
| Distribution énorme | L'environnement de fabrication contient d'autres paquets : repartir de `.venv-build`. |
| Antivirus qui bloque l'exécutable | Fréquent pour un `.exe` non signé ; signer l'exécutable (`signtool`) règle le problème pour une diffusion large. |
