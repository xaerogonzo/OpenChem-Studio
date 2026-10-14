"""An independent oracle for the score evaluator (`docs/DERIVED_SCORES_DESIGN.md` section 10).

Random formulas in the grammar are evaluated by the product's parser and evaluator and by a separate, simple evaluator written
HERE over Python's own parse tree, for the arithmetic subset. They must agree on the value or both refuse. The oracle lives in the
test and never in the product: nothing in the product evaluates Python, and `test_score_formula_guard.py` keeps it so.

What it independently decides: precedence and associativity (Python's parser, not ours, reads the text), unary minus against a power,
the arithmetic, every domain error and every overflow. What it shares with the product, by necessity: the formulas of `ramp` and
`clamp`, which are definitions and not a reading of text.
"""

from __future__ import annotations

import ast
import math
import random
import re

import pytest

from openchem.domain.score_formula import FormulaError, Problem, Refusal, evaluate, parse_formula, render

NAMES = ("a", "b", "c")
VALUES = (0.0, 1.0, -1.0, 2.5, -3.75, 0.1, 1e-3, 1e3, 12345.678, 1e150, -1e150, 1e-150, 3.0, 7.0, 0.5, -0.5, 4.0)
NUMBERS = ("0", "1", "2", "3", "0.5", "2.5", "10", "1e3", "1e-3", "7", "0.1", "100", "1e2", "0.25", "5")
FUNCTION_ARITY = {"abs": (1, 1), "min": (2, 4), "max": (2, 4), "clamp": (3, 3), "ramp": (3, 3), "sqrt": (1, 1), "ln": (1, 1), "log10": (1, 1), "exp": (1, 1)}


# --- the generator: the grammar, walked at random -------------------------------------------------------------------------------


def _space(rng: random.Random) -> str:
    return rng.choice(["", " ", "  ", "\t", " \n "])


def _atom(rng: random.Random, depth: int) -> str:
    choices = ["number", "name"] if depth <= 0 else ["number", "name", "paren", "call"]
    kind = rng.choice(choices)
    if kind == "number":
        return rng.choice(NUMBERS)
    if kind == "name":
        return rng.choice(NAMES)
    if kind == "paren":
        return f"({_space(rng)}{_expr(rng, depth - 1)}{_space(rng)})"
    name = rng.choice(list(FUNCTION_ARITY))
    fewest, most = FUNCTION_ARITY[name]
    count = rng.randint(fewest, most)
    return f"{name}({_space(rng)}{(',' + _space(rng)).join(_expr(rng, depth - 1) for _ in range(count))}{_space(rng)})"


def _power(rng: random.Random, depth: int) -> str:
    base = _atom(rng, depth)
    if rng.random() < 0.25:
        return f"{base}{_space(rng)}^{_space(rng)}{rng.choice(['-', ''])}{rng.randint(0, 6)}"
    return base


def _unary(rng: random.Random, depth: int) -> str:
    minus = "-" * rng.choice([0, 0, 0, 1, 1, 2])
    return minus + _space(rng) * (1 if minus else 0) + _power(rng, depth)


def _term(rng: random.Random, depth: int) -> str:
    parts = [_unary(rng, depth)]
    for _ in range(rng.choice([0, 0, 1, 2])):
        parts.append(rng.choice("*/"))
        parts.append(_unary(rng, depth))
    return _space(rng).join(parts)


def _expr(rng: random.Random, depth: int) -> str:
    parts = [_term(rng, depth)]
    for _ in range(rng.choice([0, 1, 1, 2])):
        parts.append(rng.choice("+-"))
        parts.append(_term(rng, depth))
    return _space(rng).join(parts)


#: The longest formula the generator hands over, a margin inside the product's own limit so a formula is not refused for its length.
LONGEST = 400


def random_formula(seed: int) -> tuple[str, dict[str, float]]:
    """A formula in the grammar and a value for each name. The nesting shrinks until the text fits, so the formulas are within the
    limits; a few shapes still exceed the node or depth limit and are skipped, and the tests count them."""
    rng = random.Random(seed)
    depth = rng.choice([1, 2, 2, 3])
    values = {name: rng.choice(VALUES) for name in NAMES}
    while True:
        text = _expr(random.Random(rng.random()), depth)
        if len(text) <= LONGEST or depth == 0:
            return text, values
        depth -= 1


