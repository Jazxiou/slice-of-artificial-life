"""
The live town lifecycle: one persistent save, reopened in place, stopped by a control file.
What is pinned here, and why it matters: the town is the one simulation that is *reopened* rather
than forked, so the reopen path must not copy a folder onto itself, must not rewrite the save's
ancestry, and must resume at the recorded step. The control protocol is how the viewer's buttons
will reach the backend, so a malformed or half-written file has to read as "no request" rather than
crash a town that has been running for a week. And the stop hook has to actually stop the loop,
which is tested against a real `ReverieServer` running a persona-free world: every part of the
lockstep machinery runs, and none of it needs a model.
"""

import datetime
import json
import os
import pathlib

import pytest
import run_livetown
import utils

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "reverie" / "backend_server"


# --- the control file protocol -------------------------------------------------------------------


@pytest.fixture()
def temp_control(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "fs_temp_storage", str(tmp_path))
    return tmp_path / "livetown_control.json"


def test_no_file_means_no_action(temp_control):
    assert run_livetown.pending_action() is None


def test_both_buttons_are_understood(temp_control):
    temp_control.write_text('{"action": "save_exit"}')
    assert run_livetown.pending_action() == "save_exit"
    temp_control.write_text('{"action": "exit"}')
    assert run_livetown.pending_action() == "exit"


def test_garbage_and_half_written_files_read_as_no_request(temp_control):
    """The backend polls between steps; an incomplete write is picked up whole on the next poll."""
    temp_control.write_text('{"action": "sav')
    assert run_livetown.pending_action() is None
    temp_control.write_text('{"action": "reboot the universe"}')
    assert run_livetown.pending_action() is None


def test_clear_removes_a_stale_click(temp_control):
    temp_control.write_text('{"action": "exit"}')
    run_livetown.clear_control()
    assert run_livetown.pending_action() is None
    run_livetown.clear_control()  # clearing nothing is fine too


# --- the town profile ------------------------------------------------------------------------------


def test_the_profile_switches_everything_on(monkeypatch):
    for name in run_livetown.TOWN_PROFILE:
        monkeypatch.setattr(utils, name, getattr(utils, name, False), raising=False)

    applied = run_livetown.apply_town_profile()

    assert all(applied.values())
    for name in run_livetown.TOWN_PROFILE:
        assert getattr(utils, name) is True
    # The profile must cover both halves: the contribution and the town guardrails.
    assert {"persona_reanchor", "importance_within_type", "world_needs", "memory_eviction", "idle_memory_dedup"} <= set(
        applied
    )


def test_a_starter_template_cannot_be_opened_as_a_town():
    """Opening base_* in place would mutate the template every future town is forked from."""
    with pytest.raises(SystemExit):
        run_livetown.main(["base_the_ville_n25"])


# --- picking a cast size for a new town ---------------------------------------------------------------


def test_an_explicit_cast_size_skips_the_question():
    assert run_livetown.choose_base("3") == "base_the_ville_isabella_maria_klaus"
    assert run_livetown.choose_base("8") == "base_the_ville_n8"
    assert run_livetown.choose_base("25") == "base_the_ville_n25"


def test_the_interactive_question_accepts_an_answer():
    assert run_livetown.choose_base(ask=lambda _: "8") == "base_the_ville_n8"
    assert run_livetown.choose_base(ask=lambda _: " 3 ") == "base_the_ville_isabella_maria_klaus"


def test_enter_and_nonsense_both_fall_back_to_the_default():
    """A blank answer means 'the default'; a typo must not crash a launch, just fall back."""
    assert run_livetown.choose_base(ask=lambda _: "") == "base_the_ville_n25"
    assert run_livetown.choose_base(ask=lambda _: "seven") == "base_the_ville_n25"


def test_a_piped_launch_never_blocks_on_input():
    """No ask function and no terminal: the launcher must decide by itself, not hang on stdin."""
    assert run_livetown.choose_base() == "base_the_ville_n25"  # pytest's stdin is not a tty


