"""
The viewer's two data feeds: the per-step world block and the periodic per-character snapshot.
The contract pinned here is what the Ville Viewer page relies on, and what the frozen baseline
relies on in the other direction: with every flag off, `step_payload` is None (so movement JSON
stays byte-identical) and `write_if_due` writes nothing. The display categories are pinned because
they are the mockup's six tile kinds, derived from the store's three real types, and a
misclassified tile would lie to a spectator.
"""

import datetime
import json
import types

import pytest
from world_ext import emotion, needs, snapshot

NOW = datetime.datetime(2023, 2, 13, 12, 0, 0)


def node(kind, description, subject="Klaus Mueller", poignancy=4, count=1):
    return types.SimpleNamespace(
        type=kind, description=description, subject=subject, poignancy=poignancy, node_count=count, created=NOW
    )


def persona(name="Klaus Mueller", nodes=()):
    scratch = types.SimpleNamespace(
        name=name,
        act_description="reading",
        chatting_with=None,
        currently="writing a paper",
        seed_currently="Klaus Mueller is writing a research paper.",
        innate="kind, inquisitive",
        learned="a student",
        needs=None,
        mood=None,
        relationships=None,
        drift_log=[],
    )
    a_mem = types.SimpleNamespace(id_to_node={f"node_{i + 1}": n for i, n in enumerate(nodes)})
    return types.SimpleNamespace(scratch=scratch, a_mem=a_mem)


@pytest.fixture(autouse=True)
def flags(monkeypatch, tmp_path):
    monkeypatch.setattr(needs, "WORLD_NEEDS", True)
    monkeypatch.setattr(emotion, "WORLD_EMOTION", True)
    monkeypatch.setattr(snapshot, "WORLD_SNAPSHOTS", True)
    monkeypatch.setattr(snapshot, "SNAPSHOT_EVERY", 30)
    monkeypatch.setattr(snapshot, "TEMP_STORAGE", str(tmp_path))
    return tmp_path


# --- with the flags off, the baseline is untouched ---------------------------------------------------


def test_all_off_means_no_payload_and_no_files(monkeypatch, tmp_path):
    monkeypatch.setattr(needs, "WORLD_NEEDS", False)
    monkeypatch.setattr(emotion, "WORLD_EMOTION", False)
    monkeypatch.setattr(snapshot, "WORLD_SNAPSHOTS", False)
    p = persona()

    assert snapshot.step_payload(p.scratch) is None  # movement JSON stays byte-identical
    assert snapshot.write_if_due(30, NOW, {"Klaus Mueller": p}) is None
    assert list(tmp_path.iterdir()) == []


def test_each_half_appears_only_with_its_own_flag(monkeypatch):
    monkeypatch.setattr(emotion, "WORLD_EMOTION", False)
    payload = snapshot.step_payload(persona().scratch)
    assert "needs" in payload and "mood" not in payload


# --- the per-step payload -----------------------------------------------------------------------------


def test_the_payload_carries_six_needs_and_a_mood():
    payload = snapshot.step_payload(persona().scratch)
    assert set(payload["needs"]) == {"sleep", "hunger", "fun", "hygiene", "bladder", "social"}
    assert payload["mood"] == {"family": "neutral", "word": "calm"}


def test_a_red_need_shows_its_override_word_in_the_payload():
    p = persona()
    p.scratch.needs = dict(needs.fresh(), hunger=10.0)
    assert snapshot.step_payload(p.scratch)["mood"] == {"family": "anger", "word": "irritable"}


# --- the display categories -----------------------------------------------------------------------------


def test_the_three_stored_types_fan_out_into_the_six_tiles():
    me = "Klaus Mueller"
    cases = [
        (node("chat", "conversation with Maria"), "conversation"),
        (node("thought", "For Klaus Mueller's planning: today he should write"), "plan"),
        (node("thought", "This is Klaus Mueller's plan for today"), "plan"),
        (node("thought", "Klaus Mueller values his research"), "reflection"),
        (node("event", "the cafe counter is being wiped", subject="the Ville:Hobbs Cafe:cafe:counter"), "place"),
        (node("event", "Maria Lopez is streaming", subject="Maria Lopez"), "social"),
        (node("event", "Klaus Mueller is reading"), "event"),
    ]
    for n, expected in cases:
        assert snapshot.category(n, me) == expected, n.description


def test_every_category_has_a_fallback_emoji():
    assert set(snapshot.CATEGORY_EMOJI) == {"event", "place", "social", "conversation", "reflection", "plan"}


# --- the periodic snapshot files -------------------------------------------------------------------------


def test_snapshots_are_written_on_the_cadence_and_only_then(flags):
    p = persona()
    assert snapshot.write_if_due(29, NOW, {"Klaus Mueller": p}) is None
    assert snapshot.write_if_due(30, NOW, {"Klaus Mueller": p}) == 1
    assert (flags / "livetown" / "Klaus_Mueller.json").exists()
    assert not (flags / "livetown" / "Klaus_Mueller.json.tmp").exists()  # renamed into place


def test_the_snapshot_carries_what_the_tabs_read(flags):
    nodes = [node("event", f"Klaus Mueller is doing thing {i}", count=i) for i in range(1, 60)]
    p = persona(nodes=nodes)
    p.scratch.relationships = {"Maria Lopez": {"friendship": 70.0, "romance": 45.0}}
    p.scratch.drift_log = [{"day": "2023-02-14", "drift": 0.2, "corrected": True}]

    snapshot.write_if_due(60, NOW, {"Klaus Mueller": p})
    snap = json.loads((flags / "livetown" / "Klaus_Mueller.json").read_text())

    assert snap["identity"]["seed"] == "Klaus Mueller is writing a research paper."
    assert snap["relationships"]["Maria Lopez"]["romance"] == 45.0
    assert snap["identity"]["drift_log"][0]["corrected"] is True
    assert len(snap["memories"]) == snapshot.SNAPSHOT_MEMORIES  # capped
    assert snap["memories"][0]["description"] == "Klaus Mueller is doing thing 59"  # newest first
    assert snap["memories"][0]["emoji"] == snapshot.CATEGORY_EMOJI["event"]


def test_the_run_header_names_the_flag():
    assert set(snapshot.config()) == {"world_snapshots", "snapshot_every"}
