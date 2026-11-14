# Théorie : ce que calcule Sikax

Notations : repère global direct (x à droite, y vers le haut), angles en radians dans le
sens trigonométrique, unités SI. Le bâti est le solide 0.

## 1. Paramétrage

Chaque solide mobile *k* est repéré par trois coordonnées : la position de son centre de
gravité et son orientation.

```text
q = (x_G1, y_G1, θ_1, …, x_Gn, y_Gn, θ_n)
```

Un point P du solide *k*, de coordonnées **s** dans le repère du solide (comptées depuis
G), a pour position, vitesse et accélération :

```text
r_P = r_G + A(θ)·s
v_P = v_G + θ'·B(θ)·s                    B = dA/dθ  (A tourné de 90°)
a_P = a_G + θ''·B(θ)·s − θ'²·A(θ)·s
```

Prendre G comme origine rend la matrice de masse diagonale : `M = diag(m, m, J_G)` pour
chaque solide.

## 2. Liaisons : équations de contrainte

Une liaison impose `Φ(q, t) = 0`. Quatre contraintes élémentaires suffisent
(`calcul/contraintes.py`) :

| Contrainte | Équation | Nombre |
|---|---|---|
| Coïncidence | `r_Pj − r_Pi = 0` | 2 |
| Angle relatif | `θ_j − θ_i − c(t) = 0` | 1 |
| Point sur droite | `n_i · (r_Pj − r_Pi) = 0`, n normale à l'axe lié au solide *i* | 1 |
| Translation pilotée | `u_i · (r_Pj − r_Pi) − c(t) = 0`, u direction de l'axe | 1 |

| Liaison | Contraintes |
|---|---|
| Pivot | coïncidence |
| Glissière | point sur droite + angle relatif constant |
| Encastrement | coïncidence + angle relatif constant |
| Ponctuelle | point sur droite |
| Moteur sur une pivot | angle relatif `c(t) = c0 + f(t)` |
| Moteur sur une glissière | translation pilotée `c(t) = c0 + f(t)` |

Les liaisons de contact (version 2) ajoutent chacune **une** équation :

| Liaison | Équation | Effort transmis |
|---|---|---|
| Engrenage extérieur / intérieur | `ra·(θa − φ) + s·rb·(θb − φ) − c0 = 0`, s = +1 / −1 | effort tangentiel `Ft` au point primitif I |
| Pignon-crémaillère | `u·(Oa − Pb) + σ·ra·(θa − θb) − c0 = 0`, u direction de la ligne primitive | `Ft` le long de la crémaillère |
| Came, poussoir à pointe ou à galet | `|P − C| − (R + ρ) = 0`, C centre du cercle, ρ rayon du galet (0 pour une pointe) | effort normal `Fn`, porté par la normale au cercle |
| Came, poussoir à plateau | `σ·n·(C − P) − R = 0`, n normale à la face du plateau | `Fn`, normal au plateau |

Pour un engrenage, `φ` est la direction de la ligne des centres OaOb, suivie
continûment. Si les deux pivots sont fixes, φ est constant et l'équation se réduit à
`ra·θa + s·rb·θb = cte`, soit le rapport `ωb/ωa = −s·Za/Zb`. Si la ligne des centres
tourne (train épicycloïdal, porte-satellites motorisé), le terme en φ donne exactement
la **formule de Willis** : `(ωb − ωp)/(ωa − ωp) = −s·Za/Zb`.

Les rayons primitifs valent `r = m·Z/2` et l'entraxe `a = m·(Za + s·Zb)/2`. L'équation
est écrite pour que son multiplicateur soit l'effort tangentiel **physique** `Ft` au
point primitif. L'effort radial `Fr = |Ft|·tan α` (α angle de pression, 20° par défaut)
ne travaille pas : il est ajouté aux réactions des pivots après le calcul, ce qui donne
les efforts réels sur les paliers. Le couple transmis à la roue *k* vaut `±Ft·rk`.

