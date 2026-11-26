**Title:** Gray-code logic synthesis (`TruthTable.q_synth(method="gray")`, `QuantumDictionary`) changes the input register for some truth tables

**Version:** qrisp 0.9.10 (PyPI) and `main` at 81fda69 (2026-11-25). Python 3.13.

**Description**

For some truth tables, Gray-code logic synthesis returns a circuit that computes the correct output bit
but does not restore the input register. This also affects `QuantumDictionary.load`, which uses
`synth_method="gray"` by default. The documented behaviour,
U|x⟩|0⟩ = |x⟩|qd[x]⟩, does not hold.

**Minimal example (Qrisp only)**

```python
from qrisp import QuantumDictionary, QuantumFloat, QuantumBool, multi_measurement

parity = [bin(i).count("1") % 2 for i in range(8)]
for k in range(8):
    key = QuantumFloat(3)
    key[:] = k
    qd = QuantumDictionary(return_type=QuantumBool())
    for i in range(8):
        qd[i] = bool(parity[i])
    print(k, multi_measurement([key, qd[key]]))
```

Output (keys 2, 3, 6 and 7 come back changed):

```
0 {(0, False): 1.0}
1 {(1, True): 1.0}
2 {(6, True): 1.0}
3 {(7, False): 1.0}
4 {(4, True): 1.0}
5 {(5, False): 1.0}
6 {(2, False): 1.0}
7 {(3, True): 1.0}
```

The same truth table with `synth_method="pprm"` is correct. Over XOR, AND, OR and 10 random truth tables
for 2 to 6 inputs, 5 of 65 are wrong with `method="gray"` (XOR with 3 to 6 inputs and one random 4-input table).

**Cause**

`single_qb_traversal` in `alg_primitives/logic_synthesis/gray_synthesis.py` applies one CNOT per step of the
parity walk returned by `hamming_tsp`, taking the first differing bit (`np.argmax`). The walk can contain steps
that change more than one bit: `hamming_tsp` starts the second salesman at a location without walking to it,
and the closing `0` is appended without intermediate steps. For the 3-input XOR the locations on the output qubit
are `[0, 6, 7]`, `hamming_tsp` returns `[0, 4, 6, 7, 6]`, and the closed walk `[0, 4, 6, 7, 6, 0]` ends with
the two-bit jump 6 → 0. That parity is never undone.

**Proposed fix**

Fill in the missing single-bit steps with the existing `hamming_movement` before building `control_seq`:

```python
walk = [tr_seq[0]]
for loc in tr_seq[1:]:
    walk += hamming_movement(walk[-1], loc, bit_amount)
tr_seq = walk
```

With this change all 65 test truth tables and the `QuantumDictionary` example are correct. A correct n-input
XOR then needs 4n − 2 CNOTs instead of 3n.
