"""
The evaluation batteries: are they measuring what they claim, and are they leaving the run alone?
Three properties matter here and none of them is visible by looking at output.
  * The battery must never write to the simulation it measures. If it did, the instrument would become
    part of the thing being measured, and unevenly so, since the conditions differ precisely in how
    they remember.
  * The same checkpoint must produce the same battery every time. A battery that varied between
    conditions would not be comparing like with like.
  * Fabrication must be scored apart from ordinary error, and abstention must not count as failure.
    Collapsing those categories would let a system that makes agents readier to guess look like an
    improvement.
Probe construction is tested against the committed three-day reference run, so the tests exercise the
real saved artefacts rather than fixtures invented to suit them. The model is replaced by a stub.
"""

import datetime
import json
import pathlib
import random

import pytest

from evaluation import probes, score

REFERENCE = pathlib.Path(__file__).resolve().parents[1] / "environment/frontend_server/storage/control_baseline_3day"  #!
AGENT = "Isabella Rodriguez"
NOW = datetime.datetime(2023, 2, 15, 23, 59, 50)

pytestmark = pytest.mark.skipif(not REFERENCE.exists(), reason="the three-day reference run is not present")


@pytest.fixture
def battery():
    return probes.build(str(REFERENCE / "personas" / AGENT), AGENT, NOW, rng=random.Random(0))


# --- what the battery asks -----------------------------------------------------------------------


def test_probes_are_built_from_the_run_itself(battery):
    """Every probe carries the ground truth it will be scored against."""
    assert battery
    assert all(p["question"] and p["truth"] for p in battery)


def test_the_battery_covers_a_range_of_ages(battery):
    """A single number cannot show degradation; a curve can."""
    ages = {p["age_hours"] for p in battery}
    assert len(ages) >= 3


def test_a_quarter_of_the_battery_is_negative_controls(battery):
    """Fabrication is only measurable by asking about things that never happened."""
    controls = [p for p in battery if p["kind"].startswith("A6")]
    assert len(controls) / len(battery) >= 0.2
    assert all(p["truth"].startswith("NOTHING HAPPENED") for p in controls)


def test_negative_controls_name_people_who_do_not_exist(battery):
    """An agent denying an absurd name has demonstrated nothing, so the invented people are ordinary."""
    nodes = probes.load_nodes(str(REFERENCE / "personas" / AGENT))
    real = {n["subject"] for n in nodes} | {n["object"] for n in nodes}
    invented = [p for p in battery if p["kind"] == "A6_control_person"]
    assert invented
    for p in invented:
        assert not any(name in p["question"] for name in real if len(name) > 4)


def test_the_same_checkpoint_yields_the_same_battery():
    """Two conditions must be asked identical questions, or the comparison is not one."""
    a = probes.build(str(REFERENCE / "personas" / AGENT), AGENT, NOW, rng=random.Random(0))
    b = probes.build(str(REFERENCE / "personas" / AGENT), AGENT, NOW, rng=random.Random(0))
    assert [p["question"] for p in a] == [p["question"] for p in b]


def test_probes_never_ask_about_idle(battery):
    """Half the store is "X is idle"; asking about it would measure nothing of interest."""
    assert not any("is idle" in p["truth"] for p in battery)


def test_no_probe_type_asks_the_same_thing_three_times(battery):
    """
    The failure the pilot caught twice. Fixed ages from a midnight checkpoint asked "what were you
    doing?" and were answered "sleeping" every time, and the place probes all landed on the cafe. An
    answer that is the same at every age is guessable without remembering anything and cannot show
    degradation, whichever probe type it belongs to.
    """
    by_kind = {}
    for p in battery:
        by_kind.setdefault(p["kind"], []).append(p["truth"])
    for kind, truths in by_kind.items():
        if len(truths) > 1:
            assert len(set(truths)) == len(truths), f"{kind} asks about the same thing more than once"


def test_place_probes_are_recovered_without_the_movement_files(battery):
    """
    The movement files are not committed — one per step, 25,920 of them — so where an agent was has to
    come from what it perceived: an agent only sees objects near it, so their addresses locate it.
    """
    places = [p for p in battery if p["kind"] == "A4_place"]
    assert places
    assert all(p["truth"] and ":" not in p["truth"] for p in places)


