"""
Posing a question to a saved agent without disturbing it.

`save()` is never run here, this module would loads a checkpoint, reads
from it, and exits. `_forbid_saving` is used to enforce this.

A question is answered through the agents own retrieval.
`retrieve.new_retrieve` scores the memory store exactly as the original
simulation would and returns what the agent can recall. It follows that
a probe can fail in two different ways, either retrieval not retrieving
the memory or because the model did not use what it was given.
"""

import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reverie", "backend_server")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from persona.cognitive_modules import retrieve as retrieve_module
from persona.persona import Persona
from persona.prompt_template.gpt_structure import ChatGPT_request, forget_answer, reply_is_english


def generate(prompt, attempts=3):
    """
    A guard against non-English replies.

    A rejected reply is dropped from the answer cache and retried.
    """
    for attempt in range(attempts):
        if attempt:
            forget_answer(prompt)
        reply = ChatGPT_request(prompt, attempt=attempt)
        if reply_is_english(reply):
            return reply
        print("  [language] reply contained non-Latin script; asking again")
    print("  [language] still not English after retries; keeping the last reply and flagging it")
    return reply


ANSWER_PROMPT = """You are !<NAME>!. Answer the question below in the first person, in one or two
sentences, as you would if someone asked you in conversation.

What comes to mind:
!<MEMORIES>!

Question: !<QUESTION>!
Answer:"""

# The interview is a different instrument and needs a different frame.
# Asking "who are you?" through the probe promptt above produced
# answers assembled entirely out of the last few hours of retrieved
# events. Now supply with what the identity stable set is plus the
# retrieved memory.
INTERVIEW_PROMPT = """!<ISS>!

Answer the following in the first person, as !<NAME>!, in two or three sentences.

Recent things on your mind:
!<MEMORIES>!

Question: !<QUESTION>!
Answer:"""


def _forbid_saving(persona):
    """Make sure writing is impossible"""

    def refuse(*args, **kwargs):
        raise RuntimeError("the evaluation battery attempted to save; it must never write to the run it measures")

    persona.a_mem.save = refuse
    persona.s_mem.save = refuse
    persona.scratch.save = refuse
    return persona


def load(sim_folder, name):
    """Load one agent from a saved simulation in read-only."""
    return _forbid_saving(Persona(name, f"{sim_folder}/personas/{name}"))


def checkpoint_time(sim_folder):
    with open(f"{sim_folder}/reverie/meta.json") as f:
        meta = json.load(f)
    import datetime

    return datetime.datetime.strptime(meta["curr_time"], "%B %d, %Y, %H:%M:%S")


def condition(sim_folder):
    """The flag set that produced this checkpoint."""
    with open(f"{sim_folder}/reverie/meta.json") as f:
        return json.load(f).get("memory_config", {})


def _render(node):
    """One recalled memory as the agent would have it."""
    return f"- {node.created.strftime('%Y-%m-%d %H:%M')}: {node.description}"


def _unchanged_by(persona, work):
    """Run `work` and put the agent's memory back exactly at it was."""
    touched = list(persona.a_mem.id_to_node.values())
    before = [(n, n.last_accessed, getattr(n, "rehearsal_count", None)) for n in touched]
    try:
        return work()
    finally:
        for node, accessed, rehearsals in before:
            node.last_accessed = accessed
            if rehearsals is None:
                if hasattr(node, "rehearsal_count"):
                    del node.rehearsal_count
            else:
                node.rehearsal_count = rehearsals


def ask(persona, question, n_memories=20, interview=False):
    """
    Put one question to an agent and return its answer alongside what
    it recalled. `interview=True` switches to the persona frame
    described above.
    """
    retrieved = _unchanged_by(persona, lambda: retrieve_module.new_retrieve(persona, [question], n_count=n_memories))
    nodes = retrieved.get(question, [])
    recalled = [_render(n) for n in nodes]
    memories = "\n".join(recalled) if recalled else "- (nothing comes to mind)"

    if interview:
        prompt = (
            INTERVIEW_PROMPT
            .replace("!<ISS>!", persona.scratch.get_str_iss())
            .replace("!<NAME>!", persona.name)
            .replace("!<MEMORIES>!", memories)
            .replace("!<QUESTION>!", question)
        )
    else:
        prompt = (
            ANSWER_PROMPT
            .replace("!<NAME>!", persona.name)
            .replace("!<MEMORIES>!", memories)
            .replace("!<QUESTION>!", question)
        )

    answer = generate(prompt).strip()
    return {
        "answer": answer,
        "english": reply_is_english(answer),
        "recalled": recalled,
        "recalled_count": len(recalled),
    }
