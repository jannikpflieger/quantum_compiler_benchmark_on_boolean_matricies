"""One function per compiler. Each takes (function name, number of inputs, topology, **options)
and returns the compiled circuit in the common form used by bench.verify, the native gate counts
and the compile time in seconds.

The oracle has n = n_in + m logical qubits (m output bits). Compilers that add helper qubits
(ancillas) get a device that is large enough; helper qubits start in |0> and must end in |0>.

Options are given in the compiler id after a colon, e.g. "qiskit:o1" (optimisation level 1),
"tket:o0", "mqt:cost" or "qiskit_mcx:n_clean_m15".
"""
import math
import os
import re
import subprocess
import tempfile
import time
import uuid

import numpy as np

from . import oracles
from .topologies import edges

MAX_MATRIX_QUBITS = 12  # compilers that take the full 2^n x 2^n matrix are not run beyond this


def _sizes(func, n_in):
    m = oracles.n_outputs(func, n_in)
    return n_in + m, m


def _need_matrix(n):
    if n > MAX_MATRIX_QUBITS:
        raise RuntimeError(f"matrix input limited to {MAX_MATRIX_QUBITS} qubits")


# ---------------------------------------------------------------- Qiskit helpers
def _from_qiskit(out):
    """Qiskit circuit -> (gates, counts). SWAP gates are expanded to three CX in the gate list."""
    gates, counts = [], {}
    for inst in out.data:
        name = inst.operation.name
        if name in ("barrier", "measure", "reset", "global_phase"):
            continue
        qs = [out.find_bit(q).index for q in inst.qubits]
        counts[name] = counts.get(name, 0) + 1
        if name == "cx":
            gates.append(("cx", qs[0], qs[1]))
        elif name == "cz":
            gates.append(("cz", qs[0], qs[1]))
        elif name == "swap":
            a, b = qs
            gates += [("cx", a, b), ("cx", b, a), ("cx", a, b)]
        elif len(qs) == 1:
            gates.append(("1q", qs[0], inst.operation.to_matrix()))
        else:
            raise RuntimeError(f"unexpected gate {name}")
    return gates, counts


def _two(counts):
    return sum(v * (3 if k == "swap" else 1) for k, v in counts.items() if k in ("cx", "cz", "swap"))


def _qiskit_transpile(circ, topology, n_logical, level=3, initially_zero=False):
    from qiskit import transpile
    from qiskit.transpiler import CouplingMap

    n_phys, e = edges(topology, circ.num_qubits)
    cmap = None if topology == "fully" else CouplingMap([list(x) for x in e] + [[b, a] for a, b in e])
    t0 = time.perf_counter()
    out = transpile(circ, basis_gates=["rx", "ry", "rz", "p", "cx"], optimization_level=level,
                    coupling_map=cmap, seed_transpiler=7, qubits_initially_zero=initially_zero)
    dt = time.perf_counter() - t0
    gates, counts = _from_qiskit(out)
    if out.layout is not None:
        initial = out.layout.initial_index_layout()[:n_logical]
        final = out.layout.final_index_layout()[:n_logical]
    else:
        initial = final = list(range(n_logical))
    return dict(gates=gates, n_phys=out.num_qubits, initial=initial, final=final, counts=counts,
                two_qubit=_two(counts), compile_time=dt)


def _level(opts, default):
    v = opts.get("variant")
    return int(v[1:]) if v and v.startswith("o") else default


def qiskit_expression(func, n_in, topology, **opts):
    """Qiskit with the oracle given as Boolean expressions (one BitFlipOracleGate per output bit)."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import BitFlipOracleGate

    n, m = _sizes(func, n_in)
    circ = QuantumCircuit(n)
    names = list(oracles.VARNAMES[:n_in])
    for j, ex in enumerate(oracles.expressions(func, n_in)):
        used = sorted(oracles.variables(ex))
        gate = BitFlipOracleGate(oracles.render(ex, names), var_order=[names[i] for i in used])
        circ.append(gate, used + [n_in + j])
    return _qiskit_transpile(circ, topology, n, level=_level(opts, 3))


def qiskit_matrix(func, n_in, topology, **opts):
    """Qiskit with the oracle given as a permutation matrix (generic unitary synthesis)."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import UnitaryGate

    n, _ = _sizes(func, n_in)
    _need_matrix(n)
    circ = QuantumCircuit(n)
    circ.append(UnitaryGate(oracles.matrix(func, n_in), check_input=False), range(n))
    return _qiskit_transpile(circ, topology, n, level=_level(opts, 3))


