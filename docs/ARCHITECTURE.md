# Architecture de Sikax

## Vue d'ensemble

Sikax est découpé en couches qui ne dépendent que des couches situées en dessous :

```text
          ui            interface Qt : fenêtre, schéma, panneaux, tutoriel, cours
           │
   ┌───────┼────────┬────────┐
fichiers  calcul   vision   i18n   lecture/écriture/Excel · solveur · photos · traduction
   └───────┼────────┴────────┘
        modele              solides, liaisons, actions, moteurs, étude, photo de fond
           │
 geometrie · physique · util
```

Deux règles tiennent l'ensemble :

- **`modele`, `calcul`, `fichiers` et `vision` n'importent jamais Qt.** Ils s'utilisent
  en script et se testent sans interface.
- **Le moteur ne parle pas français.** Une erreur de calcul ou de lecture porte un *code*
  et des paramètres (`ErreurCalcul("mobilite_non_pilotee", mobilite=2)`), jamais une
  phrase. Le texte affiché vient de `locales/<langue>.json`.

## Correspondance avec OpenMeca

Le cahier des charges demandait de s'inspirer de l'organisation d'OpenMeca
(`SRC/OpenMeca` : `Core`, `Geom`, `Item`, `Physic`, `Setting`, `Util`, `Gui`, `Rsc`).

| OpenMeca (C++) | Rôle | Sikax (Python) |
|---|---|---|
| `Core/System` | conteneur du modèle | `modele/mecanisme.py` : `Mecanisme` |
| `Core/SelectionManager`, `HistoricManager` | sélection, annuler/rétablir | `ui/document.py` : `Document` |
| `Geom` | points, vecteurs, repères | `geometrie/` |
| `Item/Body`, `Item/Part*` | solides et leurs points | `modele/solide.py` |
| `Item/Link`, `Item/Link/Revolute`, `Slider`… | liaisons | `modele/liaisons.py` |
| `Item/Load`, `Item/Link/Spring` | actions mécaniques | `modele/actions.py` |
| `Item/Link/Motor`, `Util/MotionLaw` | moteurs, lois de mouvement | `modele/moteur.py`, `modele/lois.py` |
| `Physic` | grandeurs physiques | `physique/` |
| `Util/Expr` (exprtk) | expressions | `util/expression.py` |
| `Setting/Gravity`, `Simulation`, `UnitManager`, `LangManager` | réglages | `modele/etude.py`, `physique/unites.py`, `i18n/` |
| `Gui/MainWindow`, `Viewer`, `TreeView`, `Player`, `MainPlotWindow`, `Prop` | interface | `ui/` |
| `Rsc/Lang`, `Rsc/Example`, `Rsc/Img` | ressources | `locales/`, `resources/` |
| ChronoEngine (bibliothèque externe) | solveur multicorps | `calcul/` (écrit pour Sikax) |

Différence principale : OpenMeca délègue le calcul à ChronoEngine, une bibliothèque C++
généraliste. Sikax contient son propre solveur plan, plus petit, mais qui sait répondre
aux questions du cahier des charges que Chrono ne pose pas : mobilité, degré
d'hyperstatisme et torseurs de liaison au sens du PFS.

## Le modèle (`sikax/modele`)

`Mecanisme` contient des dictionnaires indexés par identifiant : `solides` (`S0` est
toujours le bâti), `liaisons` (`L1`…), `actions` (`A1`…), `moteurs` (`M1`…), plus
l'`etude`, les `unites` d'affichage et les réglages d'`affichage`.

