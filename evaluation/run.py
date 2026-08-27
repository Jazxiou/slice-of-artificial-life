"""
Ask both sets of questions against a saved simulation.

    uv run python evaluation/run.py --sim baseline_3_day --out results/baseline_3_day.json

Nothing is written into the simulation folder. The only output is the
JSON file named by `--out`, which contains the condition that produced
the checkpoint, every question, every answer, what the agent recalled
when answering, and the grade.

The B7 interview question is generated once per character and stored in
`--pressure-file` then reused. If that file exists then it is just read
not regenerated.
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation import administer, probes, score


def _generate(prompt):
    return administer.generate(prompt)


def frozen_pressure_questions(sim_folder, names, path):
    """
    Read the B7 questions, generating and saving them for the first
    time only.

    If changes are present however, then the file is flagged as stale.
    """
    fingerprint = str(abs(hash(probes.PRESSURE_PROMPT)) % (10**12))
    stored = {}
    if os.path.exists(path):
        with open(path) as f:
            stored = json.load(f)
        if stored.get("_generator") not in (None, fingerprint):
            print(
                f"[battery] WARNING: {path} was written by a different version of the scenario generator.\n"
                f"[battery] Those scenarios are still being used, because changing them mid-evaluation "
                f"would mean conditions were asked different questions.\n"
                f"[battery] If no measured run has used them yet, delete the file and re-run to regenerate."
            )

    missing = [n for n in names if n not in stored]
    for name in missing:
        scratch = probes.load_scratch(f"{sim_folder}/personas/{name}")
        stored[name] = probes.pressure_question(scratch, _generate)
        print(f"[battery] generated the pressure scenario for {name}; it is now frozen in {path}")
    if missing:
        stored.setdefault("_generator", fingerprint)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(stored, f, indent=2)
    return stored


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", required=True, help="name of a saved simulation under storage/")
    ap.add_argument("--out", required=True, help="where to write the answers and grades")
    ap.add_argument(
        "--storage", default="environment/frontend_server/storage", help="storage root, relative to the repository"
    )
    ap.add_argument(
        "--pressure-file",
        default="evaluation/pressure_scenarios.json",
        help="frozen B7 scenarios, generated once and reused",
    )
    ap.add_argument(
        "--seed", type=int, default=0, help="fixes which negative controls are drawn, so a battery is reproducible"
    )
    ap.add_argument("--skip-interview", action="store_true")
    args = ap.parse_args()

    sim_folder = os.path.join(args.storage, args.sim)
    names = sorted(os.listdir(os.path.join(sim_folder, "personas")))
    now = administer.checkpoint_time(sim_folder)
    cfg = administer.condition(sim_folder)

    print(f"[battery] {args.sim} at {now}")
    print(f"[battery] condition: {cfg.get('summary', 'not recorded')}")

    pressure = {} if args.skip_interview else frozen_pressure_questions(sim_folder, names, args.pressure_file)

    results = {"sim": args.sim, "checkpoint": str(now), "memory_config": cfg, "agents": {}}

    for name in names:
        print(f"\n[battery] {name}")
        persona = administer.load(sim_folder, name)

        battery = probes.build(f"{sim_folder}/personas/{name}", name, now, rng=random.Random(args.seed))
        scored = []
        for probe in battery:
            given = administer.ask(persona, probe["question"])
            verdict = score.grade(probe, given["answer"], _generate)
            scored.append({"probe": probe, **given, "verdict": verdict})
            print(
                f"  [{probe['kind']:<18} {probe['age_hours']:>3}h] {verdict['grade']:<10} "
                f"({given['recalled_count']} memories recalled)"
            )

        summary = score.summarise(scored)
        score.report(summary)

        not_english = [s for s in scored if s.get("english") is False]
        if not_english:
            print(
                f"  ** {len(not_english)} answers were still not in English after retries and are flagged "
                f"in the output; their grades should not be trusted"
            )

        interview = []
        if not args.skip_interview:
            for question in probes.interview(pressure.get(name, "")):
                if not question["question"]:
                    continue
                given = administer.ask(persona, question["question"], n_memories=15, interview=True)
                interview.append({**question, **given})
            print(f"  interview: {len(interview)} answers recorded")

        results["agents"][name] = {"probes": scored, "summary": summary, "interview": interview}

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[battery] written to {args.out}")
    print("[battery] the simulation was not modified.")


if __name__ == "__main__":
    main()
