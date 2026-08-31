"""A box too small for the ligand is REPORTED, never silently resized.

Two levels, as `ui/visual_check` splits them: `ligand_extent_exceeds_box` is
arithmetic over two numbers and is tested on CONSTRUCTED values, so its guards
are not claims about RDKit's embedder; `max_heavy_atom_extent` reads a real
conformer and is exercised separately.

**THE MOTIVATING CASE DOES NOT TRIP THIS, deliberately.** The box in the
report was measured adequate for all three ligands once the extent was taken
over the atoms Vina is actually handed rather than over every hydrogen. Pinning
that is the point: a warning tuned until it fires on the case somebody
complained about is not a warning, and this file asserts the negative
explicitly so nobody later "fixes" the threshold until it does.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.binding_site import ligand_extent_exceeds_box, max_heavy_atom_extent
from openchem.domain.docking import DockingBox

#: The box the Docking panel derived from BU-72 for 5C1M, as reported.
REPORTED_BOX = DockingBox(center=(2.03, 15.92, -58.78), size=(16.00, 17.80, 16.27))

LIGANDS = {
    "BU-72": "C[C@]12CC[C@@]3(O)[C@H]4Cc5ccc(O)cc5[C@@]3(CCN4CC3CC3)[C@@H]1OC1=CC=CC=C21",
    "fentanyl": "CCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1",
    "butyryl fentanyl": "CCCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1",
}


def _lowest_energy(smiles: str) -> Chem.Mol:
    """The conformer the panel would dock: lowest MMFF energy of an ensemble."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMultipleConfs(mol, numConfs=30, randomSeed=0xC0FFEE)
    energies = AllChem.MMFFOptimizeMoleculeConfs(mol)
    best = min(range(len(energies)), key=lambda i: energies[i][1])
    single = Chem.Mol(mol)
    single.RemoveAllConformers()
    single.AddConformer(mol.GetConformer(best), assignId=True)
    return single


# --------------------------------------------------------------------------
# The predicate, on constructed numbers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extent,expected",
    [(15.9, False), (16.0, False), (16.1, True), (30.0, True)],
)
def test_the_predicate_compares_against_the_shortest_side(extent, expected):
    """The SHORTEST side, not the average or the diagonal: a ligand longer
    than the smallest dimension cannot lie along that axis, so orientations
    are excluded even though the box is roomy elsewhere."""
    box = DockingBox(center=(0.0, 0.0, 0.0), size=(16.0, 40.0, 40.0))
    assert ligand_extent_exceeds_box(extent, box) is expected


def test_an_unmeasurable_ligand_never_warns():
    """No conformer means no extent, and "I could not measure it" is not
    "it is too big" -- a diagnostic that cries wolf on missing data gets
    switched off."""
    assert ligand_extent_exceeds_box(None, REPORTED_BOX) is False


# --------------------------------------------------------------------------
# The extraction, on real geometry
# --------------------------------------------------------------------------


def test_hydrogens_do_not_inflate_the_extent():
    """The measure is HEAVY atoms, and the difference is what made the first
    version of this feature wrong.

    Counting every hydrogen put fentanyl over the reported box and made the
    box look like the explanation for a poor run. Vina's ligand PDBQT merges
    nonpolar hydrogens into their heavy atom, so that number described a
    molecule Vina never receives.
    """
    mol = _lowest_energy(LIGANDS["fentanyl"])
    heavy = max_heavy_atom_extent(mol)
    conf = mol.GetConformer()
    all_atoms = [conf.GetAtomPosition(a.GetIdx()) for a in mol.GetAtoms()]
    with_hydrogens = max(
        ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5
        for i, a in enumerate(all_atoms)
        for b in all_atoms[i + 1 :]
    )
    assert with_hydrogens > heavy + 1.0, (with_hydrogens, heavy)


def test_a_molecule_with_no_conformer_reports_no_extent():
    assert max_heavy_atom_extent(Chem.MolFromSmiles("CCO")) is None


@pytest.mark.parametrize("name", sorted(LIGANDS))
def test_the_reported_box_is_adequate_for_all_three_reported_ligands(name):
    """The negative case, asserted on purpose.

    A warning that fires on the situation somebody complained about, having
    been tuned until it did, is not evidence about that situation. This box
    was measured adequate; if a future change makes this test fail, the
    threshold moved rather than the chemistry.
    """
    extent = max_heavy_atom_extent(_lowest_energy(LIGANDS[name]))
    assert extent is not None and extent < min(REPORTED_BOX.size), (name, extent)
    assert ligand_extent_exceeds_box(extent, REPORTED_BOX) is False