**Rendement.** Avec `η < 1`, la roue menée (celle qui reçoit de la puissance, mesurée
par rapport au porte-train s'il y en a un) subit en plus le couple `−(1 − η)·C`, où C
est le couple que la denture exerce sur elle ; le porte-train encaisse la réaction. Elle
ne reçoit donc que η fois la puissance de la roue menante. Ce frottement est
proportionnel à l'effort transmis, donc à λ : les efforts sont obtenus en résolvant
exactement le système linéaire `(Φqᵀ − G)·λ = Q − M·q''`, où G regroupe ces couples
par unité d'effort. Le sens (qui mène, qui est mené) est recalculé à chaque instant.

En dérivant deux fois par rapport au temps :

```text
vitesse        Φq · q' = −Φt
accélération   Φq · q'' = γ(q, q', t)
```

où `Φq` est la jacobienne et `γ` regroupe les termes en vitesse (centripètes, Coriolis)
et la dérivée seconde de la loi du moteur. Les expressions analytiques de `Φq` et `γ`
sont vérifiées par différences finies dans `tests/test_contraintes.py`.

## 3. Validation topologique : mobilité et hyperstatisme

### Graphe des liaisons

Les sommets sont les solides (bâti compris), les arêtes les liaisons. Avec *N* solides,
*L* liaisons et *C* composantes connexes, le nombre de boucles indépendantes (nombre
cyclomatique) est

```text
γ = L − N + C
```

Sikax construit un arbre couvrant depuis le bâti ; chaque liaison hors de l'arbre ferme
une boucle.

### Fermeture cinématique

Le long d'une boucle, la somme des torseurs cinématiques relatifs est nulle. Chaque
mobilité d'une liaison apporte un torseur unitaire, réduit à l'origine :

```text
rotation d'axe e passant par P :     { ω = e ; V(O) = OP ∧ e }
translation de direction e :         { ω = 0 ; V(O) = e }
```

En écrivant ces fermetures pour les γ boucles, on obtient un système linéaire de
`Ec = d·γ` équations (d = 3 dans le plan, 6 dans l'espace) à `Ic` inconnues (la somme
des degrés de liberté des liaisons). Son rang `rc`, évalué dans la configuration
courante, donne :

```text
mobilité          m = Ic − rc
hyperstatisme     h = Ec − rc
```

On retrouve la formule statique `h = Is − Es + m`, avec `Is` la somme des inconnues de
liaison et `Es = d·(N − 1)` ; Sikax affiche les deux écritures. Le rang est calculé par
décomposition en valeurs singulières, après mise à l'échelle des longueurs.

### Dans le plan et dans l'espace

Le même calcul est fait deux fois :

- **dans le plan**, avec les mobilités planes de chaque liaison : c'est le modèle du
  mouvement simulé ;
- **dans l'espace**, en donnant à chaque liaison son *modèle spatial* (une pivot plane
  peut être une pivot, une pivot glissant, une rotule, une linéaire annulaire). Le
  mouvement plan est le même, mais `h` change.

Exemple classique, la bielle-manivelle : `h = 0` dans le plan, `h = 3` dans l'espace avec
quatre liaisons « rigides » (trois pivots et une glissière), et de nouveau `h = 0` avec
pivot, pivot glissant, rotule et pivot glissant (au prix d'une mobilité interne, la
rotation propre du piston). Ce cas est dans `tests/test_topologie.py`.

### Moteurs

En ajoutant les contraintes des moteurs à la jacobienne `Φq` du mouvement plan, Sikax
compte les mobilités réellement pilotées et celles qui restent libres. Une étude
cinématique demande qu'il n'en reste aucune.

## 4. Assemblage (résolution en position)

`Φ(q, t) = 0` est résolu par Gauss-Newton : `Δq = −Φq⁺·Φ`, où `Φq⁺` est la
pseudo-inverse. Le pas de norme minimale laisse le mécanisme au plus près de sa
configuration de départ, ce qui le maintient sur la même branche d'assemblage. Une
recherche linéaire et une limite de rotation par itération assurent la convergence
depuis une position éloignée.

Le déplacement à la souris (outil *Manipuler*) minimise la distance entre le point saisi
et le pointeur dans le noyau de `Φq`, c'est-à-dire parmi les mouvements que les liaisons
autorisent.

## 5. Étude cinématique et efforts (dynamique inverse)

À chaque instant, quand les moteurs fixent toutes les mobilités :

```text
1. position        Φ(q, t) = 0
2. vitesse         Φq · q' = −Φt
3. accélération    Φq · q'' = γ
4. efforts         Φqᵀ · λ = Q − M·q''          (PFD)
```

`Q` regroupe les actions connues : pesanteur, forces, couples, ressorts, amortissements.
Si l'option « inertie » est décochée, le terme `M·q''` est omis : c'est un calcul quasi
statique (PFS à chaque instant).

**Points morts.** Quand le moteur est sur le piston d'une bielle-manivelle, ou sur le
balancier d'un quadrilatère, la manivelle passe par des positions où `Φq` est singulière
(manivelle et bielle alignées). La vitesse de la manivelle y devient indéterminée et une
résolution directe donnerait des efforts de 10¹⁴ N ou bloquerait le calcul. Sikax :

1. **prédit** la position suivante, près d'une singularité (conditionnement de `Φq`
   au-delà de 10³), par extrapolation polynomiale des positions précédentes plutôt
   que par la vitesse : la manivelle continue sur sa lancée, comme sur une machine
   à vapeur, au lieu de rebrousser chemin ;
