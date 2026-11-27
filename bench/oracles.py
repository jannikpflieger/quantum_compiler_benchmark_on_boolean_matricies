"""Boolean functions used in the study and their reversible (bit-flip) oracles.

Convention: a function with n inputs and m outputs is mapped to n + m qubits.
Qubits 0..n-1 hold the inputs x, qubits n..n+m-1 hold the outputs y.
The oracle maps |x, y> -> |x, y XOR f(x)>.
Basis states are indexed little-endian: index = sum(x_i * 2**i) + sum(y_j * 2**(n + j)).

Every function also has a small Boolean expression tree per output bit. It is used by
the compilers that take an expression (Qiskit BitFlipOracleGate, MQT SyReC). Node forms:
    ("var", i) | ("const", 0 or 1) | ("not", e) | ("and", a, b) | ("or", a, b) | ("xor", a, b)
"""
from functools import reduce
from itertools import combinations

import numpy as np

VARNAMES = "abcdefghijklmnopqrstuvwxyz"


# ------------------------------------------------------------ expression helpers
def V(i):
    return ("var", i)


def _chain(op, items):
    return reduce(lambda a, b: (op, a, b), items)


def _balanced(op, items):
    """Balanced tree, so that long sums of products do not exceed parser nesting limits."""
    if len(items) == 1:
        return items[0]
    h = len(items) // 2
    return (op, _balanced(op, items[:h]), _balanced(op, items[h:]))


def _sop(minterms, n):
    """Sum of products over the given input indices (little-endian bits)."""
    if not minterms:
        return ("and", V(0), ("not", V(0)))
    terms = []
    for m in minterms:
        lits = [V(i) if (m >> i) & 1 else ("not", V(i)) for i in range(n)]
        terms.append(_chain("and", lits))
    return _balanced("or", terms)


def evaluate(e, bits):
    k = e[0]
    if k == "var":
        return bits[e[1]]
    if k == "const":
        return e[1]
    if k == "not":
        return 1 - evaluate(e[1], bits)
    a, b = evaluate(e[1], bits), evaluate(e[2], bits)
    return {"and": a & b, "or": a | b, "xor": a ^ b}[k]


def render(e, names, style="qiskit"):
    """Expression as text. style 'qiskit' or 'syrec' (SyReC needs brackets around every binary op)."""
    k = e[0]
    if k == "var":
        return names[e[1]]
    if k == "const":
        return str(e[1])
    if k == "not":
        return "~" + render(e[1], names, style)
    sym = {"and": "&", "or": "|", "xor": "^"}[k]
    return f"({render(e[1], names, style)} {sym} {render(e[2], names, style)})"


def variables(e, acc=None):
    acc = set() if acc is None else acc
    if e[0] == "var":
        acc.add(e[1])
    elif e[0] != "const":
        for c in e[1:]:
            variables(c, acc)
    return acc


# ------------------------------------------------------------ function definitions
def _random_table(n, seed=None):
    rng = np.random.default_rng(1000 + n if seed is None else seed)
    return rng.integers(0, 2, 2 ** n).tolist()


def _adder_exprs(n):
    """n = 2k inputs: a = x[0..k-1], b = x[k..2k-1] (little-endian); k+1 output bits of a + b."""
    k = n // 2
    outs, carry = [], None
    for i in range(k):
        a, b = V(i), V(k + i)
        s = ("xor", a, b)
        outs.append(s if carry is None else ("xor", s, carry))
        g = ("and", a, b)
        carry = g if carry is None else ("or", g, ("and", carry, s))
    outs.append(carry)
    return outs


def _less_than(n):
    """n = 2k inputs, output a < b with a = x[0..k-1], b = x[k..2k-1]."""
    k = n // 2
    e = None
    for i in range(k):  # from the least significant bit upwards
        a, b = V(i), V(k + i)
        here = ("and", ("not", a), b)
        if e is None:
            e = here
        else:
            e = ("or", here, ("and", ("not", ("xor", a, b)), e))
    return e


def _majority(n):
    need = n // 2 + 1
    terms = [_chain("and", [V(i) for i in c]) for c in combinations(range(n), need)]
    return _balanced("or", terms)


# name -> spec
#   desc, sizes (input counts), outputs(n), table(n) -> list of output tuples, exprs(n) -> list of trees
FUNCTIONS = {}


