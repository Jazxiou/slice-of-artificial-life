"""
How importance is compared across kinds of memory.

WHAT THE MEASURED RUNS SHOWED
-----------------------------
Retrieval ranks memories by recency, relevance and importance, weighted 0.5, 3 and 2, with each term
normalised across the candidates before they are added. Importance is the 1-to-10 poignancy rating the
model gives a memory when it is written, and across the 9,183 memories held at the end of the control
run that rating is not one scale but two:

    event   (what the character saw or did)    n = 7,919    median 1 / 10
    thought (a generalisation it wrote)        n = 1,180    median 7 / 10
    chat                                       n =    84    median 4 / 10

Normalising that across the whole candidate set maps almost every observation to nearly zero and almost
every reflection to nearly one, so the importance term stops being a measure of significance and becomes
a switch that prefers abstractions. Counted by node type, reflections are 13% of the store and 47% of
everything retrieval put in front of the agents during the memory battery. With the retention work on it
is worse, 58%, because coupling half-life to importance (C1) makes reflections survive about four times
longer on this scale. That is the account of why recall did not move: the battery asks what a character
was doing at a particular hour, which is an episode, and a character handed ten generalisations about its
own working habits has nothing specific to answer with and everything it needs to invent something.

WHAT THIS MODULE DOES
---------------------
`importance_within_type` normalises importance separately within each kind of memory, so that a striking
observation competes against other observations rather than against reflections. It is deliberately the
smallest change that could fix the problem: the same min-max normalisation the baseline already performs,
applied within groups instead of across everything. It does not re-rate anything, does not reweight the
three terms, and does not exclude reflections. A reflection that is important among reflections still
scores 1.0. The flag defaults off, so the control condition is untouched.
"""

import collections

try:
    from utils import *
except ImportError:
    pass


def _cfg(name, default):
    return globals().get(name, default)


IMPORTANCE_WITHIN_TYPE = _cfg("importance_within_type", False)


def enabled():
    return IMPORTANCE_WITHIN_TYPE


def _normalised(scores):
    """
    Min-max onto 0 to 1, following the baseline's own convention exactly, including its treatment of a
    group whose values are all equal: those become 0.5 rather than 0, so that a memory is not penalised
    for having no variation to be measured against.
    """
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    if high == low:
        return {key: 0.5 for key in scores}
    return {key: (value - low) / (high - low) for key, value in scores.items()}


def importance_scores(persona, nodes):
    """
    Importance, normalised within each kind of memory rather than across all of them.
    Returns the same shape the baseline's `extract_importance` returns after normalisation, so the caller
    substitutes one for the other and nothing downstream changes.
    """
    by_type = collections.defaultdict(dict)
    for node in nodes:
        by_type[node.type][node.node_id] = node.poignancy

    out = {}
    for scores in by_type.values():
        out.update(_normalised(scores))
    return out


def config():
    return {"importance_within_type": IMPORTANCE_WITHIN_TYPE}


def describe():
    if not enabled():
        return "retrieval: baseline (importance normalised across all memories at once)"
    return "retrieval: importance normalised within each kind of memory"
