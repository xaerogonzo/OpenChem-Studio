from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from rdkit import Chem

from openchem.chem.docking_providers import (
    DEFAULT_EXHAUSTIVENESS,
    DockingProviderError,
    VinaDockingProvider,
)
from openchem.chem.vina_engine import VinaEngine
from openchem.domain.docking import DockingBox
from openchem.services.progress import ProgressHandle

#: Where the fixture receptor below actually sits. Every box in this file
#: used to be centred on the ORIGIN, several Angstrom clear of it -- so
#: these tests exercised the docking plumbing while docking into vacuum.
#: That went unnoticed until `_require_receptor_in_box` refused it, which
#: is the guard doing its job on its first outing. Pointed at the receptor
#: rather than the guard being weakened: a box that contains no receptor
#: is not a case worth keeping green.
_RECEPTOR_CENTER = (12.0, 12.5, 2.7)

# Real Vina output shape (confirmed against the official documented
# format) for a single pose, fed through a FakeVinaEngine so this test
# exercises the real Open Babel receptor/ligand/pose PDBQT conversion
# pipeline (openbabel-wheel is actually installed here) without needing a
# real Vina backend (no Windows wheel available for the `vina` package —
# see chem/vina_engine.py's docstring).
FAKE_OUTPUT = """MODEL 1
REMARK VINA RESULT:    -5.2      0.000      0.000
ROOT
ATOM      1  C1  LIG     1       1.000   2.000   3.000  1.00  0.00     0.000 C
ATOM      2  C2  LIG     1       2.000   2.000   3.000  1.00  0.00     0.000 C
ENDROOT
TORSDOF 0
ENDMDL
"""

RECEPTOR_PDB = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
END
"""

# ALA residue + a crystallographic water + a non-standard HETATM (zinc, a
# common cofactor) + a duplicate-altloc atom on the CB, for exercising
# receptor_prep_options end to end through the real Open Babel pipeline.
RECEPTOR_PDB_WITH_EXTRAS = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
ATOM      5  CB AALA A   1      11.500  10.800   2.000  0.60 20.00           C
ATOM      6  CB BALA A   1      11.600  10.900   2.100  0.40 20.00           C
HETATM    7  O   HOH A   2      20.000  20.000  20.000  1.00 20.00           O
HETATM    8 ZN   ZN  A   3      25.000  25.000  25.000  1.00 20.00          ZN
END
"""


class FakeVinaEngine(VinaEngine):
    engine_id = "fake"

    def __init__(self, output: str = FAKE_OUTPUT, raise_error: bool = False) -> None:
        self._output = output
        self._raise_error = raise_error
        self.dock_calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return "1.0.0-fake"

    def dock(
        self,
        receptor_pdbqt,
        ligand_pdbqt,
        box,
        num_poses,
        exhaustiveness,
        seed,
        progress,
        scoring_function="vina",
    ):
        # A real engine would have written receptor_pdbqt/ligand_pdbqt (by
        # the time dock() is called, VinaDockingProvider has already
        # created them) -- assert that here as a sanity check, and capture
        # the receptor's actual PDBQT text now, while the scratch dir still
        # exists (VinaDockingProvider.dock's `with tempfile.TemporaryDirectory`
        # deletes it as soon as this call returns).
        assert Path(receptor_pdbqt).exists()
        assert Path(ligand_pdbqt).exists()
        self.dock_calls.append(
            {
                "receptor_pdbqt": receptor_pdbqt,
                "ligand_pdbqt": ligand_pdbqt,
                "box": box,
                "num_poses": num_poses,
                "exhaustiveness": exhaustiveness,
                "seed": seed,
                "scoring_function": scoring_function,
                "receptor_pdbqt_text": Path(receptor_pdbqt).read_text(encoding="utf-8"),
                # Captured here for the same reason as the receptor's: the
                # provider's scratch directory is deleted the moment this
                # returns, so a test that reads the file afterwards reads
                # nothing.
                "ligand_pdbqt_text": Path(ligand_pdbqt).read_text(encoding="utf-8"),
            }
        )
        if self._raise_error:
            raise RuntimeError("boom")
        progress.report(1.0, "done")
        return self._output


def test_dock_with_no_engine_raises_clear_error():
    provider = VinaDockingProvider(engine=None)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    with pytest.raises(DockingProviderError, match="No Vina docking backend"):
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())


