"""Expressions mathématiques du temps, évaluées sans ``eval``.

Une expression comme ``"0.2*sin(2*pi*t)"`` est analysée avec le module ``ast``
puis compilée en fermetures Python : seuls les nœuds et les noms de la liste
blanche sont acceptés, il n'y a donc aucune exécution de code arbitraire.

L'évaluation propage un *jet* (valeur, dérivée première, dérivée seconde par
rapport à ``t``). Les lois de mouvement obtiennent ainsi vitesse et
accélération exactes, sans différences finies.

Syntaxe : ``+ - * / **`` (``^`` accepté pour la puissance), comparaisons,
``a if condition else b``, la variable ``t``, les constantes ``pi``, ``e``,
``tau``, ``g`` et les fonctions listées dans ``FONCTIONS_DISPONIBLES``.
"""

from __future__ import annotations

import ast
import math
from functools import lru_cache
from typing import Callable, Dict, List, Sequence, Tuple, Union

__all__ = [
    "ErreurExpression",
    "Expression",
    "Jet",
    "FONCTIONS_DISPONIBLES",
    "compiler",
    "evaluer",
    "evaluer_jet",
    "est_expression",
    "vers_nombre_ou_expression",
]

LONGUEUR_MAX = 600
PROFONDEUR_MAX = 60


class ErreurExpression(ValueError):
    """Expression invalide ou impossible à évaluer."""


class Jet:
    """Valeur d'une fonction du temps et ses deux premières dérivées."""

    __slots__ = ("v", "d1", "d2")

    def __init__(self, v: float, d1: float = 0.0, d2: float = 0.0) -> None:
        self.v = v
        self.d1 = d1
        self.d2 = d2

    @property
    def constant(self) -> bool:
        return self.d1 == 0.0 and self.d2 == 0.0

    def __repr__(self) -> str:
        return f"Jet({self.v!r}, {self.d1!r}, {self.d2!r})"

    def tuple(self) -> Tuple[float, float, float]:
        return (self.v, self.d1, self.d2)


# --- arithmétique des jets ----------------------------------------------------

def _add(a: Jet, b: Jet) -> Jet:
    return Jet(a.v + b.v, a.d1 + b.d1, a.d2 + b.d2)


def _sub(a: Jet, b: Jet) -> Jet:
    return Jet(a.v - b.v, a.d1 - b.d1, a.d2 - b.d2)


def _neg(a: Jet) -> Jet:
    return Jet(-a.v, -a.d1, -a.d2)


def _mul(a: Jet, b: Jet) -> Jet:
    return Jet(a.v * b.v, a.d1 * b.v + a.v * b.d1, a.d2 * b.v + 2.0 * a.d1 * b.d1 + a.v * b.d2)


def _div(a: Jet, b: Jet) -> Jet:
    if b.v == 0.0:
        raise ErreurExpression("division par zéro")
    inv = 1.0 / b.v
    u = Jet(inv, -b.d1 * inv * inv, (2.0 * b.d1 * b.d1 - b.v * b.d2) * inv * inv * inv)
    return _mul(a, u)


def _composer(a: Jet, f: float, f1: float, f2: float) -> Jet:
    """Règle de dérivation en chaîne pour g(t) = f(a(t))."""
    return Jet(f, f1 * a.d1, f2 * a.d1 * a.d1 + f1 * a.d2)


def _pow(a: Jet, b: Jet) -> Jet:
    if b.constant:
        n = b.v
        if n == 0.0:
            return Jet(1.0)
        try:
            v = math.pow(a.v, n)
            f1 = n * math.pow(a.v, n - 1.0) if (a.d1 != 0.0 or a.d2 != 0.0) else 0.0
            c2 = n * (n - 1.0)
            f2 = c2 * math.pow(a.v, n - 2.0) if (c2 != 0.0 and a.d1 != 0.0) else 0.0
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ErreurExpression(f"puissance impossible : {a.v:g} ** {n:g}") from exc
        return _composer(a, v, f1, f2)
    if a.v <= 0.0:
        raise ErreurExpression("puissance à exposant variable : la base doit être positive")
    return _exp(_mul(b, _log(a)))


