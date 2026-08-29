"""
How importance is compared across kinds of memory.
The measured runs are what this change answers. Importance is a 1-to-10 rating given when a memory is
written, and it is not one scale: over three simulated days the median event scored 1 and the median
reflection 7. Normalising that across every candidate maps observations to nearly zero and reflections to
nearly one, so reflections came out as 47% of everything retrieval showed the agents while being 13% of
what they held.
Two properties are pinned here. With the flags off nothing changes at all, which is what lets the control
condition stay the control. With them on, an ordinary observation can outrank a mundane reflection, which
is the whole point, and reflections are not excluded or penalised, which would be a different and worse
change than the one intended.
"""

import types

import pytest
from memory_ext import retrieval


def node(node_id, kind, poignancy, key=None):
    return types.SimpleNamespace(
        node_id=node_id, type=kind, poignancy=poignancy, embedding_key=key or f"{kind} {node_id}", last_accessed=0
    )


def memory(events=(), thoughts=(), chats=()):
    return types.SimpleNamespace(seq_event=list(events), seq_thought=list(thoughts), seq_chat=list(chats))


@pytest.fixture(autouse=True)
def flags_off(monkeypatch):
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", False)


# --- with the flags off, this is the baseline ------------------------------------------------------


def test_nothing_is_enabled_by_default():
    assert retrieval.enabled() is False


# --- importance, compared within a kind ------------------------------------------------------------


def test_an_observation_can_outrank_a_mundane_reflection(monkeypatch):
    """
    The failure this exists to fix. Scored across everything, the two events here sit at 0.0 and 0.14
    against the reflections' 0.86 and 1.0, so no observation competes. Compared within their own kind,
    the striking observation is the best observation there is.
    """
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    nodes = [
        node("e_dull", "event", 1),
        node("e_striking", "event", 8),
        node("t_dull", "thought", 7),
        node("t_striking", "thought", 8),
    ]

    scores = retrieval.importance_scores(None, nodes)

    assert scores["e_striking"] == 1.0
    assert scores["e_dull"] == 0.0
    assert scores["t_striking"] == 1.0
    assert scores["t_dull"] == 0.0


def test_reflections_are_not_excluded_or_penalised(monkeypatch):
    """
    A different and worse change would have been to drop reflections or scale them down. A reflection
    that is important among reflections still scores as highly as anything else.
    """
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    nodes = [node("e", "event", 1), node("t", "thought", 8), node("t2", "thought", 1)]

    scores = retrieval.importance_scores(None, nodes)

    assert scores["t"] == 1.0
    assert set(scores) == {"e", "t", "t2"}


def test_a_kind_whose_memories_are_all_equal_follows_the_baseline_s_convention(monkeypatch):
    """
    The baseline gives a set with no variation the midpoint rather than zero, so that a memory is not
    penalised for having nothing to be compared against. Within-type normalisation keeps that rule, which
    matters because most stores hold long runs of identically rated observations.
    """
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    nodes = [node("e1", "event", 1), node("e2", "event", 1), node("t1", "thought", 7)]

    scores = retrieval.importance_scores(None, nodes)

    assert scores["e1"] == scores["e2"] == 0.5
    assert scores["t1"] == 0.5


def test_every_candidate_receives_a_score(monkeypatch):
    """The caller indexes the three component dictionaries by the same keys; a gap would be a KeyError."""
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    nodes = [node(f"n{i}", "event" if i % 2 else "thought", i + 1) for i in range(10)]

    assert set(retrieval.importance_scores(None, nodes)) == {n.node_id for n in nodes}


def test_scores_stay_inside_the_range_the_weights_assume(monkeypatch):
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    nodes = [node("a", "event", 1), node("b", "event", 10), node("c", "thought", 3)]

    assert all(0.0 <= value <= 1.0 for value in retrieval.importance_scores(None, nodes).values())


# --- the condition is recorded ---------------------------------------------------------------------


def test_the_run_header_names_the_flag():
    assert set(retrieval.config()) == {"importance_within_type"}


