"""
Scoring the persona interview: how far is this character from the
person the run started with?

Can be applied to interviews already recorded.

Two measurements:

    - The interview:
        asks the character eight questions about itself. The prompt it is answered from is the
        one the simulation actually uses, which is the identity stable set plus retrieved memory, because a
        measurement taken through a prompt the simulation never uses would measure the instrument. That fidelity
        has a consequence, and the first scored runs made it plain: every answer came back in character, 0%
        drift across forty-eight answers in both conditions. The identity stable set contains the character's
        innate and learned traits, and those never change. Klaus's says "a student at Oak Hill College studying
        sociology", so he answers "who are you" correctly however far the rest of his self-description has
        wandered. The interview measures what a character *says about itself in the world*, and that is worth
        knowing, but it is insensitive by construction to the field this project modifies.

    - The indentity check:
        therefore measures that field directly. `currently` is the one part of the
        identity stable set that is rewritten daily, it is what re-anchoring corrects, and it is where the drift
        observed in every run has actually been. It is compared with the character as originally written in
        three ways: a judgement, a distance, and a test of genre.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "reverie", "backend_server")
for _path in (ROOT, BACKEND):
    if _path not in sys.path:
        sys.path.insert(0, _path)

GRADES = ("in_character", "adapted", "drifted", "contradicts")

JUDGE_PROMPT = """Here is a character, as originally written:
!<ANCHOR>!
Some time later, that character was asked: !<QUESTION>!
They answered: !<ANSWER>!
Decide which one of these the answer is:
  in_character - it is recognisably the same person, still concerned with what they were written to be
                 concerned with
  adapted      - they have clearly changed or taken on something new, but what defines them is still
                 there. A researcher who has started helping with a community event is adapted.
  drifted      - what defines them is gone. They are not contradicting the original, they have simply
                 stopped being that person. A researcher who now describes themselves only as an event
                 organiser has drifted.
  contradicts  - the answer states something incompatible with the original, such as a different job,
                 a different field of study, or a different name.