def _exp(a: Jet) -> Jet:
    try:
        v = math.exp(a.v)
    except OverflowError as exc:
        raise ErreurExpression("dépassement de capacité dans exp()") from exc
    return _composer(a, v, v, v)


def _log(a: Jet) -> Jet:
    if a.v <= 0.0:
        raise ErreurExpression("logarithme d'un nombre négatif ou nul")
    return _composer(a, math.log(a.v), 1.0 / a.v, -1.0 / (a.v * a.v))


def _log10(a: Jet) -> Jet:
    r = _log(a)
    k = 1.0 / math.log(10.0)
    return Jet(r.v * k, r.d1 * k, r.d2 * k)


def _sqrt(a: Jet) -> Jet:
    if a.v < 0.0:
        raise ErreurExpression("racine carrée d'un nombre négatif")
    r = math.sqrt(a.v)
    if a.constant:
        return Jet(r)
    if r == 0.0:
        raise ErreurExpression("dérivée de la racine carrée non définie en zéro")
    return _composer(a, r, 0.5 / r, -0.25 / (r * a.v))


def _sin(a: Jet) -> Jet:
    s, c = math.sin(a.v), math.cos(a.v)
    return _composer(a, s, c, -s)


def _cos(a: Jet) -> Jet:
    s, c = math.sin(a.v), math.cos(a.v)
    return _composer(a, c, -s, -c)


def _tan(a: Jet) -> Jet:
    t = math.tan(a.v)
    s = 1.0 + t * t
    return _composer(a, t, s, 2.0 * t * s)


def _asin(a: Jet) -> Jet:
    if not -1.0 <= a.v <= 1.0:
        raise ErreurExpression("asin() : argument hors de [-1, 1]")
    v = math.asin(a.v)
    if a.constant:
        return Jet(v)
    u = 1.0 - a.v * a.v
    if u <= 0.0:
        raise ErreurExpression("dérivée de asin() non définie en ±1")
    r = math.sqrt(u)
    return _composer(a, v, 1.0 / r, a.v / (u * r))


def _acos(a: Jet) -> Jet:
    r = _asin(a)
    return Jet(math.pi / 2.0 - r.v, -r.d1, -r.d2)


def _atan(a: Jet) -> Jet:
    u = 1.0 + a.v * a.v
    return _composer(a, math.atan(a.v), 1.0 / u, -2.0 * a.v / (u * u))


def _atan2(y: Jet, x: Jet) -> Jet:
    d = x.v * x.v + y.v * y.v
    v = math.atan2(y.v, x.v)
    if y.constant and x.constant:
        return Jet(v)
    if d == 0.0:
        raise ErreurExpression("atan2(0, 0) n'est pas dérivable")
    n = x.v * y.d1 - y.v * x.d1
    n1 = x.v * y.d2 - y.v * x.d2
    dd = 2.0 * (x.v * x.d1 + y.v * y.d1)
    return Jet(v, n / d, (n1 * d - n * dd) / (d * d))


def _sinh(a: Jet) -> Jet:
    s, c = math.sinh(a.v), math.cosh(a.v)
    return _composer(a, s, c, s)


def _cosh(a: Jet) -> Jet:
    s, c = math.sinh(a.v), math.cosh(a.v)
    return _composer(a, c, s, c)


def _tanh(a: Jet) -> Jet:
    t = math.tanh(a.v)
    s = 1.0 - t * t
    return _composer(a, t, s, -2.0 * t * s)


def _abs(a: Jet) -> Jet:
    return a if a.v >= 0.0 else _neg(a)


def _signe(a: Jet) -> Jet:
    return Jet(0.0 if a.v == 0.0 else math.copysign(1.0, a.v))


def _echelon(a: Jet) -> Jet:
    return Jet(1.0 if a.v >= 0.0 else 0.0)