# --- the oracle: Python's own parse tree, walked by this test --------------------------------------------------------------------


class _OracleRefused(Exception):
    pass


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise _OracleRefused("not finite")
    return value


def _exponent(node: ast.expr) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value
    raise AssertionError("the generator wrote an exponent that is not a literal whole number")


def _call(name: str, args: list[float]) -> float:
    try:
        if name == "abs":
            return abs(args[0])
        if name == "min":
            return min(args)
        if name == "max":
            return max(args)
        if name == "clamp":
            x, low, high = args
            if low > high:
                raise _OracleRefused("clamp")
            return min(high, max(low, x))
        if name == "ramp":
            x, a, b = args
            if a == b:
                raise _OracleRefused("ramp")
            return min(1.0, max(0.0, (x - a) / (b - a)))
        if name == "sqrt":
            return _finite(math.sqrt(args[0]))
        if name == "ln":
            return _finite(math.log(args[0]))
        if name == "log10":
            return _finite(math.log10(args[0]))
        if name == "exp":
            return _finite(math.exp(args[0]))
    except (ValueError, OverflowError) as exc:
        raise _OracleRefused(str(exc)) from None
    raise AssertionError(name)


def oracle(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return oracle(node.body, env)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        assert isinstance(node.op, ast.USub)
        return -oracle(node.operand, env)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            base = oracle(node.left, env)
            try:
                return _finite(base ** _exponent(node.right))
            except (ZeroDivisionError, OverflowError):
                raise _OracleRefused("pow") from None
        left, right = oracle(node.left, env), oracle(node.right, env)
        if isinstance(node.op, ast.Add):
            return _finite(left + right)
        if isinstance(node.op, ast.Sub):
            return _finite(left - right)
        if isinstance(node.op, ast.Mult):
            return _finite(left * right)
        assert isinstance(node.op, ast.Div)
        if right == 0:
            raise _OracleRefused("division by zero")
        return _finite(left / right)
    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)
        return _call(node.func.id, [oracle(a, env) for a in node.args])
    raise AssertionError(f"the generator wrote something the oracle does not read: {ast.dump(node)}")


def oracle_value(text: str, env: dict[str, float]) -> float | None:
    """The value by Python's own reading of the text, or None when it refuses."""
    try:
        # Python's grammar ends a statement at a newline; ours treats every whitespace character alike, so the oracle is given one line
        one_line = re.sub(r"\s+", " ", text.strip())
        return oracle(ast.parse(one_line.replace("^", "**"), mode="eval"), env)
    except _OracleRefused:
        return None


def product_value(text: str, env: dict[str, float]) -> float | None:
    formula = parse_formula(text, NAMES)
    try:
        return evaluate(formula, {name: env[name] for name in NAMES})
    except Refusal:
        return None


# --- the tests -------------------------------------------------------------------------------------------------------------------

SEEDS = range(6000)


def test_random_formulas_agree_with_the_oracle_or_both_refuse():
    agreed = refused = skipped = 0
    for seed in SEEDS:
        text, env = random_formula(seed)
        try:
            ours = product_value(text, env)
        except FormulaError as error:
            # the generator only writes the grammar, so a refusal to PARSE is a defect, unless it is one of the size limits
            if error.problem is Problem.LIMIT:
                skipped += 1
                continue
            raise AssertionError(f"seed {seed}: {text!r} is in the grammar and was refused: {error.message}") from error
        theirs = oracle_value(text, env)
        if ours is None or theirs is None:
            assert ours is None and theirs is None, f"seed {seed}: {text!r} with {env}: product {ours!r}, oracle {theirs!r}"
            refused += 1
        else:
            assert ours == theirs, f"seed {seed}: {text!r} with {env}: product {ours!r}, oracle {theirs!r}"
            agreed += 1
    # a oracle that only ever saw refusals, or only values, would prove little
    assert agreed > len(SEEDS) * 0.5 and refused > len(SEEDS) * 0.02 and skipped < len(SEEDS) * 0.05, (agreed, refused, skipped)


