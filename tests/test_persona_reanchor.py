"""
Persona re-anchoring: does it hold a character to who they were without freezing them?
The mechanism has to fail in two directions and does neither well by accident, so both are pinned here.
If it corrects too eagerly it becomes pinning, and a character who cannot change is not believable; the
thesis claims specifically that drift falls *while believable adaptation is preserved*, and a measure
that treats all change as failure would reward the worse system. If it corrects too rarely it does
nothing at all, and the ablation would compare a condition against itself.
The other property tested here is the one the whole ablation rests on: with the flag off, the proposed
status is returned exactly as written. The day's drift is still measured and recorded, because the
measurement belongs to both conditions and only the correction is under study.
The embedding model and the language model are both replaced by stubs.
"""

import datetime
import types

import pytest
from memory_ext import persona as reanchor

SEED = "Klaus Mueller is writing a research paper on the effects of gentrification in low-income communities."
DRIFTED = (
    "Klaus had a productive start to Wednesday February 15 with Isabella preparing his favorite "
    "breakfast. He spent the morning reviewing plans for the Valentine's Day event at Hobbs Cafe."
)
# The same drift with the dates taken out. Two criteria fire independently of each other, so the tests
# for one have to use text the other does not react to, or they would pass for the wrong reason.
DRIFTED_UNDATED = (
    "Klaus Mueller has been helping organise a party at Hobbs Cafe, reviewing plans "
    "with Isabella and arranging the decorations."
)


def scratch(seed=SEED, currently=None):
    return types.SimpleNamespace(
        name="Klaus Mueller",
        innate="analytical, curious, methodical",
        learned="Klaus Mueller is a student at Oak Hill College studying sociology.",
        currently=currently or seed,
        seed_currently=seed,
        curr_time=None,
    )


def embedder(distance):
    """
    A stub embedding whose cosine distance from the anchor is whatever the test asks for.
    Two dimensions are enough: the anchor is (1, 0) and anything else is placed at the angle that gives
    the requested distance, so a test can say "pretend this drifted by 0.5" and mean it.
    """
    import math

    def embed(text):
        if text.startswith("Name: "):  # the anchor, as assembled by anchor_of
            return [1.0, 0.0]
        theta = math.acos(max(-1.0, min(1.0, 1.0 - distance)))
        return [math.cos(theta), math.sin(theta)]

    return embed


def rewriter(
    text="Klaus Mueller is a sociology student writing a paper on gentrification, and has "
    "lately been helping with an event at Hobbs Cafe.",
):
    calls = []

    def generate(prompt):
        calls.append(prompt)
        return text

    generate.calls = calls
    return generate


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", False)
    monkeypatch.setattr(reanchor, "PERSONA_DRIFT_MEASURED", True)
    monkeypatch.setattr(reanchor, "REANCHOR_DRIFT_THRESHOLD", 0.35)
    monkeypatch.setattr(reanchor, "REANCHOR_VERBATIM_SEED", True)
    monkeypatch.setattr(reanchor, "REANCHOR_GENRE_TEST", True)


# --- the guarantee -------------------------------------------------------------------------------


def test_with_the_flag_off_the_status_is_returned_untouched():
    write = rewriter()
    text, record = reanchor.reanchor(scratch(), DRIFTED, embedder(0.9), write)

    assert text == DRIFTED
    assert record["corrected"] is False
    assert write.calls == []


def test_with_the_flag_off_the_drift_is_still_measured():
    """
    The control condition needs a drift series too. The claim is that re-anchoring *reduces* drift, and
    a treatment measured against nothing is not a comparison. Measuring changes no agent-visible state.
    """
    write = rewriter()
    text, record = reanchor.reanchor(scratch(), DRIFTED, embedder(0.9), write)

    assert text == DRIFTED
    assert record["drift"] == pytest.approx(0.9)
    assert record["corrected"] is False
    assert write.calls == []  # measured, and left alone


def test_measurement_itself_can_be_turned_off_for_a_pure_baseline(monkeypatch):
    """A bit-for-bit baseline is still available, and separating the two is what makes that possible."""
    monkeypatch.setattr(reanchor, "PERSONA_DRIFT_MEASURED", False)

    def refuse(text):
        raise AssertionError("nothing should be embedded here")

    text, record = reanchor.reanchor(scratch(), DRIFTED, refuse, rewriter())
    assert text == DRIFTED
    assert record["drift"] is None


# --- correcting, and not correcting ---------------------------------------------------------------


