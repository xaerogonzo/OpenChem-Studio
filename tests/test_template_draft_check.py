"""Draft-template checker: stereo names, dummy atoms, parse."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "template_draft_check", ROOT / "tools" / "template_draft_check.py"
)
draft = importlib.util.module_from_spec(_spec)
sys.modules["template_draft_check"] = draft
assert _spec.loader is not None
_spec.loader.exec_module(draft)


def test_a_cis_name_without_slash_bonds_needs_stereo():
    assert draft.name_implies_stereo("cis-Decalin")
    assert draft.name_implies_stereo("(1R,4R)-Camphor")
    assert draft.name_implies_stereo("(S)-Ibuprofen")
    assert draft.name_implies_stereo("L-Alanine")
    assert not draft.name_implies_stereo("Benzene")
    assert not draft.name_implies_stereo(
        "1-Ethyl-3-(3-dimethylaminopropyl)carbodiimide"
    )
    assert not draft.name_implies_stereo(
        "1,1,1-Trichloro-2,2-bis(4-chlorophenyl)ethane"
    )
    assert draft.smiles_has_stereo(r"C/C=C/C")
    assert draft.smiles_has_stereo("C[C@H](O)C")
    assert not draft.smiles_has_stereo("C1CCCCC1")


def test_benzene_draft_is_a_shipped_duplicate(tmp_path: Path):
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "benzene",
                        "name": "Benzene",
                        "smiles": "c1ccccc1",
                        "category_id": "rings",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = draft.check_drafts(path)
    assert report["rows"][0]["status"] == "duplicate_shipped"


def test_a_dummy_atom_is_refused(tmp_path: Path):
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "phenyl",
                        "name": "Phenyl",
                        "smiles": "*c1ccccc1",
                        "category_id": "functional_groups",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = draft.check_drafts(path)
    assert report["rows"][0]["status"] == "refused"
    assert any("dummy" in r for r in report["rows"][0]["reasons"])


def test_a_new_named_molecule_with_stereo_is_ok(tmp_path: Path):
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "s_2_bromobutane",
                        "name": "(S)-2-Bromobutane",
                        "smiles": "CC[C@H](C)Br",
                        "category_id": "functional_groups",
                        "stereo_in_name": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = draft.check_drafts(path)
    assert report["counts"].get("ok") == 1
    assert report["rows"][0]["inchikey"]
