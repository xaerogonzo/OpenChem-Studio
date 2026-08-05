from __future__ import annotations

from ai_assistant.tools import (
    AVAILABLE_TOOLS,
    TOOL_REGISTRY,
    explain_naming,
    validate_smarts,
)


def test_validate_smarts_accepts_a_valid_pattern():
    result = validate_smarts("[#6]")
    assert "Valid SMARTS pattern" in result
    assert "1 atom" in result


def test_validate_smarts_rejects_an_invalid_pattern():
    result = validate_smarts("not a smarts pattern @#$")
    assert "Invalid SMARTS pattern" in result


def test_validate_smarts_is_registered_and_available():
    assert TOOL_REGISTRY["validate_smarts"] is validate_smarts
    assert any(tool.name == "validate_smarts" for tool in AVAILABLE_TOOLS)


# --- explain_naming: grounding the assistant in the engine's own record ---


def test_explain_naming_reports_the_engines_real_derivation():
    """The point of this tool is that it is NOT a guess. Asked why a
    structure has its name, a language model produces a fluent and often
    wrong account of IUPAC rules; this hands it the engine's own record."""
    report = explain_naming("CC(=O)Oc1ccccc1C(=O)O")

    assert "2-(acetoxy)benzoic acid" in report
    assert "benzene" in report              # the parent it chose
    assert "carboxylic_acid" in report      # the group that took the suffix
    assert "acetoxy" in report              # the substituent


def test_explain_naming_gives_the_real_atom_to_locant_map():
    """So "why is this carbon numbered 4?" is answerable from a record
    rather than reconstructed from memory."""
    report = explain_naming("CC(=O)Oc1ccccc1C(=O)O")
    assert "Atom numbering" in report
    assert "C1" in report and "C4" in report


def test_explain_naming_warns_the_model_off_inventing_locants():
    """Slightly over half of all molecules get no numbering at all. Left
    unsaid, that is exactly the gap a model fills with a confident
    fabrication -- so the tool output says so in as many words."""
    # Camphor, not caffeine: caffeine used to be the example here and now
    # takes its purine numbering from the ring table, so it no longer
    # exercises the warning. Camphor's bridged skeleton is not a numbered
    # table entry, which is the case 76 of 181 corpus molecules are in.
    report = explain_naming("CC1(C)C2CCC1(C)C(=O)C2")
    assert "No atom numbering is available" in report
    assert "Do NOT supply locants from memory" in report


def test_explain_naming_flags_atoms_outside_the_numbered_parent():
    """Aspirin numbers only its six ring atoms; the other seven have no
    locant and must not be given one."""
    report = explain_naming("CC(=O)Oc1ccccc1C(=O)O")
    assert "carry no locant" in report
    assert "Do not invent numbers for them" in report


def test_explain_naming_reports_bad_input_rather_than_raising():
    assert "Could not parse" in explain_naming("not-a-smiles")


def test_explain_naming_is_registered_and_executable_locally():
    """Every tool the assistant may request must have a local handler --
    execution never happens on the model's side."""
    assert "explain_naming" in TOOL_REGISTRY
    assert {t.name for t in AVAILABLE_TOOLS} >= {"validate_smarts", "explain_naming"}
    assert TOOL_REGISTRY["explain_naming"](smiles="CCO")
