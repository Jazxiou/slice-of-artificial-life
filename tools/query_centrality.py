"""
Why does asking an agent a question sometimes return its opinions
instead of its memories?

A test run turned up something odd. Of the memories retrieved for Maria
Lopez, 48% were reflections and none at all were for the other two
agents, although all three hold a similar proportion of reflections.
She therefore "abstained" on every question, having been handed nothing
but abstract reflections to answer from.

Known:
    -   Reflections sit nearer the centre of an agent's embedding space
        than episodes (memories of events) do.
    -   A query near that centre therefore matches abstractions
        preferentially.

This module checks if the questions asked are themselves central.

    uv run python tools/query_centrality.py --sim baseline_3_day
"""

import argparse
import json
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "reverie", "backend_server"))


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) or 1.0)


def load(sim_folder, name):
    base = f"{sim_folder}/personas/{name}/bootstrap_memory/associative_memory"
    nodes = json.load(open(f"{base}/nodes.json"))
    embs = json.load(open(f"{base}/embeddings.json"))
    scanned = [n for n in nodes.values() if "idle" not in n["embedding_key"] and n["type"] in ("event", "thought")]
    matrix = np.array([unit(embs[n["embedding_key"]]) for n in scanned])
    return scanned, matrix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", default="baseline_3_day")
    ap.add_argument("--storage", default="environment/frontend_server/storage")
    ap.add_argument("--offline", action="store_true", help="skip the part that needs the embedding model")
    args = ap.parse_args()
    sim_folder = os.path.join(args.storage, args.sim)
    random.seed(1)

    embed = None
    if not args.offline:
        from persona.prompt_template.gpt_structure import get_embedding

        embed = get_embedding

    for name in sorted(os.listdir(f"{sim_folder}/personas")):
        scanned, M = load(sim_folder, name)
        centroid = unit(M.mean(axis=0))
        is_thought = np.array([n["type"] == "thought" for n in scanned])
        centrality = M @ centroid

        print(f"\n{name}: {len(scanned)} memories scanned by retrieval")
        print(
            f"  centrality  episodes {centrality[~is_thought].mean():.3f}   "
            f"reflections {centrality[is_thought].mean():.3f}"
        )

        # Using stored memories as stand-in queries
        picks = random.sample(range(len(scanned)), min(200, len(scanned)))
        xs, ys = [], []
        for i in picks:
            xs.append(float(centrality[i]))
            top = np.argsort(-(M @ M[i]))[:20]
            ys.append(float(is_thought[top].mean()))
        xs, ys = np.array(xs), np.array(ys)
        low, high = xs < np.percentile(xs, 25), xs > np.percentile(xs, 75)
        print(
            f"  a central query pulls back abstractions: r={np.corrcoef(xs, ys)[0, 1]:+.2f}, "
            f"{ys[low].mean():.0%} for the least central queries vs {ys[high].mean():.0%} for the most"
        )

        if embed is None:
            continue

        # Now compute if the questions themselves are central. Also
        # compute how does the reflection share change as the score is
        # assembled?
        from evaluation import administer
        from evaluation import probes as probe_module

        battery = probe_module.build(
            f"{sim_folder}/personas/{name}", name, administer.checkpoint_time(sim_folder), rng=random.Random(0)
        )

        scratch = json.load(open(f"{sim_folder}/personas/{name}/bootstrap_memory/scratch.json"))
        poignancy = np.array([n["poignancy"] for n in scanned], dtype=float)
        # Recency as the baseline computes it.
        order = np.argsort([n["created"] for n in scanned])
        recency = np.empty(len(scanned))
        recency[order] = scratch["recency_decay"] ** np.arange(1, len(scanned) + 1)

        def norm(x):
            lo, hi = x.min(), x.max()
            return np.full_like(x, 0.5) if hi == lo else (x - lo) / (hi - lo)

        rec_n, imp_n = norm(recency), norm(poignancy)
        qs, by_stage = [], {"relevance only": [], "+ importance": [], "full score": []}
        for p in battery:
            q = unit(embed(p["question"]))
            rel_n = norm(M @ q)
            for label, score in (
                ("relevance only", rel_n),
                ("+ importance", scratch["relevance_w"] * rel_n * 3 + scratch["importance_w"] * imp_n * 2),
                (
                    "full score",
                    scratch["recency_w"] * rec_n * 0.5
                    + scratch["relevance_w"] * rel_n * 3
                    + scratch["importance_w"] * imp_n * 2,
                ),
            ):
                by_stage[label].append(float(is_thought[np.argsort(-score)[:20]].mean()))
            qs.append(float(q @ centroid))

        qs = np.array(qs)
        print(
            f"  the battery's own questions: centrality {qs.mean():.3f}, "
            f"more central than {float((centrality[:, None] < qs[None, :]).mean()):.0%} of its memories"
        )
        print("  reflections retrieved, as the score is assembled:")
        for label, shares in by_stage.items():
            print(f"      {label:<16} {np.mean(shares):.0%}")


if __name__ == "__main__":
    main()
