"""
Checking the automatic judge against a human, which every number in the results chapter rests on.

The memory battery is graded by a language model. That is standard practice and it is not free of
problems, so the grades are only usable next to a measured agreement rate with a person: §5.3 commits to
thirty hand-scored items, taken from a pilot rather than at the end, because "is the judge trustworthy"
and "is the result flattering" are different questions and the first cannot be answered after seeing the
answer to the second.

Two steps.

    uv run python evaluation/agreement.py --sample results/baseline_3_day3.json
    ... open results/handscore.md, write a grade after each "Your grade:", save ...
    uv run python evaluation/agreement.py --score results/handscore.md

The sheet is Markdown by default, one item per section with the question, the record and the answer each
given their own paragraph. A spreadsheet was the obvious format and it was the wrong one: these are three
paragraphs of prose per row, and in a text editor a CSV wraps them into an unreadable block. Pass a path
ending in `.csv` if a spreadsheet is wanted instead; both are read back.

The sheet deliberately does **not** contain the judge's grade. Seeing it first is the difference between
scoring an answer and agreeing with a machine, and there is no way to undo having seen it. It does carry
the grading rules, in the same words the judge is given, because agreement between two people applying
different definitions measures nothing.

Agreement is reported three ways, because one number would hide the thing worth knowing. The **raw**
rate is the share of items scored identically. **Randolph's free-marginal kappa** corrects for agreement
that chance alone would produce, and is the figure SOTOPIA reports for the comparable judgement, where
Zhou et al. (2024) measure κ = 0.503 between their model judge and human annotators. And the
**confusion table** shows *where* the disagreements fall, which matters more than their number here: this
project's central claim distinguishes a wrong answer from an invented one, so a judge that muddles
`incorrect` and `fabricated` is a problem however high its overall agreement, while one that muddles
`correct` and `partial` is largely harmless.
"""

import argparse
import csv
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from evaluation.score import CATEGORIES  # noqa: E402

COLUMNS = ["id", "agent", "kind", "age_hours", "question", "record_says", "answer_given", "your_grade"]


def items(results):
    """Every graded probe in a results file, flattened, with a stable id."""
    out = []
    for agent, block in results.get("agents", {}).items():
        for index, scored in enumerate(block.get("probes", [])):
            probe = scored.get("probe", {})
            out.append({
                "id": f"{agent.split()[0].lower()}-{index:02d}",
                "agent": agent,
                "kind": probe.get("kind", ""),
                "age_hours": probe.get("age_hours", ""),
                "question": probe.get("question", ""),
                "record_says": probe.get("truth", ""),
                "answer_given": scored.get("answer", ""),
                "judge": scored.get("verdict", {}).get("grade", ""),
            })
    return out


