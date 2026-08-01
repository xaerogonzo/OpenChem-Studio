"""Tests for the opt-in naming diagnostics (``iupac_namer.diagnostics``).

The instrument exists to find one specific failure shape: a charged
molecule whose motif no classifier claims, or whose renderer declines, is
handed back to the generic plan search -- which neutralizes it and names
the neutral skeleton.  The caller gets a confident wrong answer.

These tests pin two things that are easy to break by accident:

1. **It is off unless asked for.**  The perception layer documents "no
   module-level mutable state" as an invariant, and instrumentation that
   ran by default would both violate the spirit of that and cost a
   canonicalisation per charged molecule.
2. **It attributes the decline to the right gate.**  ``unclaimed`` means
   a classifier needs writing; ``render_failed`` means an existing
   renderer needs extending.  That distinction is invisible from the
   wrong name alone, and getting it backwards sends the fix to the wrong
   layer.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

from openchem.vendor.iupac_namer import diagnostics
from openchem.vendor.iupac_namer.engine import name_smiles
from openchem.vendor.iupac_namer.perception import charge_perception


class TestEnablement:
    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENCHEM_NAMER_DEBUG", None)
            assert diagnostics.enabled() is False

    def test_env_var_enables(self):
        with mock.patch.dict(os.environ, {"OPENCHEM_NAMER_DEBUG": "1"}):
            assert diagnostics.enabled() is True

    def test_falsy_env_values_do_not_enable(self):
        for raw in ("", "0", "false", "no", "off", "  "):
            with mock.patch.dict(os.environ, {"OPENCHEM_NAMER_DEBUG": raw}):
                assert diagnostics.enabled() is False, raw

    def test_capture_enables_without_touching_environ(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENCHEM_NAMER_DEBUG", None)
            with diagnostics.capture():
                assert diagnostics.enabled() is True
                assert "OPENCHEM_NAMER_DEBUG" not in os.environ
            assert diagnostics.enabled() is False

    def test_capture_restores_previous_recorder(self):
        with diagnostics.capture() as outer:
            with diagnostics.capture() as inner:
                assert diagnostics.current() is inner
            assert diagnostics.current() is outer


class TestGateAttribution:
    """Each defect must be attributed to the layer that has to change."""

    def test_unclaimed_when_no_classifier_recognises_the_motif(self, monkeypatch):
        """A charged molecule no classifier claims is attributed to the
        classifier layer, not to a renderer.

        Classification is forced to come back empty rather than relying on
        a live defect: this test used to pass the benzyl cation, and went
        stale the moment that case was fixed. Same trap as the
        render_failed test below -- what is pinned is the instrument, not
        which defects happen to be open today.
        """
        monkeypatch.setattr(charge_perception, "classify_charges", lambda mol: ())
        with diagnostics.capture() as rec:
            name_smiles("[CH2+]c1ccccc1")
        reasons = {g.reason for g in rec.gaps}
        assert "unclaimed" in reasons, rec.report()

    def test_render_failed_when_claimed_motif_cannot_be_composed(self, monkeypatch):
        """A claimed motif whose renderer declines is attributed to the
        renderer, not to a missing classifier.

        The renderer is forced to decline rather than using a live defect
        as the example: this test previously used the ring polyacylium
        dication, and went stale the moment that case was fixed. What is
        being pinned is the instrument, not the current defect list.
        """
        monkeypatch.setattr(charge_perception, "_render", lambda *a, **k: None)
        with diagnostics.capture() as rec:
            # Recording happens before the refusal, so the gap is captured
            # and then the ValueError propagates -- see
            # _refuse_rather_than_neutralize.
            with pytest.raises(ValueError, match="render_failed"):
                name_smiles("O=[C+]c1ccccc1[C+]=O")
        failed = [g for g in rec.gaps if g.reason == "render_failed"]
        assert failed, rec.report()
        assert failed[0].suffix_hint == "polyacylium"

    def test_successful_render_is_counted_but_is_not_a_gap(self):
        with diagnostics.capture() as rec:
            name_smiles("[C+](C)=O")  # acetylium
        assert rec.stats["acylium"]["succeeded"] == 1
        assert rec.stats["acylium"]["failed"] == 0
        assert not [g for g in rec.gaps if g.suffix_hint == "acylium"]

    def test_neutral_molecules_record_no_gaps(self):
        # detect() runs for every molecule the engine names.  Recording the
        # neutral ones would bury the handful of real cases under thousands
        # of uninteresting declines.
        with diagnostics.capture() as rec:
            name_smiles("c1ccccc1")
            name_smiles("CCO")
            name_smiles("CC(=O)O")
        assert rec.gaps == []


class TestRefusalGuard:
    """Two decline reasons refuse; the third must keep falling through.

    The split was measured, not reasoned: over the benchmark corpus plus a
    69-probe charged-species sweep (193 molecules), `render_failed`
    occurred 0 times and `partial_claim` once, while `unclaimed` occurred
    35 times and was almost always a molecule some OTHER path names
    correctly. Making `unclaimed` fatal would break dozens of correct
    names; making the other two fatal costs nothing today and converts
    any future gap from a wrong molecule into a visible failure.
    """

    def test_partial_claim_refuses_instead_of_naming_another_molecule(
        self, monkeypatch
    ):
        """A classification covering only SOME of the formal charges must
        refuse, not fall through.

        The condition is forced rather than taken from a live defect. This
        test used diazomethane, where the diazonium classifier claimed the
        [N+] and left the carbanion uncovered -- and it expired the moment
        that was fixed, exactly like the two tests above. What is pinned is
        the guard, not the current defect list.
        """
        from openchem.vendor.iupac_namer.perception.charge_perception import (
            ChargeClassification,
        )

        def _covers_only_the_carbanion(mol):
            return (
                ChargeClassification(
                    site_atom_indices=(0,),
                    charge_sign="-",
                    suffix_hint="ide",
                    site_charges=(-1,),
                ),
            )

        monkeypatch.setattr(
            charge_perception, "classify_charges", _covers_only_the_carbanion
        )
        with pytest.raises(ValueError, match="partial_claim"):
            name_smiles("[CH2-][N+]#N")

    @pytest.mark.parametrize("smiles", [
        "c1cc[nH+]cc1",          # pyridinium, retained ring-cation path
        "C[S+](C)C",             # sulfonium
        "C[N+](C)(C)CC(=O)[O-]",  # betaine
        "O=[N+]([O-])c1ccccc1",  # nitrobenzene
        "[C+]1=CC=CC=C1",        # phenylium, retained lookup
    ])
    def test_unclaimed_still_falls_through_and_names_correctly(self, smiles):
        """`unclaimed` is not a defect signal. This module deliberately
        leaves these motifs to other paths, and they name them fine."""
        assert name_smiles(smiles)


class TestRecorder:
    def test_report_is_safe_when_nothing_was_recorded(self):
        assert diagnostics.Recorder().report() == "nothing recorded"

    def test_stats_accumulate_across_calls(self):
        rec = diagnostics.Recorder()
        rec.record("polyacylium", smiles="A", succeeded=True)
        rec.record("polyacylium", smiles="B", succeeded=False)
        assert rec.stats["polyacylium"] == {
            "attempted": 2, "succeeded": 1, "failed": 1
        }
        # A failed render is also a gap -- one event, both views.
        assert [g.reason for g in rec.gaps] == ["render_failed"]

    def test_by_reason_groups_gaps(self):
        rec = diagnostics.Recorder()
        rec.record_gap("unclaimed", smiles="A")
        rec.record_gap("unclaimed", smiles="B")
        rec.record_gap("ambiguous", smiles="C")
        grouped = rec.by_reason()
        assert len(grouped["unclaimed"]) == 2
        assert len(grouped["ambiguous"]) == 1

    def test_every_emitted_reason_is_declared(self):
        """REASONS documents the reasons that can end in a neutral name."""
        rec = diagnostics.Recorder()
        with diagnostics.capture():
            pass
        for smi in ("[CH2+]c1ccccc1", "O=[C+]c1ccccc1[C+]=O", "[NH2+]=C(N)N"):
            with diagnostics.capture() as scoped:
                name_smiles(smi)
            rec.gaps.extend(scoped.gaps)
        assert {g.reason for g in rec.gaps} <= set(diagnostics.REASONS)
