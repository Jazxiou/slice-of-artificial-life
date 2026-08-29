"""
Original Author: Joon Sung Park (joonspk@stanford.edu)
Fork Maintainer: Yasmina Abdallah

File: gpt_structure.py
Description:    Wrapper functions for calling the language model and
                the embedding model.

Modifications:
    - Migrated from the openai 0.x SDK to 1.x
    - Every request now goes to the "chat completions" endpoint.
      Upstream sent its prompts to `/v1/completions` with
      `text-davinci-002/003z` which are both retired.
    - The endpoint, model and embedding model are read from `utils.py`
    - Embeddings are computed locally with sentence-transformers
      instead of `text-davinci-002/003z.
    - Failures are now logged with their exception, the return values
      are unchanged so behaviour stays the same but at least the cause
      would now be known.
"""

import json
import random
import re
import time
import traceback

import llm_trace
from openai import OpenAI
from utils import *

# Configuration
# Read from utils.py when present, so an older utils.py still works.


def _cfg(name, default):
    return globals().get(name, default)


LLM_BASE_URL = _cfg("llm_base_url", "http://localhost:11434/v1")
LLM_MODEL = _cfg("llm_model", "qwen2.5:14b")
EMBEDDING_MODEL = _cfg("embedding_model", "all-MiniLM-L6-v2")
API_KEY = _cfg("openai_api_key", "not-needed")

# How many seconds to wait for one reply.
LLM_TIMEOUT_SECONDS = _cfg("llm_timeout_seconds", 120)
LLM_MAX_RETRIES = _cfg("llm_max_retries", 1)

# Upstream's davinci prompts expect a bare continuation, not a chatty
# reply. Without this a model usually prefaces answers with "Sure! Here
# is..." etc. and the output parsers would fail.
COMPLETION_STYLE_SYSTEM_PROMPT = _cfg(
    "completion_style_system_prompt",
    "You are completing a text. Continue directly with the requested content only. "
    "Do not add greetings, explanations, preamble, commentary or markdown formatting. "
    # Qwen2.5 is bilingual and occasionally answers in Chinese.
    "Write only in English. Never use Chinese, Japanese or Korean characters, not even for a single word.",
)
USE_COMPLETION_STYLE_SYSTEM_PROMPT = _cfg("use_completion_style_system_prompt", True)

CHAT_VARIED_TEMPLATES = {
    "v3_ChatGPT/iterative_convo_v1.txt",  # the dialogue itself
    "v3_ChatGPT/agent_chat_v1.txt",  # a whole conversation
    "v3_ChatGPT/memo_on_convo_v1.txt",  # what an agent privately thinks about a chat
}
CHAT_DETERMINISTIC_TEMPERATURE = _cfg("chat_deterministic_temperature", 0.0)
CHAT_VARIED_TEMPERATURE = _cfg("chat_varied_temperature", 0.8)
# Retries need to be allowed to differ (a temp of zero wouldnt allow
# that). First attempt is deterministic and any attempt after is
# sampled.
RETRY_TEMPERATURE = _cfg("retry_temperature", 0.7)
# A ceiling on the reply, which the chat path had none of. Upstream's `gpt_param` dicts declare one
# per prompt (15 tokens for an emoji, 30 for an event triple) and the chat path discards them along
# with everything else in those dicts, so a chat call could generate until the model chose to stop.
# On a three-day run one emoji request returned 24,781 characters, roughly six thousand tokens from a
# prompt whose median reply is seventeen characters; it took 120 seconds, and a longer one in an
# earlier run took 600. The longest *legitimate* chat reply in that same run was 846 characters, so
# this cap sits well above every real answer and only truncates a model that has stopped answering.
CHAT_MAX_TOKENS = _cfg("chat_max_tokens", 512)


def chat_sampling(attempt=0):
    """
    Sampling parameters for the current prompt, chosen by which
    template it came from and by whether this is a first attempt or a
    retry.
    """
    if llm_trace.current_template() in CHAT_VARIED_TEMPLATES:
        return {"temperature": CHAT_VARIED_TEMPERATURE, "top_p": 1, "max_tokens": CHAT_MAX_TOKENS}
    temperature = CHAT_DETERMINISTIC_TEMPERATURE if attempt == 0 else RETRY_TEMPERATURE
    return {"temperature": temperature, "top_p": 1, "max_tokens": CHAT_MAX_TOKENS}