def sample(all_items, size=30, seed=0):
    """
    A sample spread across the judge's own categories rather than drawn at random.
    A purely random sample of thirty from a run where a third of answers are fabricated would carry only a
    handful of the category the whole argument turns on. Taking a share from each category instead means
    every category is checked, at the cost of a sample that is not representative of the run's proportions,
    which is the right trade here: the question is whether the judge applies each label correctly, not how
    often each label occurs.
    """
    rng = random.Random(seed)
    by_grade = {}
    for item in all_items:
        by_grade.setdefault(item["judge"], []).append(item)

    chosen, grades = [], sorted(by_grade)
    if not grades:
        return []
    per_grade = max(1, size // len(grades))
    for grade in grades:
        pool = sorted(by_grade[grade], key=lambda i: i["id"])
        chosen.extend(rng.sample(pool, min(per_grade, len(pool))))

    # Top up to the requested size from whatever is left, so a run with few categories still gives a
    # full sheet.
    remaining = sorted((i for i in all_items if i not in chosen), key=lambda i: i["id"])
    rng.shuffle(remaining)
    chosen.extend(remaining[: max(0, size - len(chosen))])
    return sorted(chosen, key=lambda i: i["id"])


RULES = """Grade each answer against what the record says, using these five, which are the same
definitions the automatic judge is given:

- **correct** — it matches the record in substance, whatever the wording.
- **partial** — part of it is right and the rest is vague or missing rather than wrong.
- **incorrect** — it is wrong, but hedged, vague or thin.
- **fabricated** — it is wrong AND specific: a confident, detailed account of something that did not
  happen, of the kind a listener would take as fact. The line between this and *incorrect* is about
  confident specificity rather than about how wrong the answer is, and it is the most important
  judgement here.
- **abstained** — it says it does not remember, or that the thing did not happen.

Where the record begins with NOTHING HAPPENED the question was about something that never occurred: a
denial is **correct** and any account of the event is **fabricated**.

Write your grade after "Your grade:" in each section. Leave any you are unsure of blank; blanks are
reported and excluded rather than counted against the judge."""


# The probe codes are internal; a person scoring should be told what was asked, not the code. Control
# probes are labelled neutrally, because the record they are shown already says NOTHING HAPPENED and the
# automatic judge sees exactly the same line, so neither is given more than the other.
KINDS = {
    "A1_activity": "what they were doing",
    "A2_conversation": "a conversation",
    "A3_learned": "what they learned from someone",
    "A4_place": "where they were",
    "A5_plan": "their plan for the day",
}


def _asked_about(kind):
    if str(kind).startswith("A6"):
        return "a check question"  # phrased so the header gives nothing the judge did not also see
    return KINDS.get(kind, str(kind).split("_", 1)[-1].replace("_", " "))


def _age(hours):
    """How long ago, in the units a person would use when judging whether an answer is plausible."""
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        return ""
    if hours < 24:
        return f"{hours} hours ago"
    days = round(hours / 24)
    return f"about {days} day{'s' if days != 1 else ''} ago"


def _wrapped(text, width=96):
    """Wrap prose so that a paragraph is readable in a plain text editor."""
    import textwrap

    paragraphs = str(text or "").split("\n")
    return "\n".join(textwrap.fill(p, width=width) if p.strip() else "" for p in paragraphs)


def write_sheet(chosen, path):
    """
    The sheet a person fills in. The judge's grade is not written to it, in either format.

    Markdown unless the path says `.csv`. The first version of this wrote only CSV, which put three
    paragraphs of prose into one row and was unreadable in an editor.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if str(path).endswith(".csv"):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            for item in chosen:
                writer.writerow({k: item.get(k, "") for k in COLUMNS})
        return path

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Hand-scoring sheet: {len(chosen)} answers\n\n{RULES}\n\n---\n")
        for item in chosen:
            kind = _asked_about(item.get("kind"))
            when = _age(item.get("age_hours"))
            f.write(f"\n## {item['id']}\n\n")
            f.write(f"*{item.get('agent', '')} · {kind} · {when}*\n\n")
            f.write(f"**The question**\n\n{_wrapped(item.get('question'))}\n\n")
            f.write(f"**What the record says**\n\n{_wrapped(item.get('record_says'))}\n\n")
            f.write(f"**What the agent answered**\n\n{_wrapped(item.get('answer_given'))}\n\n")
            f.write("**Your grade:** \n\n---\n")
    return path


_SECTION = re.compile(r"^##\s+(\S+)\s*$")
_GRADE = re.compile(r"^\*\*Your grade:\*\*\s*(.*?)\s*$")


def read_sheet(path):
    """Read either format back into the same list of rows."""
    if str(path).endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            return [row for row in csv.DictReader(f)]

    rows, current, awaiting = [], None, False
    with open(path, encoding="utf-8") as f:
        for line in f:
            text = line.rstrip()
            heading = _SECTION.match(text)
            if heading:
                current = {"id": heading.group(1), "your_grade": ""}
                rows.append(current)
                awaiting = False
                continue

            grade = _GRADE.match(text)
            if grade and current is not None:
                current["your_grade"] = grade.group(1)
                # Allow grades to be written on a different line.
                awaiting = not grade.group(1)
                continue

            if awaiting and current is not None:
                if text.strip().startswith("---"):
                    awaiting = False
                elif text.strip():
                    current["your_grade"] = text.strip()
                    awaiting = False
    return rows


def randolph_kappa(observed, categories):
    """
    Free-marginal kappa: how much better than chance the agreement is, where chance is a uniform guess
    across the available categories rather than a guess weighted by how often each was used.
    The free-marginal form is used because the categories here are fixed in advance and a judge is not
    choosing how often to use each one. It is also the figure the comparable published measurement
    reports, which makes the two numbers readable against each other.
    """
    k = len(categories)
    if k < 2:
        return None
    return (observed - 1.0 / k) / (1.0 - 1.0 / k)


def compare(rows, judged):
    """
    Compare a filled-in sheet against the judge. `judged` maps item id to the judge's grade.
    Rows left blank are reported and excluded rather than counted as disagreement, since an unscored item
    is not a disagreement and counting it as one would understate the judge.
    """
    pairs, skipped, unknown = [], 0, []
    for row in rows:
        mine = (row.get("your_grade") or "").strip().lower()
        if not mine:
            skipped += 1
            continue
        if mine not in CATEGORIES:
            unknown.append((row.get("id"), mine))
            continue
        pairs.append((row["id"], mine, judged.get(row["id"], "")))

    agreed = sum(1 for _, mine, theirs in pairs if mine == theirs)
    observed = agreed / len(pairs) if pairs else None
    confusion = {}
    for _, mine, theirs in pairs:
        confusion.setdefault(mine, {}).setdefault(theirs, 0)
        confusion[mine][theirs] += 1

    return {
        "n": len(pairs),
        "skipped": skipped,
        "unknown": unknown,
        "agreed": agreed,
        "raw": observed,
        "kappa": randolph_kappa(observed, CATEGORIES) if observed is not None else None,
        "confusion": confusion,
    }


def report(result, out=None):
    # Resolved here rather than in the signature: a default argument binds `sys.stdout` once, when the
    # module is imported, so anything that replaces it afterwards is written past rather than to.
    out = out or sys.stdout
    if not result["n"]:
        print("No rows were scored. Fill in the your_grade column and run this again.", file=out)
        return
    print(
        f"{result['agreed']} of {result['n']} items agree "
        f"({result['raw']:.0%}), Randolph's free-marginal kappa {result['kappa']:.3f}",
        file=out,
    )
    if result["skipped"]:
        print(f"{result['skipped']} rows were left blank and are not counted.", file=out)
    for item_id, grade in result["unknown"]:
        print(f"row {item_id}: {grade!r} is not one of {', '.join(CATEGORIES)}", file=out)

    print("\nwhere the disagreements are (rows: yours, columns: the judge's)", file=out)
    present = [
        c for c in CATEGORIES if c in result["confusion"] or any(c in row for row in result["confusion"].values())
    ]
    print(f"{'':<12}" + "".join(f"{c[:10]:>12}" for c in present), file=out)
    for mine in present:
        row = result["confusion"].get(mine, {})
        print(f"{mine[:12]:<12}" + "".join(f"{row.get(theirs, 0):>12}" for theirs in present), file=out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", help="a results file to draw a hand-scoring sheet from")
    ap.add_argument(
        "--out",
        default="results/handscore.md",
        help="where to write the sheet; end it in .csv for a spreadsheet instead",
    )
    ap.add_argument("--size", type=int, default=30, help="how many items to draw")
    ap.add_argument("--seed", type=int, default=0, help="so the same sheet can be drawn twice")
    ap.add_argument("--score", help="a filled-in sheet to compare against the judge")
    ap.add_argument("--against", help="the results file the sheet came from (default: recorded in it)")
    args = ap.parse_args()

    if args.sample:
        with open(args.sample) as f:
            results = json.load(f)
        chosen = sample(items(results), args.size, args.seed)
        write_sheet(chosen, args.out)
        print(f"{len(chosen)} items written to {args.out}, drawn from {results.get('sim')}.")
        print("Grade each one with: " + ", ".join(CATEGORIES))
        print("The judge's own grades are deliberately not in the file.")
        return

    if args.score:
        rows = read_sheet(args.score)
        source = args.against or _source_of(rows, args.score)
        with open(source) as f:
            results = json.load(f)
        judged = {item["id"]: item["judge"] for item in items(results)}
        report(compare(rows, judged))
        return

    ap.error("give either --sample or --score")


def _source_of(rows, sheet_path):
    """Find the results file a sheet came from, by looking for one that holds all of its ids."""
    folder = os.path.dirname(os.path.abspath(sheet_path)) or "."
    wanted = {row["id"] for row in rows}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name)) as f:
                candidate = json.load(f)
            if wanted <= {item["id"] for item in items(candidate)}:
                return os.path.join(folder, name)
        except (ValueError, KeyError, OSError):
            continue
    raise SystemExit(f"Could not tell which results file {sheet_path} came from; pass --against.")


if __name__ == "__main__":
    main()