def reference(func, n_in, topology, **opts):
    """Hand-written textbook construction, mapped by Qiskit with the same settings.
    AND: one multi-controlled X. OR: X on inputs, multi-controlled X, X on inputs and output.
    XOR: one CX per input. This is a reference point, not a compiler."""
    from qiskit import QuantumCircuit

    n = n_in + 1
    c = QuantumCircuit(n)
    ins = list(range(n_in))
    if func == "and":
        c.mcx(ins, n_in)
    elif func == "or":
        c.x(ins); c.mcx(ins, n_in); c.x(ins); c.x(n_in)
    elif func == "xor":
        for i in ins:
            c.cx(i, n_in)
    elif func == "always0":
        pass
    elif func == "always1":
        c.x(n_in)
    elif func == "identity":
        c.cx(0, n_in)
    elif func == "two_of_three":
        c.ccx(0, 1, 3); c.ccx(1, 2, 3); c.ccx(0, 2, 3)  # (a&b)^(b&c)^(a&c) equals majority
    else:
        raise RuntimeError("no textbook construction for this function")
    return _qiskit_transpile(c, topology, n)


MCX_METHODS = {
    # name: (synthesis function, number of helper qubits as a function of the control count k)
    "noaux_v24": ("synth_mcx_noaux_v24", lambda k: 0),
    "1_clean_b95": ("synth_mcx_1_clean_b95", lambda k: 1),
    "1_clean_kg24": ("synth_mcx_1_clean_kg24", lambda k: 1),
    "2_clean_kg24": ("synth_mcx_2_clean_kg24", lambda k: 2),
    "n_clean_m15": ("synth_mcx_n_clean_m15", lambda k: max(0, k - 2)),
    "1_dirty_kg24": ("synth_mcx_1_dirty_kg24", lambda k: 1),
    "n_dirty_i15": ("synth_mcx_n_dirty_i15", lambda k: max(0, k - 2)),
}


def qiskit_mcx(func, n_in, topology, **opts):
    """Ancilla study: AND / OR oracle as one multi-controlled X, synthesised by one of Qiskit's
    MCX methods that use 0, 1, 2 or k-2 helper qubits, then optimised and mapped (level 3)."""
    import qiskit.synthesis as syn
    from qiskit import QuantumCircuit

    method = opts.get("variant") or "noaux_v24"
    fname, _ = MCX_METHODS[method]
    if func not in ("and", "or") or n_in < 3:
        raise RuntimeError("ancilla study covers AND and OR with at least 3 inputs")
    core = getattr(syn, fname)(n_in)  # qubits: controls, target, helpers
    c = QuantumCircuit(core.num_qubits)
    ins = list(range(n_in))
    if func == "or":
        c.x(ins)
    c.compose(core, inplace=True)
    if func == "or":
        c.x(ins); c.x(n_in)
    r = _qiskit_transpile(c, topology, n_in + 1)
    r["helpers"] = core.num_qubits - n_in - 1
    return r


