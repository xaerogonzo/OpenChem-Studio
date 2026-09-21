"""Identical organic anions in a salt take a multiplying prefix (naming round 7, R4c).

`_multiply_identical_organic_anions` runs before the older, deliberately narrow
`_collapse_identical_salt_ions`. These tests pin the FUNCTION, so its boundaries are checked
where the D-rows (which go through whole salts) cannot reach: what it refuses to multiply is as
important as what it multiplies, because "disulfate" and "diphosphate" are different ions.
"""

import pytest

from openchem.vendor.iupac_namer.assembly import _multiply_identical_organic_anions as multiply


@pytest.mark.parametrize(
    "names,expected",
    [
        (["calcium", "acetate", "acetate"], ["calcium", "diacetate"]),
        (["aluminium", "acetate", "acetate", "acetate"], ["aluminium", "triacetate"]),
        (["magnesium", "benzoate", "benzoate"], ["magnesium", "dibenzoate"]),
        (["calcium", "propanoate", "propanoate"], ["calcium", "dipropanoate"]),
        # a prefixed name takes bis, never "dihydroxyacetate" ((HO)2CH-COO-)
        (["calcium", "hydroxyacetate", "hydroxyacetate"], ["calcium", "bis(hydroxyacetate)"]),
        (["calcium", "2-hydroxypropanoate", "2-hydroxypropanoate"], ["calcium", "bis(2-hydroxypropanoate)"]),
        (["calcium", "benzenesulfonate", "benzenesulfonate"], ["calcium", "bis(benzenesulfonate)"]),
    ],
)
def test_identical_organic_anions_are_multiplied(names, expected):
    assert multiply(names) == expected


@pytest.mark.parametrize(
    "names",
    [
        ["zirconium(4+)", "sulfate", "sulfate"],               # 'disulfate' is a different ion
        ["zirconium(4+)", "phosphate", "phosphate"],
        ["calcium", "carbonate", "carbonate"],
        ["calcium", "hydrogen carbonate", "hydrogen carbonate"],  # an inorganic oxoanion (and a space)
        ["calcium", "hydrogen oxalate", "hydrogen oxalate"],      # a space ALONE: an organic name outside this pass
        ["sodium", "phenylacetylide", "phenylacetylide"],         # OPSIN misreads 'diphenylacetylide'
        ["calcium", "chloride", "chloride"],                      # '-ide' is the older pass's
        ["calcium", "acetate"],                                   # one anion is not multiplied
        ["sodium", "acetate", "benzoate"],                        # two DIFFERENT anions
    ],
)
def test_what_is_not_multiplied(names):
    assert multiply(names) == names


def test_each_group_sits_where_its_first_member_was():
    assert multiply(["calcium", "acetate", "sodium", "acetate"]) == ["calcium", "diacetate", "sodium"]


def test_a_count_with_no_multiplier_falls_back_to_repeating():
    """get_multiplier returns None past its table; a repeated name is the safe fallback."""
    many = ["x"] + ["acetate"] * 500
    assert multiply(many) == many