def test_dock_produces_poses_via_real_openbabel_conversion():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20.0, 20.0, 20.0))

    poses = provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())

    assert len(poses) == 1
    assert poses[0].binding_affinity_kcal_mol == -5.2
    assert poses[0].rmsd_lb == 0.0
    assert "V2000" in poses[0].pose_molblock or "M  END" in poses[0].pose_molblock

    assert len(engine.dock_calls) == 1
    assert engine.dock_calls[0]["box"] is box
    assert engine.dock_calls[0]["num_poses"] == 9


def test_dock_wraps_engine_errors():
    engine = FakeVinaEngine(raise_error=True)
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    with pytest.raises(RuntimeError, match="boom"):
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())


def test_dock_with_bad_receptor_text_raises_docking_error():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    with pytest.raises(DockingProviderError, match="Failed to prepare receptor"):
        provider.dock("not a valid structure @#$%", "pdb", mol, box, 9, ProgressHandle())


def test_engine_id_and_version_reflect_selected_engine():
    provider_with_engine = VinaDockingProvider(engine=FakeVinaEngine())
    assert provider_with_engine.engine_id == "fake"
    assert provider_with_engine.engine_version() == "1.0.0-fake"

    provider_without_engine = VinaDockingProvider(engine=None)
    assert provider_without_engine.engine_id == "none"
    assert provider_without_engine.engine_version() == "unknown"


def test_executable_path_resolver_is_consulted_not_settings_directly():
    """VinaDockingProvider must stay decoupled from openchem.app.Settings
    (chem/ is a lower layer than app/) -- it only ever calls a generic
    Callable[[], str] resolver, which DockingService supplies as a closure
    over the real Settings object."""
    calls = []

    def resolver() -> str:
        calls.append(1)
        return ""

    provider = VinaDockingProvider(executable_path_resolver=resolver)
    # No real vina/executable available in this environment, so this
    # resolves to "none" -- the point is just that the resolver got called.
    assert provider.engine_id == "none"
    assert calls == [1]


def test_receptor_pdbqt_is_prepared_as_rigid_not_flexible():
    """Regression test: confirmed live against a real 327-atom protein that
    the default `pybel.Molecule.write("pdbqt", ...)` treats the WHOLE
    receptor as one flexible ligand-style structure, emitting
    ROOT/BRANCH/TORSDOF records and reporting "104 active torsions" -- a
    docking receptor must be rigid. `_convert_receptor_to_pdbqt` must pass
    Open Babel's rigid-receptor option (`opt={"r": None}`, the `-xr` CLI
    equivalent) so none of those records appear."""
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "ROOT" not in receptor_text
    assert "BRANCH" not in receptor_text
    assert "TORSDOF" not in receptor_text


#: The same alanine as RECEPTOR_PDB plus a chloride, written as mmCIF the
#: way RCSB writes it -- `type_symbol` uppercase for a two-letter element.
#: Coordinates match `_RECEPTOR_CENTER` so the box actually contains it.
RECEPTOR_MMCIF_WITH_CHLORIDE = """data_TEST
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.pdbx_formal_charge
_atom_site.auth_seq_id
_atom_site.auth_comp_id
_atom_site.auth_asym_id
_atom_site.auth_atom_id
_atom_site.pdbx_PDB_model_num
ATOM   1 N  N  . ALA A 1 1 ? 11.104 13.207 2.845 1.00 20.00 ? 1 ALA A N  1
ATOM   2 C  CA . ALA A 1 1 ? 11.999 12.040 2.945 1.00 20.00 ? 1 ALA A CA 1
ATOM   3 C  C  . ALA A 1 1 ? 13.398 12.442 2.508 1.00 20.00 ? 1 ALA A C  1
ATOM   4 O  O  . ALA A 1 1 ? 13.598 13.601 2.128 1.00 20.00 ? 1 ALA A O  1
HETATM 5 CL CL . CL  B 2 . ? 12.500 12.500 4.500 1.00 20.00 ? 2 CL  A CL 1
#
"""


