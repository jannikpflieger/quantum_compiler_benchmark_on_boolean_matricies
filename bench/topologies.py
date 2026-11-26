"""Qubit connectivity graphs used in the study (undirected edge lists)."""
import math

TOPOLOGIES = ["fully", "line", "ring", "grid"]


def edges(topology: str, n_qubits: int) -> tuple[int, list[tuple[int, int]]]:
    """Return (number of physical qubits, edge list)."""
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
    raise ValueError(topology)
