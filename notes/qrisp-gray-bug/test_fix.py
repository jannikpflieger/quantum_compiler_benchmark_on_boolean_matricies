"""Check Qrisp's Gray synthesis with and without the proposed fix on many truth tables.

Usage: python test_fix.py [orig|fixed]
"""
import importlib.util
import os
import sys

import numpy as np
from qiskit.quantum_info import Statevector
import qrisp.alg_primitives.logic_synthesis.gray_synthesis as G
from qrisp import QuantumVariable, TruthTable

if sys.argv[1:] == ["fixed"]:
    spec = importlib.util.spec_from_file_location("gs_fixed", os.path.join(os.path.dirname(__file__), "gray_synthesis_fixed.py"))
    fixed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixed)
    G.single_qb_traversal = fixed.single_qb_traversal


def check(bits):
    G.compiled_gates.clear(); G.compiled_pt_gates.clear()
    n = int(np.log2(len(bits)))
    x = QuantumVariable(n); y = QuantumVariable(1)
    TruthTable(["".join(map(str, bits))]).q_synth(x, y, method="gray")
    qc = x.qs.compile().to_qiskit()
    amps = []
    for b in range(2 ** (n + 1)):
        out = Statevector.from_int(b, 2 ** qc.num_qubits).evolve(qc).data
        target = b ^ (bits[b % 2 ** n] << n)
        amps.append(out[target])
    return abs(np.mean(amps)) > 1 - 1e-9, qc.count_ops().get("cx", 0)


rng = np.random.default_rng(1)
cases = {}
for n in range(2, 7):
    cases[f"xor{n}"] = [bin(i).count("1") % 2 for i in range(2 ** n)]
    cases[f"and{n}"] = [int(i == 2 ** n - 1) for i in range(2 ** n)]
    cases[f"or{n}"] = [int(i > 0) for i in range(2 ** n)]
    for k in range(10):
        cases[f"rand{n}_{k}"] = list(rng.integers(0, 2, 2 ** n))
wrong = [name for name, bits in cases.items() if not check(bits)[0]]
print(f"{sys.argv[1:] or ['orig']}: {len(wrong)} of {len(cases)} truth tables wrong")
print("wrong:", wrong[:20])
print("CNOT counts xor2..6:", [check(cases[f'xor{n}'])[1] for n in range(2, 7)])