Un `Solide` a une *pose* (position de l'origine de son repère et angle) et des `points`
exprimés dans ce repère. Déplacer le mécanisme ne change que les poses ; modifier la
géométrie ne change que les coordonnées locales des points. Toutes les valeurs sont en SI.
Un solide peut porter des `cercles` (centre = un de ses points, rayon) : disque, came
excentrique, cercle primitif d'une roue.

`contacts.py` regroupe la géométrie des liaisons de contact (point primitif d'un
engrenage, point de contact d'une came) et les formules des engrenages droits. `fond.py`
décrit la photo de fond (`FondPlan`) : l'image, sa place dans le modèle et son
étalonnage.

### La classe `Liaison`

```python
@dataclass
class Liaison:
    id, nom
    solide_a, point_a          # le solide qui porte l'axe éventuel
    solide_b, point_b
    modele_spatial             # réalisation dans l'espace

    TYPE              = ""                     # "pivot", "glissiere"…
    MOBILITES         = (Tx, Ty, Rz)           # mobilités de B / A, repère de la liaison
    A_UN_AXE          = False
    PILOTAGE          = None                   # "rotation", "translation" ou None
    MODELES_SPATIAUX  = ()                     # liaisons 3D compatibles
    CHAMPS            = ()                     # paramètres numériques déclarés
```

| Classe | Mobilités de B / A | Inconnues statiques | Équations |
|---|---|---|---|
| `Encastrement` | aucune | X, Y, N | 3 |
| `Pivot` | Rz | X, Y | 2 |
| `Glissiere` | Tx | Y, N | 2 |
| `Ponctuelle` | Tx, Rz | Y | 1 |

La classe ne contient **que des données et des propriétés topologiques**
(`ddl(dimension)`, `inconnues_statiques(dimension)`, `composantes_statiques()`). Les
équations de contrainte sont dans `calcul/contraintes.py`. C'est ce qui permettra
d'ajouter un solveur 3D sans toucher au modèle.

`CHAMPS` déclare les paramètres d'un objet (nom, dimension physique, valeur par défaut,
minimum). Cette déclaration unique sert au lecteur de fichiers, à l'écrivain et au
panneau de propriétés : ajouter un paramètre à une liaison ne demande aucune autre
modification.

## Le moteur de calcul (`sikax/calcul`)

`SystemeMecanique(mecanisme)` traduit le modèle en équations (voir
[THEORIE.md](THEORIE.md)) : coordonnées `q = (xG, yG, θ)` par solide mobile, contraintes
`Φ(q, t) = 0`, jacobienne, masses, forces généralisées.

| Module | Rôle |
|---|---|
| `contraintes.py` | `Coincidence`, `AngleRelatif`, `PointSurDroite`, `TranslationPilotee`, et pour les contacts `EngrenageRoues`, `EngrenageCremaillere`, `DistanceConstante` (came à pointe ou à galet), `PlateauTangent` : résidu, jacobienne, second membre en accélération, efforts et pertes |
| `systeme.py` | assemblage, forces, torseur d'une liaison à partir des multiplicateurs |
| `algebre.py` | rang, noyau, solutions de norme minimale par SVD |
| `topologie.py` | graphe des liaisons, boucles, mobilité et hyperstatisme (plan et espace) |
| `assemblage.py` | fermeture des liaisons (Gauss-Newton), déplacement à la souris |
| `configuration.py` | régler une liaison, refermer, reprendre une position calculée |
| `cinematique.py` | positions, vitesses, accélérations, puis efforts (dynamique inverse) ; franchissement des points morts |
| `statique.py` | PFS, recherche de position d'équilibre |
| `dynamique.py` | PFD : `scipy.integrate.solve_ivp` (Radau, BDF, LSODA, DOP853, RK45), lagrangien augmenté, méthodes de repli, détection d'emballement |
| `enregistreur.py`, `resultats.py` | grandeurs de sortie (dont `Ft`, `Fr`, `Fn` des contacts), zones de points morts, export CSV pour les scripts |
| `simulation.py` | `lancer_etude(mecanisme)` : point d'entrée unique |

Toutes les résolutions linéaires passent par la décomposition en valeurs singulières : un
mécanisme hyperstatique (équations liées) ou mobile (inconnues en trop) ne fait pas
échouer le calcul.

## Les fichiers (`sikax/fichiers`)

Voir [FORMAT_FICHIER.md](FORMAT_FICHIER.md). Le lecteur consigne toutes les anomalies dans
un `Rapport` au lieu de s'arrêter à la première ; l'écrivain remplace le fichier de façon
atomique et garde une copie `.bak`.

`excel.py` écrit le classeur des résultats avec openpyxl : feuille *Résultats* (de vrais
nombres, en unités d'affichage, en-têtes figés), feuille *Graphiques* (courbes Excel
natives), feuille *Informations* (projet, étude, messages). Au-delà de 400 000 cellules
le classeur est écrit en flux. L'écriture est atomique, comme pour les projets.

## Les photos (`sikax/vision`)

`detection.py` repère, avec OpenCV, les traits et les cercles d'une photo de schéma :
seuil adaptatif (éclairage inégal), squelette de l'encre (amincissement de Zhang et Suen),
segments par la transformée de Hough sur ce squelette, cercles par les trous bien ronds de
l'encre puis par la transformée de Hough à gradient. Les extrémités voisines sont réunies
et accrochées au centre des petits cercles (symboles d'articulation). `creer_solides`
transforme le résultat en barres, disques et pivots, à l'échelle de l'étalonnage. OpenCV
n'est importé qu'à l'appel : sans lui, le reste de Sikax fonctionne.

## L'interface (`sikax/ui`)

`Document` est le seul point de rencontre des composants. Il possède le `Mecanisme`, la
sélection, l'historique et les résultats, et émet quatre signaux : `modele_change`,
`selection_change`, `resultats_change`, `temps_change`. Les panneaux ne se connaissent
pas entre eux.

Toute modification passe par :

```python
with document.modification():
    document.mecanisme.creer_solide()
```

qui enregistre l'état précédent (annuler/rétablir), marque le projet comme modifié,
invalide les résultats et prévient les vues. Si l'opération lève une exception, le modèle
retrouve son état d'avant.

Le schéma (`ui/schema`) est dessiné à la main avec `QPainter` : `vue.py` gère zoom,
déplacement, aimantation et sélection ; `rendu.py` dessine solides, symboles de liaison
et vecteurs ; `outils.py` contient un outil par mode de la souris.

Le calcul tourne dans un fil séparé (`Calcul`, un `QThread`) sur une copie du modèle :
l'interface reste réactive et le calcul peut être arrêté. Le second membre de
l'intégrateur ne laisse jamais passer d'exception (LSODA est écrit en Fortran : une
exception levée dans un de ses rappels, hors du fil principal, arrêterait le programme) ;
l'annulation et les erreurs sont notées puis levées une fois l'intégrateur sorti.

Le panneau *Courbes* (`panneaux/courbes.py`) montre par défaut un tableau de bord de six
graphes (position, vitesse, accélération, efforts, couples, énergie) avec pyqtgraph ; le
mode *personnalisé* trace les grandeurs choisies, l'une en fonction de l'autre si besoin.
Les zones de points morts y sont grisées.

Aide et apprentissage :

- `tutoriel/` : la fenêtre de bienvenue (`accueil.py`), la superposition qui assombrit la
  fenêtre et met en lumière l'outil présenté (`superposition.py`), les étapes
  (`etapes.py`) et leurs animations dessinées avec `QPainter` (`demos.py`). Une animation
  peut être remplacée par un fichier `resources/tutoriel/<étape>.gif`, lu par `QMovie` ;
- `aide.py` : les boutons « ? » des panneaux. Leur infobulle donne la définition, un clic
  ouvre la fiche de cours à la bonne section ;
- `panneaux/cours.py` et `cours_figures.py` : les fiches de cours
  (`resources/cours/<langue>/*.html`) et leurs figures, dessinées à l'exécution ;
- `dialogues/detection.py` : réglage de la détection des formes d'une photo, avec aperçu.

### Thèmes

Un thème est une palette de couleurs nommées (`resources/themes/clair.json`,
`sombre.json`). `resources/themes/style.qss` est un modèle de feuille de style où chaque
nom entre doubles accolades est remplacé par sa couleur. Les dessins faits à la main
demandent leurs couleurs à `theme.couleur("force")`. Changer de thème réapplique la
feuille de style et redessine tout.

## Étendre Sikax

### Ajouter un type de liaison

1. Dans `modele/liaisons.py` : une sous-classe de `Liaison` avec `TYPE`, `MOBILITES`,
   `MODELES_SPATIAUX`, `CHAMPS`, puis l'ajouter à `REGISTRE_LIAISONS`.
2. Dans `calcul/systeme.py`, méthode `_contraintes_de` : la liste de ses contraintes
   élémentaires (en créer une dans `contraintes.py` si nécessaire).
3. Dans `ui/schema/rendu.py`, méthode `_liaison` : son symbole. Une liaison de contact
   (engrenage, came) déclare `CONTACT = True` et sa géométrie va dans `modele/contacts.py`.
4. Dans `locales/*.json` : `liaison.type.<type>` et `action.outil_<type>`.
5. Dans `fichiers/lecture.py` : ses synonymes dans `SYNONYMES_LIAISON`.

Les tests de `tests/test_contraintes.py` vérifient automatiquement par différences finies
toute nouvelle contrainte ajoutée à leur liste.

### Ajouter une loi de mouvement

Une entrée dans `LOIS` (`modele/lois.py`) avec ses paramètres, une branche dans
`LoiMouvement.evaluer` qui retourne `(f, f', f'')`, et les textes `loi.<nom>`,
`loi.aide.<nom>`, `loi.param.<paramètre>`.

### Ajouter une langue

Copier `locales/fr.json`, traduire. Rien d'autre.

### Vers la 3D

Ce qui est déjà prêt :

- `physique/torseur.py` est écrit en 3D ;
- `modele/catalogue_spatial.py` décrit les liaisons normalisées par leurs mobilités
  (rotation ou translation, axe), et `calcul/topologie.py` sait déjà en tirer mobilité et
  hyperstatisme dans l'espace ;
- le format de fichier porte un champ `dimension` ;
- le modèle ne contient aucune équation.

Ce qu'il reste à écrire : une pose 3D (position et quaternion) dans `geometrie/repere.py`,
un `calcul/contraintes_3d.py` et un `SystemeMecanique` à 6 coordonnées par solide, et
une vue 3D. Le reste (document, fichiers, panneaux, traduction, résultats) est
indépendant de la dimension.
