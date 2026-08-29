"""
Two safeguards against a run being wrecked, or misread, by a single call.
A language-model request with no ceiling on it is not merely slow. The simulation is a loop: nothing
else moves while a call is outstanding, so one request the server never answers holds the whole town
still for as long as it likes. In one measured day a prompt whose median is 0.19 seconds took 600.7,
which was 27% of that run's model time on its own. The first half of this file pins the ceiling, and
pins what happens when it is hit: the call must fail like any other failed call, so that the retry
loops already in the system pick it up, and the failure must reach the trace rather than vanishing.
The second half is about reading the trace afterwards. That same call took its template's average
from 0.19 seconds to 1.17 and put it at the top of the cost table, which sent me looking for a slow
prompt that does not exist. A mean alone cannot distinguish "this prompt is expensive" from "this
prompt was asked once while the server was stuck", so the report now prints a median and a p90 beside
it and names the outliers outright.
Nothing here contacts a model server.
"""

import importlib.util
import json
import sys
from pathlib import Path

import llm_trace
import pytest
from persona.prompt_template import gpt_structure as gs

ROOT = Path(__file__).resolve().parents[1]


def _load_trace_report():
    """`tools/` is a directory of scripts rather than a package, so the module is loaded by path."""
    spec = importlib.util.spec_from_file_location("trace_report", ROOT / "tools" / "trace_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report = _load_trace_report()


# --- the ceiling ---------------------------------------------------------------------------------


@pytest.fixture
def fresh_client(monkeypatch):
    """The client is built once and cached in a module global; these tests need it rebuilt."""
    built = {}

    def fake_openai(**kwargs):
        built.update(kwargs)
        return object()

    monkeypatch.setattr(gs, "OpenAI", fake_openai)
    monkeypatch.setattr(gs, "_client", None)
    return built


def test_the_client_is_given_a_timeout(fresh_client):
    gs.get_client()
    assert fresh_client["timeout"] == gs.LLM_TIMEOUT_SECONDS
    assert gs.LLM_TIMEOUT_SECONDS > 0


def test_the_clients_own_retries_are_bounded(fresh_client):
    """
    The OpenAI client retries a timed-out request by itself, which multiplies the wait. The simulation
    has its own retry loops and those at least re-ask at a different temperature, so the ceiling on one
    call has to stay something a reader can compute: timeout times attempts, not timeout times whatever
    the SDK happens to default to.
    """
    gs.get_client()
    assert fresh_client["max_retries"] == gs.LLM_MAX_RETRIES
    assert gs.LLM_MAX_RETRIES <= 2


def test_the_shipped_timeout_is_well_above_the_slowest_honest_prompt():
    """
    The slowest legitimate prompt measured on a real day finished in 19 seconds. A ceiling near that
    would start cutting off honest work; this one can only catch pathology.
    """
    assert gs.LLM_TIMEOUT_SECONDS >= 60


# --- what happens when it is hit -------------------------------------------------------------------


@pytest.fixture
def timing_out(monkeypatch):
    """A client whose every call raises, as a timed-out request does."""

    class Timeout(Exception):
        pass

    def fake_create(model=None, messages=None, **kwargs):
        raise Timeout("Request timed out.")

    class FakeClient:
        class chat:
            class completions:
                create = staticmethod(fake_create)

    monkeypatch.setattr(gs, "get_client", lambda: FakeClient)
    monkeypatch.setattr(llm_trace, "is_replaying", lambda: False)
    return Timeout


def test_a_timed_out_call_is_recorded_as_a_failure(monkeypatch, timing_out):
    """A trace that omits the calls that went wrong is the one place a hang would be invisible."""
    failures = []

    class Recorder:
        @staticmethod
        def failure(prompt, exc, seconds, model, kwargs):
            failures.append((prompt, type(exc).__name__))

    monkeypatch.setattr(llm_trace, "is_recording", lambda: True)
    monkeypatch.setattr(llm_trace, "recorder", Recorder)

    with pytest.raises(timing_out):
        gs._chat("anything", temperature=0)

    assert failures == [("anything", "Timeout")]


def test_a_timed_out_call_looks_like_any_other_failed_call_to_the_caller(monkeypatch, timing_out):
    """
    Which is the point of letting it raise at all: every parser in this system re-asks when it gets
    something it cannot read, and "ChatGPT ERROR" is what that machinery already knows how to see.
    """
    monkeypatch.setattr(llm_trace, "is_recording", lambda: False)
    monkeypatch.setattr(llm_trace, "current_template", lambda: "v2/task_decomp_v3.txt")

    assert gs.ChatGPT_request("anything") == "ChatGPT ERROR"


def test_a_timed_out_call_leaves_nothing_in_the_cache(monkeypatch, timing_out):
    """Otherwise the failure would be served back for the rest of the run without being re-asked."""
    monkeypatch.setattr(llm_trace, "is_recording", lambda: False)
    gs._answer_cache.clear()

    with pytest.raises(timing_out):
        gs._chat("anything", temperature=0)

    assert gs._answer_cache == {}


# --- reading the trace afterwards ------------------------------------------------------------------


def test_the_percentile_is_a_duration_that_actually_happened():
    """Nearest-rank, not interpolated: every printed number should be a call someone waited through."""
    values = [0.1, 0.2, 0.3, 0.4, 100.0]
    assert report.percentile(values, 0.9) == 100.0
    assert report.percentile(values, 0.5) == 0.3
    assert report.percentile([2.0], 0.9) == 2.0


def _write_trace(path, calls):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "run", "memory_config": {"summary": "test"}}) + "\n")
        for template, seconds, key, cached, response in calls:
            f.write(
                json.dumps({
                    "type": "llm",
                    "template": template,
                    "seconds": seconds,
                    "key": key,
                    "cached": cached,
                    "response": response,
                })
                + "\n"
            )


