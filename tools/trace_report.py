"""
Read a trace file and output what happened in the run.

A trace records every question the simulation asked the language model,
which template it came from, how long it took, and what came back. This
tool turns that into answers for three questions:

    1.  Where did the time go and which prompts dominate the run?
    2.  How many questions were asked more than once?
    3.  What were the model's replies?

Usage:
    python tools/trace_report.py traces/day1.jsonl
    python tools/trace_report.py traces/day1.jsonl --template poignancy_event
    python tools/trace_report.py traces/day1.jsonl --samples 5
"""

import argparse
import collections
import gzip
import json


def load(path):
    """Read a trace, can also handle the gzipped form"""
    records = []
    opener = (lambda: gzip.open(path, "rt", encoding="utf-8")) if str(path).endswith(".gz") else (lambda: open(path, "r", encoding="utf-8"))
    with opener() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--template", help="show the real replies for templates matching this text")
    ap.add_argument("--samples", type=int, default=3, help="how many replies to show per template")
    args = ap.parse_args()

    records = load(args.trace)
    calls = [r for r in records if r.get("type") == "llm"]
    embeddings = [r for r in records if r.get("type") == "embedding"]

    if not calls:
        print("No model calls in this trace.")
        return

    total_seconds = sum(r["seconds"] for r in calls)
    print(
        f"{len(calls)} model calls, {total_seconds / 60:.1f} minutes of model time ({total_seconds / 3600:.2f} hours)"
    )
    if embeddings:
        print(f"{len(embeddings)} embedding calls recorded")
    print()

    # === Question 1 ===
    by_template = collections.defaultdict(lambda: {"n": 0, "s": 0.0, "keys": set()})
    for r in calls:
        t = by_template[r.get("template", "unknown")]
        t["n"] += 1
        t["s"] += r["seconds"]
        t["keys"].add(r["key"])

    print("WHERE THE TIME WENT")
    print(
        f"{'prompt template':42s} {'calls':>6s} {'unique':>7s} {'repeat':>7s} "
        f"{'minutes':>8s} {'% time':>7s} {'s/call':>7s}"
    )
    print("-" * 90)
    for name, t in sorted(by_template.items(), key=lambda kv: -kv[1]["s"]):
        unique = len(t["keys"])
        repeat = 100 * (1 - unique / t["n"]) if t["n"] else 0
        print(
            f"{name[:42]:42s} {t['n']:6d} {unique:7d} {repeat:6.0f}% "
            f"{t['s']/60:8.1f} {100*t['s']/total_seconds:6.1f}%
            {t['s']/t['n']:7.2f}"
        )
    print()

    # === Question 2 ===
    all_keys = [r["key"] for r in calls]
    unique_keys = len(set(all_keys))
    wasted = len(all_keys) - unique_keys
    print("REPEATED WORK")
    print(f"  {unique_keys} distinct questions were asked {len(all_keys)} times.")
    if wasted:
        repeat_seconds = sum(t["s"] * (1 - len(t["keys"]) / t["n"]) for t in by_template.values() if t["n"])
        print(
            f"  {wasted} calls ({100*wasted/len(all_keys):.0f}%) re-asked something already asked, "
            f"costing about {repeat_seconds/60:.1f} minutes."
        )
        print(
            f"  Caching answers by question would remove roughly "
            f"{100*repeat_seconds/total_seconds:.0f}% of the run's model time."
        )
    print()

    # === Question 3 ===
    if args.template:
        matching = [r for r in calls if args.template.lower() in r.get("template", "").lower()]
        if not matching:
            print(f"No calls matched template text {args.template!r}.")
            return
        print(f"REAL REPLIES for templates matching {args.template!r} ({len(matching)} calls)")
        seen = set()
        shown = 0
        for r in matching:
            if r["key"] in seen:
                continue
            seen.add(r["key"])
            shown += 1
            if shown > args.samples:
                break
            reply = r["response"]
            if len(reply) > 400:
                reply = reply[:400] + " ..."
            print(f"\n  --- from {r['template']} ---")
            print(f"  {reply}")


if __name__ == "__main__":
    main()