def test_a_small_change_is_left_alone(monkeypatch):
    """Believable adaptation. A character who cannot change is not believable either."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    write = rewriter()
    text, record = reanchor.reanchor(scratch(), DRIFTED_UNDATED, embedder(0.10), write)

    assert text == DRIFTED_UNDATED
    assert record["corrected"] is False
    assert record["drift"] == pytest.approx(0.10)
    assert write.calls == []


def test_a_large_change_is_corrected(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    write = rewriter()
    text, record = reanchor.reanchor(scratch(), DRIFTED, embedder(0.80), write)

    assert text != DRIFTED
    assert record["corrected"] is True
    assert record["drift"] == pytest.approx(0.80)
    assert len(write.calls) == 1


def test_the_threshold_is_where_the_behaviour_changes(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    monkeypatch.setattr(reanchor, "REANCHOR_DRIFT_THRESHOLD", 0.5)

    _, just_under = reanchor.reanchor(scratch(), DRIFTED_UNDATED, embedder(0.49), rewriter())
    _, just_over = reanchor.reanchor(scratch(), DRIFTED_UNDATED, embedder(0.51), rewriter())

    assert just_under["corrected"] is False
    assert just_over["corrected"] is True


# --- what it anchors to --------------------------------------------------------------------------


def test_the_anchor_is_the_seed_not_the_current_state():
    """
    The point of the mechanism. `currently` is rewritten daily from its own previous value, so anchoring
    a run to its present state would compare the character to yesterday's drift and find no drift at all.
    """
    drifted_now = scratch(seed=SEED, currently=DRIFTED)
    anchor = reanchor.anchor_of(drifted_now)

    assert "research paper" in anchor
    assert "Hobbs Cafe" not in anchor


def test_the_anchor_carries_the_immutable_traits_too():
    anchor = reanchor.anchor_of(scratch())
    assert "sociology" in anchor and "analytical" in anchor


def test_without_a_seed_the_present_state_is_used_and_that_is_the_best_available():
    """An older checkpoint has no seed recorded; anchoring to what it has is the only option left."""
    no_seed = scratch()
    no_seed.seed_currently = None
    no_seed.currently = DRIFTED

    assert "Hobbs Cafe" in reanchor.anchor_of(no_seed)


# --- failure modes -------------------------------------------------------------------------------


def test_a_failed_measurement_is_not_treated_as_zero_drift(monkeypatch):
    """The dangerous silent failure: an unmeasurable drift must not read as a character who has not moved."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)

    def broken(text):
        raise RuntimeError("no embedding model")

    write = rewriter()
    text, record = reanchor.reanchor(scratch(), DRIFTED_UNDATED, broken, write)

    assert record["drift"] is None
    assert record["corrected"] is False
    assert write.calls == []  # and it does not rewrite blind


def test_an_empty_rewrite_keeps_the_drifted_status(monkeypatch):
    """Better a drifted character than an empty identity in every prompt the agent sees."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    text, record = reanchor.reanchor(scratch(), DRIFTED, embedder(0.9), rewriter(text="   "))

    assert text == DRIFTED
    assert record["corrected"] is False


def test_the_record_is_written_whether_or_not_it_fired(monkeypatch):
    """A drift series per agent per day is the measurement; a verdict alone would not be one."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    _, small = reanchor.reanchor(scratch(), DRIFTED_UNDATED, embedder(0.1), rewriter())
    _, large = reanchor.reanchor(scratch(), DRIFTED_UNDATED, embedder(0.9), rewriter())

    assert small["drift"] is not None and large["drift"] is not None
    assert small["threshold"] == large["threshold"] == 0.35
    assert "drift_after" in large and "drift_after" not in small


# --- the second criterion: has it stopped being a description of a person? -------------------------
#
# Added after the first three-day run. Re-anchoring corrected five of six identity rewrites and missed
# the one that mattered most: Isabella's status for the 15th was a paragraph about her afternoon and
# measured *below* the threshold, because her seed is itself about the Valentine's party, so party
# narration sits close to her anchor. Distance measures content drift and cannot see genre drift.

ISABELLA_SEED = (
    "Isabella Rodriguez is planning on having a Valentine's Day party at Hobbs Cafe with "
    "her customers on February 14th, 2023 at 5pm."
)
ISABELLA_DIARY = (
    "Isabella Rodriguez has successfully launched Hobbs Cafe's Valentine's Day event "
    "with meticulous planning and community collaboration. She dedicated today to "
    "walking through preparations alongside Klaus and Maria at 4 PM."
)


