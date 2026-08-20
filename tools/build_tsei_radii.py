"""Build `chem/data/tsei_radii.json` -- the covalent radii Cao-Liu TSEI needs.

    uv run --no-sync python tools/build_tsei_radii.py

**A RADIUS TABLE IS AN INPUT DATASET, NOT AN IMPLEMENTATION DETAIL.**
`R_C = 0.772` decides every number this method produces and RDKit
disagrees with it (`GetRcovalent("C")` is 0.760, the Cordero 2008 set),
so left inline it becomes an unexplained magic number that the next
reader "corrects" toward the library value. Measured: RDKit's radii put
the paper's own chlorine example at 1.5052 against a printed 1.4190.

**THE SOURCE TABLE IS NOT HELD LOCALLY, AND THE RADII ARE STILL
PAGE-VERIFIED -- which is the whole point of this file.**
[source:cao2004] cites its radii to *Lange's Handbook of Chemistry*, 15th
ed., p 4.35 (its ref 18), which this project does not have. Typing values
from a remembered Pauling table would be the "fields nobody can check"
failure recorded in CLAUDE.md, where six citation errors all sat in the
one field nothing could verify.

So every radius here is instead **BACKED OUT OF A TSEI VALUE THE PAPER
PRINTS**, and each row records which one. For a lone first-tier atom X,
eq 8a collapses to

    dTSEI = 8 * rho^3 / (1 + rho)^3        rho = R_X / R_C

which inverts to a radius. Measured against Table 6:

    F   0.7449  ->  0.63997     Cl  1.4190  ->  0.99001
    Br  1.6957  ->  1.14002     I   2.0265  ->  1.33000

Hydrogen comes from Table 6's methyl (1.0362, hydrogens included) and
oxygen from its methoxy (0.9505); both reproduce to five figures, and
OEt = 0.9939 is an independent third check that uses both at once. Every
one lands on a clean two-decimal value, which is itself evidence the
inversion is reading a real table rather than fitting noise.

**AN ELEMENT WITH NO PRINTED TSEI VALUE IS NOT SHIPPED**, and
`chem/tsei.py` refuses it by name rather than substituting a radius from
a neighbouring set. Nitrogen, sulfur and phosphorus are the notable
absences: the paper prints no TSEI for any substituent containing them,
so there is nothing here to check a radius against. Extending this table
wants the actual page of Lange's, not a recollection of it.

WHAT THE INVERSION DOES ESTABLISH, as a by-product: the six radii recovered
are 0.30, 0.64, 0.66, 0.772, 0.99, 1.14 and 1.33, which are Pauling's
tetrahedral covalent radii to every digit the inversion resolves. That
IDENTIFIES the family of table Lange's p 4.35 reproduces -- a measured
fact, not an inference from the numbers looking familiar -- but it still
does not license typing a seventh value from memory.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "openchem" / "chem" / "data"

_ATTRIBUTION = (
    "Radii recovered from the TSEI values printed by C. Cao & L. Liu, "
    "'Topological Steric Effect Index and Its Application', "
    "J. Chem. Inf. Comput. Sci. 2004;44:678-687, doi:10.1021/ci034266b. "
    "The paper's own radius source is Lange's Handbook of Chemistry, 15th ed., "
    "p 4.35 (its ref 18), which is not held locally."
)

#: `symbol -> (radius in 1e-8 cm, the printed value it was recovered from)`.
#:
#: CARBON AND CHLORINE ARE PRINTED OUTRIGHT in the paper's worked example
#: ("the carbon atomic covalent radius RC is 0.772 x 10-8 cm"; "Its atomic
#: covalent radius is 0.99 x 10-8 cm"), so those two are transcribed rather
#: than inverted. The rest are inverted, and `recovered_from` says how.
_RADII: dict[str, dict] = {
    "C": {
        "radius": 0.772,
        "recovered_from": "printed in the eq 5a worked example",
        "check": "Table 1: the whole normal-alkyl series, n = 1..20",
    },
    "Cl": {
        "radius": 0.99,
        "recovered_from": "printed in the heteroatom worked example",
        "check": "Table 6: Cl = 1.4190, which the example derives in full",
    },
    "H": {
        "radius": 0.30,
        "recovered_from": "inverted from Table 6 Me = 1.0362 (hydrogens included)",
        "check": "Table 6: Et = 1.1581 and t-Bu = 1.8395",
    },
    "O": {
        "radius": 0.66,
        "recovered_from": "inverted from Table 6 MeO = 0.9505",
        "check": "Table 6: OEt = 0.9939, which uses O and H together",
    },
    "F": {
        "radius": 0.64,
        "recovered_from": "inverted from Table 6 F = 0.7449",
        "check": "Table 6: F = 0.7449",
    },
    "Br": {
        "radius": 1.14,
        "recovered_from": "inverted from Table 6 Br = 1.6957",
        "check": "Table 6: Br = 1.6957",
    },
    "I": {
        "radius": 1.33,
        "recovered_from": "inverted from Table 6 I = 2.0265",
        "check": "Table 6: I = 2.0265",
    },
}

#: Every TSEI value the paper prints for a substituent containing an
#: element other than carbon, or containing hydrogens explicitly. These are
#: the acceptance oracle for the general form -- and for the RADII above,
#: which were derived from a subset of them.
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
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "_source_key": "cao2004",
        "_radius_source": (
            "Lange's Handbook of Chemistry, 15th ed., p 4.35 -- cited by "
            "[source:cao2004] as its ref 18 and NOT held locally. Every radius "
            "below is recovered from a TSEI value the paper itself prints; see "
            "`recovered_from`."
        ),
        "attribution": _ATTRIBUTION,
        "units": "1e-8 cm (the paper's own units; only ratios to carbon are used)",
        "radii": _RADII,
        "reference_values": _REFERENCE_VALUES,
    }
    (OUT / "tsei_radii.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"radii: {len(_RADII)} elements, every one tied to a printed TSEI value")
    print(f"references: {len(_REFERENCE_VALUES)} printed values for the acceptance test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