Judge the *substance*, not the wording, and do not reward an answer for repeating the original text.
Changing is not by itself failure: only mark drifted when the defining concern is absent, not when it
shares the stage with something new.
Reply with JSON and nothing else:
{"grade": "<one of the four>", "why": "<one short sentence>"}"""


def anchor_of(scratch):
    """
    The character as originally written, assembled from a saved
    `scratch.json`.

    Deliberately the same three fields the runtime mechanism anchors
    to, so a distance measured here and a distance measured during a
    run mean the same thing. `seed_currently` is the copy taken when
    the simulation was first loaded; a checkpoint saved before that
    field existed has only its current value, which is the best
    available anchor and worth knowing about, so the caller is told.
    """
    seed = scratch.get("seed_currently") or scratch.get("currently") or ""
    return (
        "\n".join([
            f"Name: {scratch.get('name', '')}",
            f"Innate traits: {scratch.get('innate', '')}",
            f"Learned traits: {scratch.get('learned', '')}",
            f"Originally: {seed}",
        ]),
        bool(scratch.get("seed_currently")),
    )


def distance(text, anchor, embed):
    """
    Cosine distance from the anchor, or None if either text cannot be
    embedded.
    """
    try:
        a, b = embed(anchor), embed(text)
    except Exception as exc:  # noqa: BLE001 - a missing model must not lose the run
        print(f"  [persona] could not embed: {type(exc).__name__}: {exc}")
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if not na or not nb:
        return None
    return 1.0 - dot / (na * nb)


def grade(answer, question, anchor, generate):
    """
    One judged answer. An unreadable reply from the judge is recorded as `unscored` rather than guessed
    at, for the same reason the memory scorer does it: a guess would put noise into the headline number.
    """
    raw = generate(
        JUDGE_PROMPT.replace("!<ANCHOR>!", anchor).replace("!<QUESTION>!", question).replace("!<ANSWER>!", answer)
    )
    import re

    verdict = {"grade": "unscored", "why": "the judge's reply could not be read"}
    try:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            parsed = json.loads(match.group(0))
            if parsed.get("grade") in GRADES:
                verdict = {"grade": parsed["grade"], "why": str(parsed.get("why", ""))[:200]}
    except (ValueError, TypeError):
        pass
    return verdict


def score_interview(answers, anchor, generate):
    """
    Grade every interview answer. Returns the answers with a `persona` field added.
    No distance is taken here.
    """
    out = []
    for item in answers:
        if not item.get("answer"):
            out.append(item)
            continue
        out.append({**item, "persona": grade(item["answer"], item["question"], anchor, generate)})
    return out


IDENTITY_QUESTION = (
    "Who is this person now? (this is the character's own current self-description, "
    "which the simulation rewrites once per simulated day)"
)


def score_identity(scratch, embed, generate):
    """
    Measure the one field that actually drifts.
    `currently` is the only part of the identity stable set the simulation rewrites, it is what
    re-anchoring corrects, and it is where every drift observed in this project has been. Three numbers,
    none of which subsumes the others: a judgement against the character as originally written, the cosine
    distance the runtime mechanism uses, and whether the text has stopped being a description of a person
    and become an account of one day.
    """
    anchor, has_seed = anchor_of(scratch)
    current = scratch.get("currently") or ""
    verdict = grade(current, IDENTITY_QUESTION, anchor, generate)
    verdict["distance"] = distance(current, anchor, embed)
    verdict["anchored_to_seed"] = has_seed
    try:
        from memory_ext import persona as persona_ext

        # The same test the running mechanism applies, so a status counted as dated here is one the
        # mechanism would have corrected. Markers are compared against the anchor, so a character written
        # with a date or a time in them is allowed to keep it.
        verdict["dated"] = persona_ext.new_markers(current, anchor)
    except Exception as exc:  # noqa: BLE001
        print(f"  [persona] could not run the genre test: {type(exc).__name__}: {exc}")
        verdict["dated"] = None
    verdict["text"] = current
    return verdict


def summarise(scored):
    """
    Counts by grade, the drift rate, and the distances.

    `drift` pools *drifted* and *contradicts*, since both are failures of the thing under test, and
    *adapted* is deliberately not among them. Unscored answers are excluded from the rates and reported,
    so a judge that fails often cannot quietly shrink the denominator.
    """
    counts = {g: 0 for g in GRADES}
    counts["unscored"] = 0
    distances = []
    for item in scored:
        verdict = item.get("persona")
        if not verdict:
            continue
        counts[verdict.get("grade", "unscored")] = counts.get(verdict.get("grade", "unscored"), 0) + 1
        if verdict.get("distance") is not None:
            distances.append(verdict["distance"])
    judged = sum(counts[g] for g in GRADES)
    summary = {
        "n": judged,
        "counts": counts,
        "drift": (counts["drifted"] + counts["contradicts"]) / judged if judged else None,
        "in_character": counts["in_character"] / judged if judged else None,
        "adapted": counts["adapted"] / judged if judged else None,
    }
    if distances:
        ordered = sorted(distances)
        summary["distance"] = {
            "n": len(ordered),
            "mean": sum(ordered) / len(ordered),
            "median": ordered[len(ordered) // 2],
            "max": ordered[-1],
        }
    return summary


def report(summary, identity=None, out=sys.stdout):
    counts = summary["counts"]
    print(
        f"  interview: {summary['n']} answers judged  "
        f"in character {counts['in_character']}, adapted {counts['adapted']}, "
        f"drifted {counts['drifted']}, contradicts {counts['contradicts']}"
        + (f", unscored {counts['unscored']}" if counts["unscored"] else ""),
        file=out,
    )
    if identity:
        dated = identity.get("dated")
        print(
            f"  identity : {identity['grade']}"
            + (f", distance {identity['distance']:.2f}" if identity.get("distance") is not None else "")
            + (
                f", reads as an account of a day ({', '.join(dated)})"
                if dated
                else ", still written as a description of a person"
                if dated == []
                else ""
            ),
            file=out,
        )
        print(f"             {identity['why'][:100]}", file=out)


def main():
    """
    Score the interviews inside a results file that has already been written.

    Kept separate from `run.py` so the two three-day runs already on disk can be scored without asking
    the agents anything again. Re-administering the battery would produce different answers and would
    make the persona numbers incomparable with the memory numbers beside them in the same file.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, help="a results file written by evaluation/run.py")
    ap.add_argument(
        "--storage",
        default="environment/frontend_server/storage",
        help="where the saved simulations live, relative to the current directory or to the repository root",
    )
    ap.add_argument("--out", help="where to write the scored file (default: overwrite --results)")
    args = ap.parse_args()

    from persona.prompt_template.gpt_structure import get_embedding  # noqa: E402

    from evaluation import administer  # noqa: E402

    with open(args.results) as f:
        results = json.load(f)

    # Run from the repository root or from anywhere else: a relative --storage that does not exist where
    # the command was typed is tried again against the repository root before giving up.
    storage = args.storage
    if not os.path.isdir(storage) and not os.path.isabs(storage):
        storage = os.path.join(ROOT, args.storage)

    for name, agent in results["agents"].items():
        scratch_path = f"{storage}/{results['sim']}/personas/{name}/bootstrap_memory/scratch.json"
        with open(scratch_path) as f:
            scratch = json.load(f)
        anchor, has_seed = anchor_of(scratch)
        if not has_seed:
            print(
                f"[persona] {name}: this checkpoint has no seed_currently, so the anchor is the character "
                f"as they had already become. Distances will understate the drift."
            )

        print(f"\n{name}")
        agent["interview"] = score_interview(agent.get("interview", []), anchor, administer.generate)
        for item in agent["interview"]:
            verdict = item.get("persona")
            if verdict:
                print(f"  [{item['kind']:<14}] {verdict['grade']:<13} {verdict['why'][:80]}")
        agent["persona_summary"] = summarise(agent["interview"])
        agent["identity"] = score_identity(scratch, get_embedding, administer.generate)
        report(agent["persona_summary"], agent["identity"])

    out = args.out or args.results
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
