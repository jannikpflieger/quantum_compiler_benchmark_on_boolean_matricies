"""Qubit connectivity graphs used in the study (undirected edge lists).

fully, line, ring, grid: generic graphs sized to the circuit (as in the thesis).
heavy_hex: IBM heavy-hex lattice of distance 5 (57 qubits), the layout family of current IBM devices.
sycamore: the 54-qubit Google Sycamore grid.
An all-to-all trapped-ion device (IonQ) has the same connectivity as "fully"; it differs only in the
noise model used in the export, so it is not compiled separately.
"""
import math

TOPOLOGIES = ["fully", "line", "ring", "grid", "heavy_hex", "sycamore"]
FIXED = {"heavy_hex", "sycamore"}

_SYCAMORE = """\
-----AB---
----ABCD--
---ABCDEF-
--ABCDEFGH
-ABCDEFGHI
ABCDEFGHI-
-CDEFGHI--
--EFGHI---
---GHI----
----I-----
"""


def _sycamore():
    cells = [(r, c) for r, row in enumerate(_SYCAMORE.splitlines()) for c, ch in enumerate(row) if ch != "-"]
    index = {rc: i for i, rc in enumerate(cells)}
    e = []
    for (r, c), i in index.items():
        for rc in ((r + 1, c), (r, c + 1)):
            if rc in index:
                e.append((i, index[rc]))
    return len(cells), e


def _heavy_hex(d=5):
    from rustworkx.generators import heavy_hex_graph

    g = heavy_hex_graph(d)
    return g.num_nodes(), [tuple(x) for x in g.edge_list()]


def edges(topology, n_qubits):
    """Return (number of physical qubits, edge list) for a circuit that needs n_qubits."""
    n = n_qubits
    if topology == "fully":
        return n, [(i, j) for i in range(n) for j in range(i + 1, n)]
    if topology == "line":
        return n, [(i, i + 1) for i in range(n - 1)]
    if topology == "ring":
        e = [(i, i + 1) for i in range(n - 1)]
        if n > 2:
            e.append((n - 1, 0))
        return n, e
    if topology == "grid":
        # smallest k x k square grid with at least n qubits (as in the thesis)
        k = max(2, math.ceil(math.sqrt(n)))
        e = []
        for r in range(k):
            for c in range(k):
                q = r * k + c
                if c + 1 < k:
                    e.append((q, q + 1))
                if r + 1 < k:
                    e.append((q, q + k))
        return k * k, e
    if topology == "heavy_hex":
        p, e = _heavy_hex(5)
    elif topology == "sycamore":
        p, e = _sycamore()
    else:
        raise ValueError(topology)
    if n > p:
        raise ValueError(f"{topology} has only {p} qubits")
    return p, e