def test_an_mmcif_receptors_chloride_reaches_vina_typed_not_deleted():
    """The damage this bug did, at the end of the pipeline it did it in.

    Open Babel's mmCIF reader is case-sensitive about `type_symbol` and
    the archive writes `CL`, so the ion arrived as element 0 --
    whereupon `_drop_untyped_atoms` DELETED it, because Open Babel writes
    an untyped atom into the PDBQT with the name `*` and an empty AutoDock
    type, and Vina 1.2.7 then refuses the whole file. So the receptor
    Vina saw was silently missing an atom rather than obviously broken,
    which is the worse of the two failures.

    The same deposit as PDB was always correct, which is why this asserts
    the mmCIF arm against the PDB arm rather than against a literal: the
    two formats of one structure must reach Vina as the same receptor.
    """
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    prepared = {}
    for label, text, source_format in (
        ("mmcif", RECEPTOR_MMCIF_WITH_CHLORIDE, "mmcif"),
        ("pdb", RECEPTOR_PDB_WITH_CHLORIDE, "pdb"),
    ):
        engine = FakeVinaEngine()
        VinaDockingProvider(engine=engine).dock(
            text, source_format, Chem.MolFromSmiles("CCO"), box, 9, ProgressHandle()
        )
        prepared[label] = engine.dock_calls[0]["receptor_pdbqt_text"]

    chloride = [
        line for line in prepared["mmcif"].splitlines()
        if line.startswith(("ATOM", "HETATM")) and line.rstrip().endswith("Cl")
    ]
    assert len(chloride) == 1, (
        "the chloride is missing from the receptor Vina was handed:\n"
        + prepared["mmcif"]
    )
    assert " * " not in prepared["mmcif"], "an untyped atom makes Vina refuse the file"

    def atom_types(text: str) -> list[str]:
        return sorted(
            line.split()[-1]
            for line in text.splitlines()
            if line.startswith(("ATOM", "HETATM"))
        )

    # AutoDock types, not merely elements. These encode hydrogen bonding
    # (`NA` is an acceptor nitrogen with no attached H, `OA` an acceptor
    # oxygen, `HD` a polar hydrogen) and Vina scores against them, so
    # matching here is the strongest available statement that the two
    # formats reach Vina as the same receptor. It only became assertable
    # once `_assign_implicit_hydrogens` closed the protonation gap -- the
    # backbone nitrogen came out `NA` from mmCIF and `N` from PDB before.
    assert atom_types(prepared["mmcif"]) == atom_types(prepared["pdb"]), (
        "the same structure in two formats must reach Vina as the same receptor"
    )
    assert "Cl" in atom_types(prepared["pdb"]), "the control arm really has one"


