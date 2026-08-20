"""
Configuration template.

    cp reverie/backend_server/utils_template.py reverie/backend_server/utils.py

`utils.py is gitignored (it can hold a real API key), so this template
is what makes the project reproducible. Upstream shipped no template at
all and documented the file in prose only.

Defaults below target a LOCAL model served over an OpenAI-compatible
endpoint, so no key is needed.
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
    "Do not add greetings, explanations, preamble, commentary or markdown formatting."
)

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
