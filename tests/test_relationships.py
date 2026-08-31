"""
Per-side friendship and romance: the tracks the drama runs on.
What is pinned here: the scores are directional (Klaus warming to Maria moves nothing in Maria's
table), the seeds mirror the character sheets asymmetries included (Francisco's crush on Abigail is
his alone), one conversation can only move a track so far, everything stays inside -100..100, an
unparseable reply changes nothing, and with the flag off the layer does not exist.
"""

import types

import pytest
from world_ext import relationships


def scratch(name="Klaus Mueller"):
    return types.SimpleNamespace(name=name, relationships=None, needs=None, mood=None)


class rewriter:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.reply


TRANSCRIPT = "Klaus Mueller: I loved talking about your stream.\nMaria Lopez: Me too, this was nice.\n"


@pytest.fixture(autouse=True)
def flag_on(monkeypatch):
    monkeypatch.setattr(relationships, "WORLD_RELATIONSHIPS", True)


# --- with the flag off, the layer does not exist ----------------------------------------------------


def test_off_means_no_scores_no_calls_no_saved_fields(monkeypatch):
    monkeypatch.setattr(relationships, "WORLD_RELATIONSHIPS", False)
    s = scratch()
    write = rewriter("friendship change: +5\nromance change: +5")

    assert relationships.after_conversation(s, "Maria Lopez", TRANSCRIPT, write) is None
    assert write.prompts == []
    assert s.relationships is None
    out = {}
    relationships.save(s, out)
    assert out == {}


# --- the seeds mirror the character sheets ------------------------------------------------------------


def test_spouses_start_married_and_strangers_start_at_zero():
    """Zero is the neutral centre of a signed scale, so a stranger can become friend or enemy."""
    john = scratch("John Lin")
    assert relationships.get(john, "Mei Lin") == {"friendship": 80.0, "romance": 70.0}
    assert relationships.get(john, "Latoya Williams") == {"friendship": 0.0, "romance": 0.0}


def test_a_one_sided_crush_is_seeded_on_one_side_only():
    """Francisco's sheet has the crush; Abigail's has nothing, and the asymmetry is the point."""
    francisco = scratch("Francisco Lopez")
    abigail = scratch("Abigail Chen")
    assert relationships.get(francisco, "Abigail Chen")["romance"] == 40.0
    assert relationships.get(abigail, "Francisco Lopez")["romance"] == 0.0


def test_the_mutual_secret_crush_is_seeded_on_both_sides():
    klaus = scratch("Klaus Mueller")
    maria = scratch("Maria Lopez")
    assert relationships.get(klaus, "Maria Lopez")["romance"] == 45.0
    assert relationships.get(maria, "Klaus Mueller")["romance"] == 45.0


# --- a conversation moves the scores, one side at a time -----------------------------------------------


def test_a_conversation_moves_this_side_and_only_this_side():
    klaus = scratch("Klaus Mueller")
    write = rewriter("friendship change: +3\nromance change: +2")

    updated = relationships.after_conversation(klaus, "Maria Lopez", TRANSCRIPT, write)

    assert updated == {"friendship": 73.0, "romance": 47.0}
    assert klaus.relationships == {"Maria Lopez": {"friendship": 73.0, "romance": 47.0}}
    # Directional: nothing here ever touched a Maria object, and her own table would start from her
    # own seed and her own reading of the same transcript.


def test_a_bad_conversation_can_cool_things_down():
    klaus = scratch("Klaus Mueller")
    relationships.after_conversation(
        klaus, "Maria Lopez", TRANSCRIPT, rewriter("friendship change: -4\nromance change: -6")
    )
    assert klaus.relationships["Maria Lopez"] == {"friendship": 66.0, "romance": 39.0}


def test_one_conversation_cannot_rewrite_a_relationship():
    """The model may answer with drama; the cap keeps it to a shift, not a rewrite."""
    klaus = scratch("Klaus Mueller")
    relationships.after_conversation(
        klaus, "Maria Lopez", TRANSCRIPT, rewriter("friendship change: +80\nromance change: -100")
    )
    assert klaus.relationships["Maria Lopez"] == {"friendship": 80.0, "romance": 35.0}