def test_the_description_says_what_is_on(monkeypatch):
    assert "baseline" in retrieval.describe()
    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    assert "within each kind" in retrieval.describe()


# --- end to end, through the real retrieval function ------------------------------------------------
#
# The tests above check the module. These check that the two conditionals in `_new_retrieve` actually
# reach it, which is where a flag-gated change usually goes wrong: the module behaves and the call site
# never calls it.

import datetime  # noqa: E402

from memory_ext import retention  # noqa: E402
from persona.cognitive_modules import retrieve  # noqa: E402

NOW = datetime.datetime(2023, 2, 13, 12, 0, 0)


class Node:
    def __init__(self, node_id, kind, poignancy, created):
        self.node_id = node_id
        self.type = kind
        self.poignancy = poignancy
        self.created = created
        self.last_accessed = created
        self.embedding_key = f"{kind} {node_id}"


class Persona:
    def __init__(self, events, thoughts, chats=()):
        nodes = list(events) + list(thoughts) + list(chats)
        self.a_mem = types.SimpleNamespace(
            seq_event=list(events),
            seq_thought=list(thoughts),
            seq_chat=list(chats),
            id_to_node={n.node_id: n for n in nodes},
            # One vector for everything, so relevance is identical for every candidate and the ranking is
            # decided by the term under test. Relevance is weighted six times as heavily as recency, so a
            # store with varied relevance would drown out the effect being measured here.
            embeddings={n.embedding_key: [1.0, 1.0] for n in nodes},
        )
        self.scratch = types.SimpleNamespace(
            curr_time=NOW, recency_decay=0.99, recency_w=1, relevance_w=1, importance_w=1
        )


def store():
    """
    Three dull observations, one striking one, and two reflections.
    The striking observation is rated 5 and the reflections 7, which is the situation the measured runs
    produce: an observation can be the most notable thing an agent saw all day and still sit below routine
    reflections on a scale where the median reflection is 7 and the median event is 1.
    """
    events = [Node(f"e{i}", "event", 1, NOW) for i in range(3)]
    events.append(Node("e_striking", "event", 5, NOW))
    thoughts = [Node(f"t{i}", "thought", 7, NOW) for i in range(2)]
    chats = [Node("c0", "chat", 4, NOW)]
    return events, thoughts, chats


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(retrieve, "get_embedding", lambda text, model=None: [1.0, 1.0])
    monkeypatch.setattr(retention, "RECENCY_TIME_BASED", False)


def test_the_striking_observation_is_retrieved_only_with_the_flag_on(monkeypatch):
    """
    The failure the measured runs found, end to end. Rated against everything, the best observation of
    the day scores below routine reflections and is not retrieved. Rated against other observations, it
    is retrieved ahead of them.
    """
    events, thoughts, _ = store()
    before = retrieve._new_retrieve(Persona(events, thoughts), ["anything"], n_count=2)["anything"]

    monkeypatch.setattr(retrieval, "IMPORTANCE_WITHIN_TYPE", True)
    events, thoughts, _ = store()
    after = retrieve._new_retrieve(Persona(events, thoughts), ["anything"], n_count=2)["anything"]

    assert "e_striking" not in [n.node_id for n in before]
    assert "e_striking" in [n.node_id for n in after]


def test_a_conversation_is_recalled_through_its_summary_not_its_transcript():
    """
    Deliberate, and worth pinning so it is not "fixed" later by mistake. Perception writes a conversation
    twice: a chat node holding the words, and an event node holding the summary that points at it. The
    event is a candidate and the transcript is not, which is why an agent recalls that it spoke with
    somebody rather than what they said. Conversation probes are the best-answered category in both
    measured runs, so this is the design working, not a gap.
    """
    events, thoughts, chats = store()
    events.append(Node("e_convo", "event", 4, NOW))  # "conversing about the party with Maria"
    recalled = retrieve._new_retrieve(Persona(events, thoughts, chats), ["anything"], n_count=10)

    ids = [n.node_id for n in recalled["anything"]]
    assert "e_convo" in ids
    assert "c0" not in ids
