"""A measured NMR reference (JCAMP-DX), and exporting a prediction.

The reference is data beside the prediction, never part of it: these tests fix
that importing and rescaling change nothing the application computed, that the
original trace is never mutated, and that identity is the original bytes.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import jcamp
from openchem.chem.nmr_export import export_jcamp, export_sdf
from openchem.chem.nmr_measured import (
    NmrReference,
    read_nmr_reference,
    reference_peaks,
)
from openchem.chem.nmr_signals import NMRSignal


def _jdx(*, units="PPM", frequency="400.13", nucleus="^1H", data_type="NMR SPECTRUM", solvent="CDCl3",
         first="8.0", delta="-0.5", ys=(0, 10, 100, 10, 0, 0, 60, 5, 0)) -> str:
    npoints = len(ys)
    header = [
        "##TITLE=ethyl test",
        "##JCAMP-DX=5.00",
        f"##DATA TYPE={data_type}",
        f"##.OBSERVE FREQUENCY={frequency}" if frequency else "",
        f"##.OBSERVE NUCLEUS={nucleus}" if nucleus else "",
        f"##.SOLVENT NAME={solvent}" if solvent else "",
        f"##XUNITS={units}",
        "##YUNITS=ARBITRARY UNITS",
        f"##FIRSTX={first}",
        f"##DELTAX={delta}",
        "##XFACTOR=1",
        "##YFACTOR=1",
        f"##NPOINTS={npoints}",
        "##XYDATA=(X++(Y..Y))",
        f"{first} " + " ".join(str(y) for y in ys),
        "##END=",
    ]
    return "\n".join(line for line in header if line)


def test_a_ppm_spectrum_is_read_with_its_provenance():
    ref = read_nmr_reference(_jdx(), "ethyl.jdx")

    assert (ref.nucleus, ref.frequency_mhz, ref.solvent, ref.source_x_units) == ("H", 400.13, "CDCl3", "PPM")
    assert ref.point_count == 9 and ref.ppm[0] == pytest.approx(8.0)
    assert ref.filename == "ethyl.jdx" and ref.source_format == "JCAMP-DX"
    assert "not a prediction" in ref.describe()


def test_an_hz_axis_is_converted_by_the_spectrometer_frequency():
    ref = read_nmr_reference(_jdx(units="HZ", first="3200.0", delta="-200.0"), "hz.jdx")

    assert ref.source_x_units == "HZ"
    assert ref.ppm[0] == pytest.approx(3200.0 / 400.13)
    assert ref.ppm[1] == pytest.approx(3000.0 / 400.13)


def test_an_hz_axis_without_a_frequency_is_refused():
    with pytest.raises(jcamp.JcampError, match="OBSERVE FREQUENCY"):
        read_nmr_reference(_jdx(units="HZ", frequency=""), "x.jdx")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"data_type": "INFRARED SPECTRUM"}, "not an NMR spectrum"),
        ({"data_type": "NMR FID"}, "FID"),
        ({"units": "NM"}, "Unsupported x axis unit"),
    ],
)
def test_what_is_not_a_processed_nmr_spectrum_is_refused_by_name(kwargs, message):
    with pytest.raises(jcamp.JcampError, match=message):
        read_nmr_reference(_jdx(**kwargs), "x.jdx")


@pytest.mark.parametrize(("header", "expected"), [("^1H", "H"), ("1H", "H"), ("^13C", "C"), ("13C", "C")])
def test_nucleus_spellings_are_recognised(header, expected):
    assert read_nmr_reference(_jdx(nucleus=header), "x.jdx").nucleus == expected


def test_an_unrecognised_nucleus_is_kept_as_text_and_matches_nothing():
    ref = read_nmr_reference(_jdx(nucleus="^31P"), "x.jdx")

    assert ref.nucleus == "31P" and not ref.matches("H") and not ref.matches("C")


def test_identity_is_the_original_bytes_not_the_trace():
    one = read_nmr_reference(_jdx(), "a.jdx")
    same = read_nmr_reference(_jdx(), "renamed.jdx")
    different = read_nmr_reference(_jdx(solvent="DMSO-d6"), "a.jdx")  # same trace, different bytes

    assert one.content_sha256 == same.content_sha256
    assert one.ppm == different.ppm and one.content_sha256 != different.content_sha256


def test_the_original_trace_is_immutable():
    ref = read_nmr_reference(_jdx(), "a.jdx")

    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
        ref.ppm = ()
    assert isinstance(ref.ppm, tuple) and isinstance(ref.intensity, tuple)


def test_reference_peaks_are_local_maxima_above_the_threshold():
    ref = read_nmr_reference(_jdx(), "a.jdx")

    peaks = reference_peaks(ref)

    assert [intensity for _ppm, intensity in peaks] == [100, 60]
    assert reference_peaks(ref, min_fraction=0.9) == [peaks[0]]


# --- exporting a prediction --------------------------------------------------


def _signals():
    return [
        NMRSignal(shift=1.2, atom_indices=[3, 4, 5], integration=3, multiplicity="t", coupling_hz=[7.0],
                  coupling_groups=((2, 7.0),)),
        NMRSignal(shift=3.6, atom_indices=[6, 7], integration=2, multiplicity="q", coupling_hz=[7.0],
                  coupling_groups=((3, 7.0),)),
    ]


def test_the_jcamp_export_round_trips_through_the_applications_own_reader():
    text = export_jcamp(_signals(), frequency_mhz=400.0, element="H", solvent="CDCl3", method="HF STO-3G")

    spectrum = jcamp.parse(text)
    ref = read_nmr_reference(text, "export.jdx")

    assert spectrum.point_count == 4096
    assert (ref.nucleus, ref.frequency_mhz, ref.solvent, ref.source_x_units) == ("H", 400.0, "CDCl3", "PPM")
    tallest = max(range(ref.point_count), key=ref.intensity.__getitem__)
    # The tallest point sits on the 1.2 ppm triplet's most intense line (centre).
    assert abs(ref.ppm[tallest] - 1.2) < 0.05


def test_the_export_says_it_is_predicted_and_not_a_measurement():
    text = export_jcamp(_signals(), frequency_mhz=400.0, element="H")

    assert "PREDICTED, not a measurement" in text
    assert "not a spin-Hamiltonian simulation" in text
    assert "##ORIGIN=OpenChem Studio" in text


def test_decoupled_export_has_one_line_per_signal():
    coupled = read_nmr_reference(export_jcamp(_signals(), frequency_mhz=400.0, element="H"), "c.jdx")
    decoupled = read_nmr_reference(
        export_jcamp(_signals(), frequency_mhz=400.0, element="H", decoupled=True), "d.jdx"
    )

    assert len(reference_peaks(decoupled)) == 2
    assert len(reference_peaks(coupled)) > len(reference_peaks(decoupled))


def test_exporting_no_signals_is_refused_not_written_as_a_flat_trace():
    with pytest.raises(ValueError):
        export_jcamp([], frequency_mhz=400.0, element="H")


def test_export_never_mutates_the_signals():
    signals = _signals()
    before = [(s.shift, s.multiplicity, s.coupling_groups, s.integration) for s in signals]

    export_jcamp(signals, frequency_mhz=400.0, element="H")
    export_sdf(Chem.AddHs(Chem.MolFromSmiles("CCO")), signals, frequency_mhz=400.0, element="H")

    assert before == [(s.shift, s.multiplicity, s.coupling_groups, s.integration) for s in signals]


def test_the_sdf_numbers_atoms_as_the_molfile_does_and_says_predicted():
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    text = export_sdf(mol, _signals(), frequency_mhz=400.0, element="H", solvent="CDCl3", method="X")

    assert text.rstrip().endswith("$$$$")
    assert "> <NMR_1H_PREDICTED_SHIFTS>" in text
    assert "4 1.200 t" in text and "8 3.600 q" in text  # atom indices are 0-based, the file is 1-based
    assert "PREDICTED, not measured" in text and "> <NMR_SOLVENT>" in text
    back = Chem.MolFromMolBlock(text.split("M  END")[0] + "M  END", removeHs=False)
    assert back is not None and back.GetNumAtoms() == mol.GetNumAtoms()
