"""Print the versions of the compilers installed in this environment (and quilc) as JSON."""
import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

PACKAGES = ["qiskit", "pytket", "cirq-core", "bqskit", "pennylane", "qibo", "qrisp", "mqt-core",
            "mqt-qmap", "mqt-syrec", "numpy", "scipy"]


def installed():
    out = {}
    for p in PACKAGES:
        try:
            out[p] = version(p)
        except PackageNotFoundError:
            pass
    return out


def quilc():
    image = os.environ.get("QUILC_IMAGE", "rigetti/quilc:1.26.0")
    try:
        r = subprocess.run(["docker", "run", "--rm", image, "--version"], capture_output=True, text=True, timeout=120)
        return r.stdout.strip().split()[0] if r.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    v = installed()
    if "--quilc" in sys.argv:
        q = quilc()
        if q:
            v["quilc"] = q
    print(json.dumps(v))
