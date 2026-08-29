"""
Does the decay-and-retention contribution leave the baseline alone when its flags are off?
The evaluation's control condition is the repaired baseline (CHANGES.md categories A and B), so the
whole argument of the ablation ladder rests on one guarantee: with every category-C flag off, the
simulation must behave *exactly* as it did before the contribution existed. That is easy to assert and
easy to get wrong, so it is checked here rather than trusted.
The first test is the important one. It transcribes upstream's `new_retrieve` (commit fe05a71) into
this file and asserts that the live code, flags off, returns the same memories in the same order. The
transcription is deliberately a copy rather than an import: if someone later edits the real function
and forgets the guarantee, the copy still says what the baseline did.
The rest of the file checks that each mechanism, once switched on, does what §4.1.1 of the thesis
claims it does. The flags are read into module-level constants when `retention` is imported, which is
how the rest of this codebase reads its configuration (`from utils import *`), so the tests set those
constants directly.
Run with:  uv run pytest tests/ -q
"""

import datetime

import pytest
from memory_ext import retention
from persona.cognitive_modules import retrieve

# --- fakes ------------------------------------------------------------------------------------
# Small stand-ins rather than real personas: retrieval touches only a handful of fields, and building
# a real Persona would need a saved simulation, an embedding model and a language model.

NOW = datetime.datetime(2023, 2, 13, 12, 0, 0)


class FakeNode:
    def __init__(self, node_id, created, poignancy, embedding_key, last_accessed=None):
        self.node_id = node_id
        self.created = created
        self.last_accessed = last_accessed or created
        self.poignancy = poignancy
        self.embedding_key = embedding_key
        self.type = "event"


class FakeScratch:
    def __init__(self, now):
        self.curr_time = now
        self.recency_decay = 0.99  # upstream's default
        self.recency_w = 1
        self.relevance_w = 1
        self.importance_w = 1


class FakeMemory:
    def __init__(self, nodes):
        self.seq_event = list(nodes)
        self.seq_thought = []
        self.id_to_node = {n.node_id: n for n in nodes}
        # One dimension per node so that relevance is distinct per memory but trivially computable.
        self.embeddings = {n.embedding_key: [1.0, float(i)] for i, n in enumerate(nodes)}


class FakePersona:
    def __init__(self, nodes, now=NOW):
        self.a_mem = FakeMemory(nodes)
        self.scratch = FakeScratch(now)


def make_store(count=8, now=NOW):
    """A store of `count` memories, each created an hour further into the past than the last."""
    return [
        FakeNode(
            f"node_{i + 1}",
            created=now - datetime.timedelta(hours=i),
            poignancy=(i % 10) + 1,
            embedding_key=f"memory number {i}",
        )
        for i in range(count)
    ]


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch):
    """Retrieval embeds the focal point; there is no model here, so return a constant vector."""
    monkeypatch.setattr(retrieve, "get_embedding", lambda text, model=None: [1.0, 1.0])


@pytest.fixture(autouse=True)
def flags_off(monkeypatch):
    """Start every test from the shipped defaults, whatever the developer's own utils.py says."""
    monkeypatch.setattr(retention, "RECENCY_TIME_BASED", False)
    monkeypatch.setattr(retention, "RECENCY_ACCESS_PERSISTED", False)
    monkeypatch.setattr(retention, "IMPORTANCE_COUPLED_DECAY", False)
    monkeypatch.setattr(retention, "REHEARSAL_STRENGTHENING", False)
    monkeypatch.setattr(retention, "BASE_HALFLIFE_HOURS", 24.0)
    monkeypatch.setattr(retention, "DECAY_SHAPE", "exponential")
    monkeypatch.setattr(retention, "POWER_LAW_EXPONENT", 1.0)
    monkeypatch.setattr(retention, "IMPORTANCE_HALFLIFE_MULTIPLIER", 4.0)
    monkeypatch.setattr(retention, "REHEARSAL_HALFLIFE_MULTIPLIER", 3.0)
    monkeypatch.setattr(retention, "REHEARSAL_SATURATION", 8.0)


# --- the guarantee ----------------------------------------------------------------------------


