from __future__ import annotations

import logging
from typing import Callable

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.plugins.interfaces import ConformerProvider

logger = logging.getLogger("openchem.chemistry")

# RDKitConformerProvider implements the same ConformerProvider ABC a future
# plugin would (openchem.plugins.interfaces.ConformerProvider) — ConformerService
# can't tell a built-in method from a plugin-supplied one.


class RDKitConformerProvider(ConformerProvider):
    """Embeds conformers one at a time (rather than RDKit's batch
    EmbedMultipleConfs) specifically so each iteration can report progress
    and honor cancellation via `on_progress`'s return value: returning
    `False` stops the loop before the next conformer starts (RDKit's own
    embed/optimize calls aren't preemptible mid-call, so this is
    best-effort, checked between conformers, not instant). A `None` return
    (the common case -- most callers' `on_progress` has no return
    statement) means "keep going," so this is fully backward compatible
    with callers that don't care about cancellation at all.
    """

    provider_id = "rdkit"

    def generate_conformers(
        self,
        mol: Chem.Mol,
        num_conformers: int,
        optimize: bool,
        on_progress: Callable[[int, int], bool | None] | None = None,
    ) -> list[tuple[Chem.Mol, float | None]]:
        results: list[tuple[Chem.Mol, float | None]] = []
        for i in range(num_conformers):
            conf_mol = self._embed_one(mol)
            energy = self._optimize_one(conf_mol) if conf_mol is not None and optimize else None
            if conf_mol is not None:
                results.append((conf_mol, energy))
            if on_progress is not None:
                should_continue = on_progress(i + 1, num_conformers)
                if should_continue is False:
                    break
        return results

    def _embed_one(self, mol: Chem.Mol) -> Chem.Mol | None:
        conf_mol = Chem.AddHs(Chem.Mol(mol))
        params = AllChem.ETKDGv3()
        conf_id = AllChem.EmbedMolecule(conf_mol, params)
        if conf_id < 0:
            # Retry once with random coordinates — some strained/unusual
            # structures fail ETKDG's distance-geometry pass otherwise.
            params.useRandomCoords = True
            conf_id = AllChem.EmbedMolecule(conf_mol, params)
        if conf_id < 0:
            logger.warning("Failed to embed a conformer for molecule")
            return None
        return conf_mol

    def _optimize_one(self, conf_mol: Chem.Mol) -> float | None:
        mmff_props = AllChem.MMFFGetMoleculeProperties(conf_mol)
        if mmff_props is not None:
            AllChem.MMFFOptimizeMolecule(conf_mol, confId=0)
            force_field = AllChem.MMFFGetMoleculeForceField(conf_mol, mmff_props, confId=0)
        else:
            # MMFF94 has no parameters for some elements/charges — UFF covers
            # a much broader range of the periodic table as a fallback.
            AllChem.UFFOptimizeMolecule(conf_mol, confId=0)
            force_field = AllChem.UFFGetMoleculeForceField(conf_mol, confId=0)
        return force_field.CalcEnergy() if force_field is not None else None
