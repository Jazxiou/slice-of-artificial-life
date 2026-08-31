"""
Record and replay harness.

A single simulated day can take an hour which can make debugging
painful. So this module sits between the simulation and the model to
record what happens.

    RECORD  Run the simulatio once and every exchange is appended to a
            trace file.
    REPLAY  Run it again offline, which will feed those same recorded
            answers back. Allows a full day to replay within seconds.

Why?
1.  Bugs become reproducible.
2.  Output parsing fixes become easier, a trace would show exactly
    replies break it.
3.  Cost and latency are measured.

How to run:
    LLM_TRACE=record LLM_TRACE_FILE=traces/day1.jsonl python reverie.py
    LLM_TRACE=replay LLM_TRACE_FILE=traces/day1.jsonl python reverie.py

    LLM_TRACE_EMBEDDINGS=1  Also record embedding vectors (bigger
                            files, only needed if you want retrieval to
                            behave identically on replay)
    LLM_TRACE_ON_MISS=error Displays error messages when replaying a
                            question that was never recorded, instead
                            of returning a placeholder.
"""

import atexit
import gzip
import hashlib
import json
import os
import threading


def _open_trace(path, mode):
    """Open a trace even if compressed."""
    if str(path).endswith(".gz"):
        return gzip.open(path, mode + "t", encoding="utf-8", compresslevel=6)
    return open(path, mode, encoding="utf-8")


MODE = os.environ.get("LLM_TRACE", "off").lower()
TRACE_FILE = os.environ.get("LLM_TRACE_FILE", "traces/run.jsonl")
RECORD_EMBEDDINGS = os.environ.get("LLM_TRACE_EMBEDDINGS", "") not in ("", "0", "false")
ON_MISS = os.environ.get("LLM_TRACE_ON_MISS", "stub").lower()

_lock = threading.Lock()

WAITING_STAGE = "waiting for the browser"

# Which prompt template produced the question about to be asked.
# `generate_prompt()` sets this just before building each prompt, so
# every recorded entry can be labelled with the exact template it came
# from (e.g. "v3_ChatGPT/poignancy_event_v1.txt").
_current_template = None


def note_template(path):
    """
    Called by generate_prompt() so the next recorded call knows which
    template it came from.
    """
    global _current_template
    if path:
        parts = str(path).replace("\\", "/").split("/")
        _current_template = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def current_template():
    return _current_template or "unknown"


