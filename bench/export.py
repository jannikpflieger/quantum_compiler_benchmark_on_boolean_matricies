"""Collect results, original thesis numbers and package versions into docs/data/results.json."""
import json
import os
import subprocess
from importlib import metadata

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def versions():
    v = {}
    for pkg in ["qiskit", "pytket", "cirq-core", "bqskit", "pennylane", "qibo", "numpy"]:
        try:
            v[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    try:
        out = subprocess.run([os.path.join(HERE, "venvs", "qrisp", "bin", "python"), "-c",
                              "from importlib import metadata as m; print(m.version('qrisp'))"],
                             capture_output=True, text=True)
        v["qrisp"] = out.stdout.strip()
    except OSError:
        pass
    try:
        out = subprocess.run(["docker", "run", "--rm", "rigetti/quilc", "--version"], capture_output=True, text=True)
        v["quilc"] = out.stdout.strip().split()[0]
    except (OSError, IndexError):
        pass
    return v


def main():
    rows = []
    with open(os.path.join(HERE, "results", "results.jsonl")) as f:
        for line in f:
            d = json.loads(line)
            d.pop("trace", None)
            rows.append(d)
    with open(os.path.join(HERE, "results", "thesis_2022.json")) as f:
        old = json.load(f)
    vpath = os.path.join(HERE, "results", "versions.json")
    if os.path.exists(vpath):
        v = json.load(open(vpath))
    else:
        v = versions()
        json.dump(v, open(vpath, "w"), indent=1)
    os.makedirs(os.path.join(HERE, "docs", "data"), exist_ok=True)
    with open(os.path.join(HERE, "docs", "data", "results.json"), "w") as f:
        json.dump({"versions": v, "results": rows, "thesis_2022": old}, f, separators=(",", ":"))
    print(len(rows), "results exported")


if __name__ == "__main__":
    main()
