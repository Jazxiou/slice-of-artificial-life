"""
The town guardrails: bounded idle memories, and compact embedding files.
Both exist because nothing in this system deletes a memory and the store grows at ~1,020 nodes per
agent per simulated day, half of them "X is idle". The properties pinned here are the ones that keep
the guarantees of §4.0 intact: with the flags off, nothing changes at all, down to the bytes written;
with the dedup on, an object's idleness is remembered at most once per hour while a *person* standing
idle is never touched, because reactions can target a person's event and never an object idle.
"""

import datetime
import json
import types

import pytest
from memory_ext import longevity

NOW = datetime.datetime(2023, 2, 13, 12, 0, 0)
LATER = lambda minutes: NOW + datetime.timedelta(minutes=minutes)  # noqa: E731

COUNTER = ("the Ville:Hobbs Cafe:cafe:behind the cafe counter", "is", "idle")
KLAUS_IDLE = ("Klaus Mueller", "is", "idle")
REAL_EVENT = ("the Ville:Hobbs Cafe:cafe:behind the cafe counter", "is", "being wiped down")


def a_mem():
    return types.SimpleNamespace()


@pytest.fixture(autouse=True)
def flags_off(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", False)
    monkeypatch.setattr(longevity, "IDLE_DEDUP_TTL_HOURS", 1.0)
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", False)


# --- with the flags off, the baseline is untouched ---------------------------------------------------


def test_nothing_is_skipped_with_the_flag_off():
    mem = a_mem()
    for _ in range(5):
        assert longevity.skip_idle_store(mem, COUNTER, NOW) is False
    assert not hasattr(mem, "_idle_seen")  # not even the registry is created


def test_compact_returns_the_callers_own_dictionary_with_the_flag_off():
    """Identity, not equality: the baseline must write byte-identical files."""
    embeddings = {"a": [0.123456789012345]}
    assert longevity.compact(embeddings) is embeddings


def test_nothing_is_enabled_by_default():
    assert longevity.enabled() is False


# --- the dedup ---------------------------------------------------------------------------------------


def test_an_object_idle_is_stored_once_then_skipped_within_the_hour(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()

    assert longevity.skip_idle_store(mem, COUNTER, NOW) is False  # first sighting: store it
    assert longevity.skip_idle_store(mem, COUNTER, LATER(1)) is True  # spam: skip
    assert longevity.skip_idle_store(mem, COUNTER, LATER(59)) is True


def test_after_the_ttl_it_is_stored_again(monkeypatch):
    """Once per hour, not never: the reflection trigger and the perception window keep working."""
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()
    longevity.skip_idle_store(mem, COUNTER, NOW)

    assert longevity.skip_idle_store(mem, COUNTER, LATER(61)) is False
    assert longevity.skip_idle_store(mem, COUNTER, LATER(62)) is True  # and the window restarts


def test_a_person_standing_idle_is_never_deduplicated(monkeypatch):
    """
    `plan._choose_retrieved` can pick another persona's event for reaction whatever its description; its
    idle filter applies only to the second pass. Deduping person idles could change who reacts to whom.
    """
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()

    for _ in range(3):
        assert longevity.skip_idle_store(mem, KLAUS_IDLE, NOW) is False


def test_a_real_event_about_the_same_object_is_never_touched(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()
    longevity.skip_idle_store(mem, COUNTER, NOW)

    for _ in range(3):
        assert longevity.skip_idle_store(mem, REAL_EVENT, LATER(1)) is False


def test_each_object_has_its_own_clock(monkeypatch):
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    mem = a_mem()
    table = ("the Ville:Oak Hill College:library:library table", "is", "idle")

    assert longevity.skip_idle_store(mem, COUNTER, NOW) is False
    assert longevity.skip_idle_store(mem, table, LATER(1)) is False  # different object: store
    assert longevity.skip_idle_store(mem, COUNTER, LATER(2)) is True


def test_a_missing_clock_never_skips(monkeypatch):
    """A fresh fork's first tick has no time yet; dropping memories blind would be worse than spam."""
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    assert longevity.skip_idle_store(a_mem(), COUNTER, None) is False


def test_the_registry_lives_on_the_memory_not_the_module(monkeypatch):
    """Two agents watching the same counter must not share a clock."""
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    isabella, klaus = a_mem(), a_mem()

    longevity.skip_idle_store(isabella, COUNTER, NOW)
    assert longevity.skip_idle_store(klaus, COUNTER, LATER(1)) is False


# --- compact embeddings ------------------------------------------------------------------------------


def test_vectors_are_rounded_to_six_decimals(monkeypatch):
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    out = longevity.compact({"a": [0.123456789, -0.000000123]})

    assert out["a"] == [0.123457, -0.0]


def test_rounding_is_within_float32_noise(monkeypatch):
    """The model computed these in float32; six decimals discards verbosity, not information."""
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    vector = [0.07423911988735199, -0.6812345981597900, 0.0001234567]
    out = longevity.compact({"a": vector})["a"]

    assert all(abs(a - b) < 1e-6 for a, b in zip(vector, out))


def test_the_written_file_gets_meaningfully_smaller(monkeypatch):
    import random

    random.seed(0)
    embeddings = {f"memory {i}": [random.uniform(-1, 1) for _ in range(384)] for i in range(20)}

    full = len(json.dumps(embeddings))
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    small = len(json.dumps(longevity.compact(embeddings)))

    # Roughly half: a full-precision component is ~19 characters and a rounded one ~9, plus the
    # unchanging keys and punctuation around them.
    assert small < full * 0.6


def test_keys_and_order_are_preserved(monkeypatch):
    monkeypatch.setattr(longevity, "COMPACT_EMBEDDINGS", True)
    embeddings = {"b": [0.1], "a": [0.2]}

    assert list(longevity.compact(embeddings)) == ["b", "a"]


# --- the condition is recorded -----------------------------------------------------------------------


def test_the_run_header_names_all_three_settings():
    assert set(longevity.config()) == {"idle_memory_dedup", "idle_dedup_ttl_hours", "compact_embeddings"}


def test_the_description_says_what_is_on(monkeypatch):
    assert "baseline" in longevity.describe()
    monkeypatch.setattr(longevity, "IDLE_MEMORY_DEDUP", True)
    assert "once per 1h" in longevity.describe()