def test_the_generator_reaches_every_function_every_operator_and_the_deep_shapes():
    seen_functions, seen_ops, deepest = set(), set(), 0
    for seed in SEEDS:
        text, _ = random_formula(seed)
        seen_functions |= {name for name in FUNCTION_ARITY if f"{name}(" in text.replace(" ", "")}
        seen_ops |= {op for op in "+-*/^" if op in text}
        deepest = max(deepest, text.count("("))
    assert seen_functions == set(FUNCTION_ARITY) and seen_ops == set("+-*/^") and deepest >= 6


def test_the_canonical_text_means_the_same_to_python_as_the_original_text_does():
    """`render` chooses its own parentheses. Python reads the rendered text, by ITS precedence rules, and must get the value the
    original text has, so the minimal parentheses are right and not merely round-trippable through our own parser."""
    for seed in SEEDS:
        text, env = random_formula(seed)
        try:
            tree = parse_formula(text, NAMES).tree
        except FormulaError as error:
            assert error.problem is Problem.LIMIT, f"seed {seed}: {text!r}: {error.message}"
            continue
        rendered = render(tree)
        assert parse_formula(rendered, NAMES).tree == tree, f"seed {seed}: {text!r} -> {rendered!r}"
        assert oracle_value(rendered, env) == oracle_value(text, env), f"seed {seed}: {text!r} -> {rendered!r}"


@pytest.mark.parametrize(
    ("text", "env", "expected"),
    [
        ("-a^2", {"a": 3.0, "b": 0.0, "c": 0.0}, -9.0),
        ("a - b - c", {"a": 10.0, "b": 3.0, "c": 2.0}, 5.0),
        ("a / b / c", {"a": 100.0, "b": 10.0, "c": 5.0}, 2.0),
        ("a + b * c", {"a": 1.0, "b": 2.0, "c": 3.0}, 7.0),
        ("a * -b", {"a": 2.0, "b": 3.0, "c": 0.0}, -6.0),
        ("a ^ -2", {"a": 2.0, "b": 0.0, "c": 0.0}, 0.25),
    ],
)
def test_the_oracle_itself_reads_precedence_the_way_the_design_says(text, env, expected):
    """The oracle is only worth trusting if it is right on the cases that could go wrong in both."""
    assert oracle_value(text, env) == expected == product_value(text, env)


# --- anything at all: terminates, and refuses in one way ----------------------------------------------------------------------------

#: Characters the fuzz draws from: the grammar's own, whitespace, and everything a person might paste that is not in it.
FUZZ_ALPHABET = (
    "abcxyz_0123456789.eE+-*/^(),  \t\n"
    "ABZ!@#$%&=<>?[]{}|\\;:'\"`~"
    "\u00b2\u00d7\u00f7\u2212\u2044\u0663\uff11\u00e9\u03b1\u200b\u00a0"
)


def test_arbitrary_text_is_either_a_formula_or_a_formula_error_and_never_hangs_or_raises_anything_else():
    """The tokenizer and the parser are loops over untrusted text. This draws 20000 strings from the grammar's characters and
    from characters outside it, and requires that each one returns a formula or raises `FormulaError`, and that an accepted
    formula evaluates to a finite number or a `Refusal`. (A non-ASCII digit once sent a mutated tokenizer round a loop it never
    left; that is what this is for.)"""
    rng = random.Random(20261014)
    accepted = 0
    for _ in range(20000):
        text = "".join(rng.choice(FUZZ_ALPHABET) for _ in range(rng.randint(0, 40)))
        try:
            formula = parse_formula(text, NAMES)
        except FormulaError:
            continue
        accepted += 1
        try:
            value = evaluate(formula, {"a": 1.5, "b": -2.0, "c": 0.0})
        except Refusal:
            continue
        assert math.isfinite(value), text
    assert accepted > 100, "the fuzz never produced a valid formula, so it exercised only the refusals"


def test_a_long_run_of_one_character_terminates_and_is_refused_by_a_limit():
    for text in ("-" * 495 + "a", "(" * 495 + "a", "a" + "+a" * 249, "1" * 500, "a^" * 250, "abs(" * 120 + "a" + ")" * 120):
        with pytest.raises(FormulaError):
            parse_formula(text, NAMES)