# ---------------------------------------------------------------- tket
def tket(func, n_in, topology, **opts):
    """tket: ToffoliBox from the permutation. Variant o2 (default): FullPeepholeOptimise,
    o1: SynthesiseTket, o0: only box decomposition and rebase."""
    from pytket import Circuit, OpType, Qubit
    from pytket.architecture import Architecture
    from pytket.circuit import ToffoliBox
    from pytket.passes import (AutoRebase, CliffordSimp, DecomposeBoxes, DefaultMappingPass,
                               FullPeepholeOptimise, KAKDecomposition, RemoveRedundancies,
                               SequencePass, SynthesiseTket)
    from pytket.predicates import CompilationUnit

    level = _level(opts, 2)
    n, _ = _sizes(func, n_in)
    circ = Circuit(n)
    pairs = oracles.bit_pairs(func, n_in)
    if pairs:
        circ.add_gate(ToffoliBox(pairs), list(range(n)))
    rebase = AutoRebase({OpType.CX, OpType.Rx, OpType.Ry, OpType.Rz})
    opt = {0: [], 1: [SynthesiseTket()], 2: [FullPeepholeOptimise()]}[level]
    n_phys, e = edges(topology, n)
    if topology == "fully":
        seq = [DecomposeBoxes()] + opt + [rebase, RemoveRedundancies()]
    else:
        post = [KAKDecomposition(allow_swaps=False), CliffordSimp(allow_swaps=False), SynthesiseTket()] if level else []
        seq = [DecomposeBoxes()] + opt + [DefaultMappingPass(Architecture(e))] + post + [rebase, RemoveRedundancies()]
    cu = CompilationUnit(circ)
    t0 = time.perf_counter()
    SequencePass(seq).apply(cu)
    dt = time.perf_counter() - t0
    out = cu.circuit

    def idx(q):
        return q.index[0] if len(q.index) == 1 else None

    initial = [idx(cu.initial_map[Qubit(l)]) for l in range(n)]
    final = [idx(cu.final_map[Qubit(l)]) for l in range(n)]
    gates, counts = [], {}
    for cmd in out.get_commands():
        t = cmd.op.type
        qs = [idx(q) for q in cmd.qubits]
        name = t.name.lower()
        counts[name] = counts.get(name, 0) + 1
        if t == OpType.CX:
            gates.append(("cx", qs[0], qs[1]))
        else:
            gates.append(("1q", qs[0], np.array(cmd.op.get_unitary())))
    perm = out.implicit_qubit_permutation()  # wire swaps left implicit by FullPeepholeOptimise
    if any(a != b for a, b in perm.items()):
        inv = {idx(a): idx(b) for a, b in perm.items()}
        final = [inv.get(f, f) for f in final]
    return dict(gates=gates, n_phys=n_phys, initial=initial, final=final, counts=counts,
                two_qubit=counts.get("cx", 0), compile_time=dt)


# ---------------------------------------------------------------- Cirq
def cirq_qsd(func, n_in, topology, **opts):
    """Cirq: quantum Shannon decomposition of the matrix, CZ target gate set, RouteCQC routing."""
    import cirq
    import networkx as nx

    n, _ = _sizes(func, n_in)
    _need_matrix(n)
    qs = cirq.LineQubit.range(n)
    m = oracles.matrix_big_endian(func, n_in)
    t0 = time.perf_counter()
    if n <= 2:
        circ = cirq.Circuit(cirq.MatrixGate(m).on(*qs))
    else:
        circ = cirq.Circuit(cirq.quantum_shannon_decomposition(qs, m))
    circ = cirq.optimize_for_target_gateset(circ, gateset=cirq.CZTargetGateset())
    initial = list(range(n))
    final = list(range(n))
    n_phys, e = edges(topology, n)
    if topology != "fully":
        g = nx.Graph()
        g.add_nodes_from(cirq.LineQubit(i) for i in range(n_phys))
        g.add_edges_from((cirq.LineQubit(a), cirq.LineQubit(b)) for a, b in e)
        routed, init_map, swap_map = cirq.RouteCQC(g).route_circuit(circ)
        circ = cirq.optimize_for_target_gateset(routed, gateset=cirq.CZTargetGateset())
        initial = [init_map[q].x if q in init_map else None for q in qs]
        # qubits without any gate are not placed by the router; put them on unused physical qubits
        free = [p for p in range(n_phys) if p not in initial]
        initial = [p if p is not None else free.pop(0) for p in initial]
        final = [swap_map[cirq.LineQubit(p)].x if cirq.LineQubit(p) in swap_map else p for p in initial]
    dt = time.perf_counter() - t0
    gates, counts = [], {}
    for op in circ.all_operations():
        name = type(op.gate).__name__
        counts[name] = counts.get(name, 0) + 1
        idxs = [q.x for q in op.qubits]
        if len(idxs) == 1:
            gates.append(("1q", idxs[0], cirq.unitary(op)))
        elif isinstance(op.gate, cirq.CZPowGate) and abs(op.gate.exponent) % 2 == 1:
            gates.append(("cz", idxs[0], idxs[1]))
        else:
            raise RuntimeError(f"unexpected gate {op}")
    return dict(gates=gates, n_phys=n_phys, initial=initial, final=final, counts=counts,
                two_qubit=counts.get("CZPowGate", 0), compile_time=dt)


