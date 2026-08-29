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
import math
import statistics


def percentile(values, fraction):
    """
    The value below which `fraction` of the sorted list falls,
    nearest-rank (no interpolation).

    Nearest-rank is used because these are measured call durations and
    every printed number should be a duration that actually occurred.
    """
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def load(path):
    """Read a trace, can also handle the gzipped form"""
    records = []
    opener = (
        (lambda: gzip.open(path, "rt", encoding="utf-8"))
        if str(path).endswith(".gz")
        else (lambda: open(path, "r", encoding="utf-8"))
    )
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

    # Which conditon produced a trace (if recorded).
    header = next((r for r in records if r.get("type") == "run"), None)
    summary = (header or {}).get("memory_config", {}).get("summary")
    print(f"CONDITION: {summary}" if summary else "CONDITION: not recorded (trace predates the run header)")

    total_seconds = sum(r["seconds"] for r in calls)
    print(
        f"{len(calls)} model calls, {total_seconds / 60:.1f} minutes of model time ({total_seconds / 3600:.2f} hours)"
    )
    if embeddings:
        print(f"{len(embeddings)} embedding calls recorded")
    print()

    # === Question 1 ===
    by_template = collections.defaultdict(lambda: {"n": 0, "s": 0.0, "keys": set(), "each": []})
    for r in calls:
        t = by_template[r.get("template", "unknown")]
        t["n"] += 1
        t["s"] += r["seconds"]
        t["keys"].add(r["key"])

        # Cache hits cost zero by construction, so they are excluded
        # from the per-call timings.
        if not r.get("cached"):
            t["each"].append(r["seconds"])

    # The mean is reported alongside the median and the 90th
    # percentile.
    print("WHERE THE TIME WENT")
    print("(median, p90, mean and max describe calls that actually reached the model)")
    print(
        f"{'prompt template':42s} {'calls':>6s} {'unique':>7s} {'repeat':>7s} "
        f"{'minutes':>8s} {'% time':>7s} {'median':>7s} {'p90':>7s} {'mean':>7s} {'max':>8s}"
    )
    print("-" * 112)
    for name, t in sorted(by_template.items(), key=lambda kv: -kv[1]["s"]):
        unique = len(t["keys"])
        repeat = 100 * (1 - unique / t["n"]) if t["n"] else 0
        row = (
            f"{name[:42]:42s} {t['n']:6d} {unique:7d} {repeat:6.0f}% "
            f"{t['s'] / 60:8.1f} {100 * t['s'] / total_seconds:6.1f}%"
        )
        if t["each"]:
            row += (
                f" {statistics.median(t['each']):7.2f} {percentile(t['each'], 0.9):7.2f} "
                f"{sum(t['each']) / len(t['each']):7.2f} {max(t['each']):8.1f}"
            )
        print(row)
    print()

    # Name the outliers
    def template_median(name):
        each = by_template[name]["each"]
        return statistics.median(each) if each else 0.0

    stalled = sorted(
        (
            r
            for r in calls
            if not r.get("cached") and r["seconds"] > max(30.0, 20 * template_median(r.get("template", "unknown")))
        ),
        key=lambda r: -r["seconds"],
    )
    if stalled:
        lost = sum(r["seconds"] for r in stalled)
        print("STALLED CALLS (over 30s, and over twenty times the median for the same prompt)")
        for r in stalled[:5]:
            name = r.get("template", "unknown")
            print(
                f"  {r['seconds']:8.1f}s  (median {template_median(name):.2f}s)  {name[:44]}  -> {r['response'][:40]!r}"
            )
        print(
            f"  {len(stalled)} such call(s), {lost / 60:.1f} minutes, {100 * lost / total_seconds:.0f}% of "
            f"the run's model time. Cap these with llm_timeout_seconds in utils.py."
        )
        print()

    # === Question 2 ===
    all_keys = [r["key"] for r in calls]
    unique_keys = len(set(all_keys))
    wasted = len(all_keys) - unique_keys
    print("REPEATED WORK")
    print(f"  {unique_keys} distinct questions were asked {len(all_keys)} times.")

    served = [r for r in calls if r.get("cached")]
    if served:
        # What was saved in cache.
        mean = {}
        for name, t in by_template.items():
            real = [r for r in calls if r.get("template") == name and not r.get("cached")]
            mean[name] = (sum(r["seconds"] for r in real) / len(real)) if real else 0.0
        saved = sum(mean.get(r.get("template"), 0.0) for r in served)
        print(
            f"  {len(served)} of those ({100 * len(served) / len(all_keys):.0f}%) were answered from the "
            f"in-run cache, at no cost."
        )
        print(
            f"  That saved about {saved / 60:.1f} minutes, or {100 * saved / (total_seconds + saved):.0f}% of "
            f"what the run would otherwise have spent."
        )
    if wasted:
        repeat_seconds = sum(t["s"] * (1 - len(t["keys"]) / t["n"]) for t in by_template.values() if t["n"])
        still = wasted - len(served)
        if served:
            print(
                f"  {still} repeats remain, costing about {repeat_seconds / 60:.1f} minutes. These are the "
                f"prompts sampled at a non-zero temperature, which are deliberately not cached."
            )
        else:
            print(
                f"  {wasted} calls ({100 * wasted / len(all_keys):.0f}%) re-asked something already asked, "
                f"costing about {repeat_seconds / 60:.1f} minutes."
            )
            print(
                f"  Caching answers by question would remove roughly "
                f"{100 * repeat_seconds / total_seconds:.0f}% of the run's model time."
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