# --- the interview -------------------------------------------------------------------------------


def test_the_interview_is_eight_fixed_questions():
    asked = probes.interview("You are asked to do something unlike you. What do you do?")
    assert len(asked) == 8
    assert [q["kind"] for q in asked][0] == "B1_identity"


def test_the_pressure_question_is_built_from_the_character_s_own_traits():
    scratch = probes.load_scratch(str(REFERENCE / "personas" / AGENT))
    seen = {}

    def fake_generate(prompt):
        seen["prompt"] = prompt
        return "A neighbour asks you to spend the whole day alone. What do you do?"

    out = probes.pressure_question(scratch, fake_generate)
    assert scratch["innate"] in seen["prompt"]
    assert out.endswith("What do you do?")


# --- scoring -------------------------------------------------------------------------------------


def judge(grade_):
    return lambda prompt: json.dumps({"grade": grade_, "why": "because"})


def test_a_denial_of_something_that_never_happened_is_correct():
    probe = {"question": "What did you and Ayesha discuss?", "truth": "NOTHING HAPPENED: invented."}
    verdict = score.grade(probe, "I don't remember meeting anyone by that name.", judge("correct"))
    assert verdict["grade"] == "correct"
    assert verdict["reads_as_abstention"]


def test_an_unreadable_judgement_is_recorded_rather_than_guessed():
    probe = {"question": "q", "truth": "t"}
    verdict = score.grade(probe, "an answer", lambda prompt: "I think it was probably fine?")
    assert verdict["grade"] == "unscored"


def test_fabrication_is_counted_separately_from_error():
    scored = [
        {"probe": {"age_hours": 24, "kind": "A1_activity"}, "verdict": {"grade": g}}
        for g in ["correct", "correct", "incorrect", "fabricated", "abstained"]
    ]
    s = score.summarise(scored)
    assert s["overall"]["fabrication"] == pytest.approx(0.2)
    assert s["counts"]["fabricated"] == 1
    assert s["counts"]["incorrect"] == 1


def test_a_correct_denial_does_not_count_towards_recall():
    """
    A negative control asks about something that never happened, so answering it well is a correct
    *denial* and there was nothing to recall. Pooling the two made a well-behaved denial raise the recall
    rate, which flatters the number and moves it for reasons unconnected to memory.
    """
    scored = [
        {"probe": {"age_hours": 24, "kind": "A1_activity"}, "verdict": {"grade": "incorrect"}},
        {"probe": {"age_hours": 24, "kind": "A6_control_person"}, "verdict": {"grade": "correct"}},
        {"probe": {"age_hours": 24, "kind": "A6_control_event"}, "verdict": {"grade": "correct"}},
    ]
    s = score.summarise(scored)

    assert s["overall"]["n"] == 1  # one real probe, not three
    assert s["overall"]["recall"] == 0.0  # and it was wrong
    assert s["negative_controls"]["n"] == 2
    assert s["negative_controls"]["fabrication"] == 0.0


def test_the_controls_report_invention_on_their_own():
    scored = [
        {"probe": {"age_hours": 24, "kind": "A6_control_person"}, "verdict": {"grade": "fabricated"}},
        {"probe": {"age_hours": 24, "kind": "A6_control_event"}, "verdict": {"grade": "fabricated"}},
        {"probe": {"age_hours": 24, "kind": "A6_control_quote"}, "verdict": {"grade": "correct"}},
    ]
    s = score.summarise(scored)

    assert s["negative_controls"]["fabrication"] == pytest.approx(2 / 3)
    assert s["overall"]["n"] == 0  # no positive probes at all here


def test_abstention_is_not_counted_as_a_wrong_answer():
    """An agent that knows it has forgotten is behaving better than one that invents."""
    abstains = [{"probe": {"age_hours": 24}, "verdict": {"grade": "abstained"}} for _ in range(4)]
    s = score.summarise(abstains)
    assert s["overall"]["fabrication"] == 0
    assert s["overall"]["wrong_when_committed"] == 0
    assert s["overall"]["abstention"] == 1.0