def retry_parameters(gpt_parameter):
    """
    Only prompts at temperature zero are touched.
    """
    if gpt_parameter.get("temperature"):
        return gpt_parameter
    escalated = dict(gpt_parameter)
    escalated["temperature"] = RETRY_TEMPERATURE
    return escalated


_client = None
_embedding_model = None


def get_client():
    """
    The OpenAI-compatible client, created once. Points wherever
    utils.llm_base_url says.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=LLM_BASE_URL, api_key=API_KEY, timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES
        )
    return _client


# === Answer Cache ===
# Caching is restricted to calls made at temperature zero.
ANSWER_CACHE = _cfg("answer_cache", True)
ANSWER_CACHE_MAX = _cfg("answer_cache_max", 50000)
_answer_cache = {}


def answer_cache_size():
    return len(_answer_cache)


def forget_answer(prompt, model=None):
    """
    Drop a cached answer because the caller rejected it.

    Without this, a first attempt that produced an unparseable reply
    would keep being served from the cache every time that question
    came around again.
    """
    _answer_cache.pop((model or LLM_MODEL, prompt), None)


def _chat(prompt, model=None, **kwargs):
    """
    Every LLM call in the system goes through here for a
    chat-completion round trip.
    """
    # Replaying: report back what the model said last time, without
    # contacting anything.
    if llm_trace.is_replaying():
        return llm_trace.replayer.llm(prompt)

    cache_key = None
    if ANSWER_CACHE and kwargs.get("temperature") == 0:
        cache_key = (model or LLM_MODEL, prompt)
        if cache_key in _answer_cache:
            cached = _answer_cache[cache_key]
            if llm_trace.is_recording():
                llm_trace.recorder.llm(prompt, cached, 0.0, model or LLM_MODEL, kwargs, cached=True)
            return cached

    messages = []
    if USE_COMPLETION_STYLE_SYSTEM_PROMPT:
        messages.append({"role": "system", "content": COMPLETION_STYLE_SYSTEM_PROMPT})
    messages.append({"role": "user", "content": prompt})

    started = time.time()
    try:
        completion = get_client().chat.completions.create(model=model or LLM_MODEL, messages=messages, **kwargs)
    except Exception as exc:
        # Record the failure too
        if llm_trace.is_recording():
            llm_trace.recorder.failure(prompt, exc, time.time() - started, model or LLM_MODEL, kwargs)
        raise

    content = completion.choices[0].message.content
    content = content if content is not None else ""

    # Only successful answers are cached, and only up to a cap.
    if cache_key is not None and len(_answer_cache) < ANSWER_CACHE_MAX:
        _answer_cache[cache_key] = content

    if llm_trace.is_recording():
        llm_trace.recorder.llm(prompt, content, time.time() - started, model or LLM_MODEL, kwargs)
    return content


def preflight(fatal=True):
    """
    Ask the model one trivial question before the simulation starts.

    Without this, an unreachable or misconfigured model server would
    have every call return an error string, the simulation substitutes
    fail-safe defaults, and it can keep running meaninglessly. Quick
    check to avoid that.

    Skipped automatically when replaying a trace.
    """
    if llm_trace.is_replaying():
        print("[preflight] replaying a recorded trace, no model server needed")
        return True

    print(f"[preflight] checking the model at {LLM_BASE_URL} (model: {LLM_MODEL}) ...")
    # Label this so it is distinguishable from the simulation in the
    # trace.
    llm_trace.note_template("preflight")
    try:
        reply = _chat("Reply with the single word: ok", max_tokens=10)
        print(f"[preflight] model responded: {reply.strip()[:60]!r}")
        return True
    except Exception as exc:
        message = (
            f"\n[preflight] COULD NOT REACH THE LANGUAGE MODEL\n"
            f"  address : {LLM_BASE_URL}\n"
            f"  model   : {LLM_MODEL}\n"
            f"  error   : {type(exc).__name__}: {exc}\n\n"
            f"  Check, in this order (ollama specific):\n"
            f"    1. Is the server running?            ollama serve      (in its own terminal)\n"
            f"    2. Is the port right?                the address above must match your server.\n"
            f"       If you set OLLAMA_HOST to a custom port, llm_base_url in utils.py must match it.\n"
            f"    3. Does the server answer?           curl {LLM_BASE_URL}/models\n"
            f"    4. Is the model pulled?              ollama list   (the name must match exactly)\n"
        )
        print(message)
        if fatal:
            raise SystemExit("Stopping before the simulation starts.")
        return False


def temp_sleep(seconds=0.1):
    time.sleep(seconds)


def ChatGPT_single_request(prompt, label=None):
    """
    A one-off call with no template file behind it. Every use is in `revise_identity`, which writes a
    character's identity from prose assembled in code rather than from a prompt file.

    Two things were wrong with that and both were invisible. The call sent *no* sampling parameters, so
    the four prompts that decide who each agent is ran at whatever temperature the server happened to
    default to. And with no template file there was no template name, so `llm_trace` kept the last one
    it had seen and filed all 29 of these calls under `wake_up_hour`, which is simply the prompt that
    runs immediately before them.

    They are generative prose, not extraction, so they sit on the varied side of the split. 0.8 is also
    what Ollama defaults to, which means stating it here records the behaviour rather than changing it.
    """
    temp_sleep()
    if label:
        llm_trace.note_template(label)
    try:
        return _chat(prompt, temperature=CHAT_VARIED_TEMPERATURE, top_p=1, max_tokens=CHAT_MAX_TOKENS)
    except Exception as exc:
        print(f"[LLM ERROR] ChatGPT_single_request: {type(exc).__name__}: {exc}")
        return "ChatGPT ERROR"


# ============================================================================
# #####################[SECTION 1: CHATGPT-3 STRUCTURE] ######################
# ============================================================================


def GPT4_request(prompt):
    """
    OLD:
    Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
    server and returns the response.
    ARGS:
      prompt: a str prompt
      gpt_parameter: a python dictionary with the keys indicating the names of
                     the parameter and the values indicating the parameter
                     values.
    RETURNS:
      a str of GPT-3's response.

    NEW:
    Kept for signature compatibility. Upstream used gpt-4 here, but now
    uses the configured model. Local deployment only serves one model.
    """
    temp_sleep()
    try:
        return _chat(prompt)
    except Exception as exc:
        print(f"[LLM ERROR] GPT4_request: {type(exc).__name__}: {exc}")
        return "ChatGPT ERROR"


def ChatGPT_request(prompt, attempt=0):
    """
    OLD:
    Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
    server and returns the response.
    ARGS:
      prompt: a str prompt
      gpt_parameter: a python dictionary with the keys indicating the names of
                     the parameter and the values indicating the parameter
                     values.
    RETURNS:
      a str of GPT-3's response.
    """
    try:
        return _chat(prompt, **chat_sampling(attempt))
    except Exception as exc:
        print(f"[LLM ERROR] ChatGPT_request: {type(exc).__name__}: {exc}")
        return "ChatGPT ERROR"


def GPT4_safe_generate_response(
    prompt,
    example_output,
    special_instruction,
    repeat=3,
    fail_safe_response="error",
    func_validate=None,
    func_clean_up=None,
    verbose=False,
):
    prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
    prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
    prompt += "Example output json:\n"
    prompt += '{"output": "' + str(example_output) + '"}'

    if verbose:
        print("CHAT GPT PROMPT")
        print(prompt)

    for i in range(repeat):
        try:
            curr_gpt_response = GPT4_request(prompt).strip()
            end_index = curr_gpt_response.rfind("}") + 1
            curr_gpt_response = curr_gpt_response[:end_index]
            curr_gpt_response = json.loads(curr_gpt_response)["output"]

            if func_validate(curr_gpt_response, prompt=prompt):
                return func_clean_up(curr_gpt_response, prompt=prompt)

            if verbose:
                print("---- repeat count: \n", i, curr_gpt_response)
                print(curr_gpt_response)
                print("~~~~")

        except Exception as exc:
            print(f"[LLM PARSE] GPT4_safe_generate_response attempt {i}: {type(exc).__name__}: {exc}")

    return False


def extract_json_output(reply):
    """
    Pull the answer out of a reply that was asked for as `{"output":
    ...}`.

    Upstream tripped everything after the last `}` and then read the
    "output" key. When the model answers without a wrapper there is no
    `}` at all, `rfind` returns -1, and the reply is truncated to the
    empty string before parsing.

    Now, try the wrapper first, else fall back to reading the reply as
    JSON anyway.
    """
    end = reply.rfind("}") + 1
    if end:
        try:
            parsed = json.loads(reply[:end])
            if isinstance(parsed, dict) and "output" in parsed:
                return parsed["output"]
        except (json.JSONDecodeError, ValueError):
            pass
    # Attempt without a wrapper.
    start = min((i for i in (reply.find("["), reply.find("{")) if i != -1), default=-1)
    candidate = reply[start:] if start != -1 else reply
    parsed = json.loads(candidate)
    if isinstance(parsed, dict) and "output" in parsed:
        return parsed["output"]
    return parsed


def ChatGPT_safe_generate_response(
    prompt,
    example_output,
    special_instruction,
    repeat=3,
    fail_safe_response="error",
    func_validate=None,
    func_clean_up=None,
    verbose=False,
):
    # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
    prompt = '"""\n' + prompt + '\n"""\n'
    prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
    prompt += "Example output json:\n"
    prompt += '{"output": "' + str(example_output) + '"}'

    if verbose:
        print("CHAT GPT PROMPT")
        print(prompt)

    for i in range(repeat):
        if i:
            forget_answer(prompt)  # the previous answer was rejected
        try:
            curr_gpt_response = ChatGPT_request(prompt, attempt=i).strip()
            if not reply_is_english(curr_gpt_response):
                print("[language] reply contained non-Latin script; asking again")
                continue
            curr_gpt_response = extract_json_output(curr_gpt_response)

            # print ("---ashdfaf")
            # print (curr_gpt_response)
            # print ("000asdfhia")

            if func_validate(curr_gpt_response, prompt=prompt):
                return func_clean_up(curr_gpt_response, prompt=prompt)

            if verbose:
                print("---- repeat count: \n", i, curr_gpt_response)
                print(curr_gpt_response)
                print("~~~~")

        except Exception as exc:
            print(f"[LLM PARSE] ChatGPT_safe_generate_response attempt {i}: {type(exc).__name__}: {exc}")

    return False


def ChatGPT_safe_generate_response_OLD(
    prompt, repeat=3, fail_safe_response="error", func_validate=None, func_clean_up=None, verbose=False
):
    if verbose:
        print("CHAT GPT PROMPT")
        print(prompt)

    for i in range(repeat):
        if i:
            forget_answer(prompt)  # the previous answer was rejected
        try:
            curr_gpt_response = ChatGPT_request(prompt, attempt=i).strip()
            if not reply_is_english(curr_gpt_response):
                print("[language] reply contained non-Latin script; asking again")
                continue
            if func_validate(curr_gpt_response, prompt=prompt):
                return func_clean_up(curr_gpt_response, prompt=prompt)
            if verbose:
                print(f"---- repeat count: {i}")
                print(curr_gpt_response)
                print("~~~~")

        except Exception as exc:
            print(f"[LLM PARSE] ChatGPT_safe_generate_response_OLD attempt {i}: {type(exc).__name__}: {exc}")
    print("FAIL SAFE TRIGGERED")
    return fail_safe_response


# ============================================================================
# ###################[SECTION 2: ORIGINAL GPT-3 STRUCTURE] ###################
# ============================================================================


def GPT_request(prompt, gpt_parameter):
    """
    OLD:
    Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
    server and returns the response.
    ARGS:
      prompt: a str prompt
      gpt_parameter: a python dictionary with the keys indicating the names of
                     the parameter and the values indicating the parameter
                     values.
    RETURNS:
      a str of GPT-3's response.

    NEW:
    Upstream sent this to `/v1/completions` with
    `gpt_parameter["engine"]`. davinci models are now retired, and the
    local runtimes use chat completions, so the request is now a chat
    call. `gpt_parameter is honoured as far as the chat endpoint
    allows, and "engine" is ignored in favour of the configured model.
    This change covers all upstream davinci call sites.
    """
    temp_sleep()
    try:
        kwargs = {}
        for src, dst in (
            ("temperature", "temperature"),
            ("max_tokens", "max_tokens"),
            ("top_p", "top_p"),
            ("frequency_penalty", "frequency_penalty"),
            ("presence_penalty", "presence_penalty"),
            ("stop", "stop"),
        ):
            if gpt_parameter.get(src) is not None:
                kwargs[dst] = gpt_parameter[src]
        return _chat(prompt, **kwargs)
    except Exception as exc:
        print(f"[LLM ERROR] GPT_request: {type(exc).__name__}: {exc}")
        return "TOKEN LIMIT EXCEEDED"


def generate_prompt(curr_input, prompt_lib_file):
    """
    Takes in the current input (e.g. comment that you want to classifiy) and
    the path to a prompt file. The prompt file contains the raw str prompt that
    will be used, which contains the following substr: !<INPUT>! -- this
    function replaces this substr with the actual curr_input to produce the
    final promopt that will be sent to the GPT3 server.
    ARGS:
      curr_input: the input we want to feed in (IF THERE ARE MORE THAN ONE
                  INPUT, THIS CAN BE A LIST.)
      prompt_lib_file: the path to the promopt file.
    RETURNS:
      a str prompt that will be sent to OpenAI's GPT server.
    """
    # Remember which template this prompt came from to label a recorded
    # call can be labelled with its exact origin.
    llm_trace.note_template(prompt_lib_file)

    if type(curr_input) == type("string"):
        curr_input = [curr_input]
    curr_input = [str(i) for i in curr_input]

    f = open(prompt_lib_file, "r")
    prompt = f.read()
    f.close()
    for count, i in enumerate(curr_input):
        prompt = prompt.replace(f"!<INPUT {count}>!", i)
    if "<commentblockmarker>###</commentblockmarker>" in prompt:
        prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
    return prompt.strip()


# Hiragana, katakana, CJK ideographs and hangul.
_NON_LATIN_SCRIPT = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff66-\uff9f]")


def reply_is_english(reply):
    """Whether a reply is usable as English text."""
    return not _NON_LATIN_SCRIPT.search(reply)


def safe_generate_response(
    prompt, gpt_parameter, repeat=5, fail_safe_response="error", func_validate=None, func_clean_up=None, verbose=False
):
    if verbose:
        print(prompt)

    for i in range(repeat):
        if i:
            forget_answer(prompt)  # the previous answer was rejected
        # Retry by changing parameters to avoid identical replies.
        curr_gpt_response = GPT_request(prompt, gpt_parameter if not i else retry_parameters(gpt_parameter))
        if not reply_is_english(curr_gpt_response):
            print("[language] reply contained non-Latin script; asking again")
            continue
        if func_validate(curr_gpt_response, prompt=prompt):
            return func_clean_up(curr_gpt_response, prompt=prompt)
        if verbose:
            print("---- repeat count: ", i, curr_gpt_response)
            print(curr_gpt_response)
            print("~~~~")
    return fail_safe_response


def get_embedding(text, model=None):
    """
    Local embeddings via sentence-transformers, replacing the OpenAI's
    text-embedding-ada-002. The model is loaded once on first use.
    Callers are unchanged, this still returns a plain list of floats,
    and `retrieve.py`'s cosine similarity works with any consistent
    vector length.
    """
    global _embedding_model
    text = text.replace("\n", " ")
    if not text:
        text = "this is blank"

    if llm_trace.is_replaying():
        return llm_trace.replayer.embedding(text)

    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer(model or EMBEDDING_MODEL)
    started = time.time()
    vector = [float(x) for x in _embedding_model.encode(text, show_progress_bar=False)]
    if not vector:
        raise RuntimeError(
            f"the embedding model returned nothing for {text[:80]!r} (model: {model or EMBEDDING_MODEL})"
        )
    if llm_trace.is_recording():
        llm_trace.recorder.embedding(text, vector, time.time() - started)
    return vector
