"""
Sampling parameters, retry escalation, and the in-run answer cache.
Three things have to hold together here, and getting any one of them wrong is silent rather than
noisy, which is why they are tested rather than eyeballed.
  * Prompts with a right answer are asked deterministically; dialogue is sampled. If that inverted,
    conversations would get more repetitive and ratings would get noisier, and nothing would crash.
  * A retry must be allowed to differ. At temperature zero, asking the same question again returns
    the same reply: measured on a real run, `generate_event_triple` re-asked twenty times and got a
    byte-identical answer every time before falling back to its fail-safe.
  * The cache must never serve an answer that was rejected, or a bad reply would be handed back on
    every future occurrence of that question and each one would waste an attempt.
The model is replaced with a counting stub throughout; nothing here contacts a server.
"""

import llm_trace
import pytest
from persona.prompt_template import gpt_structure as gs


@pytest.fixture(autouse=True)
def clean_cache():
    gs._answer_cache.clear()
    yield
    gs._answer_cache.clear()


@pytest.fixture
def calls(monkeypatch):
    """Replace the round trip with a stub that records what it was asked and with what parameters."""
    log = []

    def fake_create(model=None, messages=None, **kwargs):
        log.append({"prompt": messages[-1]["content"], **kwargs})

        class Msg:
            content = f"reply {len(log)}"

        class Choice:
            message = Msg()

        class Completion:
            choices = [Choice()]

        return Completion()

    class FakeClient:
        class chat:
            class completions:
                create = staticmethod(fake_create)

    monkeypatch.setattr(gs, "get_client", lambda: FakeClient)
    monkeypatch.setattr(llm_trace, "is_recording", lambda: False)
    monkeypatch.setattr(llm_trace, "is_replaying", lambda: False)
    return log


def use_template(monkeypatch, name):
    monkeypatch.setattr(llm_trace, "current_template", lambda: name)


# --- which prompts are sampled ------------------------------------------------------------------


