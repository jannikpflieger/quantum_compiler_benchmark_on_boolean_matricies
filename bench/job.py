"""Run one compile job and print the result as one JSON line.
Usage: python -m bench.job <compiler> <function> <n_inputs> <topology>"""
import json
import sys
import traceback
import warnings

warnings.filterwarnings("ignore")


def main():
    comp, func, n_in, topo = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    from . import oracles
    from .compilers import COMPILERS
    from .topologies import edges
    from .verify import check_edges, verify

    rec = dict(compiler=comp, function=func, n_inputs=n_in, n_qubits=n_in + 1, topology=topo)
    try:
        r = COMPILERS[comp](func, n_in, topo)
    except Exception as exc:  # noqa: BLE001
        rec.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500],
                   trace=traceback.format_exc()[-1500:])
        print("RESULT " + json.dumps(rec))
        return
    n = n_in + 1
    _, e = edges(topo, n)
    edges_ok = True if topo == "fully" else check_edges(r["gates"], e)
    try:
        perm = oracles.permutation(func, n_in)
        cands = r.get("layout_candidates") or [(r["initial"], r["final"])]
        for a, b in cands:
            ver, infid = verify(r["gates"], r["n_phys"], a, b, perm, n)
            if ver != "failed":
                break
    except Exception as exc:  # noqa: BLE001
        ver, infid = f"error: {exc}"[:200], None
    rec.update(status="ok", two_qubit=r["two_qubit"], total=sum(r["counts"].values()),
               counts=r["counts"], compile_time=round(r["compile_time"], 4),
               single_qubit=sum(r["counts"].values()) - r["two_qubit"],
               edges_ok=edges_ok, verified=ver, infidelity=infid)
    print("RESULT " + json.dumps(rec))


if __name__ == "__main__":
    main()
