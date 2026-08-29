"""
Scoring the persona interview.
The property that matters most here is that *change is not automatically failure*. The claim under test
is that re-anchoring reduces drift while preserving believable adaptation, so an instrument that graded
every change as drift would score a frozen character as a perfect one and would reward the worse system.
The four grades are therefore kept apart, and the drift rate deliberately excludes "adapted".
The second property is that the two measurements stay separate. Distance from the seed is cheap and
blunt: it sees topic and not truth. The first persona pilot produced the case that proves it, where a
cafe owner whose seed is about a Valentine's party wrote a paragraph of party narration that measured
*close* to her anchor while having stopped being a description of a person at all. A scorer that
collapsed the two numbers into one would hide exactly that.
The model and the embeddings are stubs; nothing here contacts a server.
"""

import json

import pytest

from evaluation import persona_score

KLAUS = {
    "name": "Klaus Mueller",
    "innate": "analytical, curious, methodical",
    "learned": "Klaus Mueller is a student at Oak Hill College studying sociology.",
    "currently": "Klaus Mueller has been helping organise an event at Hobbs Cafe.",
    "seed_currently": "Klaus Mueller is writing a research paper on the effects of "
    "gentrification in low-income communities.",
}


def judge(grade, why="because"):
    def generate(prompt):
        generate.prompts.append(prompt)
        return json.dumps({"grade": grade, "why": why})

    generate.prompts = []
    return generate


def embedder(distance):
    """A stub whose cosine distance from the anchor is whatever the test asks for."""
    import math

    def embed(text):
        if text.startswith("Name: "):
            return [1.0, 0.0]
        theta = math.acos(max(-1.0, min(1.0, 1.0 - distance)))
        return [math.cos(theta), math.sin(theta)]

    return embed


def answers(n=1, text="I am a sociology student writing about gentrification."):
    return [{"kind": f"B{i + 1}_x", "question": "Who are you?", "answer": text} for i in range(n)]


# --- the anchor ------------------------------------------------------------------------------------


def test_the_anchor_is_the_seed_not_the_present_state():
    anchor, has_seed = persona_score.anchor_of(KLAUS)
    assert "research paper" in anchor
    assert "Hobbs Cafe" not in anchor
    assert has_seed is True


def test_an_older_checkpoint_anchors_to_what_it_has_and_says_so():
    """Anchoring a run to its own drifted state would look like it was working while doing nothing."""
    older = {k: v for k, v in KLAUS.items() if k != "seed_currently"}
    anchor, has_seed = persona_score.anchor_of(older)
    assert "Hobbs Cafe" in anchor
    assert has_seed is False


# --- change is not automatically failure -------------------------------------------------------------


def test_an_adapted_character_is_not_counted_as_drifted():
    scored = persona_score.score_interview(answers(4), "Name: Klaus", judge("adapted"))
    summary = persona_score.summarise(scored)

    assert summary["counts"]["adapted"] == 4
    assert summary["drift"] == 0.0
    assert summary["adapted"] == 1.0


def test_drift_pools_the_two_failures_and_only_those():
    graded = ["in_character"] * 2 + ["adapted"] * 2 + ["drifted"] * 3 + ["contradicts"] * 1
    scored = []
    for grade in graded:
        scored += persona_score.score_interview(answers(1), "Name: Klaus", judge(grade))
    summary = persona_score.summarise(scored)

    assert summary["n"] == 8
    assert summary["drift"] == pytest.approx(4 / 8)
    assert summary["in_character"] == pytest.approx(2 / 8)


# --- the two measurements stay apart -----------------------------------------------------------------


def test_a_status_close_to_its_anchor_can_still_be_graded_as_drifted():
    """
    The cafe owner's case from the first persona pilot, in miniature: near the anchor and no longer a
    description of a person. If distance alone decided the grade, this is the case it would get wrong.
    """
    drifted = dict(KLAUS, currently="Klaus spent Wednesday February 15 at the cafe from 9am.")
    verdict = persona_score.score_identity(drifted, embedder(0.05), judge("drifted"))

    assert verdict["distance"] == pytest.approx(0.05)
    assert verdict["grade"] == "drifted"


def test_the_identity_check_also_reports_whether_it_still_reads_as_a_person():
    """Three numbers that do not subsume one another: a judgement, a distance, and the genre."""
    diary = dict(KLAUS, currently="Klaus spent Wednesday February 15 reviewing plans at the cafe.")
    standing = dict(KLAUS, currently="Klaus is a sociology student writing about gentrification.")

    assert persona_score.score_identity(diary, embedder(0.2), judge("drifted"))["dated"] == ["february 15", "wednesday"]
    assert persona_score.score_identity(standing, embedder(0.2), judge("in_character"))["dated"] == []


def test_the_interview_no_longer_carries_a_distance():
    """
    It measured the subject of the question, not the state of the character: the same character scored
    0.36 from its seed when asked who it was and 1.01 when asked how it would sit through a lecture.
    """
    scored = persona_score.score_interview(answers(1), "Name: Klaus", judge("in_character"))
    assert "distance" not in scored[0]["persona"]


# --- failure modes -----------------------------------------------------------------------------------


def test_a_judge_reply_that_cannot_be_read_is_not_guessed_at():
    scored = persona_score.score_interview(answers(2), "Name: Klaus", lambda prompt: "I think it's fine, honestly")
    summary = persona_score.summarise(scored)

    assert summary["counts"]["unscored"] == 2
    assert summary["n"] == 0  # unscored answers do not sit in the denominator
    assert summary["drift"] is None


def test_a_failed_embedding_does_not_lose_the_grade():
    def broken(text):
        raise RuntimeError("no embedding model")

    verdict = persona_score.score_identity(KLAUS, broken, judge("drifted"))

    assert verdict["grade"] == "drifted"
    assert verdict["distance"] is None


def test_an_unanswered_question_is_skipped_rather_than_scored():
    blank = [{"kind": "B7_pressure", "question": "", "answer": ""}]
    scored = persona_score.score_interview(blank, "Name: Klaus", judge("drifted"))

    assert "persona" not in scored[0]
    assert persona_score.summarise(scored)["n"] == 0


def test_the_judge_is_shown_the_seed_and_the_answer():
    write = judge("in_character")
    persona_score.score_interview(answers(1, text="I study physics."), "Name: Klaus\nOriginally: X", write)

    assert "Originally: X" in write.prompts[0]
    assert "I study physics." in write.prompts[0]


def test_the_scorer_puts_the_backend_on_the_path_by_itself():
    import os
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "from evaluation import persona_score;"
        "print(any(p.endswith(('reverie/backend_server', 'reverie\\\\backend_server'))"
        "          for p in sys.path))" % root
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=root)

    assert out.stdout.strip() == "True", out.stderr
