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

    def test_unclaimed_when_no_classifier_recognises_the_motif(self):
        # Benzyl cation: names as "methylbenzene" (toluene).  No classifier
        # claims it, so the fix belongs in a classifier, not a renderer.
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