def _rad(a: Jet) -> Jet:
    k = math.pi / 180.0
    return Jet(a.v * k, a.d1 * k, a.d2 * k)


def _deg(a: Jet) -> Jet:
    k = 180.0 / math.pi
    return Jet(a.v * k, a.d1 * k, a.d2 * k)


def _min(*args: Jet) -> Jet:
    return min(args, key=lambda j: j.v)


def _max(*args: Jet) -> Jet:
    return max(args, key=lambda j: j.v)


def _fraction(x: Jet, debut: Jet, fin: Jet) -> Jet:
    if fin.v == debut.v:
        raise ErreurExpression("intervalle de transition de largeur nulle")
    return _div(_sub(x, debut), _sub(fin, debut))


def _rampe(x: Jet, debut: Jet, fin: Jet) -> Jet:
    """0 avant ``debut``, 1 après ``fin``, linéaire entre les deux."""
    s = _fraction(x, debut, fin)
    if s.v <= 0.0:
        return Jet(0.0)
    if s.v >= 1.0:
        return Jet(1.0)
    return s


def _lisse(x: Jet, debut: Jet, fin: Jet) -> Jet:
    """Transition 0 → 1 de classe C² (vitesse et accélération nulles aux bords)."""
    s = _fraction(x, debut, fin)
    if s.v <= 0.0:
        return Jet(0.0)
    if s.v >= 1.0:
        return Jet(1.0)
    v = s.v
    f = v * v * v * (10.0 + v * (-15.0 + 6.0 * v))
    f1 = 30.0 * v * v * (1.0 - v) * (1.0 - v)
    f2 = 60.0 * v * (1.0 - v) * (1.0 - 2.0 * v)
    return _composer(s, f, f1, f2)


def _si(cond: Jet, a: Jet, b: Jet) -> Jet:
    return a if cond.v != 0.0 else b


# nom -> (fonction sur jets, nombre minimal d'arguments, nombre maximal ou None)
_FONCTIONS: Dict[str, Tuple[Callable[..., Jet], int, Union[int, None]]] = {
    "sin": (_sin, 1, 1),
    "cos": (_cos, 1, 1),
    "tan": (_tan, 1, 1),
    "asin": (_asin, 1, 1),
    "acos": (_acos, 1, 1),
    "atan": (_atan, 1, 1),
    "atan2": (_atan2, 2, 2),
    "sinh": (_sinh, 1, 1),
    "cosh": (_cosh, 1, 1),
    "tanh": (_tanh, 1, 1),
    "exp": (_exp, 1, 1),
    "ln": (_log, 1, 1),
    "log": (_log, 1, 1),
    "log10": (_log10, 1, 1),
    "sqrt": (_sqrt, 1, 1),
    "racine": (_sqrt, 1, 1),
    "abs": (_abs, 1, 1),
    "signe": (_signe, 1, 1),
    "sign": (_signe, 1, 1),
    "echelon": (_echelon, 1, 1),
    "rad": (_rad, 1, 1),
    "deg": (_deg, 1, 1),
    "min": (_min, 1, None),
    "max": (_max, 1, None),
    "pow": (_pow, 2, 2),
    "rampe": (_rampe, 3, 3),
    "lisse": (_lisse, 3, 3),
    "si": (_si, 3, 3),
}

FONCTIONS_DISPONIBLES: Tuple[str, ...] = tuple(sorted(_FONCTIONS))

_CONSTANTES: Dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": 2.0 * math.pi,
    "g": 9.81,
}

_BINAIRES = {
    ast.Add: _add,
    ast.Sub: _sub,
    ast.Mult: _mul,
    ast.Div: _div,
    ast.Pow: _pow,
}

_COMPARAISONS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}

Evaluateur = Callable[[float], Jet]

# Espace, espace insécable et espace fine insécable (séparateurs de milliers).
_SANS_ESPACES = {0x20: None, 0xA0: None, 0x202F: None}


