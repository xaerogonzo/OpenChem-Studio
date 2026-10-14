"""The formula of a derived score: a small grammar, a parser written for it, and a checked evaluator (`docs/DERIVED_SCORES_DESIGN.md`
section 4).

**There is no `eval`, no `exec`, no `compile`, and no use of Python's own parser as the evaluator.** The text is tokenised and parsed
by a recursive-descent parser into a tree of frozen dataclasses, and the tree is evaluated by walking it. Restricting Python's `ast` to
a whitelist is the usual shortcut and is declined: its failure mode is a construct nobody listed, and a grammar has no constructs
nobody listed. `tests/test_score_formula_guard.py` reads this module's own syntax tree and fails on any of them.

```
expr   := term (("+" | "-") term)*
term   := unary (("*" | "/") unary)*
unary  := "-" unary | power
power  := atom ("^" INTEGER)?
atom   := NUMBER | NAME | NAME "(" expr ("," expr)* ")" | "(" expr ")"
```

Three stages, each of which can refuse, and none of which can return a wrong number:

* `parse_formula` -- the text and the names it may use. Syntax, limits, an unknown name or function, the wrong number of arguments.
* `check_units` -- the unit the formula works out to, against the unit the definition declares. Strict and opaque (`score_units.py`).
* `evaluate` -- the number, in IEEE double arithmetic. A division by zero, a domain error, an overflow or any non-finite
  intermediate REFUSES the value, naming the step. It never lets a `nan` or an `inf` through into a number that looks finite.

Pure: no Qt, no chemistry, nothing read from a project.
"""

from __future__ import annotations

import enum
import math
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from openchem.domain.score_units import DIMENSIONLESS, Unit

#: Why a tooling script, and not the application, reaches this module for now. Slice 3 of the design wires it into the project
#: file and the Results reader, and this declaration goes then (`tests/test_calculator_reachability.py` fails a declaration on a
#: module that has become reachable, so it cannot be forgotten).
REACHED_BY = (
    "tooling: tools/check_score_formula.py checks a formula from the command line; the application reaches it in slice 3 of "
    "docs/DERIVED_SCORES_DESIGN.md"
)

#: The longest formula, in characters.
MAX_CHARACTERS = 500

#: The most nodes a tree may hold, every number, name, operator and call counted.
MAX_NODES = 200

#: The deepest nesting. Every parenthesis, unary minus and call argument counts as a level, so none can hide depth; a tree built by a
#: long chain of `+` is measured too, after it is built.
MAX_DEPTH = 24

#: The largest absolute value of an exponent, so no expression can build a huge number by exponentiation.
MAX_EXPONENT = 6

#: The most inputs a definition may declare.
MAX_INPUTS = 12

#: The closed set of functions, by name: `(fewest arguments, most arguments)`, a `None` meaning any number above the fewest.
#: `ramp(x, a, b)` is 0 at `a`, 1 at `b`, linear between and clamped outside; the order of `a` and `b` gives the direction, so a falling
#: desirability is `ramp(x, bad, good)`.
FUNCTIONS: dict[str, tuple[int, int | None]] = {
    "abs": (1, 1),
    "min": (2, None),
    "max": (2, None),
    "clamp": (3, 3),
    "ramp": (3, 3),
    "sqrt": (1, 1),
    "ln": (1, 1),
    "log10": (1, 1),
    "exp": (1, 1),
}

#: What an input name looks like: a lowercase ASCII letter, then lowercase letters, digits and underscores. Never Unicode, so a look-alike
#: letter cannot stand for an input.
_NAME = re.compile(r"[a-z][a-z0-9_]*")

#: The digits, by listing them. `str.isdigit` would accept a Unicode digit (`\u0663`, `\u00b2`), and the tokenizer would then read a
#: number it cannot convert and, worse, loop on it: a mutant that did exactly that is what the fuzz test is for.
_DIGITS = "0123456789"

#: The letters a name may be made of, by listing them, for the same reason as `_DIGITS`.
_LOWER = "abcdefghijklmnopqrstuvwxyz"

