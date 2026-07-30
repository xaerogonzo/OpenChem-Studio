from __future__ import annotations

from ai_assistant.tools import AVAILABLE_TOOLS, TOOL_REGISTRY, validate_smarts


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