2. **démarre** d'un point mort en écartant légèrement la configuration dans la
   direction libre du noyau de `Φq` ;
3. **dérive** les vitesses et accélérations par différences finies sur la trajectoire
   au voisinage immédiat de la singularité (conditionnement au-delà de 10⁵), en
   gardant la résolution exacte dans les directions bien conditionnées ;
4. **borne** les efforts : les directions de valeur singulière relative inférieure à
   10⁻⁵ sont écartées de la résolution, et les instants concernés sont signalés
   (bandes grisées sur les courbes, message « points morts franchis »).

Si la loi du moteur demande une position que le mécanisme ne peut pas atteindre (piston
au-delà de sa course), le calcul s'arrête au dernier instant atteint avec un message qui
l'explique et propose de motoriser la manivelle ou de faire une étude dynamique.

## 6. Multiplicateurs de Lagrange et torseurs de liaison

Les multiplicateurs `λ` sont les inconnues de liaison. L'action des liaisons sur le
solide *k* est `−Φq_kᵀ·λ` : une force appliquée en G et un moment en G. Pour une liaison
entre A et B, Sikax en déduit le torseur de **l'action de A sur B**, réduit **au point de
liaison** P (le point porté par B), dans la base globale :

```text
R   = −Φ(r_B)ᵀ · λ
M_G = −Φ(θ_B)ᵀ · λ
N = M_P = M_G − (GP ∧ R)·z
```

On vérifie ainsi que le moment est nul au centre d'une pivot, que la résultante d'une
glissière est normale à son axe, etc. L'effort d'un moteur est l'opposé de son
multiplicateur : un couple (N·m) pour une pivot, une force (N) pour une glissière. Sa
puissance est `effort × vitesse imposée`.

Les tests isolent chaque solide et vérifient que la somme des torseurs extérieurs est
nulle (PFS) ou égale au torseur dynamique (PFD).

## 7. Étude statique (PFS)

Dans la configuration donnée : `Φqᵀ · λ = Q`.

- Système carré et régulier : mécanisme isostatique, solution unique.
- `h > 0` : plus d'inconnues que d'équations indépendantes. La solution de norme
  minimale est retenue, avec un avertissement : sans modèle de déformation, la
  répartition entre liaisons surabondantes n'est pas déterminée.
- Mobilité non bloquée : le système n'a de solution que si les actions ne travaillent
  pas dans cette mobilité. Sinon Sikax indique que le mécanisme n'est pas en équilibre.

**Position d'équilibre.** Le mécanisme est déplacé dans la direction `N·Nᵀ·Q` (la
projection des actions sur les mouvements permis, N base du noyau de `Φq`), avec un pas
qui s'allonge tant que la direction se confirme et se raccourcit quand elle s'inverse.
C'est une descente de l'énergie potentielle : elle aboutit à un équilibre stable.

## 8. Étude dynamique (PFD)

```text
M·q'' + Φqᵀ·λ = Q(q, q', t)
Φq·q'' = γ
```

**Résolution par le noyau.** Avec `Φq = U·S·Vᵀ` :

```text
q''p = Φq⁺ · γ                         accélération imposée par les liaisons
N    = colonnes de V au-delà du rang   mouvements permis
(Nᵀ·M·N)·z = Nᵀ·(Q − M·q''p)           dynamique dans ces mouvements
q''  = q''p + N·z
λ    = (Φqᵀ)⁺ · (Q − M·q'')
```

Cette forme reste valable quand les équations de liaison sont liées (mécanisme
hyperstatique) et quand un solide n'a pas de masse, tant que chaque mobilité libre
entraîne de l'inertie (`Nᵀ·M·N` définie positive, ce que Sikax vérifie avant de lancer).

**Intégration.** L'état `y = (q, v)` est intégré par `scipy.integrate.solve_ivp`, avec
la méthode choisie dans l'étude : **Radau** (implicite, d'ordre 5, par défaut), **BDF**,
**LSODA** (bascule seule entre méthodes raides et non raides), **DOP853** ou **RK45**
(explicites). Les méthodes implicites supportent les problèmes raides : ressorts très
raides, solides très légers à côté de solides lourds, passages près d'un point mort.

À chaque évaluation, les accélérations sont obtenues par un **lagrangien augmenté** :

```text
A = M + α·Φqᵀ·Φq          α = 10⁶ × (masse la plus grande) / max diag(Φqᵀ·Φq)
A·q'' = Q − Φqᵀ·λ + α·Φqᵀ·γ
λ ← λ + α·(Φq·q'' − γ)     (3 itérations)
```

