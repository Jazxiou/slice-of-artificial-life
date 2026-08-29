"""
Checking the judge against a human.
Three things have to hold. The sheet must not carry the judge's grades, because a person who has seen
them is agreeing rather than scoring and there is no undoing it. The sample must reach every category,
since a random thirty from a run would carry only a handful of the one category the argument turns on.
And the arithmetic must be right, so the kappa is checked against cases whose value can be worked out by
hand.
"""

import json

import pytest

from evaluation import agreement


def results(grades, agent="Klaus Mueller"):
    return {
        "sim": "test",
        "agents": {
            agent: {
                "probes": [
                    {
                        "probe": {"kind": "A1_activity", "age_hours": 6, "question": f"q{i}", "truth": f"t{i}"},
                        "answer": f"a{i}",
                        "verdict": {"grade": grade},
                    }
                    for i, grade in enumerate(grades)
                ]
            }
        },
    }


ALL_FIVE = ["correct", "partial", "incorrect", "fabricated", "abstained"]


# --- the sheet -------------------------------------------------------------------------------------


def test_the_csv_sheet_does_not_contain_the_judges_grade(tmp_path):
    """The one property that cannot be recovered if it is got wrong."""
    path = agreement.write_sheet(agreement.items(results(["fabricated"] * 3)), tmp_path / "s.csv")
    text = open(path).read()

    assert "fabricated" not in text
    assert "your_grade" in text


def test_the_markdown_sheet_does_not_contain_the_judges_grade_either(tmp_path):
    """
    The rules block names every category, including this one, so the check is that no *item* carries a
    grade: every "Your grade:" line comes back empty when the sheet is read.
    """
    path = agreement.write_sheet(agreement.items(results(["fabricated"] * 3)), tmp_path / "s.md")

    assert all(row["your_grade"] == "" for row in agreement.read_sheet(path))


def test_the_csv_sheet_carries_what_is_needed_to_score_an_item(tmp_path):
    path = agreement.write_sheet(agreement.items(results(["correct"])), tmp_path / "s.csv")
    row = agreement.read_sheet(path)[0]

    assert row["question"] == "q0" and row["record_says"] == "t0" and row["answer_given"] == "a0"
    assert row["your_grade"] == ""


def test_the_markdown_sheet_gives_each_part_its_own_paragraph(tmp_path):
    """
    A spreadsheet was the first format and it was the wrong one: three paragraphs of prose in one row are
    unreadable in a text editor, which is where this is actually filled in.
    """
    path = agreement.write_sheet(agreement.items(results(["correct"])), tmp_path / "s.md")
    text = open(path).read()

    assert "## klaus-00" in text
    assert "**The question**\n\nq0" in text
    assert "**What the record says**\n\nt0" in text
    assert "**What the agent answered**\n\na0" in text
    assert "**Your grade:**" in text


def test_the_markdown_sheet_carries_the_grading_rules(tmp_path):
    """
    Two people applying different definitions of "fabricated" would agree or disagree for reasons that
    have nothing to do with the judge, so the sheet states the same rules the judge is given.
    """
    path = agreement.write_sheet(agreement.items(results(["correct"])), tmp_path / "s.md")
    text = open(path).read()

    assert "confident specificity" in text
    assert "NOTHING HAPPENED" in text


def test_a_filled_in_markdown_sheet_reads_back(tmp_path):
    path = agreement.write_sheet(agreement.items(results(["correct", "partial", "fabricated"])), tmp_path / "s.md")
    filled = open(path).read().replace("**Your grade:** \n", "**Your grade:** partial\n")
    open(path, "w").write(filled)

    rows = agreement.read_sheet(path)
    assert [row["id"] for row in rows] == ["klaus-00", "klaus-01", "klaus-02"]
    assert all(row["your_grade"] == "partial" for row in rows)


def test_a_half_filled_markdown_sheet_keeps_the_blanks_blank(tmp_path):
    path = agreement.write_sheet(agreement.items(results(["correct", "partial"])), tmp_path / "s.md")
    text = open(path).read()
    head, _, tail = text.partition("**Your grade:** ")
    open(path, "w").write(head + "**Your grade:** correct" + tail)

    rows = agreement.read_sheet(path)
    assert rows[0]["your_grade"] == "correct"
    assert rows[1]["your_grade"] == ""


def test_long_prose_is_wrapped_rather_than_left_on_one_line(tmp_path):
    long_answer = ["correct"]
    block = results(long_answer)
    block["agents"]["Klaus Mueller"]["probes"][0]["answer"] = "word " * 200
    path = agreement.write_sheet(agreement.items(block), tmp_path / "s.md")

    assert max(len(line) for line in open(path).read().split("\n")) < 120


def test_the_age_is_shown_in_units_a_person_would_use():
    assert agreement._age(6) == "6 hours ago"
    assert agreement._age(53) == "about 2 days ago"
    assert agreement._age(24) == "about 1 day ago"
    assert agreement._age("") == ""


def test_a_control_probe_is_labelled_without_giving_more_away_than_the_judge_sees():
    """The record shown already begins NOTHING HAPPENED, and the judge sees that same line."""
    assert agreement._asked_about("A6_control_person") == "a check question"
    assert agreement._asked_about("A1_activity") == "what they were doing"


# --- the sample ------------------------------------------------------------------------------------


