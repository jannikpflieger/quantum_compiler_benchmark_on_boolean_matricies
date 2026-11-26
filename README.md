# Benchmarking quantum compilers on Boolean functions

A re-run of my bachelor thesis *Benchmarking Quantum Compilers Based on Boolean Functions*
(Goethe University Frankfurt, January 2023) with current compiler versions and more compilers.

**Results and description: https://jannikpflieger.github.io/quantum_compiler_benchmark_on_boolean_matricies/**

## What is measured

A Boolean function f with n inputs is implemented as the reversible oracle
|x, y⟩ → |x, y ⊕ f(x)⟩ on n + 1 qubits, i.e. a permutation matrix. Each compiler turns this
oracle into one- and two-qubit gates for four qubit layouts (fully connected, line, ring,
square grid). The main metric is the number of two-qubit gates.

Functions: multiple AND, OR and XOR (3 to 10 qubits), always 0, always 1, identity, two of three.

Compilers: Qiskit (Boolean expression and matrix input), tket, Cirq, quilc, PennyLane, Qibo,
BQSKit, Qrisp (Gray and PPRM synthesis), and a hand-written textbook construction as reference.

Every compiled circuit is simulated and checked against the oracle (up to a global phase,
using the initial and final qubit placement reported by the compiler). Two-qubit gates are
also checked against the layout.

## Layout of the repository

| Path | Content |
|---|---|
| `bench/oracles.py` | Boolean functions and their permutation matrices |
| `bench/topologies.py` | Qubit layouts |
| `bench/compilers.py` | One function per compiler |
| `bench/verify.py` | Simulation-based correctness check |
| `bench/job.py`, `bench/run.py` | Run one job / the full benchmark (300 s limit per job) |
| `bench/export.py` | Writes `docs/data/results.json` for the website |
| `bench/thesis_data.py` | Extracts the 2022 numbers from the thesis spreadsheets (not included) |
| `results/` | Raw results (`results.jsonl`), 2022 numbers, package versions |
| `docs/` | The GitHub Pages site (plain HTML, CSS and JavaScript) |
| `notes/qrisp-gray-bug/` | Reproduction and proposed fix for the Qrisp Gray-synthesis error |

## Running it

Requires Python 3.13 and Docker (for quilc).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m venv venvs/qrisp && venvs/qrisp/bin/pip install -r requirements-qrisp.txt
docker pull rigetti/quilc
python -m bench.run --timeout 300 --workers 4   # appends to results/results.jsonl, resumes if interrupted
python -m bench.export
```

A single case: `python -m bench.job tket and 4 line` (compiler, function, number of inputs, layout).

The full run took about five hours on a 4-core machine.
