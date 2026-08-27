"""
Scoring answers against the ground truth.

Exact matching handles what can be checked without judgement, which is
times, names and places, and it needs no model. Everything else goes to
a language model with the ground truth supplied.

Five categories:
    1. Correct
    2. Partial
    3. Incorrect
    4. Fabricated
    5. Abstained
"""

import json
import re
import sys

CATEGORIES = ("correct", "partial", "incorrect", "fabricated", "abstained")

JUDGE_PROMPT = """You are grading one answer against a record of what actually happened.

The question asked: !<QUESTION>!

What the record says: !<TRUTH>!

The answer given: !<ANSWER>!

Grade the answer as exactly one of:
  correct    - it matches the record in substance, whatever the wording
  partial    - it gets part of it right, and the rest is vague or missing rather than wrong
  incorrect  - it is wrong, but hedged, vague or thin: it gets the thing muddled
  fabricated - it is wrong AND specific: it gives a confident, detailed account of something that did
               not happen, of the kind a listener would take as fact
  abstained  - it says it does not remember, or that the thing did not happen

The line between "incorrect" and "fabricated" is the most important judgement you make here, and it is
about *confident specificity*, not about how wrong the answer is. "I think we talked about the cafe,
maybe" contradicting a record of a conversation about a research paper is **incorrect**. "We discussed
the photo booth ideas and finalised the dinner plans" contradicting that same record is **fabricated**,
because it invents circumstantial detail that reads as a memory. This applies to every question, not
only to the ones about things that never happened.

If the record begins with "NOTHING HAPPENED", then the question was about something that never occurred.
In that case a denial or an admission of not knowing is **correct**, and any confident account of the
event is **fabricated**.

Reply with a JSON object and nothing else: {"grade": "...", "why": "one short sentence"}"""


_ABSTENTION = re.compile(
    r"\b(don'?t (remember|recall|know)|no (memory|recollection)|not sure|cannot recall|"
    r"didn'?t happen|never (met|happened|went|spoke)|no such)\b",
    re.I,
)


def looks_like_abstention(answer):
    """A pre-check."""
    return bool(_ABSTENTION.search(answer or ""))


def exact_hits(truth, answer):
    """
    What can be checked without an LLM: times, dates, proper names and
    numbers shared with the record.

    Returned as a dictionary to check correctness.
    """

    def tokens(text):
        times = set(re.findall(r"\b\d{1,2}:\d{2}\b", text or ""))
        names = set(re.findall(r"\b[A-Z][a-z]{2,}\b", text or ""))
        numbers = set(re.findall(r"\b\d+\b", text or ""))
        return times, names, numbers

    t_times, t_names, t_numbers = tokens(truth)
    a_times, a_names, a_numbers = tokens(answer)
    return {
        "times_matched": sorted(t_times & a_times),
        "names_matched": sorted(t_names & a_names),
        "numbers_matched": sorted(t_numbers & a_numbers),
        "times_expected": len(t_times),
        "names_expected": len(t_names),
    }


def grade(probe, answer, generate):
    """Grades one answer, also testable without an LLM server."""
    prompt = (
        JUDGE_PROMPT
        .replace("!<QUESTION>!", probe["question"])
        .replace("!<TRUTH>!", probe["truth"])
        .replace("!<ANSWER>!", answer)
    )
    raw = generate(prompt)

    verdict = {"grade": "unscored", "why": "the judge's reply could not be read"}
    try:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            parsed = json.loads(match.group(0))
            if parsed.get("grade") in CATEGORIES:
                verdict = {"grade": parsed["grade"], "why": str(parsed.get("why", ""))[:200]}
    except (ValueError, TypeError):
        pass

    verdict["exact"] = exact_hits(probe["truth"], answer)
    verdict["reads_as_abstention"] = looks_like_abstention(answer)
    return verdict


def _is_control(item):
    return str(item["probe"].get("kind", "")).startswith("A6")


# Grouping
AGE_BANDS = ((12, "6h"), (36, "1 day"), (60, "2 days"), (10**6, "3 days"))


def age_band(hours):
    for limit, label in AGE_BANDS:
        if hours <= limit:
            return label
    return AGE_BANDS[-1][1]


def _band_order(label):
    return [name for _, name in AGE_BANDS].index(label)


def summarise(scored):
    """Recall and fabrication rates, broken down by probe age."""
    positives = [s for s in scored if not _is_control(s)]
    controls = [s for s in scored if _is_control(s)]

    by_age = {}
    totals = dict.fromkeys(CATEGORIES + ("unscored",), 0)
    for item in positives:
        grade_ = item["verdict"]["grade"]
        totals[grade_] = totals.get(grade_, 0) + 1
        band = age_band(item["probe"]["age_hours"])
        bucket = by_age.setdefault(band, dict.fromkeys(CATEGORIES + ("unscored",), 0))
        bucket[grade_] = bucket.get(grade_, 0) + 1

    def rates(counts):
        n = sum(counts.values())
        # Avoid division by 0
        divisor = n or 1
        answered = n - counts.get("abstained", 0) - counts.get("unscored", 0)
        return {
            "n": n,
            "recall": (counts.get("correct", 0) + 0.5 * counts.get("partial", 0)) / divisor,
            "fabrication": counts.get("fabricated", 0) / divisor,
            "abstention": counts.get("abstained", 0) / divisor,
            # Of the answers where the agent did commit to something,
            # how many were wrong?
            "wrong_when_committed": ((counts.get("incorrect", 0) + counts.get("fabricated", 0)) / answered)
            if answered
            else 0.0,
        }

    control_counts = dict.fromkeys(CATEGORIES + ("unscored",), 0)
    for item in controls:
        g = item["verdict"]["grade"]
        control_counts[g] = control_counts.get(g, 0) + 1
    invented = control_counts.get("fabricated", 0)

    return {
        "overall": rates(totals),
        "by_age": {band: rates(counts) for band, counts in sorted(by_age.items(), key=lambda kv: _band_order(kv[0]))},
        "counts": totals,
        "negative_controls": {
            "n": len(controls),
            "fabricated": invented,
            "fabrication": invented / len(controls) if controls else 0.0,
            "counts": control_counts,
        },
    }


def report(summary, out=sys.stdout):
    o = summary["overall"]
    c = summary.get("negative_controls", {})
    print(
        f"  positive probes: {o['n']}   recall {o['recall']:.0%}   fabrication {o['fabrication']:.0%}   "
        f"abstention {o['abstention']:.0%}",
        file=out,
    )
    if c.get("n"):
        print(
            f"  negative controls: {c['n']}   invented an account {c['fabricated']} times ({c['fabrication']:.0%})",
            file=out,
        )
    for band, r in summary.get("by_age", {}).items():
        print(
            f"    {band:>7} ago: n={r['n']:<3} recall {r['recall']:.0%}  "
            f"fabrication {r['fabrication']:.0%}  abstention {r['abstention']:.0%}",
            file=out,
        )
    if summary["counts"].get("unscored"):
        print(
            f"  ** {summary['counts']['unscored']} answers could not be graded and are excluded from "
            f"nothing: they are counted in n, so the rates are conservative.",
            file=out,
        )
