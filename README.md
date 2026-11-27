# Benchmarking quantum compilers on Boolean functions

A re-run and extension of my bachelor thesis *Benchmarking Quantum Compilers Based on Boolean
Functions* (Goethe University Frankfurt, January 2023) with current compiler versions, more
compilers, more functions and real device layouts. The benchmark is rerun every month, so the
site also shows how the compilers change over time.

**Results and description: https://jannikpflieger.github.io/quantum_compiler_benchmark_on_boolean_matricies/**

## What is measured

A Boolean function f with n inputs and m outputs is implemented as the reversible oracle
|x, y⟩ → |x, y ⊕ f(x)⟩ on n + m qubits. Each compiler turns this oracle into one- and two-qubit
gates for a given qubit layout. Compilers that accept a Boolean function get the function
(expression or truth table); the others get the permutation matrix.

- **Functions:** multiple AND, OR and XOR (up to 16 qubits), majority, comparator (a < b),
  adder (a + b), random truth tables, and the small functions of the thesis (always 0,
  always 1, identity, two of three).
- **Compilers:** Qiskit (Boolean expression and matrix input), tket, quilc, Qrisp (Gray and
  PPRM synthesis), MQT (SyReC synthesis with QMAP mapping), Cirq, PennyLane, Qibo, BQSKit,
  and a textbook construction as reference.
- **Layouts:** fully connected, line, ring, square grid, IBM heavy-hex (57 qubits) and Google
  Sycamore (54 qubits). IonQ's all-to-all connectivity is the fully connected layout.
- **Metrics:** two-qubit gates, single-qubit gates, depth, two-qubit depth, T-count and
  arbitrary rotations, compile time, peak memory, and an estimated success probability from
  published gate error rates (IBM Heron, Google Sycamore, IonQ Forte).
- **Studies:** optimisation levels (Qiskit 0 to 3, tket 0 to 2, MQT line-aware vs.
  cost-aware synthesis) and helper qubits (Qiskit's multi-controlled X with and without
  ancillas).

Every compiled circuit with up to 24 used qubits is simulated and checked against the oracle,
using the initial and final qubit placement reported by the compiler. Helper qubits must start
and end in |0⟩. Two-qubit gates are checked against the layout.

## Layout of the repository

| Path | Content |
|---|---|
| `bench/oracles.py` | Boolean functions, truth tables and permutation matrices |
| `bench/topologies.py` | Qubit layouts |
| `bench/compilers.py` | One function per compiler |
| `bench/verify.py` | Simulation-based correctness check |
| `bench/job.py` | One compile job: compile, count, verify; prints one JSON line |
| `bench/run.py` | Runs a study or one shard with time and memory limits |
| `bench/collect.py` | Merges the shard outputs of a run into `results/runs/<date>/` |
| `bench/export.py` | Writes `docs/data/results.json` for the website (incl. the noise model) |
| `results/runs/` | One folder per run: raw results and exact package versions |
| `results/thesis_2022.json` | Numbers from the 2022 thesis |
| `docs/` | The GitHub Pages site (plain HTML, CSS and JavaScript) |
| `.github/workflows/benchmark.yml` | Monthly run as 85 parallel jobs on GitHub Actions |

## Running it

Requires Python 3.13 and Docker (for quilc). Qrisp and MQT need their own environments because
their dependencies conflict with the other packages.

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m venv venvs/qrisp && venvs/qrisp/bin/pip install -r requirements-qrisp.txt
python -m venv venvs/mqt && venvs/mqt/bin/pip install -r requirements-mqt.txt
docker pull rigetti/quilc:1.26.0

python -m bench.job tket and 4 line                  # one case: compiler, function, inputs, layout
python -m bench.run --list                           # names of all shards
python -m bench.run --shard main/tket/heavy_hex --out out/tket.jsonl
python -m bench.collect out 2026-12-01 pinned        # merge into results/runs/2026-12-01/
python -m bench.export                               # rebuild the site data
```

`requirements*.txt` pin the versions of the published runs; `requirements-latest/` lists the
same packages without versions, which the monthly run uses.

On GitHub the workflow `Benchmark` runs on the 1st of every month with the newest releases,
commits the results and redeploys the site. It can also be started by hand (pinned or latest
versions). The time limit is 600 s per compile job (1200 s for BQSKit) and the memory limit
3.5 GB per job.