RECEPTOR_PDB_WITH_CHLORIDE = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
HETATM    5 CL   CL  A   2      12.500  12.500   4.500  1.00 20.00          CL
END
"""


def test_an_mmcif_receptor_is_protonated_not_left_bare():
    """Open Babel's mmCIF reader leaves every implicit hydrogen count at
    zero, so `AddHydrogens` had almost nothing to add and an mmCIF
    receptor reached Vina essentially unprotonated -- 41 hydrogens on
    4DKL against 3,754 from the same deposit as PDB.

    Asserted as a COUNT matching the PDB arm rather than as a threshold,
    because "some hydrogens were added" was already true of the broken
    behaviour: 41 is not zero, and a `> 0` assertion would have passed
    throughout. Bond perception is deliberately not the thing under test
    here -- it was the obvious suspect and is identical between the two
    formats (3,726 bonds either way on 4DKL)."""
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    counts = {}
    for label, text, source_format in (
        ("mmcif", RECEPTOR_MMCIF_WITH_CHLORIDE, "mmcif"),
        ("pdb", RECEPTOR_PDB_WITH_CHLORIDE, "pdb"),
    ):
        engine = FakeVinaEngine()
        VinaDockingProvider(engine=engine).dock(
            text, source_format, Chem.MolFromSmiles("CCO"), box, 9, ProgressHandle()
        )
        receptor = engine.dock_calls[0]["receptor_pdbqt_text"]
        counts[label] = sum(
            1 for line in receptor.splitlines()
            if line.startswith(("ATOM", "HETATM")) and line.split()[-1] == "HD"
        )

    assert counts["pdb"] > 0, "the control arm must actually gain hydrogens"
    assert counts["mmcif"] == counts["pdb"], (
        f"mmCIF was protonated differently from PDB: {counts}"
    )


#: A ligand carbon bonded to a lysine NZ -- which is 4DKL's arrangement,
#: where beta-FNA is covalently bound to Lys233 and the catalogue records
#: it as a caveat. The attachment is to a NITROGEN on purpose: a freed
#: carbon valence takes a nonpolar hydrogen, which the rigid PDBQT writer
#: merges away, so an otherwise identical fixture built on a CB produces
#: byte-identical output either way and tests nothing.
RECEPTOR_PDB_WITH_COVALENT_LIGAND = """HEADER    TEST
ATOM      1  N   LYS A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  LYS A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   LYS A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   LYS A   1      13.598  13.601   2.128  1.00 20.00           O
ATOM      5  CB  LYS A   1      11.500  10.800   2.000  1.00 20.00           C
ATOM      6  NZ  LYS A   1      11.000   9.600   2.700  1.00 20.00           N
HETATM    7  C1  LIG A   2      10.500   8.400   1.900  1.00 20.00           C
END
"""


def test_hydrogens_are_counted_after_the_strips_not_before():
    """Stripping a COVALENTLY bound ligand frees a valence, and the atom
    it was attached to then needs one more hydrogen. Assigning implicit
    counts before the strips records the pre-strip number, and that
    hydrogen is never added.

    Not hypothetical for the bundled catalogue: 4DKL's beta-FNA is
    covalently bound to Lys233, and every catalogue box strips its own
    defining ligand -- leaving it in would dock into an occupied pocket
    (indinavir into its own 1HSG: -5.34 against -9.78).

    Measured on this fixture: the lysine reaches Vina with 4 polar
    hydrogens when the counts are assigned after the strips and 3 when
    they are assigned before."""
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    engine = FakeVinaEngine()

    VinaDockingProvider(engine=engine).dock(
        RECEPTOR_PDB_WITH_COVALENT_LIGAND, "pdb", Chem.MolFromSmiles("CCO"),
        box, 9, ProgressHandle(),
        receptor_prep_options={"strip_ligand_codes": ["LIG"]},
    )

    atoms = [
        line for line in engine.dock_calls[0]["receptor_pdbqt_text"].splitlines()
        if line.startswith(("ATOM", "HETATM"))
    ]
    assert not any(" LIG " in line for line in atoms), "the ligand really was stripped"
    polar = [line for line in atoms if line.split()[-1] == "HD"]
    assert len(polar) == 4, (
        "the lysine nitrogen did not get the hydrogen the stripped ligand "
        f"was occupying:\n" + "\n".join(atoms)
    )


def test_receptor_prep_strips_waters_by_default():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "HOH" not in receptor_text


def test_receptor_prep_keeps_waters_when_disabled():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    provider.dock(
        RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle(),
        receptor_prep_options={"strip_waters": False},
    )

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "HOH" in receptor_text


def test_receptor_prep_keeps_cofactors_by_default():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "ZN" in receptor_text


def test_receptor_prep_strips_cofactors_when_enabled():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    provider.dock(
        RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle(),
        receptor_prep_options={"strip_cofactors": True},
    )

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "ZN" not in receptor_text
    # A standard residue (ALA) must survive strip_cofactors -- it only
    # removes non-standard HETATM residues, not the receptor itself.
    assert "ALA" in receptor_text


def test_receptor_prep_filters_duplicate_altlocs():
    """Regression test: confirmed live that Open Babel's own PDB reader
    does NOT dedupe alternate locations -- a two-altloc atom comes back as
    two full atoms at two positions. `_filter_pdb_altlocs` must drop every
    altloc except blank/'A' before Open Babel ever reads the structure."""
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    # Exactly one CB atom line should survive (the 'A' altloc), not two.
    cb_lines = [line for line in receptor_text.splitlines() if " CB " in line]
    assert len(cb_lines) == 1


def test_receptor_prep_ph_is_passed_to_add_hydrogens():
    """Doesn't assert a specific protonation outcome (fragile/chemistry-
    dependent) -- just that a custom pH actually reaches AddHydrogens
    instead of always using the 7.4 default, via a spy on OBMol."""
    from openbabel import openbabel as ob

    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    calls = []
    original = ob.OBMol.AddHydrogens

    # Matches OBMol::AddHydrogens' real C++ defaults. The ligand-prep path
    # (_convert_ligand_to_pdbqt) reaches this too and USED to arrive via
    # pybel's addh() wrapper with no arguments at all, which is the defect
    # test_both_preparation_paths_receive_the_same_declared_ph now pins.
    def spy(self, polaronly=False, correct_for_ph=False, ph=7.4):
        calls.append((polaronly, correct_for_ph, ph))
        return original(self, polaronly, correct_for_ph, ph)

    with patch.object(ob.OBMol, "AddHydrogens", spy):
        provider.dock(
            RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle(),
            receptor_prep_options={"ph": 5.0},
        )

    # The receptor-prep call (polaronly=False, correctForPH=True, pH=5.0)
    # must be among the calls made -- the ligand-prep path's own addh()
    # call (with all defaults) is expected too and isn't what's under test.
    assert (False, True, 5.0) in calls


def test_last_resolved_engine_is_cached_after_dock_not_recomputed():
    """engine_id/engine_version() must describe exactly what the most
    recent dock() call actually used, read from a cache set by dock() —
    not re-resolved independently on every access. If they did re-resolve
    each time, a resolver whose return value changes between calls (e.g.
    settings changing mid-job) could make them disagree with what actually
    ran. Patches `_resolve_engine` itself to count calls, since a fixed
    `engine=` override would bypass resolution entirely and prove nothing.
    """
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(executable_path_resolver=lambda: "")
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    with patch.object(provider, "_resolve_engine", return_value=engine) as mock_resolve:
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())
        assert mock_resolve.call_count == 1

        assert provider.engine_id == "fake"
        assert provider.engine_version() == "1.0.0-fake"
        # engine_id/engine_version() must not have called _resolve_engine
        # again -- they read the cached _last_resolved_engine from dock().
        assert mock_resolve.call_count == 1


def test_dock_raises_immediately_when_progress_already_cancelled():
    """Best-effort cancellation is checked at each phase boundary
    (receptor prep / ligand prep / after the engine call) -- a
    pre-cancelled ProgressHandle must stop before wasting any work at
    all, not just eventually."""
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    progress = ProgressHandle()
    progress.cancel()

    with pytest.raises(DockingProviderError, match="cancelled"):
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, progress)

    assert engine.dock_calls == []


# --- issue #8: the unit-cell copies Open Babel invents ---------------------
#
# `pose_analysis.is_symmetry_generated` and the ANALYSIS path are guarded in
# tests/test_structure_summary.py, where the evidence was gathered. Nothing
# guarded the DOCKING-PREPARATION half until this, so deleting the
# `_drop_symmetry_copies` call from `_convert_receptor_to_pdbqt` passed the
# whole suite -- while that call is the one that stood between Vina and
# 6WGT's 73,707-atom receptor. The two halves must not be able to disagree;
# that is the whole reason the drop exists on both.

#: The same alanine as `RECEPTOR_PDB`, as mmCIF, plus a cell and a space
#: group Open Babel cannot recognise. It then applies the symmetry
#: operations it CAN read and returns the mates as ordinary atoms carrying
#: no residue record -- measured here at 2.00x, the same ratio 7M93 showed.
#:
#: `-x,-y,z` on a 20 A cell puts the copies at y ~ 6.8-8.0, well clear of
#: the deposited y ~ 12.0-13.6, so a coordinate check tells the two apart
#: rather than merely counting them.
RECEPTOR_MMCIF_WITH_SYMMETRY = """data_TEST
_cell.length_a     20.000
_cell.length_b     20.000
_cell.length_c     20.000
_cell.angle_alpha  90.000
_cell.angle_beta   90.000
_cell.angle_gamma  90.000
_symmetry.space_group_name_H-M   'Z 99 BOGUS'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
'-x,-y,z'
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.auth_seq_id
_atom_site.auth_asym_id
ATOM 1 N N  ALA A 1 11.104 13.207 2.845 1 A
ATOM 2 C CA ALA A 1 11.999 12.040 2.945 1 A
ATOM 3 C C  ALA A 1 13.398 12.442 2.508 1 A
ATOM 4 O O  ALA A 1 13.598 13.601 2.128 1 A
"""

#: What the deposit itself contains -- the number `_atom_site` rows state.
#: 7M93 and 6WGT reduce to exactly their own row counts too (5,812 and
#: 8,100); equality to the atom is what makes the identification exact
#: rather than approximate, and is a far stronger claim than "fewer".
_DEPOSITED_HEAVY_ATOMS = 4


def _receptor_heavy_atoms(pdbqt_text: str) -> list[tuple[float, float, float]]:
    """Heavy-atom coordinates from a receptor PDBQT, in file order.

    Hydrogens are excluded because `_convert_receptor_to_pdbqt` adds them
    (`AddHydrogens` at the prep pH), so a raw line count would be
    measuring protonation rather than the symmetry drop.
    """
    coordinates = []
    for line in pdbqt_text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if line.split()[-1] in ("H", "HD"):
            continue
        coordinates.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
    return coordinates


def symmetry_expansion_skip_reason() -> str | None:
    """The reason to skip the issue-#8 guards, or None to RUN them.

    **A MEASURED CAPABILITY GATE, NOT A PLATFORM CHECK**, in the shape
    `conftest.webgl_skip_reason` already uses: a plain function returning a
    REASON, so both answers are values a test can assert rather than one
    being the absence of an exception.

    It exists because this fixture is degenerate on some Open Babel
    builds. Measured 2026-08-29 -- and the cause is not the platform, it is
    which DATA FILES Open Babel found:

        BABEL_DATADIR as the wheel sets it   8 atoms, expands
        BABEL_DATADIR at the real data dir   4 atoms, does NOT expand

    The wheel points `BABEL_DATADIR` at `share/openbabel/<version>/`, which
    holds exactly one file (`splash.png`); the real tables, including
    `space-groups.txt`, are in `bin/data/`. Without the space-group database
    Open Babel cannot resolve this fixture's deliberately bogus
    `'Z 99 BOGUS'` group, warns, and falls back to "Converting to P 1 cell
    using available symmetry transformations" -- which applies the two
    operations the CIF lists and doubles the atoms. WITH the database it
    resolves nothing for a bogus name and leaves the cell alone.

    So a build that does not expand is not broken and neither is ours; the
    fixture simply cannot reproduce issue #8 there. Skipping NAMES the
    absent prerequisite rather than failing and blaming the code -- and it
    must stay able to say NO, which is what the guards in this file's
    companion assert.

    **The `BABEL_DATADIR` defect is real and is NOT fixed here.** It is
    recorded in CLAUDE.md: it affects every platform and every Open Babel
    data table, so changing it is its own measurement, not a side effect of
    repairing a test.
    """
    from openbabel import openbabel as ob
    from openbabel import pybel

    mol = pybel.readstring("mmcif", RECEPTOR_MMCIF_WITH_SYMMETRY)
    return expansion_skip_reason(len(list(ob.OBMolAtomIter(mol.OBMol))))


def expansion_skip_reason(atom_count: int) -> str | None:
    """The DECISION, split from the measurement so both answers are testable.

    The same two-level split `ui/visual_check.py` uses: this is arithmetic
    over a number somebody measured, so a guard for it needs no Open Babel
    and cannot become a claim about which build the test machine happens to
    have. `symmetry_expansion_skip_reason` does the measuring.
    """
    if atom_count != 2 * _DEPOSITED_HEAVY_ATOMS:
        return (
            "Skipped: this Open Babel build does not expand the fixture cell "
            f"({atom_count} atoms, not {2 * _DEPOSITED_HEAVY_ATOMS}), so the "
            "fixture cannot reproduce issue #8 -- see "
            "symmetry_expansion_skip_reason for the BABEL_DATADIR measurement"
        )
    return None


def test_a_measured_absence_skips_and_says_so_in_words_a_ci_log_shows():
    """The reason has to be readable in a CI log by somebody who has never
    seen this file, or a skip is indistinguishable from a test nobody
    bothered to write."""
    reason = expansion_skip_reason(_DEPOSITED_HEAVY_ATOMS)
    assert reason is not None
    assert "does not expand" in reason
    assert "issue #8" in reason


def test_a_measured_PRESENCE_does_not_skip():
    """**A CAPABILITY GATE IS WORTH WHAT ITS ABILITY TO SAY NO IS WORTH.**
    Without this, `return "skipped"` satisfies the test above and silently
    disables the issue-#8 guards on every platform."""
    assert expansion_skip_reason(2 * _DEPOSITED_HEAVY_ATOMS) is None