#: The characters that separate tokens and mean nothing else.
_WHITESPACE = " \t\r\n"

#: The single-character tokens of the grammar. Anything else that is not a number, a name or whitespace is a syntax error naming it.
_OPERATORS = "+-*/^(),"


class Problem(str, enum.Enum):
    """What is wrong with a definition. Closed, so a test can be total over it."""

    SYNTAX = "syntax"
    LIMIT = "limit"
    NAME = "name"
    FUNCTION = "function"
    EXPONENT = "exponent"
    INPUTS = "inputs"
    UNIT = "unit"


class FormulaError(ValueError):
    """A formula or a definition that cannot be accepted. `position` is a 0-based character index into the text when there is one."""

    def __init__(self, problem: Problem, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.problem = problem
        self.message = message
        self.position = position


class Refusal(Exception):
    """The value cannot be computed: no number is returned. `step` is the part of the formula that could not be evaluated."""

    def __init__(self, step: str, reason: str) -> None:
        super().__init__(f"{reason} (in {step})" if step else reason)
        self.step = step
        self.reason = reason


# --- the tree --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Number:
    value: float
    #: Where it was written, for an error message. Never part of what a tree IS, so two trees that differ only in where they were
    #: written, or how they were spaced, are equal.
    pos: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Name:
    name: str
    pos: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Neg:
    operand: Node
    pos: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Binary:
    op: str
    left: Node
    right: Node
    pos: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Power:
    base: Node
    #: A literal whole number, so a unit's exponents stay integers.
    exponent: int
    pos: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Call:
    function: str
    args: tuple[Node, ...]
    pos: int = field(default=0, compare=False)


Node = Number | Name | Neg | Binary | Power | Call


@dataclass(frozen=True)
class Formula:
    """A parsed formula: its text as written, its tree, and the inputs it uses in the order they first appear."""

    text: str
    tree: Node
    inputs_used: tuple[str, ...]


def children(node: Node) -> tuple[Node, ...]:
    if isinstance(node, Neg):
        return (node.operand,)
    if isinstance(node, Binary):
        return (node.left, node.right)
    if isinstance(node, Power):
        return (node.base,)
    if isinstance(node, Call):
        return node.args
    return ()


def measure(tree: Node) -> tuple[int, int]:
    """`(nodes, depth)` of a tree, counted without recursion so a deep tree cannot overflow the stack it is measured on."""
    nodes, deepest = 0, 0
    stack: list[tuple[Node, int]] = [(tree, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in children(node))
    return nodes, deepest


# --- the text of a tree ----------------------------------------------------------------------------------------------------

#: How tightly each binary operator binds, for `render` to decide where a parenthesis is needed. Both levels are left-associative.
_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}

#: A unary minus binds tighter than a product and looser than a power, which is why `-a^2` is `-(a^2)`.
_NEG_PRECEDENCE = 3

#: A power binds tightest of the operators.
_POWER_PRECEDENCE = 4


def _number_text(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def _precedence(node: Node) -> int:
    if isinstance(node, Binary):
        return _PRECEDENCE[node.op]
    if isinstance(node, Neg):
        return _NEG_PRECEDENCE
    if isinstance(node, Power):
        return _POWER_PRECEDENCE
    return 9


def render(node: Node) -> str:
    """The canonical text of a tree: one spacing, the fewest parentheses that read back as the SAME tree (so `render` then
    `parse_formula` is the identity on trees, which a test asserts). It is what a refusal names as the step, and what a definition's
    digest will be taken over."""
    if isinstance(node, Number):
        return _number_text(node.value)
    if isinstance(node, Name):
        return node.name
    if isinstance(node, Neg):
        inner = render(node.operand)
        return f"-({inner})" if _precedence(node.operand) < _NEG_PRECEDENCE else f"-{inner}"
    if isinstance(node, Power):
        base = render(node.base)
        simple = isinstance(node.base, (Name, Call)) or (isinstance(node.base, Number))
        return f"{base if simple else f'({base})'}^{node.exponent}"
    if isinstance(node, Call):
        return f"{node.function}({', '.join(render(a) for a in node.args)})"
    precedence = _PRECEDENCE[node.op]
    left, right = render(node.left), render(node.right)
    if _precedence(node.left) < precedence:
        left = f"({left})"
    # Left-associative: an equal-precedence right child is a DIFFERENT tree and keeps its parentheses.
    if _precedence(node.right) <= precedence:
        right = f"({right})"
    return f"{left} {node.op} {right}"


# --- the tokens ------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Token:
    kind: str  # "NUMBER", "NAME", an operator character, or "END"
    text: str
    pos: int


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in _WHITESPACE:
            i += 1
        elif c in _OPERATORS:
            tokens.append(_Token(c, c, i))
            i += 1
        elif c in _DIGITS:
            j = i
            while j < n and text[j] in _DIGITS:
                j += 1
            if j < n and text[j] == ".":
                k = j + 1
                while k < n and text[k] in _DIGITS:
                    k += 1
                if k == j + 1:
                    raise FormulaError(Problem.SYNTAX, "a decimal point needs digits after it", j)
                j = k
            if j < n and text[j] in "eE":
                k = j + 1
                if k < n and text[k] in "+-":
                    k += 1
                m = k
                while m < n and text[m] in _DIGITS:
                    m += 1
                if m == k:
                    raise FormulaError(Problem.SYNTAX, "an exponent of ten needs digits after the e", j)
                j = m
            tokens.append(_Token("NUMBER", text[i:j], i))
            i = j
        elif c in _LOWER:
            j = i + 1
            while j < n and (text[j] in _LOWER or text[j] in _DIGITS or text[j] == "_"):
                j += 1
            tokens.append(_Token("NAME", text[i:j], i))
            i = j
        else:
            hint = " (names are lowercase letters, digits and underscores)" if c.isalpha() or c == "_" else ""
            raise FormulaError(Problem.SYNTAX, f"{c!r} is not allowed in a formula{hint}", i)
    tokens.append(_Token("END", "", n))
    return tokens


# --- the parser ------------------------------------------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_Token], inputs: Collection[str]) -> None:
        self._tokens = tokens
        self._at = 0
        self._inputs = list(inputs)
        self._nodes = 0
        self.used: list[str] = []

    # -- plumbing

    def _peek(self) -> _Token:
        return self._tokens[self._at]

    def _take(self) -> _Token:
        token = self._tokens[self._at]
        self._at += 1
        return token

    def _expect(self, kind: str, why: str) -> _Token:
        token = self._peek()
        if token.kind != kind:
            raise FormulaError(Problem.SYNTAX, f"{why}, found {self._describe(token)}", token.pos)
        return self._take()

    @staticmethod
    def _describe(token: _Token) -> str:
        return "the end of the formula" if token.kind == "END" else repr(token.text)

    def _count(self, position: int) -> None:
        self._nodes += 1
        if self._nodes > MAX_NODES:
            raise FormulaError(Problem.LIMIT, f"a formula has at most {MAX_NODES} nodes", position)

    @staticmethod
    def _deeper(depth: int, position: int) -> int:
        if depth + 1 > MAX_DEPTH:
            raise FormulaError(Problem.LIMIT, f"a formula nests at most {MAX_DEPTH} levels deep", position)
        return depth + 1

    # -- the grammar

    def parse(self) -> Node:
        tree = self._expr(1)
        token = self._peek()
        if token.kind != "END":
            raise FormulaError(Problem.SYNTAX, f"unexpected {self._describe(token)}", token.pos)
        return tree

    def _expr(self, depth: int) -> Node:
        left = self._term(depth)
        while self._peek().kind in ("+", "-"):
            op = self._take()
            right = self._term(depth)
            self._count(op.pos)
            left = Binary(op.kind, left, right, op.pos)
        return left

    def _term(self, depth: int) -> Node:
        left = self._unary(depth)
        while self._peek().kind in ("*", "/"):
            op = self._take()
            right = self._unary(depth)
            self._count(op.pos)
            left = Binary(op.kind, left, right, op.pos)
        return left

    def _unary(self, depth: int) -> Node:
        token = self._peek()
        if token.kind == "-":
            self._take()
            operand = self._unary(self._deeper(depth, token.pos))
            self._count(token.pos)
            return Neg(operand, token.pos)
        return self._power(depth)

    def _power(self, depth: int) -> Node:
        base = self._atom(depth)
        caret = self._peek()
        if caret.kind != "^":
            return base
        self._take()
        sign = 1
        if self._peek().kind == "-":
            self._take()
            sign = -1
        token = self._peek()
        if token.kind != "NUMBER" or not token.text.isdigit():
            raise FormulaError(
                Problem.EXPONENT, f"an exponent is a whole number from -{MAX_EXPONENT} to {MAX_EXPONENT}, found {self._describe(token)}", token.pos
            )
        self._take()
        exponent = sign * int(token.text)
        if abs(exponent) > MAX_EXPONENT:
            raise FormulaError(Problem.EXPONENT, f"an exponent is at most {MAX_EXPONENT} in size, not {exponent}", token.pos)
        following = self._peek()
        if following.kind == "^":
            raise FormulaError(Problem.EXPONENT, "a power takes one whole-number exponent; use parentheses to power a power", following.pos)
        self._count(caret.pos)
        return Power(base, exponent, caret.pos)

    def _atom(self, depth: int) -> Node:
        token = self._peek()
        if token.kind == "NUMBER":
            self._take()
            value = float(token.text)
            if not math.isfinite(value):
                raise FormulaError(Problem.SYNTAX, f"the number {token.text} is out of range", token.pos)
            self._count(token.pos)
            return Number(value, token.pos)
        if token.kind == "NAME":
            self._take()
            if self._peek().kind == "(":
                return self._call(token, depth)
            if token.text in FUNCTIONS:
                raise FormulaError(Problem.NAME, f"{token.text} is a function; write {token.text}(...)", token.pos)
            if token.text not in self._inputs:
                known = ", ".join(self._inputs) or "none"
                raise FormulaError(Problem.NAME, f"{token.text!r} is not one of the inputs ({known})", token.pos)
            if token.text not in self.used:
                self.used.append(token.text)
            self._count(token.pos)
            return Name(token.text, token.pos)
        if token.kind == "(":
            self._take()
            inner = self._expr(self._deeper(depth, token.pos))
            self._expect(")", "a parenthesis is never closed: expected ')'")
            return inner
        raise FormulaError(Problem.SYNTAX, f"expected a number, an input, a function or '(', found {self._describe(token)}", token.pos)

    def _call(self, name: _Token, depth: int) -> Node:
        if name.text not in FUNCTIONS:
            raise FormulaError(Problem.FUNCTION, f"{name.text!r} is not a function (the functions are {', '.join(FUNCTIONS)})", name.pos)
        self._take()  # the "("
        inner = self._deeper(depth, name.pos)
        args = [self._expr(inner)]
        while self._peek().kind == ",":
            self._take()
            args.append(self._expr(inner))
        self._expect(")", f"the call to {name.text} is never closed: expected ')'")
        fewest, most = FUNCTIONS[name.text]
        if len(args) < fewest or (most is not None and len(args) > most):
            wanted = f"{fewest}" if most == fewest else f"at least {fewest}" if most is None else f"{fewest} to {most}"
            raise FormulaError(Problem.FUNCTION, f"{name.text} takes {wanted} argument(s), not {len(args)}", name.pos)
        self._count(name.pos)
        return Call(name.text, tuple(args), name.pos)


def check_input_names(names: Collection[str]) -> tuple[str, ...]:
    """The input names of a definition, or a `FormulaError`: at most `MAX_INPUTS`, each a lowercase identifier, none a function's
    name, none repeated."""
    ordered = tuple(names)
    if len(ordered) > MAX_INPUTS:
        raise FormulaError(Problem.INPUTS, f"a definition has at most {MAX_INPUTS} inputs, not {len(ordered)}")
    seen: set[str] = set()
    for name in ordered:
        if not _NAME.fullmatch(name):
            raise FormulaError(Problem.INPUTS, f"{name!r} is not a usable input name: lowercase letters, digits and underscores, starting with a letter")
        if name in FUNCTIONS:
            raise FormulaError(Problem.INPUTS, f"{name!r} is the name of a function and cannot name an input")
        if name in seen:
            raise FormulaError(Problem.INPUTS, f"the input name {name!r} is used twice")
        seen.add(name)
    return ordered


def parse_formula(text: str, inputs: Collection[str]) -> Formula:
    """The formula `text` over the declared `inputs`, or a `FormulaError` saying what is wrong and where."""
    names = check_input_names(inputs)
    if len(text) > MAX_CHARACTERS:
        raise FormulaError(Problem.LIMIT, f"a formula has at most {MAX_CHARACTERS} characters, not {len(text)}", MAX_CHARACTERS)
    if not text.strip():
        raise FormulaError(Problem.SYNTAX, "the formula is empty", 0)
    parser = _Parser(_tokenize(text), names)
    tree = parser.parse()
    _, depth = measure(tree)
    if depth > MAX_DEPTH:
        raise FormulaError(Problem.LIMIT, f"a formula nests at most {MAX_DEPTH} levels deep; this one is {depth}")
    return Formula(text=text, tree=tree, inputs_used=tuple(parser.used))


def unused_inputs(formula: Formula, inputs: Collection[str]) -> tuple[str, ...]:
    """Declared inputs the formula never uses. A definition that carries one would show a number as evidence for something the formula
    does not read, so `check_definition` refuses it."""
    return tuple(name for name in inputs if name not in formula.inputs_used)


# --- units -----------------------------------------------------------------------------------------------------------------


def _unit_error(message: str, node: Node) -> FormulaError:
    return FormulaError(Problem.UNIT, f"{message} (in {render(node)})", node.pos)


def infer_unit(node: Node, units: Mapping[str, Unit]) -> Unit:
    """The unit `node` works out to, by the rules of `docs/DERIVED_SCORES_DESIGN.md` section 4:

    `+`, `-`, `min`, `max` and `clamp` need identical units; `*` and `/` combine exponents; `^n` multiplies them; `ramp(x, a, b)` needs
    `x`, `a` and `b` in one unit and is dimensionless; `sqrt`, `ln`, `log10` and `exp` need a dimensionless argument and give one; a number
    is dimensionless; `abs` keeps its argument's unit.
    """
    if isinstance(node, Number):
        return DIMENSIONLESS
    if isinstance(node, Name):
        return units[node.name]
    if isinstance(node, Neg):
        return infer_unit(node.operand, units)
    if isinstance(node, Power):
        return infer_unit(node.base, units) ** node.exponent
    if isinstance(node, Binary):
        left, right = infer_unit(node.left, units), infer_unit(node.right, units)
        if node.op == "*":
            return left * right
        if node.op == "/":
            return left / right
        if left != right:
            verb = "add" if node.op == "+" else "subtract"
            raise _unit_error(f"cannot {verb} {left} and {right}: they are different units, and there are no conversions", node)
        return left
    argument_units = [infer_unit(a, units) for a in node.args]
    name = node.function
    if name == "abs":
        return argument_units[0]
    if name in ("min", "max", "clamp"):
        first = argument_units[0]
        if any(u != first for u in argument_units[1:]):
            shown = ", ".join(str(u) for u in argument_units)
            raise _unit_error(f"{name} needs every argument in one unit, found {shown}", node)
        return first
    if name == "ramp":
        first = argument_units[0]
        if any(u != first for u in argument_units[1:]):
            shown = ", ".join(str(u) for u in argument_units)
            raise _unit_error(f"ramp needs x, a and b in one unit, found {shown}", node)
        return DIMENSIONLESS
    if not argument_units[0].is_dimensionless:
        raise _unit_error(f"{name} needs a dimensionless argument, found {argument_units[0]}", node)
    return DIMENSIONLESS


def check_units(formula: Formula, input_units: Mapping[str, Unit], result_unit: Unit) -> Unit:
    """The unit the formula works out to; a `FormulaError` unless it equals the declared `result_unit`."""
    worked_out = infer_unit(formula.tree, input_units)
    if worked_out != result_unit:
        raise FormulaError(Problem.UNIT, f"the formula works out to {worked_out}, and the definition declares {result_unit}")
    return worked_out


def check_definition(
    text: str, input_units: Mapping[str, Unit], result_unit: Unit
) -> Formula:
    """Everything that can be said about a definition without a value: the syntax and limits, every name, the unit, and that no declared
    input goes unused. The one call the definition dialog and the loader make."""
    formula = parse_formula(text, list(input_units))
    absent = unused_inputs(formula, input_units)
    if absent:
        raise FormulaError(
            Problem.INPUTS,
            f"the input(s) {', '.join(absent)} are declared and not used; remove them, or a number would be shown as evidence the formula does not read",
        )
    check_units(formula, input_units, result_unit)
    return formula


# --- evaluation ------------------------------------------------------------------------------------------------------------


def _finite(value: float, node: Node) -> float:
    if not math.isfinite(value):
        raise Refusal(render(node), "the result is not a finite number")
    return value


def _eval(node: Node, values: Mapping[str, float]) -> float:
    if isinstance(node, Number):
        return node.value
    if isinstance(node, Name):
        return values[node.name]
    if isinstance(node, Neg):
        return -_eval(node.operand, values)
    if isinstance(node, Power):
        base = _eval(node.base, values)
        try:
            return _finite(base**node.exponent, node)
        except ZeroDivisionError:
            raise Refusal(render(node), f"zero cannot be raised to {node.exponent}") from None
        except OverflowError:
            raise Refusal(render(node), "the result is too large to represent") from None
    if isinstance(node, Binary):
        left, right = _eval(node.left, values), _eval(node.right, values)
        if node.op == "+":
            return _finite(left + right, node)
        if node.op == "-":
            return _finite(left - right, node)
        if node.op == "*":
            return _finite(left * right, node)
        if right == 0:
            raise Refusal(render(node), "division by zero")
        return _finite(left / right, node)
    args = [_eval(a, values) for a in node.args]
    return _call(node, args)


def _call(node: Call, args: list[float]) -> float:
    name, step = node.function, render(node)
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
                raise Refusal(step, f"the bounds are the wrong way round ({low} is above {high})")
            return min(high, max(low, x))
        if name == "ramp":
            x, a, b = args
            if a == b:
                raise Refusal(step, "a ramp needs two different ends")
            return min(1.0, max(0.0, (x - a) / (b - a)))
        if name == "sqrt":
            if args[0] < 0:
                raise Refusal(step, f"the square root of {args[0]} is not a real number")
            return _finite(math.sqrt(args[0]), node)
        if name == "ln":
            if args[0] <= 0:
                raise Refusal(step, f"the logarithm of {args[0]} is undefined")
            return _finite(math.log(args[0]), node)
        if name == "log10":
            if args[0] <= 0:
                raise Refusal(step, f"the logarithm of {args[0]} is undefined")
            return _finite(math.log10(args[0]), node)
        return _finite(math.exp(args[0]), node)  # exp
    except OverflowError:
        raise Refusal(step, "the result is too large to represent") from None


def evaluate(formula: Formula, values: Mapping[str, float]) -> float:
    """The value of `formula` for `values` (by input name), or a `Refusal`. Never a `nan`, never an `inf`, never a zero standing in for
    something that could not be computed.

    Every input the formula uses must be present and a finite number: a missing or non-finite one refuses the score and names the input.
    """
    for name in formula.inputs_used:
        if name not in values:
            raise Refusal(name, f"the input {name} has no value")
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Refusal(name, f"the input {name} is not a number")
        if not math.isfinite(value):
            raise Refusal(name, f"the input {name} is not a finite number")
    return float(_eval(formula.tree, {name: float(values[name]) for name in formula.inputs_used}))