def test_a_rating_is_asked_deterministically(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/poignancy_event_v1.txt")
    gs.ChatGPT_request("how important is this?")
    assert calls[0]["temperature"] == 0


def test_dialogue_is_sampled(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/iterative_convo_v1.txt")
    gs.ChatGPT_request("say something")
    assert calls[0]["temperature"] == gs.CHAT_VARIED_TEMPERATURE > 0


def test_every_call_states_its_parameters(monkeypatch, calls):
    """The defect being fixed: upstream sent the chat endpoint no sampling parameters at all."""
    use_template(monkeypatch, "v3_ChatGPT/generate_pronunciatio_v1.txt")
    gs.ChatGPT_request("an emoji for this")
    assert "temperature" in calls[0] and "top_p" in calls[0]


# --- retries have to be allowed to differ --------------------------------------------------------


def test_a_retry_escalates_off_zero(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/generate_pronunciatio_v1.txt")
    gs.ChatGPT_request("an emoji for this", attempt=0)
    gs.ChatGPT_request("an emoji for this", attempt=1)
    assert calls[0]["temperature"] == 0
    assert calls[1]["temperature"] == gs.RETRY_TEMPERATURE > 0


def test_a_retry_of_a_sampled_prompt_is_left_alone(monkeypatch, calls):
    """Dialogue is already free to differ, so nothing needs escalating."""
    use_template(monkeypatch, "v3_ChatGPT/iterative_convo_v1.txt")
    gs.ChatGPT_request("say something", attempt=3)
    assert calls[0]["temperature"] == gs.CHAT_VARIED_TEMPERATURE


def test_the_older_path_escalates_only_what_was_pinned_to_zero():
    pinned = {"temperature": 0, "max_tokens": 15}
    already_sampled = {"temperature": 0.8, "max_tokens": 15}

    assert gs.retry_parameters(pinned)["temperature"] == gs.RETRY_TEMPERATURE
    assert gs.retry_parameters(already_sampled) is already_sampled
    assert pinned["temperature"] == 0  # the caller's dictionary is not modified


# --- the cache -----------------------------------------------------------------------------------


def test_the_same_question_is_only_asked_once(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/poignancy_event_v1.txt")
    first = gs.ChatGPT_request("how important is this?")
    second = gs.ChatGPT_request("how important is this?")

    assert first == second
    assert len(calls) == 1


def test_a_sampled_prompt_is_never_cached(monkeypatch, calls):
    """Caching dialogue would quietly make the town repetitive, which is the opposite of the goal."""
    use_template(monkeypatch, "v3_ChatGPT/iterative_convo_v1.txt")
    gs.ChatGPT_request("say something")
    gs.ChatGPT_request("say something")

    assert len(calls) == 2
    assert gs.answer_cache_size() == 0


def test_a_rejected_answer_is_not_served_again(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/poignancy_event_v1.txt")
    gs.ChatGPT_request("how important is this?")
    gs.forget_answer("how important is this?")
    gs.ChatGPT_request("how important is this?")

    assert len(calls) == 2


def test_a_retry_loop_never_reuses_the_reply_it_just_rejected(monkeypatch, calls):
    """
    The whole loop, end to end: a validator that refuses everything must produce `repeat` genuinely
    distinct round trips, not one round trip and two cache hits.
    """
    use_template(monkeypatch, "v3_ChatGPT/poignancy_event_v1.txt")
    out = gs.ChatGPT_safe_generate_response_OLD(
        "how important is this?",
        repeat=3,
        fail_safe_response="fail-safe",
        func_validate=lambda r, prompt="": False,
        func_clean_up=lambda r, prompt="": r,
    )

    assert out == "fail-safe"
    assert len(calls) == 3
    assert [c["prompt"] for c in calls] == ["how important is this?"] * 3
    assert [c["temperature"] for c in calls] == [0, gs.RETRY_TEMPERATURE, gs.RETRY_TEMPERATURE]


def test_the_cache_can_be_turned_off(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/poignancy_event_v1.txt")
    monkeypatch.setattr(gs, "ANSWER_CACHE", False)
    gs.ChatGPT_request("how important is this?")
    gs.ChatGPT_request("how important is this?")

    assert len(calls) == 2


def test_the_cache_stops_growing_at_its_cap(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/poignancy_event_v1.txt")
    monkeypatch.setattr(gs, "ANSWER_CACHE_MAX", 2)
    for i in range(5):
        gs.ChatGPT_request(f"question {i}")

    assert gs.answer_cache_size() == 2
    assert len(calls) == 5


# --- a ceiling on the reply ------------------------------------------------------------------------


def test_a_chat_reply_has_a_length_ceiling(monkeypatch, calls):
    """
    The chat path sent no `max_tokens`, so a reply could run until the model chose to stop. On a
    three-day run one emoji request returned 24,781 characters and took two minutes; the longest
    legitimate chat reply in the same run was 846.
    """
    use_template(monkeypatch, "v3_ChatGPT/generate_pronunciatio_v1.txt")
    gs.ChatGPT_request("an emoji for this")
    assert calls[0]["max_tokens"] == gs.CHAT_MAX_TOKENS


def test_the_ceiling_is_above_every_legitimate_reply():
    """It exists to stop a runaway, not to shape an answer, so it must not be near the real maximum."""
    assert gs.CHAT_MAX_TOKENS >= 256


def test_sampled_prompts_are_capped_too(monkeypatch, calls):
    """Dialogue is the longest thing generated here and still comes nowhere near the cap."""
    use_template(monkeypatch, "v3_ChatGPT/iterative_convo_v1.txt")
    gs.ChatGPT_request("say something")
    assert calls[0]["max_tokens"] == gs.CHAT_MAX_TOKENS


# --- the identity rewrite ---------------------------------------------------------------------------


def test_the_identity_rewrite_states_its_parameters(monkeypatch, calls):
    """
    `ChatGPT_single_request` is used only by `revise_identity`, and it sent nothing at all: the four
    prompts that decide who each agent is ran at whatever temperature the server defaulted to. That is
    the same uncontrolled variance B24 removed from the rest of the chat path, left in the one place
    whose output this project measures.
    """
    gs.ChatGPT_single_request("write a status")
    assert calls[0]["temperature"] == gs.CHAT_VARIED_TEMPERATURE
    assert calls[0]["max_tokens"] == gs.CHAT_MAX_TOKENS


def test_the_identity_rewrite_is_labelled_in_the_trace(monkeypatch, calls):
    """
    With no template file behind it, `llm_trace` kept the last name it had seen and filed all 29 of
    these calls under `wake_up_hour`, which is merely the prompt that runs immediately before them.
    """
    noted = []
    monkeypatch.setattr(llm_trace, "note_template", lambda name: noted.append(name))
    gs.ChatGPT_single_request("write a status", label="revise_identity/currently")
    assert noted == ["revise_identity/currently"]


def test_an_unlabelled_call_does_not_claim_a_template(monkeypatch, calls):
    noted = []
    monkeypatch.setattr(llm_trace, "note_template", lambda name: noted.append(name))
    gs.ChatGPT_single_request("write a status")
    assert noted == []


# --- the system prompt actually sent ----------------------------------------------------------------


def test_the_configured_system_prompt_still_carries_the_language_guard():
    """
    A10 added an English-only instruction to the system prompt, as the prompt half of a guard whose other
    half is `reply_is_english`. It was written as the *default* in gpt_structure, and `utils.py` sets the
    same name to a shorter string, which replaces the default rather than extending it. So the instruction
    was silently absent from every request made from the shipped template: the emoji prompt came back in
    Chinese or Russian in 31% of replies on the three-day run. The test asserts what is actually sent.
    """
    assert "English" in gs.COMPLETION_STYLE_SYSTEM_PROMPT


def test_the_system_prompt_still_asks_for_a_bare_continuation():
    """The other half of the same string, and the reason it exists at all."""
    assert "Continue directly" in gs.COMPLETION_STYLE_SYSTEM_PROMPT


def test_the_system_prompt_is_what_reaches_the_model(monkeypatch, calls):
    use_template(monkeypatch, "v3_ChatGPT/generate_pronunciatio_v1.txt")
    sent = []

    def fake_create(model=None, messages=None, **kwargs):
        sent.extend(messages)

        class Msg:
            content = "ok"

        class Choice:
            message = Msg()

        class Completion:
            choices = [Choice()]

        return Completion()

    class FakeClient:
        class chat:
            class completions:
                create = staticmethod(fake_create)

    monkeypatch.setattr(gs, "get_client", lambda: FakeClient)
    gs.ChatGPT_request("an emoji for this")

    assert sent[0]["role"] == "system"
    assert sent[0]["content"] == gs.COMPLETION_STYLE_SYSTEM_PROMPT