def test_the_symmetry_gate_measures_open_babel_and_never_the_platform():
    """The Linux job was permanently red here, so a platform check is the
    tempting repair -- and it would be wrong twice: it would encode a
    conclusion about an environment rather than measuring one, and it would
    keep skipping if a future wheel fixed its data directory.

    Asserted on the SOURCE, because a platform read could be added without
    any fixture noticing on the platform that still runs the tests.
    """
    import ast
    import inspect

    source = inspect.getsource(symmetry_expansion_skip_reason)
    tree = ast.parse(textwrap.dedent(source))
    banned = {"platform", "system", "name", "uname"}
    offenders = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in banned
    ]
    assert not offenders, offenders
    # ...and assert the setup: it really does read Open Babel, so a gate
    # that stopped measuring anything could not pass this vacuously.
    assert "readstring" in source


def test_open_babel_really_does_invent_symmetry_copies_from_this_fixture():
    """ASSERTS THE SETUP, so the guard below cannot go vacuous.

    If Open Babel does not expand this cell, the fixture arrives with
    nothing to drop and `test_symmetry_copies_never_reach_the_receptor`
    would pass while testing nothing -- the same failure mode
    `test_a_tab_bars_scroll_buttons_are_qt_s_own` asserts its own setup
    against.

    It used to FAIL in that case, which made the Linux job permanently red
    on a guard doing its job and saturated the only signal that job has.
    It SKIPS now, naming the measured prerequisite -- and the assertions
    below still run wherever the prerequisite is present, so the setup is
    still asserted rather than assumed.
    """
    from openbabel import openbabel as ob
    from openbabel import pybel

    reason = symmetry_expansion_skip_reason()
    if reason:
        pytest.skip(reason)

    mol = pybel.readstring("mmcif", RECEPTOR_MMCIF_WITH_SYMMETRY)
    atoms = list(ob.OBMolAtomIter(mol.OBMol))
    invented = [atom for atom in atoms if atom.GetResidue() is None]

    assert len(atoms) == 2 * _DEPOSITED_HEAVY_ATOMS
    assert len(invented) == _DEPOSITED_HEAVY_ATOMS