def upstream_new_retrieve(persona, focal_points, n_count=30):
    """
    Upstream's `new_retrieve`, transcribed from commit fe05a71 with only the comments removed.
    Relevance and importance are taken from the live module because this change does not touch them;
    the recency term, the sort and the ranking are reproduced here so the comparison is against code
    that predates the contribution.
    """
    retrieved = dict()
    for focal_pt in focal_points:
        nodes = [
            [i.last_accessed, i]
            for i in persona.a_mem.seq_event + persona.a_mem.seq_thought
            if "idle" not in i.embedding_key
        ]
        nodes = sorted(nodes, key=lambda x: x[0])
        nodes = [i for created, i in nodes]

        recency_vals = [persona.scratch.recency_decay**i for i in range(1, len(nodes) + 1)]
        recency_out = {node.node_id: recency_vals[count] for count, node in enumerate(nodes)}
        recency_out = retrieve.normalize_dict_floats(recency_out, 0, 1)
        importance_out = retrieve.normalize_dict_floats(retrieve.extract_importance(persona, nodes), 0, 1)
        relevance_out = retrieve.normalize_dict_floats(retrieve.extract_relevance(persona, nodes, focal_pt), 0, 1)

        gw = [0.5, 3, 2]
        master_out = dict()
        for key in recency_out.keys():
            master_out[key] = (
                persona.scratch.recency_w * recency_out[key] * gw[0]
                + persona.scratch.relevance_w * relevance_out[key] * gw[1]
                + persona.scratch.importance_w * importance_out[key] * gw[2]
            )

        master_out = retrieve.top_highest_x_values(master_out, n_count)
        master_nodes = [persona.a_mem.id_to_node[key] for key in list(master_out.keys())]
        for n in master_nodes:
            n.last_accessed = persona.scratch.curr_time
        retrieved[focal_pt] = master_nodes

    return retrieved


def test_flags_off_reproduces_upstream_retrieval_exactly():
    """The whole ablation rests on this: flags off, the live path is upstream's, memory for memory."""
    focal = ["What did I do today?"]
    # Two independent stores, because retrieval writes back to the nodes it returns.
    mine = retrieve._new_retrieve(FakePersona(make_store()), focal, n_count=5)
    theirs = upstream_new_retrieve(FakePersona(make_store()), focal, n_count=5)

    assert [n.node_id for n in mine[focal[0]]] == [n.node_id for n in theirs[focal[0]]]


def test_flags_off_never_consults_the_contribution(monkeypatch):
    """Not just the same answer by coincidence: the new module is not entered at all."""

    def refuse(*args, **kwargs):
        raise AssertionError("retention.recency_scores was called with the flag off")

    monkeypatch.setattr(retention, "recency_scores", refuse)
    retrieve._new_retrieve(FakePersona(make_store()), ["anything"], n_count=3)


def test_flags_off_leaves_no_rehearsal_count_on_nodes():
    nodes = make_store()
    retrieve._new_retrieve(FakePersona(nodes), ["anything"], n_count=3)
    assert not any(hasattr(n, "rehearsal_count") for n in nodes)


def test_flags_off_ignores_a_saved_access_history():
    """A checkpoint written by this fork must still load as a baseline checkpoint."""
    node = FakeNode("node_1", created=NOW - datetime.timedelta(days=3), poignancy=5, embedding_key="k")
    retention.restore_access(node, {"last_accessed": "2023-02-13 11:00:00", "rehearsal_count": 7})

    assert node.last_accessed == node.created
    assert not hasattr(node, "rehearsal_count")


# --- what the contribution does once it is switched on ------------------------------------------


def enable(monkeypatch, **flags):
    monkeypatch.setattr(retention, "RECENCY_TIME_BASED", True)
    for name, value in flags.items():
        monkeypatch.setattr(retention, name.upper(), value)


def test_recency_halves_at_the_half_life(monkeypatch):
    enable(monkeypatch)
    node = FakeNode("node_1", created=NOW - datetime.timedelta(hours=24), poignancy=5, embedding_key="k")

    assert retention.recency_score(node, NOW) == pytest.approx(0.5)


def test_a_recent_memory_outscores_a_stale_one(monkeypatch):
    """The baseline has this backwards: its first-listed, least recently used memory scores highest."""
    enable(monkeypatch)
    recent = FakeNode("a", created=NOW - datetime.timedelta(hours=1), poignancy=5, embedding_key="k")
    stale = FakeNode("b", created=NOW - datetime.timedelta(hours=100), poignancy=5, embedding_key="k")

    assert retention.recency_score(recent, NOW) > retention.recency_score(stale, NOW)


def test_score_does_not_depend_on_how_much_else_the_agent_remembers(monkeypatch):
    """
    The baseline's exponent is a memory's position in a list, so the same memory scores differently in
    a small store and a large one. Time-based scoring is a property of the memory alone.
    """
    enable(monkeypatch)
    node = FakeNode("node_1", created=NOW - datetime.timedelta(hours=6), poignancy=5, embedding_key="k")
    alone = retention.recency_score(node, NOW)

    make_store(500)  # a busier agent; the memory itself has not changed
    assert retention.recency_score(node, NOW) == alone


