"""Extract the numbers plotted in the 2022/23 thesis from its spreadsheets.

The spreadsheets are not part of this repository. Usage:
    python -m bench.thesis_data <path to Projects/Data/Spreadsheets> results/thesis_2022.json
"""
import json
import sys

import pandas as pd

# (function, topology) -> spreadsheet names for Qiskit, tket, pyQuil (as used by the thesis plot script)
FILES = {
    ("and", "fully"): ("Qiskit_AND", "toffoli_test_and", "pyQuil_AND"),
    ("and", "ring"): ("qiskit_AND_ring", "ring_architecture", "pyquil_AND_ring"),
    ("and", "line"): ("Qiskit_AND_Line", "line_architecture_and", "pyquil_AND_line"),
    ("and", "grid"): ("qiskit_and_square_test", "grid_architecture_and", "pyQuil_AND_square"),
    ("or", "fully"): ("Qiskit_Or_gates", "toffoli_test_or", "pyQuil_OR"),
    ("or", "ring"): ("qiskit_or_ring_2", "ring_architecture_or", "pyquil_OR_ring"),
    ("or", "line"): ("qiskit_or_line_2", "line_architecture_or", "pyquil_OR_line"),
    ("or", "grid"): ("qiskit_or_grid_2", "grid_architecture_or", "pyQuil_OR_square"),
    ("xor", "fully"): ("Qiskit_XOR", "toffoli_test_xor", "pyQuil_XOR"),
    ("xor", "line"): ("qiskit_xor_line_2", "line_architecture_xor", "pyquil_XOR_line"),
    ("xor", "ring"): ("qiskit_xor_ring_2", "ring_architecture_xor", "pyquil_XOR_ring"),
    ("xor", "grid"): ("qiskit_xor_square_2", "grid_architecture_xor", "pyQuil_XOR_square"),
}


def main(src, out):
    rows = []
    for (func, topo), files in FILES.items():
        for comp, name in zip(["qiskit", "tket", "pyquil"], files):
            df = pd.read_excel(f"{src}/{name}.ods", engine="odf")
            col = "cz" if comp == "pyquil" else "cx"
            for _, r in df.iterrows():
                if pd.isna(r["#qubits"]) or pd.isna(r.get(col)):
                    continue
                rec = dict(compiler=comp, function=func, topology=topo, n_qubits=int(r["#qubits"]),
                           two_qubit=int(r[col]))
                if comp == "pyquil" and "xy" in df.columns and not pd.isna(r["xy"]):
                    rec["xy"] = int(r["xy"])
                rows.append(rec)
    with open(out, "w") as f:
        json.dump(rows, f, indent=0)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
