"""
The live town: an open-ended, resumable simulation with one persistent save per town.

    cd reverie/backend_server
    uv run python run_livetown.py Name_of_Simulation

This is a second entry point beside `reverie.py`, and the two stay separate on purpose. The stock
entry point exists to run *measured conditions*: it asks which simulation to fork, forks it into a
fresh folder, runs an exact number of steps, and its flags come from `utils.py` so a condition is
what the configuration file says it is. The town is the opposite kind of thing: one world with one
name, running for as long as it is watched, resumed across sessions, with every system switched on.
So the town gets its own command, its own lifecycle, and its own flag profile, and the stock flow
keeps its exact behaviour and terminal UI.

How the lifecycle works:

  * **First launch** with a new name forks the 25-agent base (`base_the_ville_n25`) into
    `storage/<name>`. That folder is the town's one save, forever.
  * **Every later launch** with the same name reopens that folder in place; no fork-per-session, so
    storage does not grow by a copy of the whole town each time it is opened.
  * **No step count is asked for.** The run is open-ended and stops when told to: the viewer's
    save-and-exit or exit button (which write the control file below), or Ctrl-C in the terminal,
    which saves and stops (the stock interrupt behaviour, and the safe default).
  * **Save and exit** writes the save and ends the session; the next launch picks up at that exact
    step. **Exit** ends the session without writing, so the next launch resumes from the last
    checkpoint instead: the midnight autosave (`autosave_every`) checkpoints the town once per
    simulated day whatever the buttons do.

How the viewer talks to a running town: it writes one small JSON file,
`temp_storage/livetown_control.json`, containing `{"action": "save_exit"}` or `{"action": "exit"}`.
The backend polls it between steps. A file, not a socket, because files are already how this
codebase's two halves talk (the frontend posts the world as `environment/<step>.json`, the backend
answers with `movement/<step>.json`), and the control file simply joins that protocol. Until the
viewer's buttons exist, writing the file by hand does the same job, and Ctrl-C is always available.

The town profile: the flags below are applied to the configuration *before* the simulation modules
are imported, because every module copies its flags out of `utils` at import time. This is also why
`reverie` is imported inside `main()` rather than at the top of this file: importing it first would
freeze the measured-condition defaults before the profile could be applied. `utils.py` itself is
untouched, so the same checkout runs measured conditions through `reverie.py` and the town through
this command without editing configuration in between.
"""

import argparse
import datetime
import json
import os
import sys

import utils

# Everything on: the research contribution (the town is the whole improved system) and the town
# guardrails (dedup, compact files, overnight eviction) plus the needs layer. Measured conditions
# never run through this entry point, so these never leak into an evaluation.
TOWN_PROFILE = {
    "recency_time_based": True,
    "recency_access_persisted": True,
    "importance_coupled_decay": True,
    "rehearsal_strengthening": True,
    "importance_within_type": True,
    "persona_reanchor": True,
    "world_needs": True,
    "world_emotion": True,
    "world_relationships": True,
    "world_snapshots": True,
    "idle_memory_dedup": True,
    "compact_embeddings": True,
    "memory_eviction": True,
}

# The three cast sizes a new town can start from, so a run can be sized to the machine at hand.
CAST_BASES = {"3": "base_the_ville_isabella_maria_klaus", "8": "base_the_ville_n8", "25": "base_the_ville_n25"}
DEFAULT_CAST = "25"

CONTROL_ACTIONS = ("save_exit", "exit")


def choose_base(cast=None, ask=None):
    """
    The starter simulation for a NEW town: from --cast when given, else by asking, else the default.
    `ask` is injected so tests can script the answer; it is only consulted when the terminal is
    interactive, so a piped or scheduled launch never blocks on input.
    """
    if cast:
        return CAST_BASES[str(cast)]
    if ask is None and sys.stdin.isatty():
        ask = input
    if ask is not None:
        answer = ask(f"How many characters? 3, 8 or 25 (enter for {DEFAULT_CAST}): ").strip()
        if answer in CAST_BASES:
            return CAST_BASES[answer]
        if answer:
            print(f"[livetown] '{answer}' is not a cast size; using {DEFAULT_CAST}.")
    return CAST_BASES[DEFAULT_CAST]


def default_trace_path(save_name, now=None):
    """One trace file per town session, so a long-lived town stays analysable run by run."""
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M")
    return f"../../traces/livetown_{save_name}_{stamp}.jsonl.gz"