def isabella(currently=None):
    return types.SimpleNamespace(
        name="Isabella Rodriguez",
        innate="friendly, outgoing, hospitable",
        learned="Isabella Rodriguez is a cafe owner of Hobbs Cafe who loves to make people feel welcome.",
        currently=currently or ISABELLA_SEED,
        seed_currently=ISABELLA_SEED,
        curr_time=None,
    )


def test_a_status_that_reads_as_a_day_is_corrected_even_when_it_measures_close(monkeypatch):
    """The case the pilot found, with the real text and a distance well inside the threshold."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    write = rewriter()
    text, record = reanchor.reanchor(isabella(), ISABELLA_DIARY, embedder(0.12), write)

    assert record["drift"] == pytest.approx(0.12)  # nowhere near 0.35
    assert record["corrected"] is True
    assert record["dated"] == ["today"]
    assert record["reason"] == "dated"
    assert len(write.calls) == 1


def test_a_character_may_be_as_dated_as_they_were_written(monkeypatch):
    """
    Isabella's seed names February 14th. A status repeating the date she was written with is still a
    description of her, so only markers the anchor does not carry count. Testing the text in isolation
    would fire on her every single day and turn the mechanism into pinning.
    """
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    still_her = (
        "Isabella Rodriguez is preparing a Valentine's Day party at Hobbs Cafe on "
        "February 14th, and has been gathering decorations with help from her regulars."
    )
    write = rewriter()
    text, record = reanchor.reanchor(isabella(), still_her, embedder(0.12), write)

    assert record["dated"] == []
    assert record["corrected"] is False
    assert text == still_her


def test_a_status_with_no_seed_date_is_flagged_by_one(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    dated = (
        "Klaus Mueller spent Wednesday February 15 continuing his efforts to organize the "
        "Valentine's Day event at Hobbs Cafe."
    )
    _, record = reanchor.reanchor(scratch(), dated, embedder(0.1), rewriter())

    assert record["dated"] == ["february 15", "wednesday"]
    assert record["corrected"] is True


def test_the_genre_test_can_be_turned_off(monkeypatch):
    """It is separable from the distance criterion, so the ablation can attribute the difference."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    monkeypatch.setattr(reanchor, "REANCHOR_GENRE_TEST", False)
    text, record = reanchor.reanchor(isabella(), ISABELLA_DIARY, embedder(0.12), rewriter())

    assert record["corrected"] is False
    assert text == ISABELLA_DIARY


def test_the_genre_test_fires_even_when_the_distance_cannot_be_measured(monkeypatch):
    """
    It does not depend on the embedding model, so unlike the distance criterion it is still a real
    measurement when the model is unavailable, and acting on it is not acting blind.
    """
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)

    def broken(text):
        raise RuntimeError("no embedding model")

    write = rewriter()
    _, record = reanchor.reanchor(isabella(), ISABELLA_DIARY, broken, write)

    assert record["drift"] is None
    assert record["corrected"] is True
    assert len(write.calls) == 1


