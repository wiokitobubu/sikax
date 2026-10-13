# Format des fichiers `.sikax`

Un projet Sikax est un document **JSON** encodé en **UTF-8**. Toutes les grandeurs sont en
unités **SI** (m, rad, kg, s, N, N·m) ; le bloc `unites` ne décrit que l'affichage choisi.
Le fichier se lit et se corrige dans n'importe quel éditeur de texte.

## Exemple

```json
{
  "format": "sikax",
  "version": 1,
  "dimension": 2,
  "meta": { "titre": "Pendule simple", "auteur": "", "description": "" },
  "unites": { "longueur": "mm", "angle": "deg" },
  "solides": [
    {
      "id": "S0", "nom": "Bâti", "bati": true, "couleur": "#7C8696",
      "pose": { "x": 0.0, "y": 0.0, "angle": 0.0 },
      "points": [ { "id": "P1", "nom": "A", "x": 0.0, "y": 0.0 } ],
      "segments": [],
      "inertie": { "masse": 0.0, "g": [0.0, 0.0], "jz": 0.0 }
    },
    {
      "id": "S1", "nom": "Pendule", "bati": false, "couleur": "#3B82F6",
      "pose": { "x": 0.0, "y": 0.0, "angle": 0.0 },
      "points": [
        { "id": "P1", "nom": "A", "x": 0.0, "y": 0.0 },
        { "id": "P2", "nom": "B", "x": 0.433, "y": -0.25 }
      ],
      "segments": [ ["P1", "P2"] ],
      "inertie": { "masse": 1.0, "g": [0.2165, -0.125], "jz": 0.0208 }
    }
  ],
  "liaisons": [
    {
      "id": "L1", "nom": "Pivot A", "type": "pivot",
      "solide_a": "S0", "point_a": "P1",
      "solide_b": "S1", "point_b": "P1",
      "modele_spatial": "pivot_z",
      "amortissement": 0.0, "vitesse_initiale": 0.0
    }
  ],
  "actions": [],
  "moteurs": [],
  "etude": {
    "type": "dynamique", "duree": 3.0, "pas": 0.005,
    "pesanteur": true, "gravite": [0.0, -9.81],
    "inertie": true, "tolerance": 1e-10, "precision": 1e-08
  },
  "affichage": { "grille": true, "pas_grille": 0.01, "aimantation": true }
}
```

## Sections

### `solides`

| Champ | Sens |
|---|---|
| `id` | identifiant unique. Le bâti est `S0`. |
| `bati` | `true` pour le bâti (un seul). |
| `pose` | position de l'origine du repère du solide et `angle`, dans le repère global. |
| `points` | points du solide, dans **son** repère. |
| `segments` | paires de points reliées par un trait (le « squelette » dessiné). |
| `inertie` | `masse`, centre de gravité `g` dans le repère du solide, moment d'inertie `jz` en G. |

### `liaisons`

Champs communs : `id`, `nom`, `type`, `solide_a`, `point_a`, `solide_b`, `point_b`,
`modele_spatial`. Le torseur calculé est celui de l'action de A sur B.

| `type` | Champs propres | Modèles spatiaux |
|---|---|---|
| `pivot` | `amortissement` (N·m·s/rad), `vitesse_initiale` (rad/s) | `pivot_z`, `pivot_glissant_z`, `rotule`, `lineaire_annulaire_z` |
| `glissiere` | `angle_axe`, `angle_relatif`, `amortissement` (N·s/m), `vitesse_initiale` (m/s) | `glissiere_x`, `pivot_glissant_x`, `appui_plan_y` |
| `encastrement` | `angle_relatif` | `encastrement` |
| `ponctuelle` | `angle_axe` | `ponctuelle_y`, `lineaire_annulaire_x`, `lineaire_rectiligne_y` |

`angle_axe` est la direction de l'axe **dans le repère du solide A**. `angle_relatif` est
l'orientation constante de B par rapport à A.

### `actions`

| `type` | Champs |
|---|---|
| `force` | `solide`, `point`, `fx`, `fy`, `repere` (`global` ou `local`) |
| `couple` | `solide`, `mz` |
| `ressort` | `solide_a`, `point_a`, `solide_b`, `point_b`, `raideur`, `amortissement`, `longueur_libre` |

`fx`, `fy` et `mz` acceptent un nombre ou une expression du temps entre guillemets :
`"100*sin(2*pi*t)"`. Tous ont un champ `actif`.

### `moteurs`

