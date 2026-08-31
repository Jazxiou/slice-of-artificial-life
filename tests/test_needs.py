"""
The six Sims-style needs
"""

import datetime
import types

import pytest
from world_ext import needs

NOW = datetime.datetime(2023, 2, 13, 12, 0, 0)


def scratch(name="Klaus Mueller", action=None, chatting_with=None, values=None):
    s = types.SimpleNamespace(name=name, act_description=action, chatting_with=chatting_with, curr_time=NOW, needs=None)
    if values is not None:
        s.needs = dict(needs.fresh(), **values)
    return s


def hours(scratch_, n, step=10 / 3600):
    """Run n simulated hours of ticks at the real step size, ten seconds apiece."""
    for _ in range(int(n * 3600 / 10)):
        needs.tick(scratch_, step)
    return scratch_.needs


@pytest.fixture(autouse=True)
def flag_on(monkeypatch):
    monkeypatch.setattr(needs, "WORLD_NEEDS", True)
    monkeypatch.setattr(needs, "NEEDS_RED_THRESHOLD", 25.0)


# --- with the flag off, the layer does not exist ----------------------------------------------------


def test_off_means_no_needs_dictionary_is_ever_created(monkeypatch):
    monkeypatch.setattr(needs, "WORLD_NEEDS", False)
    s = scratch()
    assert needs.tick(s, 1.0) is None
    assert s.needs is None


def test_off_means_the_identity_block_gains_nothing(monkeypatch):
    monkeypatch.setattr(needs, "WORLD_NEEDS", False)
    s = scratch(values={"hunger": 1.0})
    assert needs.iss_line(s) == ""
    assert needs.mood_override(s) is None


def test_off_means_saves_carry_no_new_fields(monkeypatch):
    monkeypatch.setattr(needs, "WORLD_NEEDS", False)
    out = {}
    needs.save(scratch(), out)
    assert out == {}


# --- the anchors ----------------------------------------------------------------------------


def test_eight_hours_of_sleep_fills_the_bar_from_empty():
    """The one rate that is not a guess: everything else is calibrated around it."""
    s = scratch(action="sleeping", values={"sleep": 0.0})
    hours(s, 8)
    assert s.needs["sleep"] == pytest.approx(100.0)


def test_a_nap_gives_proportionally_less():
    s = scratch(action="taking a nap on the sofa", values={"sleep": 40.0})
    hours(s, 0.5)
    assert s.needs["sleep"] == pytest.approx(40.0 + 12.5 * 0.5, abs=0.1)


def test_social_refills_only_through_a_real_conversation():
    """
    No description can refill Social, not even one that says the word.
    """
    talking_about_it = scratch(action="hosting a social gathering for the neighbourhood", values={"social": 20.0})
    hours(talking_about_it, 1)
    assert talking_about_it.needs["social"] < 20.0  # decayed despite the wording

    actually_talking = scratch(chatting_with="Isabella Rodriguez", values={"social": 20.0})
    hours(actually_talking, 1)
    assert actually_talking.needs["social"] > 40.0  # a real conversation refills


def test_needs_decay_on_the_clock():
    s = scratch(action="writing his research paper")
    before = dict(s.needs or needs.fresh())
    s.needs = dict(before)
    hours(s, 2)
    assert all(s.needs[k] < before[k] for k in ("sleep", "hunger", "bladder", "social"))


def test_eating_refills_hunger():
    s = scratch(action="eating lunch at Hobbs Cafe", values={"hunger": 30.0})
    hours(s, 0.5)
    assert s.needs["hunger"] > 55.0


def test_fun_is_personal():
    """Maria's streaming is her fun; the same description does nothing for Klaus's bar."""
    maria = scratch(name="Maria Lopez", action="streaming on Twitch", values={"fun": 30.0})
    klaus = scratch(name="Klaus Mueller", action="streaming on Twitch", values={"fun": 30.0})
    hours(maria, 1)
    hours(klaus, 1)
    assert maria.needs["fun"] > 50.0
    assert klaus.needs["fun"] < 30.0