def test_importance_lengthens_the_half_life(monkeypatch):
    enable(monkeypatch, importance_coupled_decay=True)
    dull = FakeNode("a", created=NOW, poignancy=1, embedding_key="k")
    vivid = FakeNode("b", created=NOW, poignancy=10, embedding_key="k")

    assert retention.effective_halflife(dull) == pytest.approx(24.0)
    assert retention.effective_halflife(vivid) == pytest.approx(24.0 * 4.0)
    # Which is to say: a poignant memory survives four days as well as a mundane one survives one.
    assert retention.recency_score(vivid, NOW + datetime.timedelta(days=4)) == pytest.approx(
        retention.recency_score(dull, NOW + datetime.timedelta(days=1))
    )
    # At the same age the poignant one is always the better recalled.
    day = NOW + datetime.timedelta(days=1)
    assert retention.recency_score(vivid, day) > retention.recency_score(dull, day)


def test_importance_is_ignored_unless_its_own_flag_is_on(monkeypatch):
    enable(monkeypatch)  # time-based recency, but no importance coupling
    vivid = FakeNode("b", created=NOW, poignancy=10, embedding_key="k")

    assert retention.effective_halflife(vivid) == pytest.approx(24.0)


def test_rehearsal_strengthens_with_diminishing_returns_and_a_ceiling(monkeypatch):
    enable(monkeypatch, rehearsal_strengthening=True)

    def halflife_after(recalls):
        node = FakeNode("a", created=NOW, poignancy=5, embedding_key="k")
        node.rehearsal_count = recalls
        return retention.effective_halflife(node)

    first = halflife_after(1) - halflife_after(0)
    hundredth = halflife_after(100) - halflife_after(99)
    assert first > hundredth > 0  # each recall helps, but less than the last
    assert halflife_after(10_000) < 24.0 * 3.0  # nothing ever becomes permanent


def test_a_recall_is_counted_only_when_rehearsal_is_on(monkeypatch):
    node = FakeNode("a", created=NOW, poignancy=5, embedding_key="k")
    retention.note_retrieval(node)
    assert not hasattr(node, "rehearsal_count")

    enable(monkeypatch, rehearsal_strengthening=True)
    retention.note_retrieval(node)
    assert node.rehearsal_count == 1


def test_the_power_law_forgets_more_gently_than_the_exponential(monkeypatch):
    """
    Murre and Dros (2015) find a power law fits human forgetting better than a single exponential: the
    rate of forgetting itself slows, so old memories decline more gently. Both are offered so the claim
    can be tested rather than assumed.
    """
    old = FakeNode("a", created=NOW - datetime.timedelta(days=30), poignancy=5, embedding_key="k")

    enable(monkeypatch)
    exponential = retention.recency_score(old, NOW)
    enable(monkeypatch, decay_shape="power_law")
    power_law = retention.recency_score(old, NOW)

    assert power_law > exponential


def test_the_contribution_takes_over_retrieval_when_enabled(monkeypatch):
    """Turning the flag on must actually change which memories come back, or nothing is being tested."""
    focal = ["What did I do today?"]
    baseline = retrieve._new_retrieve(FakePersona(make_store()), focal, n_count=3)

    enable(monkeypatch)
    improved = retrieve._new_retrieve(FakePersona(make_store()), focal, n_count=3)

    assert [n.node_id for n in improved[focal[0]]] != [n.node_id for n in baseline[focal[0]]]


# --- persisting the access history ---------------------------------------------------------------


def test_a_saved_access_history_is_restored_when_the_flag_is_on(monkeypatch):
    monkeypatch.setattr(retention, "RECENCY_ACCESS_PERSISTED", True)
    node = FakeNode("node_1", created=NOW - datetime.timedelta(days=3), poignancy=5, embedding_key="k")
    retention.restore_access(node, {"last_accessed": "2023-02-13 11:00:00", "rehearsal_count": 7})

    assert node.last_accessed == datetime.datetime(2023, 2, 13, 11, 0, 0)
    assert node.rehearsal_count == 7


def test_an_older_checkpoint_without_the_new_fields_still_loads(monkeypatch):
    """The three-day reference run predates both fields; it must not become unloadable."""
    monkeypatch.setattr(retention, "RECENCY_ACCESS_PERSISTED", True)
    node = FakeNode("node_1", created=NOW - datetime.timedelta(days=3), poignancy=5, embedding_key="k")
    retention.restore_access(node, {"created": "2023-02-10 12:00:00"})

    assert node.last_accessed == node.created
    assert node.rehearsal_count == 0


def test_an_unreadable_timestamp_falls_back_to_the_creation_time(monkeypatch):
    monkeypatch.setattr(retention, "RECENCY_ACCESS_PERSISTED", True)
    node = FakeNode("node_1", created=NOW - datetime.timedelta(days=3), poignancy=5, embedding_key="k")
    retention.restore_access(node, {"last_accessed": "yesterday afternoon"})

    assert node.last_accessed == node.created
