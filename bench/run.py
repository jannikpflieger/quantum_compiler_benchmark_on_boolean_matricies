"""Run the full benchmark.

Each (compiler, function, topology) series is run for growing qubit numbers.
Every job runs in its own process with a time limit; once a job times out,
larger sizes of the same series are skipped. Results are appended to a JSON-lines file,
so an interrupted run can be resumed.

Usage: python -m bench.run [--out results/results.jsonl] [--timeout 300] [--workers 4]
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

# Python interpreter per compiler (Qrisp needs an older Qiskit, so it has its own environment)
PYTHON = {"qrisp_gray": os.path.join(HERE, "venvs", "qrisp", "bin", "python"),
          "qrisp_pprm": os.path.join(HERE, "venvs", "qrisp", "bin", "python")}

COMPILERS = ["qiskit", "qiskit_matrix", "tket", "cirq", "quilc", "pennylane", "qibo",
             "bqskit", "qrisp_gray", "qrisp_pprm", "reference"]
FULLY_ONLY = {"qrisp_gray", "qrisp_pprm"}
MULTI = ["and", "or", "xor"]
SIZES = list(range(2, 10))  # number of inputs; qubits = inputs + 1 (3 .. 10)


def series():
    for comp in COMPILERS:
        for topo in TOPOLOGIES:
            if comp in FULLY_ONLY and topo != "fully":
                continue
            for func in MULTI:
                yield comp, func, topo, SIZES
            for func, spec in FUNCTIONS.items():
                if spec[3] is not None:
                    yield comp, func, topo, [spec[3]]


def run_job(comp, func, n_in, topo, timeout):
    py = PYTHON.get(comp, sys.executable)
    env = dict(os.environ, BQSKIT_WORKERS="1", PYTHONWARNINGS="ignore")
    t0 = time.time()
    try:
        r = subprocess.run([py, "-m", "bench.job", comp, func, str(n_in), topo], cwd=HERE,
                           capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        if comp == "quilc":
            subprocess.run("docker ps -q --filter name=quilc- | xargs -r docker kill", shell=True,
                           capture_output=True)
        return dict(compiler=comp, function=func, n_inputs=n_in, n_qubits=n_in + 1, topology=topo,
                    status="timeout", timeout=timeout)
    for line in reversed(r.stdout.splitlines()):
        if line.startswith("RESULT "):
            rec = json.loads(line[7:])
            rec["wall_time"] = round(time.time() - t0, 2)
            return rec
    return dict(compiler=comp, function=func, n_inputs=n_in, n_qubits=n_in + 1, topology=topo,
                status="crash", error=(r.stderr or r.stdout)[-800:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "results", "results.jsonl"))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--compilers", default=",".join(COMPILERS))
    args = ap.parse_args()
    wanted = set(args.compilers.split(","))

    done = {}
    if os.path.exists(args.out):
        with open(args.out) as f:
            for line in f:
                d = json.loads(line)
                done[(d["compiler"], d["function"], d["n_inputs"], d["topology"])] = d["status"]

    out = open(args.out, "a")

    def run_series(s):
        comp, func, topo, sizes = s
        for n_in in sizes:
            key = (comp, func, n_in, topo)
            if key in done:
                if done[key] in ("timeout", "crash"):
                    break
                continue
            rec = run_job(comp, func, n_in, topo, args.timeout)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(f"{comp:14s} {func:12s} {topo:6s} n={n_in + 1:2d} {rec['status']:8s} "
                  f"2q={rec.get('two_qubit')} ver={rec.get('verified')}", flush=True)
            if rec["status"] in ("timeout", "crash"):
                break

    todo = [s for s in series() if s[0] in wanted]
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(run_series, todo))


if __name__ == "__main__":
    main()