def test_every_category_the_judge_used_appears_in_the_sample():
    """
    A third of the answers in a real run are fabricated and very few are abstentions. Drawn at random,
    thirty items would barely test the categories the argument depends on.
    """
    lopsided = ["correct"] * 40 + ["fabricated"] * 2 + ["abstained"] * 1
    chosen = agreement.sample(agreement.items(results(lopsided)), size=9)

    assert {item["judge"] for item in chosen} == {"correct", "fabricated", "abstained"}


def test_the_same_sheet_can_be_drawn_twice():
    all_items = agreement.items(results(ALL_FIVE * 8))
    assert agreement.sample(all_items, 15, seed=3) == agreement.sample(all_items, 15, seed=3)


def test_a_small_run_gives_what_it_has_rather_than_failing():
    chosen = agreement.sample(agreement.items(results(["correct", "partial"])), size=30)
    assert len(chosen) == 2


def test_nothing_is_drawn_twice():
    chosen = agreement.sample(agreement.items(results(ALL_FIVE * 10)), size=30)
    assert len({item["id"] for item in chosen}) == len(chosen)


# --- the arithmetic --------------------------------------------------------------------------------


def test_perfect_agreement_is_one():
    assert agreement.randolph_kappa(1.0, ALL_FIVE) == pytest.approx(1.0)


def test_chance_agreement_is_zero():
    """With five categories, a judge guessing uniformly agrees a fifth of the time."""
    assert agreement.randolph_kappa(0.2, ALL_FIVE) == pytest.approx(0.0)


def test_worse_than_chance_is_negative():
    assert agreement.randolph_kappa(0.1, ALL_FIVE) < 0


def test_a_worked_case():
    """0.6 observed over five categories: (0.6 - 0.2) / (1 - 0.2) = 0.5."""
    assert agreement.randolph_kappa(0.6, ALL_FIVE) == pytest.approx(0.5)


# --- comparing -------------------------------------------------------------------------------------


def sheet(pairs):
    """Rows as they come back from a filled-in sheet: (id, what the person wrote)."""
    return [{"id": item_id, "your_grade": mine} for item_id, mine in pairs]


def test_agreement_is_counted_over_the_rows_that_were_scored():
    judged = {"klaus-00": "correct", "klaus-01": "fabricated", "klaus-02": "partial"}
    result = agreement.compare(
        sheet([("klaus-00", "correct"), ("klaus-01", "fabricated"), ("klaus-02", "incorrect")]), judged
    )

    assert result["n"] == 3
    assert result["agreed"] == 2
    assert result["raw"] == pytest.approx(2 / 3)


def test_a_blank_row_is_not_a_disagreement():
    """Counting an unscored item as a disagreement would understate the judge."""
    judged = {"klaus-00": "correct", "klaus-01": "correct"}
    result = agreement.compare(sheet([("klaus-00", "correct"), ("klaus-01", "")]), judged)

    assert result["n"] == 1
    assert result["skipped"] == 1
    assert result["raw"] == 1.0


def test_a_grade_that_is_not_a_category_is_reported_rather_than_counted():
    result = agreement.compare(
        sheet([("klaus-00", "good"), ("klaus-01", "correct")]), {"klaus-00": "correct", "klaus-01": "correct"}
    )

    assert result["unknown"] == [("klaus-00", "good")]
    assert result["n"] == 1


def test_the_confusion_table_says_where_the_disagreement_is():
    """
    The number that matters most for this project. Muddling correct with partial is harmless; muddling
    incorrect with fabricated attacks the distinction the whole memory claim rests on.
    """
    judged = {"a": "fabricated", "b": "fabricated", "c": "correct"}
    result = agreement.compare(sheet([("a", "incorrect"), ("b", "incorrect"), ("c", "correct")]), judged)

    assert result["confusion"]["incorrect"]["fabricated"] == 2
    assert result["confusion"]["correct"]["correct"] == 1


def test_case_and_spacing_in_a_filled_in_sheet_are_forgiven():
    result = agreement.compare([{"id": "a", "your_grade": " Correct "}], {"a": "correct"})
    assert result["agreed"] == 1


def test_an_empty_sheet_reports_rather_than_dividing_by_zero(capsys):
    agreement.report(agreement.compare(sheet([("a", "")]), {"a": "correct"}))
    assert "No rows were scored" in capsys.readouterr().out


def test_a_grade_written_on_the_line_below_is_read(tmp_path):
    """
    The natural way to fill the sheet in, and what the first person to use it did. The parser read only
    the same line, so a completed sheet came back as thirty blanks and would have reported no agreement
    at all.
    """
    path = agreement.write_sheet(agreement.items(results(["correct", "partial"])), tmp_path / "s.md")
    filled = open(path).read().replace("**Your grade:** \n", "**Your grade:** \n\nfabricated\n")
    open(path, "w").write(filled)

    assert [row["your_grade"] for row in agreement.read_sheet(path)] == ["fabricated", "fabricated"]


def test_an_unanswered_section_stays_blank_when_grades_may_be_on_the_next_line(tmp_path):
    """The lookahead must stop at the section's own rule, or a blank would swallow the next heading."""
    path = agreement.write_sheet(agreement.items(results(["correct", "partial"])), tmp_path / "s.md")

    assert [row["your_grade"] for row in agreement.read_sheet(path)] == ["", ""]
