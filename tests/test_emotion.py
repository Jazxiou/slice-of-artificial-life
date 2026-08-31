"""
The mood layer: an Ekman family underneath, a curated word on screen, the red needs on top.
The properties pinned here are the contract the viewer will rely on. Every word a spectator can see
is on the curated list (the model's reply is parsed against the vocabulary, never displayed raw). A
red need's word outranks the model's choice and steps aside the moment the bar recovers. The two
per-step triggers, waking and recovering, fire on the edge and only on the edge, so the cost stays
at a few model calls per agent-day. And with the flag off the layer does not exist: no state, no
calls, nothing in a save.
"""

import types

import pytest
from world_ext import emotion, needs


def scratch(name="Klaus Mueller", action=None, values=None, currently="writing a paper"):
    s = types.SimpleNamespace(
        name=name, act_description=action, chatting_with=None, currently=currently, needs=None, mood=None
    )
    if values is not None:
        s.needs = dict(needs.fresh(), **values)
    return s


class rewriter:
    """A fake model that answers with whatever the test wants and remembers what it was asked."""

    def __init__(self, reply="content"):
        self.reply = reply
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setattr(emotion, "WORLD_EMOTION", True)
    monkeypatch.setattr(needs, "WORLD_NEEDS", True)
    monkeypatch.setattr(needs, "NEEDS_RED_THRESHOLD", 25.0)


# --- with the flag off, the layer does not exist ----------------------------------------------------


def test_off_means_no_mood_no_calls_no_saved_fields(monkeypatch):
    monkeypatch.setattr(emotion, "WORLD_EMOTION", False)
    s = scratch()
    write = rewriter()

    assert emotion.mood(s) is None
    assert emotion.update(s, "just woke up", write) is None
    assert emotion.tick(s, write) is None
    assert write.prompts == []
    assert s.mood is None
    out = {}
    emotion.save(s, out)
    assert out == {}


# --- the vocabulary is closed ------------------------------------------------------------------------


def test_every_display_word_belongs_to_exactly_one_family():
    seen = [w for words in emotion.FAMILIES.values() for w in words]
    assert len(seen) == len(set(seen))
    assert set(emotion.WORD_TO_FAMILY) == set(seen)


def test_a_chatty_reply_still_lands_on_a_vocabulary_word():
    s = scratch()
    emotion.update(s, "just woke up", rewriter("I think Klaus is feeling quite inspired today."))
    assert s.mood == {"family": "joy", "word": "inspired"}


def test_a_two_word_mood_parses():
    s = scratch()
    emotion.update(s, "just finished a conversation", rewriter("fed up"))
    assert s.mood == {"family": "disgust", "word": "fed up"}


def test_a_word_inside_another_word_does_not_count():
    """'retired' must not read as 'tired'; matching is on whole words."""
    s = scratch()
    assert emotion.update(s, "just woke up", rewriter("He retired to his room.")) is None
    assert s.mood["word"] == emotion.DEFAULT_WORD


def test_an_off_list_reply_changes_nothing():
    """Yesterday's mood is a better answer than a crash; the next trigger asks again."""
    s = scratch()
    emotion.update(s, "trigger", rewriter("cheerful"))
    assert emotion.update(s, "trigger", rewriter("ecstatic beyond all words")) is None
    assert s.mood == {"family": "joy", "word": "cheerful"}


# --- the red-need override ----------------------------------------------------------------------------


def test_a_red_need_outranks_the_model():
    s = scratch(values={"hunger": 10.0})
    emotion.update(s, "trigger", rewriter("cheerful"))
    assert emotion.mood(s) == ("anger", "irritable")


def test_the_chosen_mood_returns_when_the_bar_recovers():
    s = scratch(values={"hunger": 10.0})
    emotion.update(s, "trigger", rewriter("cheerful"))
    s.needs["hunger"] = 80.0
    assert emotion.mood(s) == ("joy", "cheerful")


def test_every_override_word_has_a_colour_family():
    red_words = {spec["red_mood"] for spec in needs.NEEDS.values()}
    assert red_words <= set(emotion.OVERRIDE_FAMILY)


# --- the per-step triggers fire on edges only ----------------------------------------------------------


def test_the_first_tick_only_records_state_and_never_fires():
    """Reopening a save must not greet the town with a burst of spurious mood calls."""
    s = scratch(action="sleeping", values={})
    write = rewriter()
    emotion.tick(s, write)
    assert write.prompts == []


def test_waking_up_fires_once():
    s = scratch(action="sleeping in bed", values={})
    write = rewriter("cheerful")
    emotion.tick(s, write)  # baseline: asleep
    s.act_description = "making breakfast"
    emotion.tick(s, write)  # the edge: woke up
    emotion.tick(s, write)  # still awake: no second call
    assert len(write.prompts) == 1
    assert "just woke up" in write.prompts[0]
    assert s.mood["word"] == "cheerful"


def test_a_need_recovering_fires_once():
    s = scratch(action="eating lunch", values={"hunger": 10.0})
    write = rewriter("content")
    emotion.tick(s, write)  # baseline: in the red
    s.needs["hunger"] = 60.0
    emotion.tick(s, write)  # the edge: recovered
    emotion.tick(s, write)
    assert len(write.prompts) == 1
    assert "comfortable again" in write.prompts[0]


def test_slipping_into_the_red_is_not_a_model_trigger():
    """Going red needs no call: the override is deterministic and already showing."""
    s = scratch(action="working", values={"hunger": 60.0})
    write = rewriter()
    emotion.tick(s, write)
    s.needs["hunger"] = 10.0
    emotion.tick(s, write)
    assert write.prompts == []
    assert emotion.mood(s) == ("anger", "irritable")


# --- the prompt carries what the model needs -----------------------------------------------------------


def test_the_prompt_names_the_moment_and_the_current_mood():
    s = scratch()
    write = rewriter("gloomy")
    emotion.update(s, "just finished a conversation with Maria Lopez", write)
    assert "just finished a conversation with Maria Lopez" in write.prompts[0]
    assert emotion.DEFAULT_WORD in write.prompts[0]
    assert "fed up" in write.prompts[0]  # the whole vocabulary is offered


# --- the read path: mood shapes what is said -----------------------------------------------------------


def test_the_feeling_line_reads_the_mood_into_words():
    s = scratch()
    emotion.update(s, "trigger", rewriter("gloomy"))
    assert emotion.feeling_line(s) == "Klaus Mueller is currently feeling gloomy.\n"


def test_the_feeling_line_carries_the_override_while_a_need_is_red():
    s = scratch(values={"hunger": 10.0})
    assert emotion.feeling_line(s) == "Klaus Mueller is currently feeling irritable.\n"


def test_the_feeling_line_is_empty_with_the_flag_off(monkeypatch):
    monkeypatch.setattr(emotion, "WORLD_EMOTION", False)
    assert emotion.feeling_line(scratch()) == ""


# --- persistence -----------------------------------------------------------------------------------------


def test_the_mood_survives_a_save_and_load():
    s = scratch()
    emotion.update(s, "trigger", rewriter("anxious"))
    out = {}
    emotion.save(s, out)
    restored = scratch()
    emotion.load(restored, out)
    assert restored.mood == {"family": "fear", "word": "anxious"}


def test_an_old_checkpoint_without_a_mood_starts_calm():
    restored = scratch()
    emotion.load(restored, {"currently": "..."})
    assert emotion.mood(restored) == ("neutral", "calm")


def test_the_run_header_names_the_flag():
    assert set(emotion.config()) == {"world_emotion"}
