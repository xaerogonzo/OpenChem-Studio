"""Persisted pKa site records: order, mapping honesty, codec, unchanged pKa text."""

from __future__ import annotations

import json

from rdkit import Chem

from openchem.chem.descriptor_providers import _pka_line, compute_pka_dataset
from openchem.chem.ionisable_sites import ACID, BASE, UNKNOWN, kind_of, read_sites
from openchem.chem.pka_providers import PkaPrediction
from openchem.chem.pka_sites import (
    SITES_KEY,
    PkaSiteRecord,
    load_records,
    ordered_predictions,
    records_from_predictions,
    records_from_provenance,
    with_site_records,
)
from openchem.domain import result_codec
from openchem.chem import pka_providers

ACID_SITE = PkaPrediction(
    atom_index=6, value=4.2, stddev=0.3, protonated_site=(1, 0), deprotonated_site=(0, -1)
)
BASE_SITE = PkaPrediction(
    atom_index=0, value=10.4, stddev=0.0, protonated_site=(3, 1), deprotonated_site=(2, 0)
)
UNMAPPED = PkaPrediction(
    atom_index=None, value=5.1, stddev=0.2, protonated_site=(1, 0), deprotonated_site=(0, -1)
)


def test_none_atom_index_stays_none():
    record = records_from_predictions([UNMAPPED])[0]
    assert record.atom_index is None
    assert load_records([record.to_plain()])[0].atom_index is None


def test_kind_comes_only_from_the_protonated_site():
    assert records_from_predictions([ACID_SITE])[0].kind == ACID
    assert records_from_predictions([BASE_SITE])[0].kind == BASE
    unknown = PkaPrediction(atom_index=1, value=7.0, stddev=0.0)
    assert records_from_predictions([unknown])[0].kind == UNKNOWN
    assert kind_of(None) == UNKNOWN


def test_equal_pka_order_is_stable_by_atom_then_original_position():
    first = PkaPrediction(atom_index=4, value=5.0, protonated_site=(1, 0), deprotonated_site=(0, -1))
    second = PkaPrediction(atom_index=1, value=5.0, protonated_site=(1, 0), deprotonated_site=(0, -1))
    third = PkaPrediction(atom_index=None, value=5.0, protonated_site=(1, 0), deprotonated_site=(0, -1))
    ordered = ordered_predictions([first, second, third])
    assert [p.atom_index for p in ordered] == [None, 1, 4]


def test_read_sites_uses_the_same_order():
    sites = read_sites([BASE_SITE, ACID_SITE], 7.4)
    records = records_from_predictions([BASE_SITE, ACID_SITE])
    assert [s.pka for s in sites] == [r.pka for r in records] == [4.2, 10.4]


def test_pka_text_is_unchanged_when_records_are_attached(monkeypatch):
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: True)
    monkeypatch.setattr(pka_providers, "compute_pka", lambda *_a, **_k: [ACID_SITE])
    mol = Chem.MolFromSmiles("NCCCC(=O)O")
    result = compute_pka_dataset(mol, "m", {}, "x")
    assert result.matched[0] == _pka_line(ACID_SITE, {}, mol)
    records = records_from_provenance(result.provenance)
    assert records[0].atom_index == 6 and records[0].kind == ACID
    assert records[0].protonated_site == (1, 0) and records[0].deprotonated_site == (0, -1)


def test_codec_round_trip_keeps_none_and_state_tuples(monkeypatch):
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: True)
    monkeypatch.setattr(pka_providers, "compute_pka", lambda *_a, **_k: [UNMAPPED, ACID_SITE])
    mol = Chem.MolFromSmiles("NCCCC(=O)O")
    result = compute_pka_dataset(mol, "m", {}, "x")
    restored = result_codec.decode(json.loads(json.dumps(result_codec.encode(result))))
    original = records_from_provenance(result.provenance)
    back = records_from_provenance(restored.provenance)
    assert back == original
    assert back[0].atom_index is None or back[1].atom_index is None
    assert SITES_KEY in restored.provenance.parameters


def test_from_plain_refuses_a_broken_payload():
    assert PkaSiteRecord.from_plain({"pka": "nope"}) is None
    assert load_records([{"pka": 4.2}, "bad"]) == ()


def test_with_site_records_does_not_overwrite_other_parameters():
    records = records_from_predictions([ACID_SITE])
    payload = with_site_records({"pka_values": [4.2]}, records)
    assert payload["pka_values"] == [4.2]
    assert load_records(payload[SITES_KEY]) == records