def test_bars_stay_inside_their_range():
    s = scratch(action="sleeping", values={"sleep": 99.0})
    hours(s, 4)
    assert s.needs["sleep"] == 100.0
    s2 = scratch(action="writing", values={"bladder": 3.0})
    hours(s2, 2)
    assert s2.needs["bladder"] == 0.0


def test_the_bladder_drains_slowly_during_sleep():
    """Or the whole town wakes uncomfortable every morning, as the first 25-character pilot did."""
    asleep = scratch(action="sleeping", values={"bladder": 60.0, "sleep": 50.0})
    awake = scratch(action="reading at the desk", values={"bladder": 60.0})
    hours(asleep, 8)
    hours(awake, 8)
    assert asleep.needs["bladder"] > 40.0  # eight hours asleep leaves the bar comfortable
    assert awake.needs["bladder"] == pytest.approx(4.0, abs=0.5)  # the waking rate drains it


# --- what the red zone does --------------------------------------------------------------------------


def test_a_red_bar_forces_the_matching_mood():
    assert needs.mood_override(scratch(values={"sleep": 10.0})) == "tired"
    assert needs.mood_override(scratch(values={"fun": 10.0})) == "bored"
    assert needs.mood_override(scratch(values={"hunger": 10.0})) == "irritable"
    assert needs.mood_override(scratch(values={"social": 10.0})) == "lonely"


def test_hygiene_and_bladder_read_uncomfortable():
    """Neither state has a mood word of its own that a screen should say out loud."""
    assert needs.mood_override(scratch(values={"hygiene": 5.0})) == "uncomfortable"
    assert needs.mood_override(scratch(values={"bladder": 5.0})) == "uncomfortable"


def test_the_worst_bar_decides_the_mood():
    s = scratch(values={"hunger": 20.0, "sleep": 5.0})
    assert needs.mood_override(s) == "tired"


def test_a_deficit_becomes_one_readable_sentence():
    s = scratch(values={"hunger": 10.0, "sleep": 15.0})
    line = needs.iss_line(s)
    # Worst bar first: hunger is at 10 and sleep at 15, so hunger leads the sentence.
    assert line == "Current condition: Klaus Mueller is very hungry and tired.\n"


def test_a_healthy_character_adds_nothing_to_the_identity_block():
    """The identity block must be byte-identical to the baseline's until something is actually wrong."""
    assert needs.iss_line(scratch(values={})) == ""


def test_recovery_lifts_the_override():
    s = scratch(action="sleeping", values={"sleep": 20.0})
    assert needs.mood_override(s) == "tired"
    hours(s, 2)
    assert needs.mood_override(s) is None


# --- persistence -------------------------------------------------------------------------------------


def test_needs_survive_a_save_and_load():
    s = scratch(values={"hunger": 42.4218})
    out = {}
    needs.save(s, out)
    restored = scratch()
    needs.load(restored, out)
    assert restored.needs["hunger"] == pytest.approx(42.42)


def test_an_old_checkpoint_without_needs_still_loads_and_starts_fresh():
    restored = scratch()
    needs.load(restored, {"currently": "..."})
    assert restored.needs is None
    needs.tick(restored, 10 / 3600)
    assert restored.needs["sleep"] < 75.0 and restored.needs["sleep"] > 74.9


def test_the_run_header_names_the_flag():
    assert set(needs.config()) == {"world_needs", "needs_red_threshold"}


def test_personal_fun_names_only_real_cast_members():
    """A typo in this table would silently give a character no personal fun at all."""
    import json
    import pathlib

    meta = (
        pathlib.Path(__file__).resolve().parents[1]
        / "environment"
        / "frontend_server"
        / "storage"
        / "base_the_ville_n25"
        / "reverie"
        / "meta.json"
    )
    cast = set(json.loads(meta.read_text())["persona_names"])
    assert set(needs.PERSONAL_FUN) <= cast