def test_both_criteria_are_named_when_both_fire(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    _, record = reanchor.reanchor(scratch(), DRIFTED, embedder(0.9), rewriter())

    assert "distance" in record["reason"] and "dated" in record["reason"]


def test_the_record_says_whether_the_rewrite_actually_undated_it(monkeypatch):
    """A correction that fires on the genre test and comes back still dated is a failed correction."""
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    _, good = reanchor.reanchor(isabella(), ISABELLA_DIARY, embedder(0.12), rewriter())
    _, bad = reanchor.reanchor(
        isabella(), ISABELLA_DIARY, embedder(0.12), rewriter(text="Isabella spent today at the cafe.")
    )

    assert good["dated_after"] == []
    assert bad["dated_after"] == ["today"]


def test_an_ordinary_standing_description_is_not_flagged():
    """False positives here would be corrections of characters who were fine, so the bar matters."""
    for text in [
        SEED,
        "Klaus Mueller is a sociology student who opens his day at the library at 8am.",
        "Maria Lopez studies physics and streams on Twitch most evenings.",
    ]:
        assert reanchor.reads_as_a_diary(scratch(), text) == []


def test_the_recorded_condition_names_every_flag_that_changes_what_a_run_produces():
    """
    The trace header is the only record of which condition produced a run. `persona_drift_measured`
    decides whether a drift series exists at all, so a header without it cannot distinguish a condition
    that was measured from one that was not.
    """
    recorded = set(reanchor.config())
    assert {
        "persona_reanchor",
        "persona_drift_measured",
        "reanchor_drift_threshold",
        "reanchor_genre_test",
        "reanchor_verbatim_seed",
    } <= recorded


def test_the_drift_series_is_written_to_the_trace(tmp_path, monkeypatch):
    """
    The record used to exist only in the saved simulation state, which is far larger than a trace and is
    not committed alongside a run, so the two three-day runs of 2026-08-28 produced their drift series
    into a directory and nowhere else. Six records per three-day run cost nothing to write here.
    """
    import json

    import llm_trace

    path = tmp_path / "t.jsonl"
    recorder = llm_trace._Recorder(str(path))
    monkeypatch.setattr(llm_trace, "recorder", recorder)

    llm_trace.drift(
        "Klaus Mueller",
        {"day": "2023-02-14", "drift": 0.42, "threshold": 0.35, "corrected": True, "dated": ["wednesday"]},
    )
    recorder.close() if hasattr(recorder, "close") else None

    written = [json.loads(l) for l in open(path) if l.strip()]
    record = next(r for r in written if r.get("type") == "drift")
    assert record["agent"] == "Klaus Mueller"
    assert record["drift"] == 0.42
    assert record["corrected"] is True
    assert record["dated"] == ["wednesday"]


def test_the_drift_series_survives_a_save(tmp_path):
    """
    It did not. `drift_log` was kept in memory during a run and never written by `Scratch.save()`, so the
    first two three-day runs ended with the second research question's measurement existing nowhere on
    disk. The trace now carries it too, but a checkpoint that loses it silently is the failure that cost
    the numbers, so it is pinned here as well.
    """
    import json

    from persona.memory_structures.scratch import Scratch

    seed = json.load(
        open(
            "environment/frontend_server/storage/base_the_ville_isabella_maria_klaus"
            "/personas/Klaus Mueller/bootstrap_memory/scratch.json"
        )
    )
    first = tmp_path / "scratch.json"
    first.write_text(json.dumps(seed))

    scratch = Scratch(str(first))
    # A seed carries no clock and no action; upstream's save() assumes a run has started.
    scratch.curr_time = datetime.datetime(2023, 2, 15)
    scratch.act_start_time = datetime.datetime(2023, 2, 15)
    scratch.drift_log = [{"day": "2023-02-14", "drift": 0.42, "corrected": True}]
    saved = tmp_path / "again.json"
    scratch.save(str(saved))

    assert Scratch(str(saved)).drift_log == scratch.drift_log


def test_a_checkpoint_written_before_this_still_loads():
    """Older saved states have no drift_log at all, and must not fail to load because of it."""
    import json

    from persona.memory_structures.scratch import Scratch

    path = (
        "environment/frontend_server/storage/base_the_ville_isabella_maria_klaus"
        "/personas/Klaus Mueller/bootstrap_memory/scratch.json"
    )
    assert "drift_log" not in json.load(open(path))
    assert Scratch(path).drift_log == []


def test_several_clock_times_read_as_a_timetable(monkeypatch):
    """
    Klaus finished the control run with this, and the date test alone did not catch it: five clock times
    and no date at all. It is plainly an account of one day rather than a description of a person.
    """
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    timetable = (
        "Klaus Mueller began his day by checking emails at 7:00 am, then proceeded to the "
        "library by 8:00 am. He had lunch from 12:00 pm to 1:00 pm before conducting "
        "interviews until 6:00 pm."
    )
    _, record = reanchor.reanchor(scratch(), timetable, embedder(0.1), rewriter())

    assert record["corrected"] is True
    assert "7am" in record["dated"] and "8am" in record["dated"]


def test_one_clock_time_is_a_routine_and_is_left_alone(monkeypatch):
    """
    The false positive this threshold exists to avoid. "She opens the cafe at 8am" is how a standing
    description of a person with a job actually reads, and correcting it would be the pinning the design
    exists to avoid.
    """
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    routine = "Klaus Mueller is a sociology student who opens his day at the library at 8am."
    text, record = reanchor.reanchor(scratch(), routine, embedder(0.1), rewriter())

    assert record["dated"] == []
    assert record["corrected"] is False
    assert text == routine


def test_a_time_the_character_was_written_with_does_not_count(monkeypatch):
    """Isabella's seed names a party at 5pm, so a status repeating it is still a description of her."""
    seeded = types.SimpleNamespace(
        name="Isabella Rodriguez",
        innate="friendly",
        learned="She owns Hobbs Cafe.",
        currently="",
        seed_currently="Isabella is planning a party at Hobbs Cafe on February 14th, 2023, from 5pm to 7pm.",
        curr_time=None,
    )
    repeats = "Isabella Rodriguez is making ready for the party from 5:00 pm to 7:00 pm at Hobbs Cafe."

    assert reanchor.reads_as_a_diary(seeded, repeats) == []


def test_times_are_normalised_before_they_are_compared():
    assert reanchor.clock_times("from 5pm to 7:00 PM") == {"5pm", "7pm"}


def test_the_rewriter_is_told_todays_date(monkeypatch):
    """
    The anchor is a snapshot, and a snapshot can contain a dated intention that expires mid-run:
    Isabella's seed has her planning a party "on February 14th, 2023", and in the second treatment run
    the correction on the 15th faithfully restored her preparations for a party that had already
    happened. The rewrite therefore has to know what day it is, or it cannot know the past from the
    future.
    """
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    s = scratch()
    s.curr_time = datetime.datetime(2023, 2, 15, 0, 0)
    write = rewriter()
    reanchor.reanchor(s, DRIFTED_UNDATED, embedder(0.80), write)

    assert "Today is Wednesday, February 15, 2023." in write.calls[0]


def test_a_missing_clock_does_not_stop_a_correction(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    write = rewriter()
    text, record = reanchor.reanchor(scratch(), DRIFTED_UNDATED, embedder(0.80), write)

    assert record["corrected"] is True
    assert "Today is not known." in write.calls[0]


# --- the calendar's verdict on the anchor's dated event is made by code, not the model --------------
# The third treatment run showed why. At midnight of February 14 the model was told "an event on a
# date now in the past has happened"; it rounded "today is the 14th" to "the 14th is over", declared
# the party a success eighteen hours before it was due, and the party was silently never hosted.
# Which side of today a date falls on is exactly the kind of judgement code gets right every time
# and a small model gets right most of the time, so it moved into code.

DATED_SEED = (
    "Isabella Rodriguez is planning on having a Valentine's Day party at Hobbs Cafe "
    "with her customers on February 14th, 2023 at 5pm."
)


def dated_scratch(day):
    s = scratch(seed=DATED_SEED)
    s.name = "Isabella Rodriguez"
    s.curr_time = datetime.datetime(2023, 2, day, 0, 0)
    return s


def test_the_day_before_the_event_is_upcoming():
    verdict, line = reanchor.anchor_event_guidance(dated_scratch(13))
    assert verdict == "upcoming"
    assert "has NOT happened yet" in line


def test_the_day_of_the_event_is_still_upcoming():
    """The exact regression: a rewrite happens at midnight, before anything scheduled that day."""
    verdict, line = reanchor.anchor_event_guidance(dated_scratch(14))
    assert verdict == "upcoming"
    assert "February 14" in line and "has NOT happened yet" in line


def test_the_day_after_the_event_is_past():
    verdict, line = reanchor.anchor_event_guidance(dated_scratch(15))
    assert verdict == "past"
    assert "already taken place" in line


def test_an_anchor_without_a_date_gets_no_event_rule_at_all():
    monkeypatch_free = scratch()  # Klaus's seed carries no date
    monkeypatch_free.curr_time = datetime.datetime(2023, 2, 15, 0, 0)
    verdict, line = reanchor.anchor_event_guidance(monkeypatch_free)
    assert verdict is None and line == ""


def test_an_explicit_year_is_believed_over_the_clock():
    s = dated_scratch(15)
    s.seed_currently = s.currently = "planning a reunion on February 14th, 2024."
    verdict, _ = reanchor.anchor_event_guidance(s)
    assert verdict == "upcoming"  # 2024 is ahead of the 2023 clock, whatever the day says


def test_the_correction_prompt_carries_the_calendar_verdict(monkeypatch):
    monkeypatch.setattr(reanchor, "PERSONA_REANCHOR", True)
    write = rewriter()
    s = dated_scratch(14)
    text, record = reanchor.reanchor(s, DRIFTED_UNDATED, embedder(0.80), write)
    assert "has NOT happened yet" in write.calls[0]
    assert record["anchor_event"] == "upcoming"

    write2 = rewriter()
    s2 = dated_scratch(15)
    text, record2 = reanchor.reanchor(s2, DRIFTED_UNDATED, embedder(0.80), write2)
    assert "already taken place" in write2.calls[0]
    assert "has NOT happened yet" not in write2.calls[0]
    assert record2["anchor_event"] == "past"
