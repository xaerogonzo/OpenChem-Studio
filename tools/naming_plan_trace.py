"""Print every top-level plan the engine ranks for a structure: the candidate-set proof.

    python tools/naming_plan_trace.py "OC(=O)CC(O)(CC(O)=O)C(O)=O" "OC(=O)C(C(O)=O)C(O)=O"

For each structure it lists the DISTINCT plans in ranking order (best first) with the parent candidate (type and length),
the principal-group class, how many principal instances the plan carries, its suffix groups and their locant counts, and
the two tier values that decide most parent choices: `pcg_count` (P-44.1.1) and the legacy `parent_selection`.

**WHY IT EXISTS.** A defect is not called a ranking defect, a generation defect or an assignment defect until a trace says
which. Naming round 8's first W1 claim was a ranking defect in a scoring band, asserted from reading code; this tool showed
the parent with three suffix groups was never among the plans, so the comparator never saw it. "Candidate absent",
"present but lost" and "assigned wrong" are three different fixes, and the trace is what tells them apart: the expected
plan is either in this list or it is not.

Read-only. It spies on `engine._search_plans`, exactly as `naming_stage_artifact.py` does, and changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def trace(smiles: str) -> None:
    from rdkit import RDLogger

    RDLogger.DisableLog("rdApp.*")
    from openchem.vendor.iupac_namer import engine as eng
    from openchem.vendor.iupac_namer import name_smiles
    from openchem.vendor.iupac_namer.preference import TIER_SPECS
    from openchem.vendor.iupac_namer.strategy import IUPACCanonical
    from openchem.vendor.iupac_namer.types import OutputForm, SubstitutivePlan

    tiers = [t.name for t in TIER_SPECS]
    strategy = IUPACCanonical()
    original = eng._search_plans
    captured: list = []

    def spy(perception, mol, output_form, free_valence, query, strategy_, session):
        ranked = original(perception, mol, output_form, free_valence, query, strategy_, session)
        if output_form in (OutputForm.STANDALONE, OutputForm.CATION) and not captured:
            captured.append((mol, ranked))
        return ranked

    eng._search_plans = spy
    try:
        name = name_smiles(smiles)
    finally:
        eng._search_plans = original
    mol, ranked = captured[0]
    print(f"\n#### {smiles}\n     engine name: {name}\n     {len(ranked)} ranked plans (best first below)")
    seen: set = set()
    for _score, _quality, plan in reversed(ranked):
        if not isinstance(plan, SubstitutivePlan):
            continue
        candidate = plan.named_parent.candidate
        groups = [(getattr(sg, "base_form", "?"), len(sg.locants or ())) for sg in plan.suffix_groups]
        row = (candidate.type, candidate.length, plan.pcg_type, tuple(groups))
        if row in seen:
            continue
        seen.add(row)
        values = getattr(strategy.preference_key(plan, mol), "tiers", None)
        pcg_count = values[tiers.index("pcg_count")] if values else "?"
        selection = values[tiers.index("parent_selection")] if values else "?"
        print(f"  {candidate.type}/len={candidate.length}  pcg={plan.pcg_type}  instances={len(plan.pcg_instances or ())}"
              f"  suffix_groups={groups}  pcg_count={pcg_count}  parent_selection={selection}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("smiles", nargs="+")
    for smiles in parser.parse_args().smiles:
        trace(smiles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