def _add(name, desc, sizes, exprs, outputs=lambda n: 1, table=None, group="new"):
    FUNCTIONS[name] = dict(desc=desc, sizes=list(sizes), outputs=outputs, exprs=exprs, table=table,
                           group=group)


_add("and", "Multiple AND", range(2, 16), lambda n: [_chain("and", [V(i) for i in range(n)])], group="multi")
_add("or", "Multiple OR", range(2, 16), lambda n: [_chain("or", [V(i) for i in range(n)])], group="multi")
_add("xor", "Multiple XOR", range(2, 16), lambda n: [_chain("xor", [V(i) for i in range(n)])], group="multi")
_add("always0", "Always 0 (A AND NOT A)", [1], lambda n: [("and", V(0), ("not", V(0)))], group="small")
_add("always1", "Always 1 (A OR NOT A)", [1], lambda n: [("or", V(0), ("not", V(0)))], group="small")
_add("identity", "Identity (A)", [1], lambda n: [V(0)], group="small")
_add("two_of_three", "Two of three", [3],
     lambda n: [("or", ("or", ("and", V(0), V(1)), ("and", V(1), V(2))), ("and", V(0), V(2)))], group="small")
_add("majority", "Majority of n inputs", [3, 5, 7, 9, 11], lambda n: [_majority(n)])
_add("less_than", "Comparator a < b (two k-bit numbers)", [2, 4, 6, 8, 10], lambda n: [_less_than(n)])
_add("adder", "Adder a + b (k+1 output bits)", [2, 4, 6, 8], _adder_exprs, outputs=lambda n: n // 2 + 1)
_add("random", "Random truth table (fixed seed)", range(2, 9),
     lambda n: [_sop([i for i, v in enumerate(_random_table(n)) if v], n)],
     table=lambda n: [(v,) for v in _random_table(n)])


def n_outputs(func, n_in):
    return FUNCTIONS[func]["outputs"](n_in)


def expressions(func, n_in):
    return FUNCTIONS[func]["exprs"](n_in)


def output_table(func, n_in):
    """List over x (little-endian index) of output bit tuples (y_0, ..., y_{m-1})."""
    spec = FUNCTIONS[func]
    if spec["table"] is not None:
        return spec["table"](n_in)
    ex = expressions(func, n_in)
    rows = []
    for idx in range(2 ** n_in):
        bits = [(idx >> i) & 1 for i in range(n_in)]
        rows.append(tuple(evaluate(e, bits) for e in ex))
    return rows


def truth_table(func, n_in, out=0):
    return [r[out] for r in output_table(func, n_in)]


def expression(func, n_in, out=0):
    return render(expressions(func, n_in)[out], VARNAMES)


def permutation(func, n_in):
    """perm[i] = image of basis state i under the oracle (n_in + m qubits)."""
    rows = output_table(func, n_in)
    m = len(rows[0])
    mask = (1 << n_in) - 1
    ints = [sum(b << j for j, b in enumerate(r)) for r in rows]
    return [i ^ (ints[i & mask] << n_in) for i in range(2 ** (n_in + m))]


def matrix(func, n_in):
    """Permutation matrix in little-endian (Qiskit) ordering."""
    perm = permutation(func, n_in)
    m = np.zeros((len(perm), len(perm)))
    m[perm, np.arange(len(perm))] = 1.0
    return m


def reverse_bits(i, n):
    return int(format(i, f"0{n}b")[::-1], 2)


def matrix_big_endian(func, n_in):
    """Same operator in big-endian ordering (Cirq, Quil DEFGATE, BQSKit, Qibo, PennyLane)."""
    perm = permutation(func, n_in)
    n = len(perm).bit_length() - 1
    rev = np.array([reverse_bits(i, n) for i in range(len(perm))])
    m = np.zeros((len(perm), len(perm)))
    m[rev[np.array(perm)], rev] = 1.0
    return m


def bit_pairs(func, n_in):
    """(input bits, output bits) for every basis state that changes, qubit order 0..n+m-1."""
    perm = permutation(func, n_in)
    n = len(perm).bit_length() - 1
    return [([bool((i >> k) & 1) for k in range(n)], [bool((j >> k) & 1) for k in range(n)])
            for i, j in enumerate(perm) if i != j]