def test_symmetry_copies_never_reach_the_receptor_vina_is_handed():
    """Issue #8, at the end of the pipeline it did its damage in.

    6WGT's 8,100-atom deposit reached Vina as 73,707 atoms -- eight
    overlapping copies of the protein -- and Vina searched it and returned
    plausible-looking affinities rather than crashing. So the assertion
    that matters is about the file Vina is actually handed, not about the
    predicate in isolation.

    IT ASSERTS WHAT SURVIVES, not merely that the count fell. A drop that
    deleted too much would satisfy both "fewer atoms" and "no null-residue
    atoms remain"; only the deposited coordinates coming back intact
    separates the fix from an over-broad one.

    Gated on the SAME measured prerequisite as the setup guard above:
    where Open Babel does not expand the cell there is nothing to drop,
    so this would pass while testing nothing.
    """
    reason = symmetry_expansion_skip_reason()
    if reason:
        pytest.skip(reason)

    engine = FakeVinaEngine()
    VinaDockingProvider(engine=engine).dock(
        RECEPTOR_MMCIF_WITH_SYMMETRY,
        "mmcif",
        Chem.MolFromSmiles("CCO"),
        DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20)),
        9,
        ProgressHandle(),
    )
    heavy = _receptor_heavy_atoms(engine.dock_calls[0]["receptor_pdbqt_text"])

    assert len(heavy) == _DEPOSITED_HEAVY_ATOMS, (
        f"the receptor Vina was handed holds {len(heavy)} heavy atoms for a "
        f"{_DEPOSITED_HEAVY_ATOMS}-atom deposit"
    )
    assert sorted(heavy) == sorted(
        [
            (11.104, 13.207, 2.845),
            (11.999, 12.040, 2.945),
            (13.398, 12.442, 2.508),
            (13.598, 13.601, 2.128),
        ]
    ), "the surviving atoms are not the deposited ones"


