"""The Lewis diagram model, its types, and the electron budget.

**No RDKit in this file.** Every diagram here is built by hand, which is
the point of the model existing separately: a renderer bug cannot
masquerade as a chemistry bug, and the arithmetic can be checked against
counts written from the chemistry rather than produced by the code that
is being tested.

THE ORACLE IS HAND-AUTHORED, and it has already been wrong once. Nitrate
and carbonate went into the plan's table as 4 delocalised electrons from
intuition; both are 2. Every entry below is worked from the full budget:

    total electrons = sum of group valence electrons - total formal charge
                    = 2 x localised pairs + delocalised + 2 x lone pairs
"""

from __future__ import annotations

import pytest

from openchem.chem.lewis_diagram import (
    Abstention,
    Accounting,
    Atom,
    BondPairs,
    Known,
    LewisDiagram,
    Region,
    Status,
    Unknown,
    total,
)

#: Group valence electrons, for building fixtures by hand.
GROUP = {"H": 1, "C": 4, "N": 5, "O": 6, "S": 6, "Cl": 7}


def _atom(index, symbol, lone_pairs, charge=0, x=0.0, y=0.0):
    return Atom(
        index=index,
        symbol=symbol,
        x=x,
        y=y,
        lone_pairs=Known(lone_pairs) if isinstance(lone_pairs, int) else lone_pairs,
        valence_electrons=GROUP[symbol],
        formal_charge=charge,
    )


def _diagram(atoms, bonds, regions=(), status=Status.SUPPORTED):
    return LewisDiagram(
        status=status,
        atoms=tuple(atoms),
        bond_pairs=tuple(
            BondPairs(a, b, Known(n) if isinstance(n, int) else n) for a, b, n in bonds
        ),
        regions=tuple(regions),
    )


# --- the fixtures, each worked by hand ---------------------------------------


def water():
    """O 6 + 2H 2 = 8. Two O-H pairs (4 e-) and two lone pairs (4 e-)."""
    return _diagram(
        [_atom(0, "O", 2), _atom(1, "H", 0), _atom(2, "H", 0)],
        [(0, 1, 1), (0, 2, 1)],
    )


def ammonium():
    """N 5 + 4H 4 = 9, charge +1, so 8. Four bonding pairs, no lone pairs.

    The cation is the case that catches a sign error: subtracting the
    charge is what makes this 8 rather than 10.
    """
    return _diagram(
        [_atom(0, "N", 0, charge=1)] + [_atom(i, "H", 0) for i in range(1, 5)],
        [(0, i, 1) for i in range(1, 5)],
    )


def hydroxide():
    """O 6 + H 1 = 7, charge -1, so 8. One pair, three lone pairs."""
    return _diagram([_atom(0, "O", 3, charge=-1), _atom(1, "H", 0)], [(0, 1, 1)])


def benzene():
    """6C 24 + 6H 6 = 30. Twelve localised pairs -- six ring sigma and six
    C-H -- plus a six-electron region. Never three doubles and three
    singles."""
    atoms = [_atom(i, "C", 0) for i in range(6)] + [_atom(6 + i, "H", 0) for i in range(6)]
    ring = [(i, (i + 1) % 6, 1) for i in range(6)]
    hydrogens = [(i, 6 + i, 1) for i in range(6)]
    region = Region(
        atom_indices=tuple(range(6)),
        electrons=Known(6),
        is_ring=True,
        bonds=tuple((i, (i + 1) % 6) for i in range(6)),
    )
    return _diagram(atoms, ring + hydrogens, [region])


def acetate():
    """2C 8 + 3H 3 + 2O 12 = 23, charge -1, so 24.

    Six localised pairs (C-C, three C-H, two C-O sigma) = 12 e-, one
    two-electron region over O-C-O, and five lone pairs = 10 e-.
    """
    atoms = [
        _atom(0, "C", 0),
        _atom(1, "C", 0),
        _atom(2, "O", 2),
        _atom(3, "O", 3, charge=-1),
        _atom(4, "H", 0),
        _atom(5, "H", 0),
        _atom(6, "H", 0),
    ]
    bonds = [(0, 1, 1), (1, 2, 1), (1, 3, 1), (0, 4, 1), (0, 5, 1), (0, 6, 1)]
    region = Region((1, 2, 3), Known(2), is_ring=False, bonds=((1, 2), (1, 3)))
    return _diagram(atoms, bonds, [region])


