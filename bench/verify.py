"""Check that a compiled circuit implements the oracle.

A compiled circuit is given in a small common form:
    gates: list of ("1q", q, 2x2 matrix) | ("cx", control, target) | ("cz", a, b)
on physical qubits 0..P-1, together with
    initial[l] = physical qubit holding logical qubit l at the start
    final[l]   = physical qubit holding logical qubit l at the end.
Unused physical qubits are assumed to start in |0> and must end in |0>.

We compute F = |sum_b <perm(b)| U |b>| / (number of inputs), i.e. the normalised
overlap |Tr(P_oracle^dagger U)| / d restricted to the checked inputs. F = 1 exactly
when every input is mapped to the right basis state with one common phase, i.e.
U = e^{i phi} * P_oracle. Synthesis-based compilers (BQSKit) are approximate, so a
circuit passes when 1 - F < TOL.
"""
import numpy as np

MAX_ELEMENTS = 2 ** 22  # state size * batch size handled at once
MAX_WORK = 1e10         # gates * elements; above this fewer inputs are sampled
TOL = 1e-6


def _apply(state, gate, n_phys):
    kind = gate[0]
    dim = state.shape[0]
    idx = np.arange(dim)
    if kind == "1q":
        _, q, m = gate
        s = state.reshape(2 ** (n_phys - q - 1), 2, 2 ** q, -1)
        s = np.einsum("ab,xbyk->xayk", m, s)
        return s.reshape(dim, -1)
    if kind == "cx":
        _, c, t = gate
        src = np.where((idx >> c) & 1, idx ^ (1 << t), idx)
        return state[src]
    if kind == "cz":
        _, a, b = gate
        sign = np.where(((idx >> a) & 1) & ((idx >> b) & 1), -1.0, 1.0)
        return state * sign[:, None]
    raise ValueError(kind)


def check_edges(gates, edge_list):
    allowed = {frozenset(e) for e in edge_list}
    for g in gates:
        if g[0] in ("cx", "cz") and frozenset((g[1], g[2])) not in allowed:
            return False
    return True


def verify(gates, n_phys, initial, final, perm, n_logical, rng_seed=0):
    """Return (mode, infidelity). mode is 'full', 'sampled', 'failed' or 'skipped'."""
    n_in = 2 ** n_logical
    dim = 2 ** n_phys
    inputs = list(range(n_in))
    mode = "full"
    if dim * n_in > MAX_ELEMENTS:
        k = min(max(1, MAX_ELEMENTS // dim), 64)
        rng = np.random.default_rng(rng_seed)
        extra = rng.choice(n_in, size=min(k, n_in), replace=False).tolist()
        inputs = sorted(set([0, n_in - 1, n_in // 2 - 1] + extra))
        mode = "sampled"
    if len(gates) * dim * len(inputs) > MAX_WORK:
        k = int(MAX_WORK // (len(gates) * dim))
        if k < 4:
            return "skipped", None
        rest = [b for b in inputs if b not in (0, n_in - 1)]
        rest = np.random.default_rng(rng_seed + 1).permutation(rest)[: k - 2].tolist() if rest else []
        keep = [0, n_in - 1] + rest
        inputs = sorted(set(keep))
        mode = "sampled"

    def place(b, layout):
        p = 0
        for l in range(n_logical):
            if (b >> l) & 1:
                p |= 1 << layout[l]
        return p

    state = np.zeros((dim, len(inputs)), dtype=complex)
    for k, b in enumerate(inputs):
        state[place(b, initial), k] = 1.0
    for g in gates:
        state = _apply(state, g, n_phys)
    amps = np.array([state[place(perm[b], final), k] for k, b in enumerate(inputs)])
    infid = float(max(0.0, 1 - abs(amps.mean())))
    return (mode if infid < TOL else "failed"), infid