def test_scores_can_go_negative_and_stop_at_the_floor():
    """Grudges are representable: repeated bad conversations drive a score below zero, to -100."""
    abigail = scratch("Abigail Chen")
    for _ in range(11):
        relationships.after_conversation(
            abigail, "Francisco Lopez", TRANSCRIPT, rewriter("friendship change: -10\nromance change: -10")
        )
    assert abigail.relationships["Francisco Lopez"] == {"friendship": -100.0, "romance": -100.0}


def test_the_attitude_line_reads_this_sides_scores_into_words():
    klaus = scratch("Klaus Mueller")
    line = relationships.attitude_line(klaus, "Maria Lopez")
    assert line == "Klaus Mueller sees Maria Lopez as one of their closest friends and is secretly drawn to them.\n"
    stranger = scratch("Latoya Williams")
    assert relationships.attitude_line(stranger, "Klaus Mueller") == "Latoya Williams barely knows Klaus Mueller.\n"


def test_hostility_has_words_too():
    a = scratch("Tom Moreno")
    a.relationships = {"Adam Smith": {"friendship": -60.0, "romance": -40.0}}
    assert (
        relationships.attitude_line(a, "Adam Smith")
        == "Tom Moreno cannot stand Adam Smith and finds the thought of romance "
        "with them unpleasant.\n"
    )


def test_the_attitude_line_is_empty_with_the_flag_off(monkeypatch):
    monkeypatch.setattr(relationships, "WORLD_RELATIONSHIPS", False)
    assert relationships.attitude_line(scratch("Klaus Mueller"), "Maria Lopez") == ""


def test_the_update_prompt_carries_the_speakers_mood_when_the_mood_layer_is_on(monkeypatch):
    from world_ext import emotion

    monkeypatch.setattr(emotion, "WORLD_EMOTION", True)
    klaus = scratch("Klaus Mueller")
    klaus.needs = None
    klaus.mood = {"family": "anger", "word": "irritated"}
    write = rewriter("friendship change: -2\nromance change: 0")
    relationships.after_conversation(klaus, "Maria Lopez", TRANSCRIPT, write)
    assert "Klaus Mueller is feeling irritated." in write.prompts[0]


def test_an_unparseable_reply_changes_nothing():
    klaus = scratch("Klaus Mueller")
    before = dict(relationships.get(klaus, "Maria Lopez"))
    result = relationships.after_conversation(
        klaus, "Maria Lopez", TRANSCRIPT, rewriter("They had a lovely time together.")
    )
    assert result is None
    assert klaus.relationships["Maria Lopez"] == before


def test_the_prompt_carries_the_transcript_and_the_current_scores():
    klaus = scratch("Klaus Mueller")
    write = rewriter("friendship change: 0\nromance change: 0")
    relationships.after_conversation(klaus, "Maria Lopez", TRANSCRIPT, write)
    assert "I loved talking about your stream." in write.prompts[0]
    assert "friendship 70" in write.prompts[0]
    assert "romance 45" in write.prompts[0]


# --- persistence -----------------------------------------------------------------------------------------


def test_scores_survive_a_save_and_load():
    klaus = scratch("Klaus Mueller")
    relationships.after_conversation(
        klaus, "Maria Lopez", TRANSCRIPT, rewriter("friendship change: +3\nromance change: +2")
    )
    out = {}
    relationships.save(klaus, out)
    restored = scratch("Klaus Mueller")
    relationships.load(restored, out)
    assert restored.relationships == {"Maria Lopez": {"friendship": 73.0, "romance": 47.0}}


def test_an_old_checkpoint_without_scores_starts_from_the_seeds():
    restored = scratch("Klaus Mueller")
    relationships.load(restored, {"currently": "..."})
    assert restored.relationships is None
    assert relationships.get(restored, "Maria Lopez")["friendship"] == 70.0


def test_the_run_header_names_the_flag():
    assert set(relationships.config()) == {"world_relationships"}
