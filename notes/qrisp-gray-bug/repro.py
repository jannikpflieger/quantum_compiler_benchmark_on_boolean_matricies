"""Minimal reproduction: Qrisp's Gray-code logic synthesis returns a wrong XOR oracle.

Expected oracle: |x, y> -> |x, y XOR f(x)> with f(x) = x0 XOR x1 XOR x2,
and the input register x left unchanged.
Tested with qrisp 0.9.10, Python 3.13. Qiskit (a qrisp dependency) is only used to simulate.
"""
import sys

from qiskit.quantum_info import Statevector
from qrisp import QuantumVariable, TruthTable

method = sys.argv[1] if len(sys.argv) > 1 else "gray"
n = 3
tt = TruthTable(["01101001"])  # 3-bit parity; entry i is f(i)

x = QuantumVariable(n)
y = QuantumVariable(1)
tt.q_synth(x, y, method=method)
qc = x.qs.compile().to_qiskit()  # qubits 0..n-1 = x (x0 least significant), qubit n = y

bad = 0
for xin in range(2 ** n):
    out = Statevector.from_int(xin, 2 ** qc.num_qubits).evolve(qc)
    idx = max(range(2 ** qc.num_qubits), key=lambda k: abs(out.data[k]))
    x_out, y_out = idx % 2 ** n, idx >> n
    exp_y = bin(xin).count("1") % 2
    ok = x_out == xin and y_out == exp_y and abs(abs(out.data[idx]) - 1) < 1e-9
    bad += not ok
    print(f"x={xin:03b} -> x={x_out:03b} y={y_out}   expected x={xin:03b} y={exp_y}   {'ok' if ok else 'WRONG'}")
print(f"method={method}: {bad} of {2 ** n} inputs wrong")
