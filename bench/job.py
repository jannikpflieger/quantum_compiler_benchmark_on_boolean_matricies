"""Run one compile job and print the result as one JSON line.
Usage: python -m bench.job <compiler[:variant]> <function> <n_inputs> <topology>"""
import json
import math
import resource
import sys
import traceback
import warnings

import numpy as np

warnings.filterwarnings("ignore")

MAX_VERIFY_QUBITS = 24


def compact(r, n):
    """Relabel the physical qubits that are touched (by gates or the layouts) to 0..k-1, so that
    circuits placed on large devices can be simulated."""
    used = set(r["initial"]) | set(r["final"])
    for g in r["gates"]:
        used.update(g[1:3] if g[0] != "1q" else (g[1],))
    cands = r.get("layout_candidates") or [(r["initial"], r["final"])]
    for a, b in cands:
        used.update(a)
        used.update(b)
    order = sorted(used)
    idx = {p: i for i, p in enumerate(order)}
    gates = [(g[0], idx[g[1]], g[2]) if g[0] == "1q" else (g[0], idx[g[1]], idx[g[2]]) for g in r["gates"]]
    cands = [([idx[p] for p in a], [idx[p] for p in b]) for a, b in cands]
    return gates, len(order), cands, idx


def depths(gates, n_phys):
    """(depth, two-qubit depth) with as-soon-as-possible layering."""
    t_all = [0] * n_phys
    t_two = [0] * n_phys
    for g in gates:
        if g[0] == "1q":
            t_all[g[1]] += 1
        else:
            a, b = g[1], g[2]
            d = max(t_all[a], t_all[b]) + 1
            t_all[a] = t_all[b] = d
            d2 = max(t_two[a], t_two[b]) + 1
            t_two[a] = t_two[b] = d2
    return max(t_all, default=0), max(t_two, default=0)


def _zxz_angles(u):
    """Angles (a, b, c) with u = phase * Rz(a) Rx(b) Rz(c), reduced to the essential ones."""
    v = u / np.sqrt(np.linalg.det(u))
    cb, sb = abs(v[0, 0]), abs(v[1, 0])
    beta = 2 * math.atan2(sb, cb)
    s = -2 * np.angle(v[0, 0]) if cb > 1e-9 else 0.0
    d = 2 * np.angle(v[1, 0]) if sb > 1e-9 else 0.0
    alpha, gamma = (s + d) / 2, (s - d) / 2
    a, c = alpha + math.pi / 2, gamma - math.pi / 2  # Ry(b) = Rz(-pi/2) Rx(b) Rz(pi/2)
    two_pi = 2 * math.pi
    if abs(math.remainder(beta, two_pi)) < 1e-7:
        return [s]
    if abs(math.remainder(beta - math.pi, two_pi)) < 1e-7:
        return [a - c]
    return [a, beta, c]


def t_cost(gates):
    """(T gates, other non-Clifford rotations) after writing every single-qubit gate as Rz Rx Rz.
    An angle that is an odd multiple of pi/4 counts as one T gate, a multiple of pi/2 is Clifford,
    any other angle is an arbitrary rotation (it would need approximate Clifford+T synthesis)."""
    t = rot = 0
    for g in gates:
        if g[0] != "1q":
            continue
        for th in _zxz_angles(np.asarray(g[2], dtype=complex)):
            k = th / (math.pi / 4)
            if abs(k - round(k)) < 1e-6:
                t += round(k) % 2
            else:
                rot += 1
    return t, rot


def main():
    comp_id, func, n_in, topo = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    from . import oracles
    from .compilers import get
    from .topologies import edges
    from .verify import check_edges, verify

    m = oracles.n_outputs(func, n_in)
    n = n_in + m
    rec = dict(compiler=comp_id, function=func, n_inputs=n_in, n_outputs=m, n_qubits=n, topology=topo)
    fn, opts = get(comp_id)
    try:
        r = fn(func, n_in, topo, **opts)
    except Exception as exc:  # noqa: BLE001
        rec.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500],
                   trace=traceback.format_exc()[-1500:])
        print("RESULT " + json.dumps(rec))
        return
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    _, e = edges(topo, max(n, r["n_phys"]) if topo not in ("heavy_hex", "sycamore") else n)
    edges_ok = True if topo == "fully" else check_edges(r["gates"], e)
    gates, k, cands, _ = compact(r, n)
    depth, depth2 = depths(gates, k)
    t, rot = t_cost(gates)
    try:
        if k > MAX_VERIFY_QUBITS:
            ver, infid = "skipped", None
        else:
            perm = oracles.permutation(func, n_in)
            for a, b in cands:
                ver, infid = verify(gates, k, a, b, perm, n)
                if ver != "failed":
                    break
    except Exception as exc:  # noqa: BLE001
        ver, infid = f"error: {exc}"[:200], None
    total = sum(r["counts"].values())
    rec.update(status="ok", two_qubit=r["two_qubit"], total=total, counts=r["counts"],
               single_qubit=total - sum(v for kk, v in r["counts"].items()
                                        if kk.lower() in ("cx", "cz", "cnot", "czpowgate", "cnotgate", "swap")),
               depth=depth, depth_2q=depth2, t_count=t, rotations=rot,
               qubits_used=k, helpers=r.get("helpers", max(0, k - n)),
               compile_time=round(r["compile_time"], 4), peak_mem_mb=round(peak, 1),
               edges_ok=edges_ok, verified=ver, infidelity=infid)
    print("RESULT " + json.dumps(rec))


if __name__ == "__main__":
    main()
