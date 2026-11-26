# Qrisp: Gray-code logic synthesis returns wrong oracles

Found while running the benchmark. Confirmed with qrisp 0.9.10 (latest PyPI release) and with
upstream `main` at commit 81fda69 (2026-11-25), whose `gray_synthesis.py` is identical. Confirmed both with
Qiskit's simulator (`repro.py`) and with Qrisp alone (`repro_qrisp_only.py`). It also affects the documented
`QuantumDictionary.load`, whose default `synth_method` is `"gray"`. A search of Qrisp's issues and pull requests
(gray, truth table, q_synth, gray_synthesis, QuantumDictionary, logic synthesis, hamming, TruthTable) found no
existing report. `ISSUE_DRAFT.md` contains a ready-to-file issue text.

## Symptom

`TruthTable(...).q_synth(x, y, method="gray")` should build the oracle
|x, y⟩ → |x, y ⊕ f(x)⟩. For the 3-bit XOR (and other truth tables) the circuit
changes the input register:

```
$ python repro.py gray
x=000 -> x=000 y=0   expected x=000 y=0   ok
x=001 -> x=001 y=1   expected x=001 y=1   ok
x=010 -> x=110 y=1   expected x=010 y=1   WRONG
x=011 -> x=111 y=0   expected x=011 y=0   WRONG
x=100 -> x=100 y=1   expected x=100 y=1   ok
x=101 -> x=101 y=0   expected x=101 y=0   ok
x=110 -> x=010 y=0   expected x=110 y=0   WRONG
x=111 -> x=011 y=1   expected x=111 y=1   WRONG
method=gray: 4 of 8 inputs wrong
```

`method="pprm"` gives the correct circuit for the same truth table.
With the test set in `test_fix.py` (XOR, AND, OR and 10 random truth tables
for 2 to 6 inputs), 5 of 65 truth tables are wrong: XOR for 3 to 6 inputs and
one random 4-input table.

## Where the fault is

File `qrisp/alg_primitives/logic_synthesis/gray_synthesis.py`, function
`single_qb_traversal`.

Gray synthesis implements the diagonal phase operator by walking through the
parity functions that carry a non-zero phase. One CNOT is added per step, and
each step changes the parity held on the operation qubit by one input bit.
For this to work, consecutive entries of the walk must differ in exactly one bit,
and the walk must end at 0 so the operation qubit is restored.

`single_qb_traversal` takes the walk from `hamming_tsp` and makes sure it ends at 0:

```python
tr_seq = hamming_tsp(locations, bit_amount)
if tr_seq[-1] != 0:
    tr_seq = tr_seq + [0]
```

and then emits one CNOT per step, using only the first differing bit
(`np.argmax` of the difference vector). This breaks in two places:

1. `hamming_tsp` itself can return non-adjacent steps. The second salesman starts
   at a location without walking there from 0.
2. Appending `0` adds a jump from the last location to 0, which can be more than one bit.

Example for the 3-input XOR: the parities that must be visited on the operation
qubit are `[0, 6, 7]`. `hamming_tsp` returns `[0, 4, 6, 7, 6]`, and the closing
step gives `[0, 4, 6, 7, 6, 0]`. The jump 6 → 0 (binary 110 → 000) changes two
bits, but only one CNOT is applied. The operation qubit therefore does not
return to its original value, and the phase circuit is no longer diagonal.
Qrisp also builds the bit-reversed variant and keeps the shallower of the two.
In that variant the operation qubit is an input qubit, so the leftover parity
shows up as a changed input bit, as in the output above.

## Fix

Fill in the missing single-bit steps between consecutive entries with the
existing helper `hamming_movement` (see `fix.patch`):

```python
walk = [tr_seq[0]]
for loc in tr_seq[1:]:
    walk += hamming_movement(walk[-1], loc, bit_amount)
tr_seq = walk
```

For the example the walk becomes `[0, 4, 6, 7, 6, 2, 0]`. With this change all
65 test truth tables are correct (`python test_fix.py fixed`).
The fixed circuits are larger: a correct n-input XOR needs 4n − 2 CNOTs
(10 for 3 inputs) instead of 3n (9). The wrong circuits were cheaper only because
they skipped steps.
A better tour in `hamming_tsp` could recover some of this. That is an
optimisation, not needed for correctness.

## Files

- `repro.py`: minimal reproduction, simulated with Qiskit (`python repro.py gray` / `python repro.py pprm`)
- `repro_qrisp_only.py`: the same check with Qrisp's own simulator, plus `QuantumDictionary` (`--fixed` applies the patch in memory)
- `ISSUE_DRAFT.md`: issue text for the Qrisp repository
- `test_fix.py`: checks 65 truth tables, with the original code or with the fix applied in memory
- `gray_synthesis_fixed.py`: the patched module (qrisp 0.9.10)
- `fix.patch`: the change as a unified diff