`A` reste définie positive même quand les liaisons sont surabondantes ou qu'un solide
n'a pas de masse, et la factorisation de Cholesky est faite une fois par évaluation.
Les écarts numériques sur les liaisons sont repris en douceur (stabilisation de temps
caractéristique τ = 0,05 s) :

```text
q' = v̂ + δq/τ        v' = q'' + (v̂ − v)/τ
```

où `v̂` est la vitesse ramenée sur `Φq·v = −Φt` et `δq` le petit déplacement qui
referme `Φ = 0`. Les résultats enregistrés sont ensuite **reprojetés exactement** sur
les liaisons, en position puis en vitesse, et les accélérations et efforts y sont
recalculés par la méthode du noyau ci-dessus : les courbes respectent les liaisons à la
tolérance de l'étude.

**Sécurités.**

- Si la méthode choisie échoue en cours de route, le calcul reprend au dernier instant
  atteint avec une autre méthode (Radau → BDF → LSODA…), et le message l'indique.
- Un solide dont la vitesse dépasse 10⁴ rad/s ou 10³ m/s arrête le calcul : c'est un
  **emballement** (couple moteur que rien n'équilibre). Le message donne le solide,
  la vitesse atteinte et l'instant.
- Une énergie cinétique qui ne fait que croître jusqu'à plus de 100 fois sa valeur du
  début est signalée (« accélération continue »).
- Un intégrateur qui piétine (le temps n'avance plus) est arrêté proprement, et une
  expression qui devient incalculable (racine d'un nombre négatif…) donne une erreur
  claire au lieu d'interrompre le programme.
- Sans mobilité libre (tout est imposé par les moteurs), le PFD ne sert qu'aux efforts :
  le calcul est fait directement, comme l'étude cinématique avec inertie.

**Configurations singulières.** Quand une direction de liaison devient presque dégénérée
(valeur singulière relative inférieure à 10⁻⁶), elle n'est plus imposée en accélération ;
la projection en position continue de la faire respecter. Sans cela, la division par une
valeur singulière minuscule rend le problème raide et l'intégrateur s'arrête. Un double
parallélogramme traverse ainsi sa position aplatie en conservant son énergie (écart
relatif inférieur à 10⁻⁶, vérifié par un test).

**Conditions initiales.** Les vitesses initiales demandées sur les liaisons sont
satisfaites au mieux, puis projetées sur les liaisons.

## 9. Lois de mouvement et expressions

Une loi fournit `f(t)`, `f'(t)` et `f''(t)`. Pour une expression saisie par
l'utilisateur, les dérivées sont obtenues par différentiation automatique : chaque
opération propage le triplet (valeur, dérivée, dérivée seconde). Vitesses et
accélérations imposées sont donc exactes. L'analyse de l'expression n'utilise pas
`eval` : seuls les opérateurs, fonctions et noms d'une liste blanche sont acceptés.

## 10. Validation numérique

| Cas | Référence | Écart constaté |
|---|---|---|
| Bielle-manivelle, position, vitesse, accélération du piston | formules analytiques | < 10⁻⁸ |
| Couple moteur quasi statique | travaux virtuels, `C = F·dx/dθ` | < 10⁻⁸ N·m |
| Puissance moteur (4 mécanismes) | dérivée de l'énergie mécanique | < 0,02 % |
| Poutre sur deux appuis, console | statique élémentaire | exact |
| Pendule pesant, petites oscillations | `T = 2π·√(2L/3g)` | < 0,02 % |
| Pendule lâché à l'horizontale | intégrale elliptique | < 0,001 % |
| Masse-ressort-amortisseur | solution exponentielle | < 2·10⁻⁸ m |
| Volant freiné | `ω = ω0·exp(−c·t/J)` | < 10⁻⁶ |
| Échelle glissant contre un mur | `θ'' = −(3g/2L)·cos θ`, décollement à `sin θ = ⅔·sin θ0` | < 10⁻⁹ au lâcher ; décollement trouvé à un pas d'échantillonnage près |
| Énergie du double pendule sur 5 s | conservation | < 2·10⁻⁶ de l'énergie échangée |
| Pendule, petites oscillations, chacun des 5 intégrateurs | `T = 2π·√(2L/3g)·(1 + θ0²/16)` | < 3·10⁻⁷ |
| Réducteur à deux étages 15/45 – 15/45 | rapport 1/9 | < 2·10⁻¹⁴ |
| Train épicycloïdal (couronne fixe) | formule de Willis | < 10⁻⁶ |
| Came excentrique, poussoir à pointe, galet ou plateau, deux tours | levée analytique | < 10⁻¹⁰ m |
| Piston piloté sur toute sa course, deux tours de manivelle | géométrie exacte de la bielle-manivelle | < 2·10⁻¹⁰ m ; 720° sans saut ; effort moteur borné (< 260 N) |