def test_both_preparation_paths_receive_the_same_declared_ph():
    """One declared pH reaches the receptor AND the ligand, asserted at the
    PROVIDER boundary rather than in the UI.

    The panel showing a single control proves nothing about what is passed
    downstream -- a future refactor could leave one spinbox on screen and hand
    the two conversions different numbers, and every widget-level assertion
    would still pass. This watches the call Open Babel actually receives.

    Two pH-correct calls, same value, is the invariant. The ligand path used to
    contribute none of them.
    """
    from openbabel import openbabel as ob

    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))

    calls = []
    original = ob.OBMol.AddHydrogens

    def spy(self, polaronly=False, correct_for_ph=False, ph=7.4):
        calls.append((polaronly, correct_for_ph, ph))
        return original(self, polaronly, correct_for_ph, ph)

    with patch.object(ob.OBMol, "AddHydrogens", spy):
        provider.dock(
            RECEPTOR_PDB, "pdb", Chem.MolFromSmiles("CCN"), box, 9, ProgressHandle(),
            receptor_prep_options={"ph": 6.25},
        )

    ph_corrected = [call for call in calls if call[1] is True]
    assert len(ph_corrected) == 2, f"expected receptor AND ligand, got {ph_corrected}"
    assert {call[2] for call in ph_corrected} == {6.25}, ph_corrected