`id`, `nom`, `liaison` (une pivot ou une glissière), `relatif`, `actif`, et `loi` :

| `loi.type` | `loi.parametres` |
|---|---|
| `vitesse_constante` | `vitesse`, `position_initiale` |
| `uniformement_accelere` | `acceleration`, `vitesse_initiale`, `position_initiale` |
| `sinusoidale` | `amplitude`, `frequence` (Hz), `phase`, `decalage` |
| `trapeze` | `course`, `vitesse_max`, `acceleration`, `depart` |
| `blocage` | `position` |
| `expression` | `expression` |

## Ce que fait le lecteur

Le code est dans `sikax/fichiers/lecture.py`. Ses principes :

**Tout signaler.** Le lecteur parcourt le document en entier et consigne chaque anomalie
avec son emplacement, par exemple :

```text
✕ liaisons[1] (L2) : type de liaison inconnu « engrenage ». Types reconnus : pivot, glissiere, encastrement, ponctuelle.
✕ liaisons[2] (L3) : « point_b » : le point « P42 » n'existe pas dans le solide « S3 ».
⚠ solides[1] (S1) : couleur invalide « rouge » ; couleur par défaut utilisée.
```

**Deux modes.** En mode strict (par défaut), la moindre erreur empêche l'ouverture :
rien n'est chargé à moitié. L'interface montre alors le compte rendu et propose le mode
tolérant, qui ouvre le projet en écartant les éléments en erreur.

**Souple sur la forme.** Sont acceptés et signalés comme simples informations :

| Écriture | Exemple |
|---|---|
| majuscules et accents dans les clés | `"Liaisons"`, `"Bâti"`, `"Étude"` |
| synonymes des types | `"articulation"`, `"revolute"` → pivot ; `"prismatique"`, `"slider"` → glissière ; `"appui simple"` → ponctuelle |
| synonymes des clés | `"joints"` → `liaisons`, `"body_a"` → `solide_a`, `"name"` → `nom` |
| nombres écrits en texte | `"1,5"`, `" 0.3 "` |
| angles en degrés | `"angle_axe_deg": 45` au lieu de `"angle_axe"` |
| référence par le nom | `"solide_a": "Manivelle"` au lieu de `"S1"` |
| identifiants entiers | `"solide_a": 1` pour `"S1"` |
| liaison donnée par sa position | `"position": [0.2, 0.0]` au lieu de `point_a` et `point_b` |
| sections en dictionnaire | `"liaisons": { "L1": { … } }` |
| commentaires | toute clé commençant par `_` est ignorée |

**Strict sur le sens.** Sont des erreurs : type de liaison inconnu, solide ou point
introuvable, liaison d'un solide avec lui-même, identifiant en double, nombre illisible,
non fini ou démesuré (au-delà de 10¹⁵), valeur négative là où elle n'a pas de sens,
expression invalide, moteur sur une liaison qui ne se motorise pas, bâti absent.

**Contrôle de la géométrie.** Après lecture, la fermeture de chaque liaison est vérifiée.
Si la configuration enregistrée n'est pas assemblée (fichier modifié à la main, par
exemple), l'écart est signalé liaison par liaison et le mécanisme est refermé.

**Fichiers abîmés.** Fichier vide, binaire, tronqué, JSON invalide (la ligne et la colonne
sont indiquées), `NaN`, encodage inattendu (UTF-8 avec ou sans BOM, UTF-16, sinon
Windows-1252 avec un avertissement), taille déraisonnable : chaque cas a son message.
Les tests soumettent le lecteur à plusieurs milliers de documents altérés au hasard ; il
répond toujours par un projet cohérent ou par une erreur expliquée.

## Écriture

L'enregistrement est **atomique** : le texte est écrit dans un fichier temporaire du même
dossier, synchronisé sur le disque, puis substitué à l'ancien en une opération. Une
coupure pendant l'écriture ne peut pas laisser un projet tronqué. La version précédente
est gardée sous `<nom>.sikax.bak`. Un projet contenant une valeur non finie est refusé
avant toute écriture.

Les nombres sont écrits avec tous leurs chiffres significatifs : un projet relu est
exactement égal au projet enregistré, sans perte d'arrondi.

## Versions du format

`version` augmente à chaque changement incompatible. `sikax/fichiers/migrations.py`
contient une fonction par passage de version ; elles s'enchaînent à la lecture. Un
fichier plus récent que l'application est lu au mieux, avec un avertissement.
