"""Reproduction using only Qrisp (its own simulator), no Qiskit.

For every 3-bit input x, prepare |x>|0>, apply the Gray-synthesised XOR oracle,
and measure both registers with Qrisp's simulator. A correct oracle returns
x unchanged and y = parity(x). Also tests the documented QuantumDictionary.load,
which uses Gray synthesis by default.
"""
import sys

from qrisp import QuantumDictionary, QuantumVariable, multi_measurement, x as xgate
from qrisp.alg_primitives.logic_synthesis import TruthTable

method = sys.argv[1] if len(sys.argv) > 1 else "gray"
if "--fixed" in sys.argv:  # apply the proposed fix in memory
    import importlib.util, os
    import qrisp.alg_primitives.logic_synthesis.gray_synthesis as G
    spec = importlib.util.spec_from_file_location("gs_fixed", os.path.join(os.path.dirname(os.path.abspath(__file__)), "gray_synthesis_fixed.py"))
    fixed = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixed)
    G.single_qb_traversal = fixed.single_qb_traversal
n = 3
parity = [bin(i).count("1") % 2 for i in range(2 ** n)]
tt = TruthTable(["".join(map(str, parity))])


def run_truth_table(xin):
    xv = QuantumVariable(n)
    y = QuantumVariable(1)
    for k in range(n):  # qubit k of xv holds bit k of xin (Qrisp's little-endian convention)
        if (xin >> k) & 1:
            xgate(xv[k])
    tt.q_synth(xv, y, method=method)
    return multi_measurement([xv, y])


def run_dictionary(xin):
    # QuantumDictionary maps a key to a value; here key = 3-bit integer, value = parity bit
    from qrisp import QuantumFloat, QuantumBool
    key = QuantumFloat(n)
    key[:] = xin
    qd = QuantumDictionary(return_type=QuantumBool())
    for k in range(2 ** n):
        qd[k] = bool(parity[k])
    val = qd[key] if method == "gray" else None
    return multi_measurement([key, val])


print("TruthTable.q_synth, method =", method)
bad = 0
for xin in range(2 ** n):
    res = run_truth_table(xin)
    print(f"  x={xin:03b} (qubit order 0,1,2: {format(xin, '03b')[::-1]}): measured {{(x, y): p}} = {res}")
    (xo, yo), p = max(res.items(), key=lambda kv: kv[1])
    xo_int = int(xo[::-1], 2)  # Qrisp prints qubit 0 first
    if not (len(res) == 1 and xo_int == xin and int(yo, 2) == parity[xin]):
        bad += 1
print(f"  -> {bad} of {2 ** n} inputs wrong")

if method == "gray":
    print("QuantumDictionary (default synth_method='gray')")
    bad = 0
    for xin in range(2 ** n):
        res = run_dictionary(xin)
        print(f"  key={xin}: {{(key, value): probability}} = {res}")
        if res != {(xin, bool(parity[xin])): 1.0}:
            bad += 1
    print(f"  -> {bad} of {2 ** n} keys wrong")