def run_report(path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["trace_report.py", str(path)])
    report.main()
    return capsys.readouterr().out


def test_one_stalled_call_does_not_make_a_cheap_prompt_look_expensive(tmp_path, capsys, monkeypatch):
    """The failure this column was added for: the median and p90 stay honest while the mean does not."""
    trace = tmp_path / "t.jsonl"
    _write_trace(
        trace,
        [("pronunciatio", 0.2, f"k{i}", False, "{}") for i in range(20)]
        + [("pronunciatio", 600.0, "k99", False, "{}")],
    )

    out = run_report(trace, capsys, monkeypatch)
    row = next(line for line in out.splitlines() if line.startswith("pronunciatio"))
    numbers = row.split()
    assert "0.20" in numbers  # median
    assert "600.0" in numbers  # max, so the outlier is still visible
    assert "28.76" in numbers  # mean, 140 times the median


def test_a_stalled_call_is_named(tmp_path, capsys, monkeypatch):
    trace = tmp_path / "t.jsonl"
    _write_trace(
        trace,
        [("pronunciatio", 0.2, f"k{i}", False, "{}") for i in range(20)]
        + [("pronunciatio", 600.0, "k99", False, '{"output": " zanyat"}')],
    )

    out = run_report(trace, capsys, monkeypatch)
    assert "STALLED CALLS" in out
    assert "600.0s" in out
    assert "zanyat" in out  # what came back, which is how it was diagnosed


def test_an_ordinary_run_reports_no_stalled_calls(tmp_path, capsys, monkeypatch):
    """The threshold is relative to the prompt, so a uniformly slow machine must not trip it."""
    trace = tmp_path / "t.jsonl"
    _write_trace(trace, [("decomp", 40.0 + i * 0.1, f"k{i}", False, "{}") for i in range(20)])

    assert "STALLED CALLS" not in run_report(trace, capsys, monkeypatch)


def test_a_slow_prompt_does_not_hide_a_stall_in_a_fast_one(tmp_path, capsys, monkeypatch):
    """
    Which is why the comparison is per template. A run containing one prompt that legitimately takes
    fifteen seconds would set a run-wide threshold high enough to swallow a hang in a prompt whose
    median is a fifth of a second.
    """
    trace = tmp_path / "t.jsonl"
    _write_trace(
        trace,
        [("decomp", 15.0, f"d{i}", False, "{}") for i in range(20)]
        + [("pronunciatio", 0.2, f"p{i}", False, "{}") for i in range(20)]
        + [("pronunciatio", 300.0, "p99", False, "{}")],
    )

    out = run_report(trace, capsys, monkeypatch)
    assert "STALLED CALLS" in out
    assert "pronunciatio" in out.split("STALLED CALLS")[1]
    assert "decomp" not in out.split("STALLED CALLS")[1].split("REPEATED WORK")[0]


def test_cache_hits_do_not_drag_the_median_to_zero(tmp_path, capsys, monkeypatch):
    """
    A cache hit costs nothing by construction. Counting those zeroes in the per-call timings made a
    prompt that takes two seconds report a median of 0.00, which reads as "this prompt is free" when
    what is free is the cache. The minutes column still counts every call.
    """
    trace = tmp_path / "t.jsonl"
    _write_trace(
        trace, [("summarize", 2.0, "k1", False, "x")] + [("summarize", 0.0, "k1", True, "x") for _ in range(9)]
    )

    row = next(line for line in run_report(trace, capsys, monkeypatch).splitlines() if line.startswith("summarize"))
    assert "2.00" in row.split()
    assert "0.00" not in row.split()


def test_a_wholly_cached_template_still_prints(tmp_path, capsys, monkeypatch):
    """Excluding cache hits leaves nothing to time; the row must not disappear or raise."""
    trace = tmp_path / "t.jsonl"
    _write_trace(trace, [("real", 1.0, "k0", False, "x")] + [("cached_only", 0.0, "k1", True, "x") for _ in range(3)])

    out = run_report(trace, capsys, monkeypatch)
    assert "cached_only" in out
