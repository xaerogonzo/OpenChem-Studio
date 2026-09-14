"""One Open Babel charge calculation, in a process of its own.

    python benchmarks/charges/openbabel_child.py <arm> <method> <molblock path>

A child process because one of the arms crashes the interpreter: QEq
dereferences an empty parameter table when `qeq.txt` cannot be opened.

`arm` says where `BABEL_DATADIR` points when the model first reads its file:

    plain                      whatever the environment and the wheel leave
    python_after_import_win    <package>/bin/data, set from Python AFTER import
    python_after_import_posix  the same directory, written /D/... style

Prints one `RESULT {json}` line: the charges and, per atom, what Open Babel
read (element, highest bond order, formal charge, coordinates), so a caller
can check both sides of a comparison saw the same input.
"""

import json
import os
import pathlib
import sys

from openbabel import openbabel as ob

arm, method, mol_path = sys.argv[1], sys.argv[2], sys.argv[3]
data = pathlib.Path(ob.__file__).parent / "bin" / "data"
if arm == "python_after_import_win":
    os.environ["BABEL_DATADIR"] = str(data)
elif arm == "python_after_import_posix":
    os.environ["BABEL_DATADIR"] = "/" + str(data).replace(":\\", "/").replace("\\", "/")

conversion = ob.OBConversion()
conversion.SetInFormat("mol")
mol = ob.OBMol()
conversion.ReadString(mol, pathlib.Path(mol_path).read_text())
model = ob.OBChargeModel.FindType(method)
ok = model.ComputeCharges(mol) if model is not None else False
atoms = []
for index in range(mol.NumAtoms()):
    atom = mol.GetAtom(index + 1)
    atoms.append({
        "z": atom.GetAtomicNum(),
        "hbo": atom.HighestBondOrder(),
        "fc": atom.GetFormalCharge(),
        "xyz": [atom.GetX(), atom.GetY(), atom.GetZ()],
        "q": atom.GetPartialCharge(),
    })
print("RESULT " + json.dumps({
    "arm": arm,
    "method": method,
    "model_found": model is not None,
    "ok": bool(ok),
    "python_sees": os.environ.get("BABEL_DATADIR"),
    "atoms": atoms,
}))
