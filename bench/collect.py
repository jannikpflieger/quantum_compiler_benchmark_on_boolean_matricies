"""Merge the shard outputs of one benchmark run into results/runs/<run_id>/.
Usage: python -m bench.collect <shard dir> <run_id> <pinned|latest>"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    src, run_id, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    dest = os.path.join(HERE, "results", "runs", run_id)
    os.makedirs(dest, exist_ok=True)
    recs = []
    for path in sorted(glob.glob(os.path.join(src, "**", "*.jsonl"), recursive=True)):
        with open(path) as f:
            recs += [json.loads(line) for line in f if line.strip()]
    versions = {}
    for path in sorted(glob.glob(os.path.join(src, "**", "*.versions.json"), recursive=True)):
        with open(path) as f:
            for k, v in json.load(f).items():
                versions.setdefault(k, v)
    with open(os.path.join(dest, "results.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(dest, "run.json"), "w") as f:
        json.dump({"run_id": run_id, "mode": mode, "jobs": len(recs), "versions": versions}, f, indent=1)
    print(f"{len(recs)} records -> {dest}")


if __name__ == "__main__":
    main()