def apply_town_profile():
    """Set the town's flags on the configuration module. Must run before `import reverie`."""
    for name, value in TOWN_PROFILE.items():
        setattr(utils, name, value)
    return dict(TOWN_PROFILE)


def control_path():
    # Read from `utils` at call time, not import time, so tests can point it at a scratch folder.
    return f"{utils.fs_temp_storage}/livetown_control.json"


def pending_action():
    """
    The action the viewer has asked for, or None.
    A half-written or malformed file reads as None rather than an error: the backend polls between
    steps, so an incomplete write is simply picked up whole on the next poll.
    """
    path = control_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            action = json.load(f).get("action")
    except (json.JSONDecodeError, OSError):
        return None
    return action if action in CONTROL_ACTIONS else None


def clear_control():
    path = control_path()
    if os.path.exists(path):
        os.remove(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the live town: open-ended, resumable, every system on.")
    parser.add_argument("save_name", help="the town's name; also its save folder under storage/")
    parser.add_argument(
        "--cast",
        choices=sorted(CAST_BASES),
        default=None,
        help="characters in a NEW town: 3, 8 or 25 (asked interactively if omitted)",
    )
    parser.add_argument("--base", default=None, help="explicit starter simulation for a new town (overrides --cast)")
    parser.add_argument("--no-trace", action="store_true", help="do not record a model-call trace for this session")
    args = parser.parse_args(argv)

    if args.save_name.startswith("base_"):
        # The starter simulations are templates. Opening one in place would mutate the template itself
        # and quietly poison every future town and evaluation forked from it.
        sys.exit(f"'{args.save_name}' is a starter template; pick a town name that does not begin with 'base_'.")

    profile = apply_town_profile()

    # Record every session by default: the town is the long-run instrument, and a trace costs a few
    # megabytes per simulated day against hours of model time that are gone if unrecorded. An
    # explicitly set LLM_TRACE always wins; --no-trace turns recording off for this session.
    if not args.no_trace and "LLM_TRACE" not in os.environ:
        os.environ["LLM_TRACE"] = "record"
        os.environ.setdefault("LLM_TRACE_FILE", default_trace_path(args.save_name))

    # Imported only now, after the profile and the trace environment are set.
    from memory_ext import longevity, retention
    from memory_ext import persona as persona_ext
    from world_ext import emotion as world_emotion
    from world_ext import needs as world_needs
    from world_ext import relationships as world_relationships

    import reverie

    sim_folder = f"{utils.fs_storage}/{args.save_name}"
    resuming = os.path.exists(sim_folder)
    # A resumed town keeps the cast it was created with; the question is only asked for a new one.
    fork = args.save_name if resuming else (args.base or choose_base(args.cast))

    clear_control()  # a click left over from the previous session must not stop this one

    server = reverie.ReverieServer(fork, args.save_name)
    server.stop_requested = pending_action

    print("---")
    if resuming:
        print(f"[livetown] resuming '{args.save_name}' at step {server.step} ({server.curr_time})")
    else:
        print(f"[livetown] new town '{args.save_name}' created from {fork} ({len(server.personas)} characters)")
    for line in (
        retention.describe(),
        persona_ext.describe(),
        longevity.describe(),
        world_needs.describe(),
        world_emotion.describe(),
        world_relationships.describe(),
    ):
        print(f"[livetown] {line}")
    if os.environ.get("LLM_TRACE", "off").lower() == "record":
        print(f"[livetown] recording this session's model calls to {os.environ.get('LLM_TRACE_FILE')}")
    print("[livetown] open http://localhost:8000/livetown in the browser (it drives the clock).")
    print("[livetown] to stop: the viewer's save-and-exit / exit buttons, or Ctrl-C here (saves, then stops).")
    print("---")

    # Open-ended: the loop ends through the control file, or through Ctrl-C (which saves inside
    # start_server before returning). The counter is only a ceiling the town never reaches.
    server.start_server(10**9)

    action = pending_action()
    clear_control()
    if action == "save_exit":
        server.save()
        print(
            f"[livetown] saved at step {server.step} ({server.curr_time}). "
            f"Launching '{args.save_name}' again picks up exactly here."
        )
    elif action == "exit":
        print(
            f"[livetown] exited without saving. The next launch of '{args.save_name}' resumes "
            f"from the last checkpoint (midnight autosave or last save-and-exit)."
        )
    else:
        print(
            f"[livetown] stopped at step {server.step}; progress was saved. "
            f"Launching '{args.save_name}' again picks up here."
        )


if __name__ == "__main__":
    main()