def _key(text):
    """
    A short id for a piece of text, so the same question can be found
    again on replay.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# === Recording ===


class _Recorder:
    def __init__(self, path):
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        _open_trace(self.path, "w").close()  # start a fresh file for each run
        self.calls = 0
        self.seconds = 0.0
        self.failures = 0
        self.cached = 0
        # Wall-clock
        self.stages = {}
        self.steps = 0
        self.step_seconds = 0.0
        self._write_header()

    def _write_header(self):
        """
        For the first line of the trace list which conditions produced
        it.
        """
        config, persona_config = {}, {}
        try:
            from memory_ext import longevity, persona, retention, retrieval
            from world_ext import emotion as world_emotion
            from world_ext import needs as world_needs
            from world_ext import relationships as world_relationships
            from world_ext import snapshot as world_snapshot

            config, persona_config = retention.config(), persona.config()
            config = dict(
                config,
                **retrieval.config(),
                **longevity.config(),
                **world_needs.config(),
                **world_emotion.config(),
                **world_relationships.config(),
                **world_snapshot.config(),
            )
        except Exception:
            pass  # a trace can still be read without the header
        self._write({"type": "run", "memory_config": config, "persona_config": persona_config})

    def _write(self, record):
        with _lock, _open_trace(self.path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def llm(self, prompt, response, seconds, model, params, cached=False):
        self.calls += 1
        self.seconds += seconds
        if cached:
            self.cached += 1
        record = {
            "type": "llm",
            "template": current_template(),
            "key": _key(prompt),
            "model": model,
            "params": params,
            "seconds": round(seconds, 3),
            "prompt": prompt,
            "response": response,
        }
        if cached:
            record["cached"] = True
        self._write(record)

    def failure(self, prompt, exc, seconds, model, params):
        """Record failures (calls that were not answered)."""
        self.calls += 1
        self.seconds += seconds
        self.failures += 1
        self._write({
            "type": "llm_failure",
            "template": current_template(),
            "key": _key(prompt),
            "model": model,
            "params": params,
            "seconds": round(seconds, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "prompt": prompt,
        })

    def stage(self, name, seconds):
        """
        Accumulate time spent in a non-model stage, e.g. retrieval or
        saving state.
        """
        entry = self.stages.setdefault(name, [0, 0.0])
        entry[0] += 1
        entry[1] += seconds

    def step(self, index, seconds):
        self.steps += 1
        self.step_seconds += seconds
        self._write({"type": "step", "step": index, "seconds": round(seconds, 3)})

    def world(self, step, when, memory_counts):
        """
        A snapshot of how big each agent's memory has grown, recorded
        at each checkpoint.
        """
        self._write({"type": "world", "step": step, "when": when, "memories": memory_counts})

    def drift(self, agent, record):
        """
        One agent's identity drift for one simulated day, and whether anything was done about it.
        """
        self._write({"type": "drift", "agent": agent, **record})

    def evicted(self, agent, record):
        """
        One overnight eviction sweep: how big the store was, how big it is now, and under what cap.
        Written at most once per agent per simulated day, and only when a sweep actually ran, so a town
        trace shows exactly when forgetting happened and how much it took.
        """
        self._write({"type": "evicted", "agent": agent, **record})

    def embedding(self, text, vector, seconds):
        # Count and time every embedding even when the vectors are not
        # being stored.
        self.stage("embedding", seconds)
        if not RECORD_EMBEDDINGS:
            return
        self._write({
            "type": "embedding",
            "key": _key(text),
            "seconds": round(seconds, 3),
            "text": text,
            "vector": [round(float(x), 5) for x in vector],
        })


# === Replaying ===


class _Replayer:
    """
    Replays previously recorded answers.

    Looking up an answer, in order of preference:
        1.  The exact same question was recorded -> give back exactly
            what the model said.
        2.  The next unused answer from the same prompt template, lets
            a run still finish after a prompt has been edited.
        3.  Otherwise a placeholder (or an error with
            LLM_TRACE_ON_MISS=error).

    The counts of each are printed at the end to see how faithful a
    replay was.
    """

    def __init__(self, path):
        self.by_question = {}
        self.by_template = {}
        self.cursor = {}
        self.embeddings = {}
        with _open_trace(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("type") == "llm":
                    self.by_question.setdefault(rec["key"], rec["response"])
                    self.by_template.setdefault(rec.get("template", "unknown"), []).append(rec["response"])
                elif rec.get("type") == "embedding":
                    self.embeddings[rec["key"]] = rec["vector"]
        self.exact = 0
        self.same_template = 0
        self.missing = 0

    def llm(self, prompt):
        k = _key(prompt)
        if k in self.by_question:
            self.exact += 1
            return self.by_question[k]

        pool = self.by_template.get(current_template())
        if pool:
            i = self.cursor.get(current_template(), 0)
            self.cursor[current_template()] = i + 1
            self.same_template += 1
            return pool[i % len(pool)]

        self.missing += 1
        if ON_MISS == "error":
            raise KeyError(f"No recorded answer for a prompt from template {current_template()!r}")
        return "This is a replayed placeholder (nothing was recorded for this prompt)."

    def embedding(self, text, dim=384):
        """
        Recorded vector if it exists. Otherwise a made-up but
        consistent vector derived from the text, so the same text
        always gets the same vector and retrieval behaves stably. It is
        not the real model's opinion, so don't judge retrieval quality
        from it.
        """
        k = _key(text)
        if k in self.embeddings:
            return self.embeddings[k]
        import numpy as np

        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        v = np.random.default_rng(seed).standard_normal(dim)
        return [float(x) for x in v / (np.linalg.norm(v) + 1e-10)]

    def summary(self):
        return (
            f"[trace] replay finished — exact matches: {self.exact}, "
            f"same-template fallbacks: {self.same_template}, missing: {self.missing}"
        )


# ======

recorder = _Recorder(TRACE_FILE) if MODE == "record" else None
replayer = _Replayer(TRACE_FILE) if MODE == "replay" else None

if MODE == "record":
    print(f"[trace] recording every model call to {TRACE_FILE}")
elif MODE == "replay":
    print(f"[trace] replaying model calls from {TRACE_FILE}")


def is_replaying():
    return replayer is not None


def is_recording():
    return recorder is not None


def stage(name, seconds):
    """Record time spent in a non-model stage."""
    if recorder:
        recorder.stage(name, seconds)


def step(index, seconds):
    """Record the wall-clock of one simulation step."""
    if recorder:
        recorder.step(index, seconds)


def world(step_index, when, memory_counts):
    """Record how large each agent's memory is."""
    if recorder:
        recorder.world(step_index, when, memory_counts)


def drift(agent, record):
    """Record one agent's daily identity drift."""
    if recorder:
        recorder.drift(agent, record)


def evicted(agent, record):
    """Record one overnight memory-eviction sweep. Ignored when tracing is off."""
    if recorder:
        recorder.evicted(agent, record)


def report():
    """Print a short summary at the end of a run."""
    if recorder:
        n, s, f = recorder.calls, recorder.seconds, recorder.failures
        mean = (s / n) if n else 0
        note = f", {f} FAILED" if f else ""
        print(
            f"[trace] recorded {n} model calls{note}, {s / 60:.1f} minutes of model time "
            f"({mean:.2f}s average) -> {recorder.path}"
        )
        if f and f == n:
            print(
                "[trace] every call failed, the model was unreachable. "
                "Check llm_base_url in utils.py against your running server."
            )
        if recorder.steps:
            # Total run time is the sum of the two.
            waiting = recorder.stages.get(WAITING_STAGE, [0, 0.0])[1]
            body = recorder.step_seconds
            total = body + waiting
            inside = {k: v for k, v in recorder.stages.items() if k != WAITING_STAGE}
            print(f"[trace] {recorder.steps} steps, {total / 60:.1f} minutes total")
            print(
                f"[trace]    {body / 60:6.1f} min  {100 * body / total:5.1f}%  the backend thinking, broken down below"
            )
            accounted = s
            for name, (count, secs) in sorted(inside.items(), key=lambda x: -x[1][1]):
                accounted += secs
                print(f"[trace]      {secs / 60:6.1f} min  {100 * secs / body:5.1f}%  {name} ({count} calls)")
            print(f"[trace]      {s / 60:6.1f} min  {100 * s / body:5.1f}%  model calls")
            print(
                f"[trace]      {(body - accounted) / 60:6.1f} min  {100 * (body - accounted) / body:5.1f}%  "
                f"pathfinding, saving state, everything else"
            )
            if waiting:
                print(
                    f"[trace]    {waiting / 60:6.1f} min  {100 * waiting / total:5.1f}%  waiting for the browser "
                    f"to animate and post the world back"
                )
    if replayer:
        print(replayer.summary())


# Print the summary however the run ends
if MODE in ("record", "replay"):
    atexit.register(report)