def carbon_dioxide():
    """C 4 + 2O 12 = 16. Two localised DOUBLE bonds -- four pairs, 8 e- --
    and four lone pairs, 8 e-. The case where a localised bond carries
    two pairs rather than one."""
    return _diagram(
        [_atom(0, "C", 0), _atom(1, "O", 2), _atom(2, "O", 2)],
        [(0, 1, 2), (0, 2, 2)],
    )


ORACLE = {
    #  fixture          valence  localised pairs  delocalised e-  lone pairs
    "water": (water, 8, 2, 0, 2),
    "ammonium": (ammonium, 8, 4, 0, 0),
    "hydroxide": (hydroxide, 8, 1, 0, 3),
    "carbon dioxide": (carbon_dioxide, 16, 4, 0, 4),
    "benzene": (benzene, 30, 12, 6, 0),
    "acetate": (acetate, 24, 6, 2, 5),
}


@pytest.mark.parametrize("case", list(ORACLE), ids=list(ORACLE))
def test_the_electron_budget_balances_against_the_hand_authored_table(case):
    """**The whole breakdown is printed on failure**, because
    `assert 30 == 28` says nothing about which half is wrong."""
    build, valence, pairs, delocalised, lone_pairs = ORACLE[case]
    diagram = build()

    accounting = diagram.accounting

    assert accounting.valence_electrons == Known(valence), accounting.describe()
    assert accounting.localised_bonding_electrons == Known(2 * pairs), accounting.describe()
    assert accounting.delocalised_electrons == Known(delocalised), accounting.describe()
    assert accounting.lone_pair_electrons == Known(2 * lone_pairs), accounting.describe()
    assert accounting.balances, accounting.describe()


def test_the_charge_is_SUBTRACTED_and_the_two_ions_prove_the_sign():
    """An anion has MORE electrons than its neutral atoms provide and a
    cation fewer, so the sign is the thing to get wrong. Hydroxide's
    atoms give 7 and it has 8; ammonium's give 9 and it has 8."""
    assert hydroxide().accounting.valence_electrons == Known(8)
    assert ammonium().accounting.valence_electrons == Known(8)

    neutral = water().accounting.valence_electrons
    assert neutral == Known(8)


# --- zero is not unknown ------------------------------------------------------


def test_an_unknown_has_no_value_at_all():
    """The type doing the work: anything treating it as a number raises
    at the point of the mistake rather than contributing a silent zero."""
    assert not hasattr(Unknown("because"), "value")
    assert Known(0).value == 0


def test_a_total_is_CONTAGIOUS_rather_than_treating_unknown_as_zero():
    """The lone-pair overlay's fourth-state bug, prevented by
    arithmetic. Iron(III) drew nothing, was not refused, and the status
    bar said "No lone pairs" -- which the analysis had declined to say."""
    assert total([Known(2), Known(3)]) == Known(5)
    assert total([]) == Known(0)

    mixed = total([Known(2), Unknown("a metal"), Known(3)])
    assert isinstance(mixed, Unknown)
    assert "a metal" in mixed.reason


def test_the_reasons_survive_a_total_so_the_ui_can_say_which():
    mixed = total([Unknown("a metal"), Unknown("an unpaired electron"), Known(1)])

    assert "a metal" in mixed.reason and "unpaired" in mixed.reason


def test_a_repeated_reason_is_said_once():
    mixed = total([Unknown("a metal"), Unknown("a metal")])

    assert mixed.reason == "a metal"


def test_an_unknown_lone_pair_count_makes_the_budget_unknown_not_wrong():
    """Pyrrole's region, and iron's lone pairs, are the real cases. The
    budget must decline rather than report a number that omits them."""
    diagram = _diagram(
        [_atom(0, "O", Unknown("a metal centre")), _atom(1, "H", 0)], [(0, 1, 1)]
    )

    accounting = diagram.accounting

    assert isinstance(accounting.lone_pair_electrons, Unknown)
    assert isinstance(accounting.accounted, Unknown)
    assert not accounting.balances, "an unknown budget must never read as balanced"