def test_every_cast_size_names_a_base_that_exists():
    """A typo in CAST_BASES would only surface at first launch; catch it here instead."""
    storage = BACKEND.parents[1] / "environment" / "frontend_server" / "storage"
    for base in run_livetown.CAST_BASES.values():
        assert (storage / base / "reverie" / "meta.json").exists()


def test_the_default_trace_path_names_the_town_and_the_moment():
    when = datetime.datetime(2023, 2, 13, 21, 5)
    assert (
        run_livetown.default_trace_path("Dramarama", when) == "../../traces/livetown_Dramarama_20230213_2105.jsonl.gz"
    )


# --- reopening a save in place ----------------------------------------------------------------------
# These construct a real ReverieServer on a persona-free world: the maze, the meta handling and the
# step loop are all the real ones; only the cast is empty, so no model is ever consulted.


def town_folder(storage, name, step=0, fork="base_the_ville_n25"):
    folder = storage / name
    (folder / "reverie").mkdir(parents=True)
    (folder / "environment").mkdir()
    meta = {
        "fork_sim_code": fork,
        "start_date": "February 13, 2023",
        "curr_time": "February 13, 2023, 00:00:00",
        "sec_per_step": 10,
        "maze_name": "the_ville",
        "persona_names": [],
        "step": step,
    }
    (folder / "reverie" / "meta.json").write_text(json.dumps(meta))
    (folder / "environment" / f"{step}.json").write_text("{}")
    return folder


@pytest.fixture()
def reverie_module(tmp_path, monkeypatch):
    """The real reverie module, pointed at scratch storage, run from the backend directory."""
    monkeypatch.chdir(BACKEND)
    import reverie

    storage = tmp_path / "storage"
    temp = tmp_path / "temp_storage"
    storage.mkdir()
    temp.mkdir()
    monkeypatch.setattr(reverie, "fs_storage", str(storage))
    monkeypatch.setattr(reverie, "fs_temp_storage", str(temp))
    return reverie, storage


def test_reopening_neither_copies_nor_rewrites_the_ancestry(reverie_module):
    reverie, storage = reverie_module
    town_folder(storage, "dramarama", step=7)
    (storage / "dramarama" / "environment" / "7.json").write_text("{}")
    before = (storage / "dramarama" / "reverie" / "meta.json").read_text()

    server = reverie.ReverieServer("dramarama", "dramarama")

    assert server.step == 7  # resumed, not restarted
    assert server.fork_sim_code == "base_the_ville_n25"  # ancestry kept, not self-parented
    assert (storage / "dramarama" / "reverie" / "meta.json").read_text() == before
    assert [p.name for p in storage.iterdir()] == ["dramarama"]  # no second copy appeared


def test_forking_still_copies_and_records_the_fork(reverie_module):
    """The stock path, unchanged: two different names make a copy and stamp its parentage."""
    reverie, storage = reverie_module
    town_folder(storage, "parent")

    server = reverie.ReverieServer("parent", "child")

    assert (storage / "child").exists()
    meta = json.loads((storage / "child" / "reverie" / "meta.json").read_text())
    assert meta["fork_sim_code"] == "parent"
    assert server.fork_sim_code == "parent"


def test_the_stop_hook_ends_an_open_ended_run(reverie_module):
    """
    Two steps' worth of environment files are on disk and the counter allows both, but the hook asks
    to stop after the first: the loop must end at step 1, not step 2. This is the exact mechanism the
    viewer's buttons use, driven through the real step loop.
    """
    reverie, storage = reverie_module
    folder = town_folder(storage, "stoppable")
    (folder / "environment" / "1.json").write_text("{}")

    server = reverie.ReverieServer("stoppable", "stoppable")
    server.server_sleep = 0
    server.stop_requested = lambda: "exit"
    server.start_server(2)

    assert server.step == 1
    assert server.curr_time == datetime.datetime(2023, 2, 13, 0, 0, 10)
    assert (folder / "movement" / "0.json").exists()  # the step it took was a real one
    assert not (folder / "movement" / "1.json").exists()  # and the one it was denied never ran
