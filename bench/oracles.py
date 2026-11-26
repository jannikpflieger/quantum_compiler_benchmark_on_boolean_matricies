"""Boolean functions used in the study and their reversible (bit-flip) oracles.

Convention: a function with n inputs is mapped to n + 1 qubits.
Qubits 0..n-1 hold the inputs x, qubit n holds the output y.
The oracle maps |x, y> -> |x, y XOR f(x)>.
Basis states are indexed little-endian: index = sum(x_i * 2**i) + y * 2**n.
"""
from itertools import product

import numpy as np

# name -> (description, function on a tuple of input bits, expression builder, fixed input count or None)
FUNCTIONS = {
    "and": ("Multiple AND", lambda x: int(all(x)), lambda v: " & ".join(v), None),
    "or": ("Multiple OR", lambda x: int(any(x)), lambda v: " | ".join(v), None),
    "xor": ("Multiple XOR", lambda x: sum(x) % 2, lambda v: " ^ ".join(v), None),
    "always0": ("Always 0 (A AND NOT A)", lambda x: 0, lambda v: f"{v[0]} & ~{v[0]}", 1),
    "always1": ("Always 1 (A OR NOT A)", lambda x: 1, lambda v: f"{v[0]} | ~{v[0]}", 1),
    "identity": ("Identity (A)", lambda x: x[0], lambda v: v[0], 1),
    "two_of_three": (
        "Two of three (majority)",
        lambda x: int(sum(x) >= 2),
        lambda v: f"({v[0]} & {v[1]}) | ({v[1]} & {v[2]}) | ({v[0]} & {v[2]})",
        3,
    ),
}

VARNAMES = "abcdefghijklmnopqrstuvwxyz"


def truth_table(func: str, n_inputs: int) -> list[int]:
    """f(x) for all x, x indexed little-endian."""
    f = FUNCTIONS[func][1]
    out = []
    for idx in range(2 ** n_inputs):
        bits = tuple((idx >> i) & 1 for i in range(n_inputs))
        out.append(f(bits))
    return out


def expression(func: str, n_inputs: int) -> str:
    return FUNCTIONS[func][2](list(VARNAMES[:n_inputs]))


def permutation(func: str, n_inputs: int) -> list[int]:
    """perm[i] = image of basis state i under the oracle (n_inputs + 1 qubits)."""
    tt = truth_table(func, n_inputs)
    n = n_inputs
    return [i ^ (tt[i & ((1 << n) - 1)] << n) for i in range(2 ** (n + 1))]


def matrix(func: str, n_inputs: int) -> np.ndarray:
    """Permutation matrix in little-endian (Qiskit) ordering."""
    perm = permutation(func, n_inputs)
    dim = len(perm)
    m = np.zeros((dim, dim))
    for i, j in enumerate(perm):
        m[j, i] = 1.0
    return m


def reverse_bits(i: int, n: int) -> int:
    return int(format(i, f"0{n}b")[::-1], 2)


def matrix_big_endian(func: str, n_inputs: int) -> np.ndarray:
    """Same operator in big-endian ordering (Cirq, Quil DEFGATE, BQSKit)."""
    n = n_inputs + 1
    perm = permutation(func, n_inputs)
    dim = len(perm)
    m = np.zeros((dim, dim))
    for i, j in enumerate(perm):
        m[reverse_bits(j, n), reverse_bits(i, n)] = 1.0
    return m


def bit_pairs(func: str, n_inputs: int):
    """(input bits, output bits) for every basis state that changes, qubit order 0..n."""
    n = n_inputs + 1
    perm = permutation(func, n_inputs)
    pairs = []
    for i, j in enumerate(perm):
        if i != j:
            pairs.append(([bool((i >> k) & 1) for k in range(n)], [bool((j >> k) & 1) for k in range(n)]))
    return pairs