def test_guessing_more_shows_up_even_when_recall_rises():
    """
    The failure mode the split is there to catch: a change that raises recall by making the agent
    willing to guess should be visible, not hidden by a single accuracy number.
    """
    cautious = [
        {"probe": {"age_hours": 24}, "verdict": {"grade": g}}
        for g in ["correct", "abstained", "abstained", "abstained"]
    ]
    reckless = [
        {"probe": {"age_hours": 24}, "verdict": {"grade": g}}
        for g in ["correct", "correct", "fabricated", "fabricated"]
    ]

    a, b = score.summarise(cautious)["overall"], score.summarise(reckless)["overall"]
    assert b["recall"] > a["recall"]  # looks like an improvement
    assert b["fabrication"] > a["fabrication"]  # and is visibly not one
    assert b["wrong_when_committed"] > a["wrong_when_committed"]


def test_a_non_english_reply_is_asked_again():
    """
    The guard against non-English replies lives inside gpt_structure's retry loops, not at the model
    boundary, so the battery bypassed it by calling the model directly. A pilot caught an agent answering
    its persona interview in Chinese, graded as though it were an answer.
    """
    from evaluation import administer

    replies = iter(["回答问题的内容在这里", "回答问题的内容在这里", "I am a sociology student."])
    asked = []

    def fake_request(prompt, attempt=0):
        asked.append(attempt)
        return next(replies)

    administer.ChatGPT_request = fake_request
    administer.forget_answer = lambda prompt, model=None: None
    try:
        assert administer.generate("who are you?") == "I am a sociology student."
        assert asked == [0, 1, 2]  # it escalated rather than re-asking identically
    finally:
        import importlib

        importlib.reload(administer)


def test_exact_matching_needs_no_judge():
    hits = score.exact_hits("She met Klaus at 14:30", "I think I saw Klaus around 14:30")
    assert hits["names_matched"] == ["Klaus"]
    assert hits["times_matched"] == ["14:30"]


def test_rates_break_down_by_age():
    scored = [
        {"probe": {"age_hours": a, "kind": "A1_activity"}, "verdict": {"grade": g}}
        for a, g in [(6, "correct"), (6, "correct"), (72, "incorrect"), (72, "abstained")]
    ]
    s = score.summarise(scored)
    assert s["by_age"]["6h"]["recall"] == 1.0
    assert s["by_age"]["3 days"]["recall"] == 0.0


def test_the_battery_runner_puts_the_backend_on_the_path_by_itself():
    """
    The same ordering bug persona_score had, one file over. run.py imported `persona` relying on the
    modules imported just above it having put the backend directory on the path as a side effect; on one
    machine that ordering did not hold and the battery died with `No module named 'persona'` before
    asking a single question. The probe runs in a subprocess (conftest puts the backend on the path, so
    an in-process check proves nothing) and stubs out run.py's sibling imports, because administer and
    persona_score each add the backend path themselves and would mask a regression: with the stubs in
    place, the persona import at the top of run.py succeeds only if run.py added the path on its own.
    """
    import os
    import subprocess
    import sys
    import textwrap

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    probe = (
        textwrap.dedent("""
      import importlib.util, os, sys, types
      root = %r
      sys.path.insert(0, root)
      backend = os.path.join(root, "reverie", "backend_server")
      if not os.path.exists(os.path.join(backend, "utils.py")):
          spec = importlib.util.spec_from_file_location(
              "utils", os.path.join(backend, "utils_template.py"))
          utils = importlib.util.module_from_spec(spec)
          sys.modules["utils"] = utils
          spec.loader.exec_module(utils)
      import evaluation
      for name in ("administer", "persona_score", "probes", "score"):
          stub = types.ModuleType("evaluation." + name)
          sys.modules["evaluation." + name] = stub
          setattr(evaluation, name, stub)
      import evaluation.run
      print("ok")
  """)
        % root
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=root)

    assert out.stdout.strip() == "ok", out.stderr
