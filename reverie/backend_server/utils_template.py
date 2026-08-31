"""
Configuration template.

    cp reverie/backend_server/utils_template.py reverie/backend_server/utils.py

`utils.py is gitignored (it can hold a real API key), so this template
is what makes the project reproducible. Upstream shipped no template at
all and documented the file in prose only.

Defaults below target a LOCAL model served over an OpenAI-compatible
endpoint, so no key is needed.

The flags ship ON: a copied, unedited utils.py runs the complete
system, world layer included.

The CONTROL (repaired baseline) sets every flag in the world-layer,
research-contribution and town-guardrail sections to False.

The TREATMENT sets only the six contribution flags to True
(recency_time_based, recency_access_persisted,
importance_coupled_decay, rehearsal_strengthening,
importance_within_type, persona_reanchor) with everything else False.
"""

# === Language Model ===
# Any OpenAI-compatible server. Ollama's is 11434
llm_base_url = "http://localhost:11434/v1"

# Must match a model your server has. With Ollama check with `ollama
# list`
llm_model = "qwen2.5:14b"

# Client requires some value here, keep like this if using a local
# server. Put a real key here only if you point llm_base_url at OpenAI.
openai_api_key = "not-needed"
key_owner = "your-name"

# How long to wait for one reply before giving up on it. A timeout
# raises, is recorded as a failure in the trace, and is retried.
llm_timeout_seconds = 120
# How many times to retry
llm_max_retries = 1

# === Embeddings ===
# Computed locally with this sentence-transformers.
embedding_model = "all-MiniLM-L6-v2"

# === Prompt Compatibility ===
# Chat models add preamble ("Sure! Here is...") which breaks those
# parsers, so a short system message asks for direct output. Set to
# false to observe the un-nudged behaviour.
use_completion_style_system_prompt = True
completion_style_system_prompt = (
    "You are completing a text. Continue directly with the requested content only. "
    "Do not add greetings, explanations, preamble, commentary or markdown formatting. "
    "Write only in English. Never use Chinese, Japanese or Korean characters, "
    "not even for a single word."
)

# === Sampling ===
# Prompts with a right answer (an importance rating, an emoji for an
# action, a location from a list) run deterministically. Dialogue and
# thoughts written about it are sampled, so conversation still differs.
chat_deterministic_temperature = 0.0
chat_varied_temperature = 0.8
# A retry has to be allowed to differ (or it would be identical,
# defeating the purpose).
retry_temperature = 0.7
# A ceiling on the length of a chat reply. Should only truncate a model
# that has stopped answering the question.
chat_max_tokens = 512

# === Answer Cache ===
# Remembers answers to temperature-zero questions for that run.
answer_cache = True
answer_cache_max = 50000

# === Paths ===
# Relative to reverie/backend_server/ so the simulation must be started
# from that directory.
maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"

collision_block_id = "32125"

# === Misc ===
debug = True

# === Long Runs ===
# Steps between automatic checkpoints. One simulated day is 8640 steps,
# so this saves at every midnight. Set to 0 to disable.
autosave_every = 8640

# === Sims-style Needs (WORLD LAYER) ===
# Lives in `reverie/backend_server/world_ext/needs.py`.

# Six needs decaying on the simulated clock, refilled by what the
# character is actually doing, with "Social" refilled ONLY by real
# conversation. A need in the red forces a mood (tired / bored /
# irritable / lonely) and adds one sentence to the identity block,
# so the deficit reaches planning and dialogue.
world_needs = True  # Keep False unless running the live town
needs_red_threshold = 25.0

# Mood (world_ext/emotion.py). A need in the red overrides the model's
# word until the bar recovers
world_emotion = True  # keep False unless running the live town

# Relationships (world_ext/relationships.py). Per-side friendship and
# romance.
world_relationships = True  # keep False unless running the live town

# Viewer Feeds (world_ext/snapshot.py). Display Ville Viewer's card.
world_snapshots = True
snapshot_every = 30

# === Town Guardrails (TOWN RUNS ONLY) ===
# Lives in `reverie/backend_server/memory_ext/longevity.py`.

# An object seen idle is remembered at most once per hour, instead of
# every time it drifts out of the perception window. Half of a run's
# score was idle observations, and scored retrieval filters them out
# anyway. People standing idle are never deduplicated, only objects,
# because reactions can target a person's event.
idle_memory_dedup = True  # Keep False if not running a live town.
idle_dedup_ttl_hours = 1.0

# Write embedding vectors rounded to six decimals. The model computes
# them in float32, which has about seven significant digits; the JSON
# writer stores full float64 verbosity, which is precision the numbers
# never had. Cuts the largest file in every saved simulation
# several-fold.
compact_embeddings = True  # Keep False if not running a live town.

# Real forgetting for towns that run for weeks. Once a store outgrows
# its cap it is trimmed to 90% of it overnight, weakest memories first,
# where "weakest" is the retention module's own judgement.
memory_eviction = True  # Keep False if not running a live town.
eviction_max_nodes = 10000

# === Decay and Retention (RESEARCH CONTRIBUTION)===
# Lives in `reverie/backend_server/memory_ext/retention.py`. When flags
# are False, the simulation will behave as the baseline.

# Option 1. Score recency by elapsed simulated time since a memory was
# recalled. Everything else here depends on this being on.
recency_time_based = True

# Option 1b. Read the saved access history back when a checkpoint is
# loaded. If off then every checkpoint resets each memory's access time
# to its creation time (baseline mechanic).
recency_access_persisted = True

# Option 1c. Let importance lengthen a memory's half-life.
importance_coupled_decay = True

# Option 1d. Each recall lengthens the half-life a little, with
# diminishing returns and a cap. Needs `recency_access_persisted`.
rehearsal_strengthening = True

# Parameters
recency_halflife_hours = 24.0
decay_shape = "exponential"  # "exponential" or "power_law"
power_law_exponent = 1.0  # used only when decay_shape == "power_law"
importance_halflife_multiplier = 4.0  # half-life at importance 10 relative to
# importance 1
rehearsal_halflife_multiplier = 3.0  # maximum of the rehearsal bonus
rehearsal_saturation = 8.0  # amount of recalls needed for half of that
# bonus

# === How Importance is Compared (RESEARCH CONTRIBUTION) ===
# Lives in `reverie/backend_server/memory_ext/retrieval.py`. On by
# default.

# Importance is a 1-to-10 rating the model gives a memory when it is
# written. Baseline's median event scored 1 and the median reflection
# scored 7. This normalises importance within each kind of memory, so a
# striking observation competes with other observations. Reflections
# stay retrievable, they simply stop crowding out episodes.
importance_within_type = True

# === Persona Re-anchoring (RESEARCH CONTRIBUTION) ===
# Lives in `reverie/backend_server/memory_ext/persona.py`.

# Re-anchoring measures how far each day's rewrite has moved from the
# seed and corrects it only when it has moved too far, so that
# believable change is left alone.
persona_reanchor = True

# Measure the daily drift even in the control condition.
persona_drift_measured = True

# Cosine distance from the anchor at which a correction fires. 0 is the
# anchor itself, 1 is unrelated.
reanchor_drift_threshold = 0.35

# Correct a status that stopped being a description of a person and
# has become an account of one day. The test is textual (a date,
# a weekday, or a word like "today")
reanchor_genre_test = True

# Put the seed's own words in front of the rewriter rather than only
# its traits.
reanchor_verbatim_seed = True
