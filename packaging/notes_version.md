## Nouveautés de Sikax 2.0

- **Calcul stable.** La dynamique utilise les intégrateurs de SciPy (Radau par défaut,
  BDF, LSODA, DOP853, RK45, au choix dans l'étude). Les points morts sont franchis sans
  efforts démesurés ; un mécanisme qui s'emballe est arrêté avec un message clair.
- **Courbes.** Position, vitesse, accélération, efforts et couples s'affichent
  directement dans l'onglet *Courbes*. Export des résultats vers **Excel** (`.xlsx`),
  avec les graphiques.
- **Cercles, cames, engrenages.** Outil *Cercle* (disque, came excentrique), contact
  came-poussoir (pointe, galet, plateau), engrenages extérieur, intérieur et
  pignon-crémaillère (module, nombres de dents, angle de pression, rendement). Liaison
  directe entre deux solides en deux clics. Nouveaux modèles : came et poussoir, train
  d'engrenages, train épicycloïdal, pignon-crémaillère.
- **Apprendre.** Fenêtre de bienvenue, tutoriel animé (`F1`), fiches de cours et
  boutons « ? » (cinématique, statique, dynamique, moment, torseur, inertie, engrenages…).
- **Partir d'une photo.** Import d'une photo de schéma en fond, étalonnage par deux
  clics, détection automatique des barres, disques et pivots.

Les projets de la version 1 s'ouvrent tels quels.

## Installer

1. Téléchargez `Sikax-…-windows.zip` ci-dessous.
2. Décompressez l'archive (clic droit → *Extraire tout*).
3. Ouvrez le dossier `Sikax` et lancez `Sikax.exe`.

Il n'y a rien à installer : Python et les bibliothèques sont dans le dossier `runtime`.
Gardez le dossier entier : `Sikax.exe` a besoin de `runtime`, `locales` et `resources` à côté de lui.

Au premier lancement, Windows peut afficher « Windows a protégé votre ordinateur », car
le programme n'est pas signé. Cliquez sur *Informations complémentaires*, puis sur
*Exécuter quand même*.

Pour commencer : répondez à la question de bienvenue, ou *Fichier → Exemples →
Bielle-manivelle*, puis `F5`.