def test_the_recorded_settings_are_what_actually_ran():
    """The stored result reports the run, not this file's own constants.

    These fields used to be the literals `"vina"`, `8` and `None`, written at
    the call site. They were true only by coincidence -- they described the
    defaults the service happened to believe in, and would have gone silently
    stale the moment a default moved. A stored result naming settings it did
    not use is worse than one naming none, because nothing distinguishes it
    from a measurement.
    """
    from openchem.services.docking_service import _recorded_settings

    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    provider.dock(
        RECEPTOR_PDB, "pdb", Chem.MolFromSmiles("CCN"), box, 9, ProgressHandle(),
        receptor_prep_options={"ph": 6.25},
        search_options={"exhaustiveness": 17, "seed": 4242, "scoring_function": "vinardo"},
    )
    recorded = _recorded_settings(provider, {"ph": 6.25})

    assert recorded["exhaustiveness"] == 17
    assert recorded["seed"] == 4242
    assert recorded["scoring_function"] == "vinardo"
    assert recorded["ligand_prep_params"] == {"ph": 6.25}
    # And they describe the ENGINE INVOCATION, not merely the request.
    assert engine.dock_calls[-1]["exhaustiveness"] == 17
    assert engine.dock_calls[-1]["seed"] == 4242
    assert engine.dock_calls[-1]["scoring_function"] == "vinardo"


def test_a_seed_is_chosen_and_recorded_when_the_caller_pins_none():
    """`seed=None` used to reach Vina as its own "pick randomly", so a run
    could not be reproduced even in principle and nothing recorded what was
    used. A seed is chosen here instead and travels to both the engine and the
    result.

    This records the seed so a run can be reproduced under the SAME engine,
    version and settings. It is not a claim of determinism across Vina
    versions, backends or thread counts.
    """
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    provider.dock(
        RECEPTOR_PDB, "pdb", Chem.MolFromSmiles("CCN"), box, 9, ProgressHandle(),
    )
    seed = provider._last_run_settings["seed"]
    assert isinstance(seed, int) and seed > 0
    assert engine.dock_calls[-1]["seed"] == seed


def test_the_default_exhaustiveness_reaches_the_engine():
    """The default is honoured rather than restated downstream -- which is how
    the old hardcoded `exhaustiveness=8` in the service came to disagree with
    the constant it was copied from."""
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    provider.dock(RECEPTOR_PDB, "pdb", Chem.MolFromSmiles("CCN"), box, 9, ProgressHandle())
    assert engine.dock_calls[-1]["exhaustiveness"] == DEFAULT_EXHAUSTIVENESS


def test_an_unknown_scoring_function_is_refused_before_the_engine_runs():
    """Fail closed, and name the setting.

    An unrecognised name would otherwise reach Vina's command line and be
    rejected there, surfacing as a non-zero exit status that names neither the
    setting nor where it came from -- the same shape as the untyped atom that
    made Vina reject a whole receptor.
    """
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    box = DockingBox(center=_RECEPTOR_CENTER, size=(20, 20, 20))
    with pytest.raises(DockingProviderError, match="scoring function"):
        provider.dock(
            RECEPTOR_PDB, "pdb", Chem.MolFromSmiles("CCN"), box, 9, ProgressHandle(),
            search_options={"scoring_function": "not-a-real-function"},
        )
    assert engine.dock_calls == [], "the engine must not have been invoked"