# ---------------------------------------------------------------- BQSKit
def _region(n_phys, e, k):
    """k physical qubits forming a connected region around the most central node, and the
    edges between them relabelled to 0..k-1."""
    import networkx as nx

    g = nx.Graph(e)
    centre = min(g.nodes, key=lambda v: max(nx.single_source_shortest_path_length(g, v).values()))
    order = list(nx.bfs_tree(g, centre))[:k]
    idx = {p: i for i, p in enumerate(order)}
    return order, [(idx[a], idx[b]) for a, b in e if a in idx and b in idx]


def bqskit(func, n_in, topology, **opts):
    """BQSKit: numerical synthesis of the matrix with mapping. Variant oK sets optimization_level K."""
    from bqskit import MachineModel, compile
    from bqskit.compiler import Compiler
    from bqskit.ir.gates import CNOTGate, RXGate, RYGate, RZGate

    n, _ = _sizes(func, n_in)
    _need_matrix(n)
    n_phys, e = edges(topology, n)
    phys = list(range(n_phys))
    if n_phys > n:
        # BQSKit is slow on a 50+ qubit device: give it a connected region of
        # n qubits (breadth-first from the device centre) and translate the result back
        phys, e = _region(n_phys, e, n)
    m = oracles.matrix_big_endian(func, n_in)
    model = MachineModel(len(phys), e, gate_set={CNOTGate(), RXGate(), RYGate(), RZGate()})
    with Compiler(num_workers=int(os.environ.get("BQSKIT_WORKERS", "2"))) as comp:
        t0 = time.perf_counter()
        out, pi, pf = compile(m, model=model, optimization_level=_level(opts, 2),
                              max_synthesis_size=max(3, n), with_mapping=True, compiler=comp, seed=7)
        dt = time.perf_counter() - t0
    gates, counts = [], {}
    for op in out:
        name = op.gate.name
        counts[name] = counts.get(name, 0) + 1
        loc = list(op.location)
        if op.gate.num_qudits == 1:
            gates.append(("1q", loc[0], op.get_unitary().numpy))
        elif isinstance(op.gate, CNOTGate):
            gates.append(("cx", loc[0], loc[1]))
        else:
            raise RuntimeError(op.gate)
    gates = [(g[0], phys[g[1]], g[2]) if g[0] == "1q" else (g[0], phys[g[1]], phys[g[2]]) for g in gates]
    return dict(gates=gates, n_phys=n_phys, initial=[phys[pi[l]] for l in range(n)],
                final=[phys[pf[l]] for l in range(n)], counts=counts,
                two_qubit=counts.get("CNOTGate", 0), compile_time=dt)


# ---------------------------------------------------------------- quilc
QUILC_IMAGE = os.environ.get("QUILC_IMAGE", "rigetti/quilc:1.26.0")


