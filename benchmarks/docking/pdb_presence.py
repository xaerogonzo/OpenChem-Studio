"""Has this compound ever been a PDB chemical component?

**WHAT THIS BUYS, STATED NARROWLY, because the tempting reading is stronger
than the fact.** Every PDBbind entry is a co-crystallised complex, so a
compound that appears as NO PDB chemical component cannot have been in
PDBbind -- and therefore cannot have been in Vina's training set (PDBbind
2007) or Vinardo's selection set (122 of PDBbind Core 2013), neither of whose
code lists is obtainable from here. That is a **sufficient exclusion under a
stated identity criterion**, and it is one-way:

    no exact component match  ->  certainly not in PDBbind
    an exact component match  ->  NOTHING follows. A compound can be in the
                                  PDB bound to a protein PDBbind never
                                  included.

So the excluding arm is conservative and the including arm is not
contaminated by construction.

**IT IS A MINIMAL BOUND, NOT A LEAKAGE-FREE CLAIM.** Exact InChIKey identity
breaks on protonation, tautomer, salt and solvate representation, stereo
description and component splits, so "no exact match" is not "never
crystallised" -- which is why the verdict is named for what was measured.
Similarity leakage, in the ligand or the protein, is not addressed here at
all.

**THE 204 TRAP.** RCSB answers a zero-hit search with **HTTP 204 and an empty
body**, so `json.loads` raises on it and the obvious `except Exception:
return None` reads "this compound is not in the PDB" as a failure -- or,
worse, folds both into one "clean" bucket and biases the leakage split
OPTIMISTIC. Absence and inability are different answers and this module
returns three values.

**GET, not POST.** `openchem.net.open_url` is the project's one HTTP entry
point and takes no request body, so the search goes through RCSB's documented
`?json=` form and keeps the shared User-Agent. Adding `data=` to `net.py` is
a `src/` change for a benchmark's convenience and would be its own decision.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
from enum import Enum

from openchem.net import open_url

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"

#: Long enough for a cold RCSB search, short enough that a stalled corpus
#: build says so rather than hanging. Every lookup is cached, so this is paid
#: once per distinct compound.
TIMEOUT_S = 30.0


class PdbPresence(Enum):
    """Three-valued, because "I could not find out" is not "it is not there".

    Same shape as the sources registry's citation/citation_and_claim/
    unverified and `rescore_power.Leakage`, and for the same reason: a
    two-valued answer here would have to fold one of these into the other,
    and either folding biases the leakage split in a direction nobody chose.
    """

    PRESENT = "an exact InChIKey match exists as a PDB chemical component"
    ABSENT = "no exact InChIKey match among PDB chemical components"
    UNRESOLVED = "the lookup could not be completed"


def _query(inchikey: str) -> str:
    payload = {
        "query": {
            "type": "terminal",
            "service": "text_chem",
            "parameters": {
                "attribute": "rcsb_chem_comp_descriptor.InChIKey",
                "operator": "exact_match",
                "value": inchikey,
            },
        },
        "return_type": "mol_definition",
        "request_options": {"paginate": {"start": 0, "rows": 10}},
    }
    return f"{SEARCH_URL}?{urllib.parse.urlencode({'json': json.dumps(payload)})}"


def lookup(inchikey: str) -> tuple[PdbPresence, list[str]]:
    """`(verdict, component ids)` for one compound.

    The component ids are returned even though only the verdict feeds the
    leakage split, because a reader auditing a PRESENT row wants to see WHICH
    component -- and because an id is checkable against RCSB by hand where a
    bare boolean is not.

    **A MALFORMED KEY IS UNRESOLVED, NOT ABSENT.** RCSB would answer 204 for a
    key that cannot match anything, which is indistinguishable from a real
    absence -- so the shape is checked here rather than inferred from the
    reply. An InChIKey is 14-10-1 characters in three hyphenated blocks.
    """
    key = (inchikey or "").strip().upper()
    blocks = key.split("-")
    if len(blocks) != 3 or [len(b) for b in blocks] != [14, 10, 1] or not key.replace("-", "").isalpha():
        return PdbPresence.UNRESOLVED, []
    try:
        with open_url(_query(key), timeout=TIMEOUT_S) as response:
            status = getattr(response, "status", 200)
            body = response.read()
    except urllib.error.HTTPError as exc:
        # 204 arrives here on some stacks and as a 200-with-empty-body on
        # others, so BOTH routes have to mean the same thing.
        if exc.code == 204:
            return PdbPresence.ABSENT, []
        return PdbPresence.UNRESOLVED, []
    except Exception:  # noqa: BLE001 - a network fault is UNRESOLVED, never ABSENT
        return PdbPresence.UNRESOLVED, []

    if status == 204 or not body.strip():
        return PdbPresence.ABSENT, []
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return PdbPresence.UNRESOLVED, []
    identifiers = [
        str(hit.get("identifier", "")) for hit in parsed.get("result_set", []) if hit.get("identifier")
    ]
    if not identifiers:
        # A 200 with an empty result set is a real, complete answer.
        return PdbPresence.ABSENT, []
    return PdbPresence.PRESENT, identifiers
