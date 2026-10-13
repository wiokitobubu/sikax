"""Évaluateur d'expressions : sécurité, valeurs et dérivées exactes."""

import math

import pytest

from sikax.util.expression import (
    ErreurExpression,
    Expression,
    compiler,
    evaluer,
    evaluer_jet,
    vers_nombre_ou_expression,
)

EXPRESSIONS = [
    "0.2*sin(2*pi*t) + t^2",
    "exp(-0.5*t)*cos(3*t)",
    "sqrt(1 + t**2) / (2 + t)",
    "atan2(sin(t), 2 + cos(t))",
    "tanh(t) + log(1 + t*t) - log10(2 + t)",
    "lisse(t, 0.2, 1.7) * 3",
    "(1 + t)**(2*t)",
    "asin(0.5*sin(t)) + acos(0.3*cos(t)) + atan(t)",
    "sinh(0.3*t) - cosh(0.2*t) + tan(0.1*t)",
    "abs(t - 5) + rad(30*t) + deg(0.01*t)",
    "3*t**3 - 2*t + 1 if t < 10 else 0",
]


@pytest.mark.parametrize("source", EXPRESSIONS)
@pytest.mark.parametrize("t", [0.37, 0.9, 1.31])
def test_derivees_exactes(source, t):
    e = compiler(source)
    v, d1, d2 = e.jet(t).tuple()
    h = 1e-4
    num1 = (e.valeur(t + h) - e.valeur(t - h)) / (2 * h)
    num2 = (e.valeur(t + h) - 2 * e.valeur(t) + e.valeur(t - h)) / (h * h)
    assert v == pytest.approx(e.valeur(t))
    assert d1 == pytest.approx(num1, rel=1e-6, abs=1e-7)
    assert d2 == pytest.approx(num2, rel=1e-4, abs=1e-5)


def test_valeurs_connues():
    assert evaluer("2*pi") == pytest.approx(2 * math.pi)
    assert evaluer("3^2") == 9.0
    assert evaluer("min(3, 1, 2) + max(4, 7)") == 8.0
    assert evaluer("si(t > 1, 10, 20)", 2.0) == 10.0
    assert evaluer("si(t > 1, 10, 20)", 0.5) == 20.0
    assert evaluer("echelon(t - 1)", 0.5) == 0.0
    assert evaluer("rampe(t, 1, 3)", 2.0) == pytest.approx(0.5)
    assert evaluer("lisse(t, 0, 1)", 0.5) == pytest.approx(0.5)
    assert evaluer("1 < t <= 2 and t != 1.5", 1.7) == 1.0
    assert evaluer(4) == 4.0
    assert evaluer_jet(2.5) == (2.5, 0.0, 0.0)
    assert evaluer("-t", 3.0) == -3.0
    assert evaluer("2×π÷2") == pytest.approx(math.pi)


def test_lisse_est_c2():
    e = compiler("lisse(t, 1, 2)")
    for t in (1.0, 2.0):
        _, d1, d2 = e.jet(t).tuple()
        assert d1 == pytest.approx(0.0, abs=1e-12)
        assert d2 == pytest.approx(0.0, abs=1e-12)
    assert e.valeur(0.0) == 0.0 and e.valeur(5.0) == 1.0


def test_dependance_au_temps():
    assert compiler("2*t").depend_du_temps
    assert not compiler("2*pi").depend_du_temps


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('ls')",
        "().__class__",
        "open('x')",
        "t.real",
        "[1, 2]",
        "lambda: 1",
        "x + 1",
        "sin",
        "sin(1, 2)",
        "t if",
        "",
        "   ",
        "'texte'",
        "True",
        "1 // 2",
        "1 % 2",
        "1 << 2",
        "sin(t=1)",
        "f'{t}'",
        "t[0]",
        "{1: 2}",
        "(t := 3)",
        "1e999",
        "9" * 700,
        "sin(" * 70 + "t" + ")" * 70,
    ],
)
def test_expressions_refusees(source):
    with pytest.raises(ErreurExpression):
        Expression(source)


@pytest.mark.parametrize("source,t", [("1/t", 0.0), ("sqrt(t)", -1.0), ("log(t)", 0.0), ("asin(t)", 2.0), ("exp(1000*t)", 1.0)])
def test_erreurs_de_domaine(source, t):
    with pytest.raises(ErreurExpression):
        compiler(source).jet(t)


def test_constante_invalide_detectee_a_la_compilation():
    with pytest.raises(ErreurExpression):
        Expression("1/0")
    with pytest.raises(ErreurExpression):
        Expression("sqrt(-1)")


def test_saisie_nombre_ou_expression():
    assert vers_nombre_ou_expression("1,5") == 1.5
    assert vers_nombre_ou_expression(" 2.5e3 ") == 2500.0
    assert vers_nombre_ou_expression("1 000,25") == 1000.25
    assert vers_nombre_ou_expression(3) == 3.0
    assert vers_nombre_ou_expression("2*t") == "2*t"
    assert vers_nombre_ou_expression("max(1,2)") == "max(1,2)"
    for mauvais in ("", "abc", "nan", "inf", float("nan"), float("inf"), True):
        with pytest.raises(ErreurExpression):
            vers_nombre_ou_expression(mauvais)
