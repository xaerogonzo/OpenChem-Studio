"""Nothing that scores evaluates Python (`docs/DERIVED_SCORES_DESIGN.md` sections 4 and 10).

A derived score is a formula a person typed. It is parsed by a grammar written for it and evaluated by walking the tree that
grammar makes, and no module that does so may import a parser for Python or call something that runs a string. This reads each
module's SYNTAX TREE, never its text: a text scan would match the sentence in the module's own docstring that explains the rule
("there is no `eval`..."), which is the lesson "three guards I wrote matched the prose explaining their own rule".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "src" / "openchem" / "domain"

#: Modules that parse Python or run a string, by import.
FORBIDDEN_MODULES = frozenset({"ast", "code", "codeop", "runpy", "importlib", "builtins"})

#: Bare calls that run, compile or import a string. `compile` is here and NOT among the attributes below, because `re.compile` compiles a
#: regular expression and is ordinary; `builtins.compile` is caught by forbidding the `builtins` import.
FORBIDDEN_NAME_CALLS = frozenset({"eval", "exec", "compile", "__import__"})

#: Attribute calls that run or import a string, whatever the object (`builtins.eval(...)`, `ast.literal_eval(...)`, `importlib.import_module(...)`).
FORBIDDEN_ATTRIBUTE_CALLS = frozenset({"eval", "exec", "__import__", "literal_eval", "import_module", "run_path", "run_module"})


def score_modules() -> list[Path]:
    """Every module that is part of scoring: the `score_*.py` modules of the domain, and the checker tool."""
    return sorted(DOMAIN.glob("score_*.py")) + [ROOT / "tools" / "check_score_formula.py"]


def violations(source: str) -> list[str]:
    """What in `source`'s syntax tree imports a Python parser or runs a string. Empty when there is nothing."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                found.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAME_CALLS:
                found.append(f"a call to {func.id}")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRIBUTE_CALLS:
                found.append(f"a call to {func.attr}")
    return found


# --- the real modules ----------------------------------------------------------------------------------------------------------


def test_the_guard_covers_the_modules_that_matter_and_there_are_no_fewer_than_three():
    names = {path.name for path in score_modules()}
    assert {"score_formula.py", "score_units.py", "check_score_formula.py"} <= names, names


@pytest.mark.parametrize("path", score_modules(), ids=lambda p: p.name)
def test_no_scoring_module_imports_a_python_parser_or_runs_a_string(path):
    assert path.exists(), path
    assert violations(path.read_text(encoding="utf-8")) == []


# --- the guard itself, so a clean result means something ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import ast", ["import ast"]),
        ("import ast.foo", ["import ast.foo"]),
        ("from ast import literal_eval", ["from ast import ..."]),
        ("from ast import parse as p", ["from ast import ..."]),
        ("import code", ["import code"]),
        ("import importlib", ["import importlib"]),
        ("from importlib import import_module", ["from importlib import ..."]),
        ("import builtins", ["import builtins"]),
        ("import runpy", ["import runpy"]),
        ("x = eval('1 + 1')", ["a call to eval"]),
        ("exec('x = 1')", ["a call to exec"]),
        ("c = compile('1', '', 'eval')", ["a call to compile"]),
        ("m = __import__('os')", ["a call to __import__"]),
        ("import builtins\nbuiltins.eval('1')", ["import builtins", "a call to eval"]),
        ("def f():\n    return obj.exec('x')", ["a call to exec"]),
        ("y = module.literal_eval('1')", ["a call to literal_eval"]),
    ],
)
def test_the_guard_finds_each_way_of_evaluating_python(source, expected):
    assert sorted(violations(source)) == sorted(expected)


def test_a_docstring_or_a_string_that_names_the_forbidden_things_is_not_a_violation():
    prose = '"""There is no eval, no exec, no compile, and no import of ast."""\nTEXT = "eval(x) and exec(y)"\n'
    assert violations(prose) == []


def test_a_name_that_merely_contains_a_forbidden_word_is_not_a_call_to_it():
    assert violations("def evaluate(f):\n    return f.evaluate()\nrender_compile = 1\nx = compiler(1)\n") == []


def test_compiling_a_regular_expression_is_ordinary_and_compiling_a_string_of_python_is_not():
    assert violations("import re\nPATTERN = re.compile(r'[a-z]+')\n") == []
    assert violations("source = 'x'\ncode_object = compile(source, '', 'eval')\n") == ["a call to compile"]


def test_ordinary_imports_are_fine():
    assert violations("import math\nimport re\nfrom dataclasses import dataclass\nfrom collections.abc import Mapping\n") == []
