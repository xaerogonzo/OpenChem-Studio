"""The predicted IR spectrum written out as a JCAMP-DX peak table."""

from __future__ import annotations

import pytest

from openchem.chem import jcamp
from openchem.chem.ir_export import export_jcamp_peaks
from openchem.domain.scientific_result import VibrationalMode


def _mode(wavenumber, intensity=10.0):
    return VibrationalMode(wavenumber_cm1=wavenumber, ir_intensity_km_mol=intensity)


def _rows(text):
    start = text.index("##PEAKTABLE=(XY..XY)") + 1
    out = []
    for line in text.splitlines()[text.splitlines().index("##PEAKTABLE=(XY..XY)") + 1:]:
        if line.startswith("##"):
            break
        x, y = (float(v) for v in line.split(","))
        out.append((x, y))
    assert start
    return out


def test_every_real_band_is_written_high_wavenumber_first():
    text = export_jcamp_peaks([_mode(1600.0, 40.0), _mode(3400.0, 20.0), _mode(500.0, 5.0)])
    assert _rows(text) == [(3400.0, 20.0), (1600.0, 40.0), (500.0, 5.0)]
    assert "##NPOINTS=3" in text and "##XUNITS=1/CM" in text and "##YUNITS=KM/MOL" in text


def test_it_says_it_is_predicted_and_harmonic():
    text = export_jcamp_peaks([_mode(1000.0)], method="B3LYP def2-SVP")
    assert "PREDICTED, not a measurement" in text and "Harmonic" in text and "B3LYP def2-SVP" in text
    assert text.splitlines()[2] == "##DATA TYPE=INFRARED SPECTRUM"


def test_a_scaling_factor_is_recorded_only_when_one_was_applied():
    assert "scaled" not in export_jcamp_peaks([_mode(1000.0)])
    assert "scaled by 0.97" in export_jcamp_peaks([_mode(1000.0)], scaling_factor=0.97)


def test_an_imaginary_mode_is_named_and_never_written_as_a_band():
    text = export_jcamp_peaks([_mode(-1436.0), _mode(1600.0)])
    assert _rows(text) == [(1600.0, 10.0)]
    assert "1 imaginary mode(s) are not listed" in text and "##NPOINTS=1" in text


def test_a_mode_with_no_reported_intensity_is_written_as_zero():
    assert _rows(export_jcamp_peaks([VibrationalMode(wavenumber_cm1=900.0)])) == [(900.0, 0.0)]


def test_nothing_real_to_export_is_refused_not_written_empty():
    for modes in ([], [_mode(-100.0)]):
        with pytest.raises(ValueError, match="no real bands"):
            export_jcamp_peaks(modes)


def test_this_applications_own_reader_refuses_a_peak_table_by_design():
    """Recorded rather than hidden: the file is for other tools, and the overlay
    import says why it will not take it."""
    with pytest.raises(jcamp.JcampError, match="peak tables"):
        jcamp.parse(export_jcamp_peaks([_mode(1000.0)]))