def test_a_box_genuinely_too_small_does_warn():
    """The guard can say YES -- otherwise the test above passes vacuously and
    the feature could be entirely dead."""
    extent = max_heavy_atom_extent(_lowest_energy(LIGANDS["butyryl fentanyl"]))
    cramped = DockingBox(center=REPORTED_BOX.center, size=(10.0, 30.0, 30.0))
    assert ligand_extent_exceeds_box(extent, cramped) is True


# --------------------------------------------------------------------------
# The panel wiring: the warning has to reach the screen, and the settings
# the provider
# --------------------------------------------------------------------------


def _panel_with(ligand_smiles: str, box: DockingBox):
    """A real DockingPanel with a real ligand conformer, box set by hand."""
    from openchem.app.settings import Settings
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.conformer import ConformerModel
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel
    from openchem.events.base import EventBus
    from openchem.services.docking_service import DockingService
    from openchem.ui.panels.docking_panel import DockingPanel

    class _Recording(DockingService):
        def __init__(self, bus):
            super().__init__(bus, Settings(bus), providers={})
            self.requests = []

        def request_docking(self, **kwargs):
            self.requests.append(kwargs)

    bus = EventBus()
    engine = ChemistryEngine()
    service = _Recording(bus)
    panel = DockingPanel(service, engine, Settings(bus), bus)

    ligand = MoleculeModel(display_name="Ligand")
    engine.set_structure_from_smiles(ligand, ligand_smiles)
    ligand.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(_lowest_energy(ligand_smiles))))

    project = ProjectModel(name="T")
    project.macromolecules.append(
        MacromoleculeModel(display_name="R", structure_text="HEADER\nATOM\nEND\n", source_format="pdb")
    )
    project.molecules.append(ligand)
    panel.set_project(project)
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)
    for spin, value in zip(
        (panel._size_x, panel._size_y, panel._size_z), box.size
    ):
        spin.setValue(value)
    return panel, service


def test_a_cramped_box_warns_on_screen(qapp):
    """The warning has to REACH the status label, not merely be computable.

    Testing the predicate alone would prove the arithmetic works and say
    nothing about whether anyone is ever told.
    """
    panel, _ = _panel_with(LIGANDS["butyryl fentanyl"], DockingBox(center=(0.0, 0.0, 0.0), size=(10.0, 30.0, 30.0)))
    panel._on_dock_clicked()
    text = panel._box_status_label.text()
    assert "exceeds the shortest box dimension" in text, text
    # And never the stronger claim: fit is orientation-dependent.
    assert "does not fit" not in text.lower(), text


def test_a_roomy_box_says_nothing_about_the_ligands_extent(qapp):
    """The negative arm. A warning that always fires is not a warning, and
    this is the one that would go unnoticed."""
    panel, _ = _panel_with(LIGANDS["fentanyl"], DockingBox(center=(0.0, 0.0, 0.0), size=(40.0, 40.0, 40.0)))
    panel._on_dock_clicked()
    assert "exceeds the shortest box dimension" not in panel._box_status_label.text()


def test_the_panels_search_settings_reach_the_service(qapp):
    """One accessor, and what it reads is what is sent.

    Asserted on the REQUEST rather than on the widgets: the panel showing 25
    proves nothing about what the provider is handed, which is the same
    reason `displayed_box` exists as a single accessor.
    """
    panel, service = _panel_with(LIGANDS["fentanyl"], DockingBox(center=(0.0, 0.0, 0.0), size=(30.0, 30.0, 30.0)))
    panel._exhaustiveness_combo.setCurrentIndex(panel._exhaustiveness_combo.findData(32))
    panel._scoring_combo.setCurrentIndex(panel._scoring_combo.findData("vinardo"))
    panel._seed_spin.setValue(99)

    panel._on_dock_clicked()

    sent = service.requests[-1]["search_options"]
    assert sent == {"exhaustiveness": 32, "scoring_function": "vinardo", "seed": 99}


def test_the_seed_spinboxs_zero_means_random_rather_than_zero(qapp):
    """0 is the spinbox's special "Random" value. Sending it as a literal 0
    would pin every unpinned run to one seed -- the opposite of what the
    control says, and invisible until someone noticed every run agreeing."""
    panel, service = _panel_with(LIGANDS["fentanyl"], DockingBox(center=(0.0, 0.0, 0.0), size=(30.0, 30.0, 30.0)))
    panel._seed_spin.setValue(0)
    assert panel._seed_spin.text() == "Random"

    panel._on_dock_clicked()

    assert service.requests[-1]["search_options"]["seed"] is None