def quilc(func, n_in, topology, timeout=None, **opts):
    import json

    n, _ = _sizes(func, n_in)
    n_phys, e = edges(topology, n)
    # Quil gates are big-endian in the order the qubits are listed. The qubits are listed
    # as 0 .. n-1 (outputs last, as in the thesis), so the permutation is bit-reversed.
    # quilc is sensitive to this order (listing the output first gave ~4x more CZ for n=3).
    perm_le = oracles.permutation(func, n_in)
    perm_be = [oracles.reverse_bits(perm_le[oracles.reverse_bits(i, n)], n) for i in range(2 ** n)]
    prog = "DEFGATE ORACLE AS PERMUTATION:\n    " + ", ".join(map(str, perm_be)) + "\n"
    prog += "ORACLE " + " ".join(str(q) for q in range(n)) + "\n"
    isa = {"isa": {"1Q": {str(q): {} for q in range(n_phys)},
                   "2Q": {f"{min(a, b)}-{max(a, b)}": {} for a, b in e}}}
    with tempfile.TemporaryDirectory() as d:
        os.chmod(d, 0o755)
        with open(os.path.join(d, "isa.json"), "w") as f:
            json.dump(isa, f)
        name = "quilc-" + uuid.uuid4().hex[:8]
        t0 = time.perf_counter()
        try:
            r = subprocess.run(["docker", "run", "--rm", "-i", "--name", name, "-v", f"{d}:/isa", QUILC_IMAGE,
                                "--isa", "/isa/isa.json", "--quiet"],
                               input=prog, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            raise
        dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    return parse_quil(r.stdout, n, n_phys, dt)


def _angle(s):
    return float(eval(s.replace("pi", str(math.pi)), {"__builtins__": {}}))


def _rx(t):
    c, s = math.cos(t / 2), math.sin(t / 2)
    return np.array([[c, -1j * s], [-1j * s, c]])


def _rz(t):
    return np.array([[np.exp(-1j * t / 2), 0], [0, np.exp(1j * t / 2)]])


def parse_quil(text, n, n_phys, dt):
    gates, counts = [], {}
    entering = exiting = None
    for line in text.splitlines():
        m = re.search(r"Entering rewiring: #\(([\d ]*)\)", line)
        if m:
            entering = [int(x) for x in m.group(1).split()]
        m = re.search(r"Exiting rewiring: #\(([\d ]*)\)", line)
        if m:
            exiting = [int(x) for x in m.group(1).split()]
        code = line.split("#")[0].strip()
        if not code or code.startswith(("DEFGATE", "HALT", "PRAGMA")) or code[0].isdigit():
            continue
        m = re.match(r"(RX|RZ)\((.+)\) (\d+)$", code)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
            t = _angle(m.group(2))
            gates.append(("1q", int(m.group(3)), _rx(t) if m.group(1) == "RX" else _rz(t)))
            continue
        m = re.match(r"CZ (\d+) (\d+)$", code)
        if m:
            counts["CZ"] = counts.get("CZ", 0) + 1
            gates.append(("cz", int(m.group(1)), int(m.group(2))))
            continue
        raise RuntimeError(f"unparsed quil line: {code}")
    # rewiring vectors: entry l = physical qubit of logical qubit l
    initial = entering[:n] if entering else list(range(n))
    final = exiting[:n] if exiting else initial
    return dict(gates=gates, n_phys=n_phys, initial=initial, final=final, counts=counts,
                two_qubit=counts.get("CZ", 0), compile_time=dt)


# ---------------------------------------------------------------- PennyLane
def pennylane(func, n_in, topology, **opts):
    """PennyLane: QubitUnitary decomposition, qml.compile optimisation, qml.transforms.transpile routing."""
    import pennylane as qml

    n, _ = _sizes(func, n_in)
    _need_matrix(n)
    n_phys, e = edges(topology, n)
    m = oracles.matrix_big_endian(func, n_in)
    basis = {"RX", "RY", "RZ", "CNOT", "GlobalPhase"}

    def prog():
        qml.QubitUnitary(m, wires=range(n))

    tape = qml.tape.make_qscript(prog)()
    t0 = time.perf_counter()
    [tape], _ = qml.transforms.decompose(tape, gate_set=basis)
    [tape], _ = qml.compile(tape)
    [tape], _ = qml.transforms.decompose(tape, gate_set=basis)
    final = list(range(n))
    if topology != "fully":
        [tape], _ = qml.transforms.transpile(tape, coupling_map=e)
        pos = list(range(n_phys))  # pos[l] = physical wire of logical l, tracked through SWAPs
        for op in tape.operations:
            if op.name == "SWAP":
                a, b = op.wires.tolist()
                pos = [b if p == a else a if p == b else p for p in pos]
        final = pos[:n]
        [tape], _ = qml.transforms.decompose(tape, gate_set=basis)
        [tape], _ = qml.compile(tape, pipeline=[qml.transforms.cancel_inverses, qml.transforms.merge_rotations])
        [tape], _ = qml.transforms.decompose(tape, gate_set=basis)
    dt = time.perf_counter() - t0
    gates, counts = [], {}
    for op in tape.operations:
        if op.name == "GlobalPhase":
            continue
        counts[op.name] = counts.get(op.name, 0) + 1
        w = op.wires.tolist()
        if op.name == "CNOT":
            gates.append(("cx", w[0], w[1]))
        else:
            gates.append(("1q", w[0], qml.matrix(op)))
    return dict(gates=gates, n_phys=n_phys, initial=list(range(n)), final=final, counts=counts,
                two_qubit=counts.get("CNOT", 0), compile_time=dt)


# ---------------------------------------------------------------- Qibo
def qibo(func, n_in, topology, **opts):
    """Qibo transpiler preset (optimization_level=2): unroll, Sabre placement and routing."""
    import networkx as nx
    from qibo import Circuit, gates as qg, set_backend
    from qibo.transpiler import NativeGates, generate_preset_passes

    set_backend("numpy")
    n, _ = _sizes(func, n_in)
    _need_matrix(n)
    n_phys, e = edges(topology, n)
    g = nx.Graph()
    g.add_nodes_from(range(n_phys))
    g.add_edges_from(e)
    m = oracles.matrix_big_endian(func, n_in)
    c = Circuit(n)
    c.add(qg.Unitary(m, *range(n)))
    passes = generate_preset_passes(connectivity=g, native_gates=NativeGates.CNOT | NativeGates.U3,
                                    seed=7, optimization_level=_level(opts, 2))
    t0 = time.perf_counter()
    out, final_layout = passes(c)
    dt = time.perf_counter() - t0
    wn = [int(w) for w in out.wire_names]  # circuit qubit k sits on hardware node wire_names[k]
    gates, counts = [], {}
    for gt in out.queue:
        name = type(gt).__name__
        if name == "GlobalPhase":
            continue
        counts[name] = counts.get(name, 0) + 1
        if name == "CNOT":
            gates.append(("cx", wn[gt.control_qubits[0]], wn[gt.target_qubits[0]]))
        elif len(gt.qubits) == 1:
            gates.append(("1q", wn[gt.qubits[0]], np.array(gt.matrix())))
        else:
            raise RuntimeError(name)
    # As in qibo.transpiler.asserts.assert_circuit_equivalence: logical qubit l enters on circuit
    # qubit l and leaves on circuit qubit list(final_layout.values())[l].
    ordering = [int(v) for v in final_layout.values()]
    return dict(gates=gates, n_phys=max(n_phys, max(wn) + 1), initial=[wn[l] for l in range(n)],
                final=[wn[ordering[l]] for l in range(n)], counts=counts,
                two_qubit=counts.get("CNOT", 0), compile_time=dt)


# ---------------------------------------------------------------- Qrisp
def _qrisp(func, n_in, topology, method):
    """Qrisp truth-table synthesis. Qrisp has no qubit routing, so for restricted layouts the
    synthesised circuit is routed with Qiskit's Sabre pass (no further optimisation)."""
    from qiskit import transpile
    from qiskit.transpiler import CouplingMap
    from qrisp import QuantumVariable, TruthTable

    n, m = _sizes(func, n_in)
    rows = oracles.output_table(func, n_in)
    cols = ["".join(str(r[j]) for r in rows) for j in range(m)]
    t0 = time.perf_counter()
    x = QuantumVariable(n_in)
    y = QuantumVariable(m)
    TruthTable(cols).q_synth(x, y, method=method)
    qc = x.qs.compile().to_qiskit()
    # basis translation only, so the counts reflect Qrisp's synthesis. qubits_initially_zero=False:
    # an oracle must work for every input, so idle qubits must not be used as clean ancillas.
    kw = dict(basis_gates=["rx", "ry", "rz", "p", "cx"], optimization_level=0, qubits_initially_zero=False)
    if topology != "fully":
        n_phys, e = edges(topology, qc.num_qubits)
        kw.update(coupling_map=CouplingMap([list(a) for a in e] + [[b, a] for a, b in e]),
                  layout_method="sabre", routing_method="sabre", seed_transpiler=7)
    out = transpile(qc, **kw)
    dt = time.perf_counter() - t0
    gates, counts = _from_qiskit(out)
    if out.layout is not None and topology != "fully":
        initial = out.layout.initial_index_layout()[:n]
        final = out.layout.final_index_layout()[:n]
    else:
        initial = final = list(range(n))  # x[0..n_in-1] then y are the first qubits
    return dict(gates=gates, n_phys=max(out.num_qubits, n), initial=initial, final=final,
                counts=counts, two_qubit=_two(counts), compile_time=dt)


def qrisp_gray(func, n_in, topology, **opts):
    return _qrisp(func, n_in, topology, "gray")


def qrisp_pprm(func, n_in, topology, **opts):
    return _qrisp(func, n_in, topology, "pprm")


# ---------------------------------------------------------------- MQT (SyReC + QMAP)
def syrec_program(func, n_in):
    n, m = _sizes(func, n_in)
    xs = [f"x{i}" for i in range(n_in)]
    ys = [f"y{j}" for j in range(m)]
    head = ", ".join([f"in {v}(1)" for v in xs] + [f"inout {v}(1)" for v in ys])
    body = ";\n".join(f"  {ys[j]} ^= {oracles.render(ex, xs, 'syrec')}"
                      for j, ex in enumerate(oracles.expressions(func, n_in)))
    return f"module main({head})\n{body}\n"


def mqt(func, n_in, topology, **opts):
    """MQT: SyReC synthesis of the expressions (line-aware by default, variant 'cost' for cost-aware),
    garbage on helper lines uncomputed, then QMAP heuristic mapping with its pre- and post-mapping
    optimisations. Multi-controlled Toffolis are expanded with Qiskit's default synthesis."""
    import mqt.syrec as S
    from mqt.core.plugins.qiskit import mqt_to_qiskit
    from mqt.core import load
    from mqt.qmap.sc import Architecture, Configuration, map_
    from qiskit import QuantumCircuit, transpile

    n, m = _sizes(func, n_in)
    t0 = time.perf_counter()
    prog = S.Program()
    err = prog.read_from_string(syrec_program(func, n_in))
    if err:
        raise RuntimeError(f"SyReC parse error: {err}")
    aqc = S.AnnotatableQuantumComputation()
    synth = S.cost_aware_synthesis if opts.get("variant") == "cost" else S.line_aware_synthesis
    if not synth(aqc, prog):
        raise RuntimeError("SyReC synthesis failed")
    raw = mqt_to_qiskit(aqc)
    labels = [aqc.get_qubit_label(i, S.QubitLabelType.internal).split("[")[0] for i in range(aqc.num_qubits)]
    logical = [f"x{i}" for i in range(n_in)] + [f"y{j}" for j in range(m)]
    pos = {lab: i for i, lab in enumerate(labels) if not lab.startswith("__")}
    order = [pos[l] for l in logical] + [i for i, l in enumerate(labels) if l.startswith("__")]
    outs = {pos[f"y{j}"] for j in range(m)}
    # re-order: logical qubits first, helpers after; uncompute helper lines (garbage) by appending
    # the inverse of every gate that does not write an output. This is valid because outputs are
    # only XOR targets and never read.
    c = QuantumCircuit(raw.num_qubits)
    remap = {old: new for new, old in enumerate(order)}
    keep = []
    for inst in raw.data:
        qs = [remap[raw.find_bit(q).index] for q in inst.qubits]
        if any(q in {remap[o] for o in outs} for q in qs[:-1]):
            raise RuntimeError("output line used as control")
        c.append(inst.operation, qs)
        if qs[-1] not in {remap[o] for o in outs}:
            keep.append((inst.operation, qs))
    helpers = raw.num_qubits - n
    if helpers:
        for op, qs in reversed(keep):
            c.append(op.inverse(), qs)
    elem = transpile(c, basis_gates=["u", "cx"], optimization_level=0, qubits_initially_zero=False)
    n_phys, e = edges(topology, c.num_qubits)
    if topology == "fully":
        e = [(a, b) for a in range(n_phys) for b in range(a + 1, n_phys)]
    arch = Architecture(n_phys, {(a, b) for a, b in e} | {(b, a) for a, b in e})
    cfg = Configuration()
    cfg.add_measurements_to_mapped_circuit = False
    cfg.pre_mapping_optimizations = True
    cfg.post_mapping_optimizations = True
    qm, _ = map_(load(elem), arch, cfg)
    out = mqt_to_qiskit(qm)
    dt = time.perf_counter() - t0
    gates, counts = _from_qiskit(out)
    # layouts as physical -> logical maps from QMAP (the Qiskit layout ignores the output permutation)
    inv_in = {lq: p for p, lq in qm.initial_layout.items()}
    inv_out = {lq: p for p, lq in qm.output_permutation.items()}
    initial = [inv_in[l] for l in range(n)]
    final = [inv_out[l] for l in range(n)]
    return dict(gates=gates, n_phys=out.num_qubits, initial=initial, final=final, counts=counts,
                two_qubit=_two(counts), compile_time=dt, helpers=helpers)


COMPILERS = {
    "qiskit": qiskit_expression,
    "qiskit_matrix": qiskit_matrix,
    "tket": tket,
    "cirq": cirq_qsd,
    "bqskit": bqskit,
    "quilc": quilc,
    "reference": reference,
    "pennylane": pennylane,
    "qibo": qibo,
    "qrisp_gray": qrisp_gray,
    "qrisp_pprm": qrisp_pprm,
    "mqt": mqt,
    "qiskit_mcx": qiskit_mcx,
}


def get(compiler_id):
    """'name' or 'name:variant' -> (function, options)."""
    name, _, variant = compiler_id.partition(":")
    return COMPILERS[name], ({"variant": variant} if variant else {})
