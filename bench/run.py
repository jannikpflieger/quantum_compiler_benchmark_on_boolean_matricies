"""Run the benchmark (or one shard of it).

Each (compiler, function, topology) series is run for growing sizes. Every job runs in its own
process with a time limit; once a job times out or crashes, larger sizes of the same series are
skipped. Results are appended to a JSON-lines file, so an interrupted run can be resumed.

Studies:
  main     all compilers, all functions, all layouts
  levels   optimisation levels of Qiskit and tket (and MQT cost-aware synthesis)
  ancilla  Qiskit multi-controlled X synthesis with 0, 1, 2 or k-2 helper qubits

Usage:
  python -m bench.run --list                         # print the shard names
  python -m bench.run --shard main/tket/line --out results/runs/X/results.jsonl
  python -m bench.run --study main --compilers tket,qiskit --topologies fully
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .oracles import FUNCTIONS
from .topologies import TOPOLOGIES

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _venv(name):
    return os.environ.get(f"PY_{name.upper()}", os.path.join(HERE, "venvs", name, "bin", "python"))


def python_for(comp):
    base = comp.split(":")[0]
    if base.startswith("qrisp"):
        return _venv("qrisp")
    if base == "mqt":
        return _venv("mqt")
    return sys.executable


MAIN = ["qiskit", "qiskit_matrix", "tket", "cirq", "quilc", "pennylane", "qibo", "bqskit",
        "qrisp_gray", "qrisp_pprm", "mqt", "reference"]
REFERENCE_FUNCS = {"and", "or", "xor", "always0", "always1", "identity", "two_of_three"}
LEVELS = ["qiskit:o0", "qiskit:o1", "qiskit:o2", "tket:o0", "tket:o1", "mqt:cost"]
LEVEL_FUNCS = ["and", "or", "xor", "majority", "adder"]
ANCILLA = ["qiskit_mcx:" + m for m in
           ["noaux_v24", "1_clean_b95", "1_clean_kg24", "2_clean_kg24", "n_clean_m15", "1_dirty_kg24", "n_dirty_i15"]]
STUDY_TOPOS = ["fully", "heavy_hex"]
TIMEOUT_FACTOR = {"bqskit": 2}  # numerical synthesis gets twice the time limit


def series(study, compilers=None, topologies=None):
    if study == "main":
        comps, topos, funcs = MAIN, TOPOLOGIES, list(FUNCTIONS)
    elif study == "levels":
        comps, topos, funcs = LEVELS, STUDY_TOPOS, LEVEL_FUNCS
    elif study == "ancilla":
        comps, topos, funcs = ANCILLA, STUDY_TOPOS, ["and", "or"]
    else:
        raise ValueError(study)
    for comp in comps:
        if compilers and comp not in compilers and comp.split(":")[0] not in compilers:
            continue
        for topo in topos:
            if topologies and topo not in topologies:
                continue
            for func in funcs:
                if comp == "reference" and func not in REFERENCE_FUNCS:
                    continue
                sizes = FUNCTIONS[func]["sizes"]
                if comp.startswith("qiskit_mcx"):
                    sizes = [s for s in sizes if s >= 3]
                yield study, comp, func, topo, sizes


def shards():
    out = []
    for comp in MAIN:
        for topo in TOPOLOGIES:
            out.append(f"main/{comp}/{topo}")
    for comp in LEVELS + ANCILLA:
        out.append(f"{'levels' if comp in LEVELS else 'ancilla'}/{comp}/all")
    return out


def run_job(comp, func, n_in, topo, timeout):
    py = python_for(comp)
    env = dict(os.environ, PYTHONWARNINGS="ignore")
    env.setdefault("BQSKIT_WORKERS", "2")
    t0 = time.time()
    base = dict(compiler=comp, function=func, n_inputs=n_in, topology=topo)
    try:
        r = subprocess.run([py, "-m", "bench.job", comp, func, str(n_in), topo], cwd=HERE,
                           capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        if comp.startswith("quilc"):
            subprocess.run("docker ps -q --filter name=quilc- | xargs -r docker kill", shell=True,
                           capture_output=True)
        return dict(base, status="timeout", timeout=timeout)
    for line in reversed(r.stdout.splitlines()):
        if line.startswith("RESULT "):
            rec = json.loads(line[7:])
            rec["wall_time"] = round(time.time() - t0, 2)
            return rec
    return dict(base, status="crash", error=(r.stderr or r.stdout)[-800:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "results", "local.jsonl"))
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--study", default="main")
    ap.add_argument("--compilers", default="")
    ap.add_argument("--topologies", default="")
    ap.add_argument("--shard", default="")
    ap.add_argument("--max-qubits", type=int, default=99)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        print(json.dumps(shards()))
        return
    study, comps, topos = args.study, set(filter(None, args.compilers.split(","))), set(
        filter(None, args.topologies.split(",")))
    if args.shard:
        study, comp, topo = args.shard.split("/")
        comps = {comp}
        topos = set() if topo == "all" else {topo}

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    done = {}
    if os.path.exists(args.out):
        with open(args.out) as f:
            for line in f:
                d = json.loads(line)
                done[(d["compiler"], d["function"], d["n_inputs"], d["topology"])] = d["status"]
    out = open(args.out, "a")

    def run_series(s):
        st, comp, func, topo, sizes = s
        timeout = args.timeout * TIMEOUT_FACTOR.get(comp.split(":")[0], 1)
        for n_in in sizes:
            from .oracles import n_outputs
            if n_in + n_outputs(func, n_in) > args.max_qubits:
                break
            key = (comp, func, n_in, topo)
            if key in done:
                if done[key] in ("timeout", "crash"):
                    break
                continue
            rec = run_job(comp, func, n_in, topo, timeout)
            rec["study"] = st
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(f"{comp:22s} {func:12s} {topo:9s} n={n_in:2d} {rec['status']:8s} "
                  f"2q={rec.get('two_qubit')} ver={rec.get('verified')}", flush=True)
            if rec["status"] in ("timeout", "crash"):
                break

    todo = list(series(study, comps or None, topos or None))
    # longest series first so the pool stays busy
    todo.sort(key=lambda s: -len(s[4]))
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(run_series, todo))


if __name__ == "__main__":
    main()