def _normaliser(source: str) -> str:
    texte = source.strip()
    for avant, apres in (("^", "**"), ("π", "pi"), ("×", "*"), ("·", "*"), ("÷", "/"), ("−", "-")):
        texte = texte.replace(avant, apres)
    return texte


class _Compilateur:
    def __init__(self) -> None:
        self.depend_du_temps = False

    def compiler(self, noeud: ast.AST, profondeur: int = 0) -> Evaluateur:
        if profondeur > PROFONDEUR_MAX:
            raise ErreurExpression("expression trop imbriquée")
        p = profondeur + 1

        if isinstance(noeud, ast.Constant):
            valeur = noeud.value
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
                raise ErreurExpression(f"constante non numérique : {valeur!r}")
            if not math.isfinite(float(valeur)):
                raise ErreurExpression("nombre non fini")
            jet = Jet(float(valeur))
            return lambda t: jet

        if isinstance(noeud, ast.Name):
            nom = noeud.id
            if nom == "t":
                self.depend_du_temps = True
                return lambda t: Jet(t, 1.0, 0.0)
            if nom in _CONSTANTES:
                jet = Jet(_CONSTANTES[nom])
                return lambda t: jet
            raise ErreurExpression(f"nom inconnu : « {nom} »")

        if isinstance(noeud, ast.UnaryOp):
            operande = self.compiler(noeud.operand, p)
            if isinstance(noeud.op, ast.USub):
                return lambda t: _neg(operande(t))
            if isinstance(noeud.op, ast.UAdd):
                return operande
            if isinstance(noeud.op, ast.Not):
                return lambda t: Jet(0.0 if operande(t).v != 0.0 else 1.0)
            raise ErreurExpression("opérateur unaire non autorisé")

        if isinstance(noeud, ast.BinOp):
            operation = _BINAIRES.get(type(noeud.op))
            if operation is None:
                raise ErreurExpression("opérateur non autorisé")
            gauche = self.compiler(noeud.left, p)
            droite = self.compiler(noeud.right, p)
            return lambda t: operation(gauche(t), droite(t))

        if isinstance(noeud, ast.Compare):
            termes = [self.compiler(noeud.left, p)] + [self.compiler(c, p) for c in noeud.comparators]
            tests = []
            for op in noeud.ops:
                test = _COMPARAISONS.get(type(op))
                if test is None:
                    raise ErreurExpression("comparaison non autorisée")
                tests.append(test)

            def comparer(t: float) -> Jet:
                valeurs = [f(t).v for f in termes]
                for i, test in enumerate(tests):
                    if not test(valeurs[i], valeurs[i + 1]):
                        return Jet(0.0)
                return Jet(1.0)

            return comparer

        if isinstance(noeud, ast.BoolOp):
            termes = [self.compiler(v, p) for v in noeud.values]
            if isinstance(noeud.op, ast.And):
                return lambda t: Jet(1.0 if all(f(t).v != 0.0 for f in termes) else 0.0)
            return lambda t: Jet(1.0 if any(f(t).v != 0.0 for f in termes) else 0.0)

        if isinstance(noeud, ast.IfExp):
            condition = self.compiler(noeud.test, p)
            si_vrai = self.compiler(noeud.body, p)
            si_faux = self.compiler(noeud.orelse, p)
            return lambda t: si_vrai(t) if condition(t).v != 0.0 else si_faux(t)

        if isinstance(noeud, ast.Call):
            if not isinstance(noeud.func, ast.Name) or noeud.keywords:
                raise ErreurExpression("appel de fonction non autorisé")
            nom = noeud.func.id
            if nom not in _FONCTIONS:
                raise ErreurExpression(f"fonction inconnue : « {nom} »")
            fonction, mini, maxi = _FONCTIONS[nom]
            n = len(noeud.args)
            if n < mini or (maxi is not None and n > maxi):
                attendu = str(mini) if maxi == mini else f"au moins {mini}"
                raise ErreurExpression(f"{nom}() attend {attendu} argument(s), {n} fourni(s)")
            arguments = [self.compiler(a, p) for a in noeud.args]
            if n == 1:
                unique = arguments[0]
                return lambda t: fonction(unique(t))
            return lambda t: fonction(*[a(t) for a in arguments])

        raise ErreurExpression("élément de syntaxe non autorisé")


