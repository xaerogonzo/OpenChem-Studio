"""Build `chem/data/tsei_radii.json` -- the covalent radii Cao-Liu TSEI needs.

    uv run --no-sync python tools/build_tsei_radii.py

**A RADIUS TABLE IS AN INPUT DATASET, NOT AN IMPLEMENTATION DETAIL.**
`R_C = 0.772` decides every number this method produces and RDKit
disagrees with it (`GetRcovalent("C")` is 0.760, the Cordero 2008 set),
so left inline it becomes an unexplained magic number that the next
reader "corrects" toward the library value. Measured: RDKit's radii put
the paper's own chlorine example at 1.5052 against a printed 1.4190.

**THE SOURCE TABLE IS Lange's Handbook of Chemistry, 15th ed., Table 4.7
"Covalent Radii for Atoms", p 4.35** -- [source:cao2004]'s own ref 18,
[source:langes15]. Read from the book, and confirmed against a 400 dpi
render of that page rather than trusted to the text layer. Its footnote
is the one that matters: *"Single-bond radii are for a tetrahedral
(CN = 4) structure"*, which is what makes these the right column.

TWO INDEPENDENT ROUTES AGREE TO THE LAST DIGIT
==============================================

The book was not held when this file was first written, so every radius
was **recovered by inverting a TSEI value the paper prints**: for a lone
first-tier atom X, eq 8a collapses to `8 rho^3 / (1 + rho)^3` with
`rho = R_X / R_C`, which inverts to a radius. That gave

    F   0.7449  ->  0.63997     Cl  1.4190  ->  0.99001
    Br  1.6957  ->  1.14002     I   2.0265  ->  1.33000
    H   from Me  = 1.0362  ->  0.30001
    O   from MeO = 0.9505  ->  0.66000

**The book gives 64, 99, 114, 133, 30 and 66 pm**, and carbon at
**77.2 pm** rather than a rounded 77 -- the extra digit the paper writes,
which is what identifies this as the right table rather than a
neighbouring one. Seven for seven, from a transcription and a
back-calculation that share no step.

`tests/test_tsei.py` asserts that agreement, so the inversion survives as
a live cross-check on the transcription rather than as history: a mistyped
radius for any of those seven fails against the paper's printed TSEI.

**NINETEEN MORE ELEMENTS SHIP BECAUSE THE BOOK HAS THEM**, and nitrogen,
sulfur and phosphorus are the ones that matter -- the paper prints no TSEI
for any substituent containing them, so the inversion could never reach
them and the projection refused every amine and thiol. It does not now.

**THE EQUATION IS GEOMETRIC AND THE VALIDATION IS NOT**, which is the
distinction to keep. `R^3 / l^3` has no per-element fitting, so a radius
is the only input any element needs; but Cao & Liu validated TSEI on
alkyl, halogen and ether substituents, so a silver or a mercury radius
buys arithmetic rather than evidence. `chem/tsei.py`'s contract says so.

TRANSCRIPTION NOTES
===================

- The book's ordering is alphabetical **except that Silicon precedes
  Selenium**, which is the book's own quirk and not a misread row.
- Radii are printed in **pm** and stored in the paper's `1e-8 cm`
  (= 100 pm), so every value here is the book's divided by 100.
- Only the **single-bond** column is carried. The double- and
  triple-bond columns exist and are not used: the paper takes one radius
  per element -- its chlorine example uses 0.99 whatever the bond order
  -- and eq 8a is stated per atom X with covalent radius R_X.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "openchem" / "chem" / "data"

_ATTRIBUTION = (
    "Covalent radii from J. A. Dean (ed.), Lange's Handbook of Chemistry, "
    "15th ed.; McGraw-Hill: New York, 1999; Table 4.7 'Covalent Radii for "
    "Atoms', p 4.35 -- the source cited as ref 18 by C. Cao & L. Liu, "
    "'Topological Steric Effect Index and Its Application', J. Chem. Inf. "
    "Comput. Sci. 2004;44:678-687, doi:10.1021/ci034266b. Transcribed from a "
    "400 dpi render of that page."
)

#: Table 4.7's single-bond column, in the book's own order, in **pm**.
#: The element name is the book's; the symbol is added here and asserted
#: against RDKit's periodic table by the build below, so a typo cannot
#: ship as a silently unreachable row.
_TABLE_4_7_PM: list[tuple[str, str, float]] = [
    ("Aluminum", "Al", 126),
    ("Antimony", "Sb", 141),
    ("Arsenic", "As", 121),
    ("Beryllium", "Be", 106),
    ("Boron", "B", 88),
    ("Bromine", "Br", 114),
    ("Cadmium", "Cd", 148),
    ("Carbon", "C", 77.2),
    ("Chlorine", "Cl", 99),
    ("Copper", "Cu", 135),
    ("Fluorine", "F", 64),
    ("Gallium", "Ga", 126),
    ("Germanium", "Ge", 122),
    ("Hydrogen", "H", 30),
    ("Indium", "In", 144),
    ("Iodine", "I", 133),
    ("Magnesium", "Mg", 140),
    ("Mercury", "Hg", 148),
    ("Nitrogen", "N", 70),
    ("Oxygen", "O", 66),
    ("Phosphorus", "P", 110),
    # The book prints Silicon before Selenium. Kept in its order so a
    # future audit runs against the page line by line.
    ("Silicon", "Si", 117),
    ("Selenium", "Se", 117),
    ("Silver", "Ag", 152),
    ("Sulfur", "S", 104),
    ("Tellurium", "Te", 137),
    ("Tin", "Sn", 140),
    ("Zinc", "Zn", 131),
]

#: `symbol -> the TSEI value the paper prints that this radius can be
#: recovered from`. SEVEN OF THE TWENTY-EIGHT, and they are the
#: cross-check: a transcription slip in any of them disagrees with a
#: printed TSEI, from a route that shares no step with the transcription.
#:
#: Carbon and chlorine are also printed OUTRIGHT in the paper's worked
#: examples ("the carbon atomic covalent radius RC is 0.772 x 10-8 cm";
#: "Its atomic covalent radius is 0.99 x 10-8 cm").
_CROSS_CHECKED: dict[str, str] = {
    "C": "printed outright in the eq 5a worked example; Table 1's whole series",
    "Cl": "printed outright in the heteroatom worked example; Table 6 Cl = 1.4190",
    "H": "inverted from Table 6 Me = 1.0362 (hydrogens included)",
    "O": "inverted from Table 6 MeO = 0.9505; OEt = 0.9939 uses O and H together",
    "F": "inverted from Table 6 F = 0.7449",
    "Br": "inverted from Table 6 Br = 1.6957",
    "I": "inverted from Table 6 I = 2.0265",
}

#: Every TSEI value the paper prints for a substituent containing an
#: element other than carbon, or containing hydrogens explicitly. These are
#: the acceptance oracle for the general form -- and for the seven radii
#: above, which were derived from a subset of them before the book arrived.
#:
#: `hydrogens` says which of the paper's two conventions the row uses:
#: Table 1/2/4 ignore hydrogens (eq 6's simplification), Table 6 includes
#: them and its footnote c says so outright. One paper, two conventions,
#: each labelled -- so a consumer must say which it wants.
_REFERENCE_VALUES: list[dict] = [
    {"label": "Me", "smiles": "CC", "tsei": 1.0362, "hydrogens": True, "table": "6"},
    {"label": "Et", "smiles": "CCC", "tsei": 1.1581, "hydrogens": True, "table": "6"},
    {"label": "t-Bu", "smiles": "CC(C)(C)C", "tsei": 1.8395, "hydrogens": True, "table": "6"},
    {"label": "MeO", "smiles": "COC", "tsei": 0.9505, "hydrogens": True, "table": "6"},
    {"label": "OEt", "smiles": "COCC", "tsei": 0.9939, "hydrogens": True, "table": "6"},
    {"label": "F", "smiles": "CF", "tsei": 0.7449, "hydrogens": True, "table": "6"},
    {"label": "Cl", "smiles": "CCl", "tsei": 1.4190, "hydrogens": True, "table": "6"},
    {"label": "Br", "smiles": "CBr", "tsei": 1.6957, "hydrogens": True, "table": "6"},
    {"label": "I", "smiles": "CI", "tsei": 2.0265, "hydrogens": True, "table": "6"},
    {"label": "Me", "smiles": "CC", "tsei": 1.0000, "hydrogens": False, "table": "2"},
    {"label": "Et", "smiles": "CCC", "tsei": 1.1250, "hydrogens": False, "table": "2"},
    {"label": "i-Pr", "smiles": "CC(C)C", "tsei": 1.2500, "hydrogens": False, "table": "2"},
    {"label": "t-Bu", "smiles": "CC(C)(C)C", "tsei": 1.8125, "hydrogens": False, "table": "2b"},
    {"label": "n-Bu", "smiles": "CCCCC", "tsei": 1.1777, "hydrogens": False, "table": "4"},
    {"label": "i-Bu", "smiles": "CCC(C)C", "tsei": 1.1990, "hydrogens": False, "table": "4"},
    {"label": "s-Bu", "smiles": "CC(C)CC", "tsei": 1.2870, "hydrogens": False, "table": "4"},
    {"label": "i-C5H11", "smiles": "CCCC(C)C", "tsei": 1.1933, "hydrogens": False, "table": "4"},
    {"label": "CH(Et)2", "smiles": "CC(CC)CC", "tsei": 1.3240, "hydrogens": False, "table": "4"},
]


def main() -> int:
    from rdkit import Chem

    OUT.mkdir(parents=True, exist_ok=True)
    periodic = Chem.GetPeriodicTable()

    radii: dict[str, dict] = {}
    for name, symbol, picometres in _TABLE_4_7_PM:
        # FAIL CLOSED ON A TYPO'D SYMBOL. A row keyed on "Cr" where the
        # book says chromium-nothing would ship as a radius no molecule
        # can ever reach, which looks exactly like the element simply not
        # being covered.
        assert periodic.GetAtomicNumber(symbol) > 0, f"{symbol!r} is not an element"
        assert symbol not in radii, f"{symbol!r} appears twice"
        radii[symbol] = {
            "radius": round(picometres / 100.0, 5),
            "picometres": picometres,
            "element": name,
            "source": "Lange's Handbook 15th ed., Table 4.7, single-bond column",
            "cross_check": _CROSS_CHECKED.get(symbol, ""),
        }

    payload = {
        "_source_key": "langes15",
        "_supplementary_source_keys": ["cao2004"],
        "attribution": _ATTRIBUTION,
        "units": "1e-8 cm (the paper's own units; the book prints pm, which is 100x)",
        "radii": radii,
        "reference_values": _REFERENCE_VALUES,
    }
    (OUT / "tsei_radii.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    checked = sum(1 for row in radii.values() if row["cross_check"])
    print(f"radii: {len(radii)} elements from Table 4.7")
    print(f"       {checked} of them independently recoverable from a printed TSEI")
    print(f"references: {len(_REFERENCE_VALUES)} printed values for the acceptance test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