def test_a_region_with_an_unknown_count_is_still_a_REGION():
    """Pyrrole: the ring IS delocalised and the electron count is not
    determinable from bond orders. Those are different statements and the
    model keeps them apart."""
    region = Region((0, 1, 2, 3, 4), Unknown("a lone pair completes the sextet"), is_ring=True)
    diagram = _diagram([_atom(i, "C", 0) for i in range(5)], [], [region])

    assert diagram.regions[0].is_ring
    assert isinstance(diagram.regions[0].electrons, Unknown)
    assert not diagram.accounting.balances


# --- the four outcomes --------------------------------------------------------


def test_a_refusal_and_a_rendering_failure_never_share_a_message():
    """Different causes, different fixes. Telling a user the second when
    it is the first sends them looking in the wrong place."""
    refused = LewisDiagram(status=Status.CHEMISTRY_REFUSED, reason="an unpaired electron")
    failed = LewisDiagram(status=Status.RENDERING_FAILED, reason="no room beside atom 4")

    assert refused.summary() != failed.summary()
    assert "unavailable" in refused.summary()
    assert "could not be drawn" in failed.summary()
    assert not refused.drawable and not failed.drawable


def test_abstentions_are_counted_and_named_not_lumped_together():
    diagram = LewisDiagram(
        status=Status.SUPPORTED_WITH_ABSTENTIONS,
        atoms=(_atom(0, "S", 0),),
        abstentions=(
            Abstention("S1-O2", "an expanded octet is contested"),
            Abstention("S1-O3", "an expanded octet is contested"),
        ),
    )

    assert diagram.drawable
    assert "2 abstention" in diagram.summary()
    assert all(a.subject for a in diagram.abstentions)


def test_a_region_is_a_RESULT_and_never_an_abstention():
    """Benzene is a success with something to say, not a partial
    failure. Filing its pi system under "bonds we could not draw" would
    report the feature's best answer as a defect."""
    assert benzene().status is Status.SUPPORTED
    assert benzene().abstentions == ()
    assert benzene().regions[0].electrons == Known(6)


# --- labels -------------------------------------------------------------------


@pytest.mark.parametrize(
    "symbol,charge,isotope,expected",
    [
        ("O", 0, 0, "O"),
        ("N", 1, 0, "N+"),
        ("O", -1, 0, "O-"),
        ("H", 0, 2, "2H"),
        ("Cl", 3, 0, "Cl3+"),
        ("C", -2, 0, "C2-"),
    ],
)
def test_the_label_carries_isotope_and_charge_but_no_implicit_hydrogens(
    symbol, charge, isotope, expected
):
    """A Lewis structure draws hydrogens as their own atoms, so there is
    no `NH3` here. That absence is what makes this a different picture
    from the canvas rather than the same one annotated."""
    atom = Atom(0, symbol, 0.0, 0.0, Known(0), GROUP.get(symbol, 4), charge, isotope)

    assert atom.label == expected


def test_an_empty_diagram_accounts_for_nothing_and_says_so():
    empty = LewisDiagram(status=Status.SUPPORTED)

    assert empty.accounting.valence_electrons == Known(0)
    assert empty.accounting.balances, "0 = 0 is a balance, not a failure"


def test_the_model_imports_no_rdkit_and_no_qt():
    """**The separation, asserted rather than intended.**

    The model is the contract between a chemistry builder and an SVG
    renderer. If it reaches for RDKit, the renderer's tests start needing
    a chemistry toolkit and a renderer regression becomes indistinguish-
    able from a chemistry one -- which is the arrangement this whole
    three-layer split exists to avoid.

    Walked as an AST rather than searched as text, for two reasons: the
    prose above says "RDKit" repeatedly and a string check flags its own
    documentation, and an AST walk still reaches a LAZY import inside a
    function, which `sys.modules` at test time would not.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "src/openchem/chem/lewis_diagram.py"
    ).read_text(encoding="utf-8")

    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = [
        name
        for name in imported
        if name.split(".")[0] in {"rdkit", "PySide6", "PyQt5", "PyQt6"}
        or name.startswith("openchem.chem.lewis.")
        or name == "openchem.chem.lewis"
    ]
    assert not offenders, f"lewis_diagram.py imports {offenders}"
    assert imported, "nothing imported at all -- the walk found nothing to check"