class Expression:
    """Expression compilée de la variable ``t``."""

    __slots__ = ("source", "_fonction", "depend_du_temps")

    def __init__(self, source: str) -> None:
        if not isinstance(source, str):
            raise ErreurExpression("une expression doit être une chaîne de caractères")
        if len(source) > LONGUEUR_MAX:
            raise ErreurExpression("expression trop longue")
        texte = _normaliser(source)
        if not texte:
            raise ErreurExpression("expression vide")
        try:
            arbre = ast.parse(texte, mode="eval")
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            raise ErreurExpression("syntaxe invalide") from exc
        compilateur = _Compilateur()
        self.source = source.strip()
        try:
            self._fonction = compilateur.compiler(arbre.body)
        except RecursionError as exc:
            raise ErreurExpression("expression trop imbriquée") from exc
        self.depend_du_temps = compilateur.depend_du_temps
        # Une première évaluation détecte tôt les erreurs de domaine constantes.
        if not self.depend_du_temps:
            self.jet(0.0)

    def jet(self, t: float) -> Jet:
        try:
            resultat = self._fonction(float(t))
        except ErreurExpression:
            raise
        except (ArithmeticError, ValueError) as exc:
            raise ErreurExpression(f"évaluation impossible à t = {t:g} : {exc}") from exc
        if not (math.isfinite(resultat.v) and math.isfinite(resultat.d1) and math.isfinite(resultat.d2)):
            raise ErreurExpression(f"résultat non fini à t = {t:g}")
        return resultat

    def valeur(self, t: float = 0.0) -> float:
        return self.jet(t).v

    def __repr__(self) -> str:
        return f"Expression({self.source!r})"


@lru_cache(maxsize=512)
def compiler(source: str) -> Expression:
    """Compile une expression (résultat mis en cache par texte source)."""
    return Expression(source)


Valeur = Union[float, int, str]


def est_expression(valeur: Valeur) -> bool:
    return isinstance(valeur, str)


def evaluer(valeur: Valeur, t: float = 0.0) -> float:
    """Valeur numérique d'un champ qui contient un nombre ou une expression."""
    if isinstance(valeur, str):
        return compiler(valeur).valeur(t)
    return float(valeur)


def evaluer_jet(valeur: Valeur, t: float = 0.0) -> Tuple[float, float, float]:
    if isinstance(valeur, str):
        return compiler(valeur).jet(t).tuple()
    return (float(valeur), 0.0, 0.0)


def depend_du_temps(valeur: Valeur) -> bool:
    return isinstance(valeur, str) and compiler(valeur).depend_du_temps


def vers_nombre_ou_expression(texte: Union[str, float, int]) -> Valeur:
    """Interprète une saisie : nombre (virgule décimale admise) ou expression.

    Lève ``ErreurExpression`` si le texte n'est ni l'un ni l'autre.
    """
    if isinstance(texte, bool):
        raise ErreurExpression("valeur booléenne inattendue")
    if isinstance(texte, (int, float)):
        if not math.isfinite(float(texte)):
            raise ErreurExpression("nombre non fini")
        return float(texte)
    brut = str(texte).strip()
    if not brut:
        raise ErreurExpression("valeur vide")
    candidat = brut.translate(_SANS_ESPACES)
    if candidat.count(",") == 1 and "." not in candidat and "(" not in candidat:
        candidat = candidat.replace(",", ".")
    try:
        nombre = float(candidat)
    except ValueError:
        compiler(brut)
        return brut
    if not math.isfinite(nombre):
        raise ErreurExpression("nombre non fini")
    return nombre


def liste_fonctions() -> List[str]:
    return list(FONCTIONS_DISPONIBLES)


def constantes() -> Sequence[str]:
    return tuple(_CONSTANTES)
