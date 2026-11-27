"""Build docs/data/results.json for the site from results/runs/*.

latest   all records of the newest run (compact keys), with the estimated success probability
history  two-qubit counts and verification status of every run, for the "over time" view
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Representative error rates (per gate, depolarising-type). They are order-of-magnitude values
# for one device of each family, not a calibration of a specific chip on a specific day.
NOISE = {
    "ibm": {"name": "IBM Heron (superconducting, heavy-hex)", "e1": 2.5e-4, "e2": 3.0e-3,
            "source": "IBM Quantum documentation, example calibration of ibm_marrakesh "
                      "(CZ error 2.9e-3); single-qubit error assumed 2.5e-4",
            "layouts": ["heavy_hex", "line", "ring", "grid"]},
    "google": {"name": "Google Sycamore (superconducting, grid)", "e1": 1.6e-3, "e2": 6.2e-3,
               "source": "Arute et al., Nature 574, 505 (2019): simultaneous Pauli errors",
               "layouts": ["sycamore"]},
    "ionq": {"name": "IonQ Forte (trapped ion, all-to-all)", "e1": 2.0e-4, "e2": 4.64e-3,
             "source": "Chen et al., arXiv:2308.05071 (2023): median direct RB errors",
             "layouts": ["fully"]},
}
PLATFORM = {t: k for k, v in NOISE.items() for t in v["layouts"]}

KEYS = {"compiler": "c", "function": "f", "n_inputs": "n", "n_qubits": "q", "topology": "t",
        "status": "s", "two_qubit": "two", "single_qubit": "one", "total": "tot", "depth": "d",
        "depth_2q": "d2", "t_count": "T", "rotations": "rot", "qubits_used": "u", "helpers": "h",
        "compile_time": "ct", "peak_mem_mb": "mem", "verified": "v", "edges_ok": "e", "study": "st",
        "timeout": "to"}


def esp(r):
    p = NOISE[PLATFORM[r["topology"]]]
    return (1 - p["e1"]) ** r.get("single_qubit", 0) * (1 - p["e2"]) ** r["two_qubit"]


def load_run(d):
    with open(os.path.join(d, "run.json")) as f:
        meta = json.load(f)
    recs = []
    with open(os.path.join(d, "results.jsonl")) as f:
        for line in f:
            if line.strip():
                recs.append(json.loads(line))
    return meta, recs


def compact(r):
    out = {KEYS[k]: v for k, v in r.items() if k in KEYS}
    if out.get("s") == "error":
        out["err"] = (r.get("error") or "")[:160]
    if r.get("status") == "ok" and r.get("two_qubit") is not None and "single_qubit" in r:
        out["esp"] = round(esp(r), 5)
    if isinstance(out.get("v"), str) and out["v"].startswith("error"):
        out["v"] = "error"
    return out


def main():
    runs = sorted(glob.glob(os.path.join(HERE, "results", "runs", "*")),
                  key=lambda d: (os.path.basename(d)[:10], not os.path.basename(d).endswith("initial")))
    metas, history = [], []
    latest = None
    for d in runs:
        meta, recs = load_run(d)
        metas.append(meta)
        for r in recs:
            if r.get("status") == "ok" and r.get("study", "main") == "main":
                history.append([meta["run_id"], r["compiler"], r["function"], r["n_inputs"], r["topology"],
                                r["two_qubit"], r.get("verified")])
        latest = (meta, recs)
    meta, recs = latest
    with open(os.path.join(HERE, "results", "thesis_2022.json")) as f:
        old = json.load(f)
    data = {"runs": metas, "latest": meta, "results": [compact(r) for r in recs],
            "history": history, "noise": NOISE, "thesis_2022": old}
    os.makedirs(os.path.join(HERE, "docs", "data"), exist_ok=True)
    with open(os.path.join(HERE, "docs", "data", "results.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"{len(recs)} results of run {meta['run_id']} exported, {len(metas)} runs in history")


if __name__ == "__main__":
    main()
