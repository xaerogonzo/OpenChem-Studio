"""What the partial-charge models do with a radical (item 13 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

**WHY.** Gasteiger, EEM and QEq have no spin term, and nobody had measured them on a radical. Measured 2026-11-24 (`benchmarks/open_shell/charge_models.py`, rule in `charge_models_rule.py` fixed before the run, the table
in `charge_models_result.txt`): against ORCA Hirshfeld (B3LYP/def2-SVP, UKS), on nine radicals and their closed-shell parents, the largest excess error on a heavy atom (radical minus parent) was

    QEq (Rappe-Goddard)                 +0.035 e   PASS (limit 0.05 e)
    Gasteiger                           +0.073 e   FAIL
    EEM, Bultinck 2002                  +0.084 e   FAIL
    EEM, Ionescu 2013, 6-31G*           +0.062 e   FAIL
    EEM, Ionescu 2013, 6-31G**          +0.127 e   FAIL

Löwdin, a sensitivity row that could not change a verdict, agreed on all five. The largest excess of a failing model sits on the radical centre or its neighbour (hydroperoxyl's HO oxygen, tert-butyl's radical carbon, TEMPO's nitrogen, methoxy's carbon). A model that FAILED returns no charges for an
open-shell structure (`open_shell_charge_refusal`); QEq returns them with a note that says what was and was not measured. The typed EEM models (NEEMP, Jiroušková) already refuse an unpaired electron and were not measured.

**A PASS IS NOT A VALIDATION.** The test is relative (a model wrong on both the radical and its parent can pass), so the note says "no radical-specific degradation beyond 0.05 e on this panel" and nothing more.

The model codes are written out here, not imported, because `geometry_charges` and `charge_evaluation` both need this module and one of them imports the other; `tests/test_open_shell_charges.py` holds each to its constant.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.open_shell import is_open_shell

#: Models that FAILED the preregistered rule, with the excess error (e) that failed them (ORCA Hirshfeld, the deciding reference).
FAILED_MODELS = {
    "gasteiger": 0.073,
    "eem_bultinck2002_part1": 0.084,
    "eem_ionescu2013_e_mpa_631gs_gas": 0.062,
    "eem_ionescu2013_e_mpa_631gss_gas": 0.127,
}
#: Models that PASSED it, with their worst excess error (e).
PASSED_MODELS = {"qeq_rg1991_lambda_half_h_experimental": 0.035}
#: The deciding limit (e), as in `benchmarks/open_shell/charge_models_rule.THRESHOLD_E`.
LIMIT_E = 0.05

#: The refusal code for a calculator-level refusal (`domain/refusal_kinds`, a LIMIT).
REFUSAL_CODE = "OPEN_SHELL"

#: The sentence a refusal carries.
REFUSAL_MESSAGE = (
    "{model} has no spin-dependent term, and on radicals its charge on the radical centre moved {excess:.3f} e further from ORCA's Hirshfeld charge than on the closed-shell parent "
    "(limit {limit:.2f} e; item 13 of the open-shell design), so no charges are returned for a structure with unpaired electrons."
)
#: The note a model that passed carries on an open-shell structure.
PASS_NOTE = (
    "Spin is not modelled. On nine radicals against ORCA Hirshfeld charges this model's charge on a heavy atom was at most {excess:.3f} e further off than on the closed-shell parent "
    "(limit {limit:.2f} e): no radical-specific degradation beyond that on this panel, which is not a validation of radical charges."
)


def open_shell_charge_refusal(mol: Chem.Mol, model_key: str, model_label: str) -> str:
    """The refusal sentence when `model_key` failed the measurement and `mol` is open-shell, else ''."""
    excess = FAILED_MODELS.get(model_key)
    if excess is None or not is_open_shell(mol):
        return ""
    return REFUSAL_MESSAGE.format(model=model_label, excess=excess, limit=LIMIT_E)


def open_shell_charge_note(mol: Chem.Mol, model_key: str) -> str:
    """The note for a model that passed, on an open-shell structure, else ''."""
    excess = PASSED_MODELS.get(model_key)
    if excess is None or not is_open_shell(mol):
        return ""
    return PASS_NOTE.format(excess=excess, limit=LIMIT_E)
